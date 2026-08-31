# -*- coding: utf-8 -*-
"""공통 유틸 — HTTP 호출, 설정 로드, 좌표·행정코드, 기상청 격자 변환.

표준 라이브러리만 쓴다. 연구원 PC 에 pip 설치를 요구하지 않기 위해서다.
세종시 물환경 상황판(sejong_water)의 같은 파일에서 갈라져 나왔고,
교통 쪽에서 필요한 것(좌표 정규화, XML 파싱, 포털 껍데기 해체)이 더 붙었다.
"""
from __future__ import annotations

import json
import math
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
KST = timezone(timedelta(hours=9))

USER_AGENT = "sejong-traffic-dashboard/1.0 (+python-urllib)"
DEFAULT_TIMEOUT = 20

# 세종특별자치시 — 단일 자치시라 시군구가 없다.
#   법정동코드 앞 5자리 36110. 도로교통공단 siDo/guGun 은 별도 코드체계라 config 에 둔다.
SEJONG_BJD = "36110"
SEJONG_BBOX = (127.05, 36.34, 127.45, 36.75)      # minX, minY, maxX, maxY (WGS84)
SEJONG_CENTER = (36.48, 127.289)


def safe_url(url) -> str:
    """오류 메시지·로그에 쓸 주소. 인증키를 가린다.

    포털은 serviceKey, ITS 는 apiKey, TAAS 는 authKey 로 키를 넘긴다.
    이 문자열이 공개 저장소의 실행 로그에 남으면 키가 새므로 전부 가린다.
    """
    text = str(url or "")
    if "?" not in text:
        return text
    base, _, query = text.partition("?")
    parts = []
    for chunk in query.split("&"):
        name = chunk.split("=", 1)[0]
        if name.lower() in ("servicekey", "key", "authkey", "apikey", "api_key"):
            parts.append(name + "=<KEY>")
        else:
            parts.append(chunk)
    return base + "?" + "&".join(parts)


class CollectError(Exception):
    """수집 실패. 메시지는 상황판에 그대로 노출되므로 사람이 읽을 수 있게 쓴다."""


# --------------------------------------------------------------------------- 시간

def now_kst() -> datetime:
    return datetime.now(KST)


def stamp(dt: datetime | None = None) -> str:
    return (dt or now_kst()).strftime("%Y-%m-%d %H:%M")


def parse_stamp(text):
    """'2026-08-31 19:40' / '20260831194000' / ISO 문자열을 datetime 으로."""
    raw = str(text or "").strip()
    if not raw:
        return None
    for length, fmt_ in ((19, "%Y-%m-%d %H:%M:%S"), (19, "%Y-%m-%dT%H:%M:%S"),
                         (16, "%Y-%m-%d %H:%M"), (16, "%Y-%m-%dT%H:%M"),
                         (10, "%Y-%m-%d")):
        try:
            return datetime.strptime(raw[:length], fmt_).replace(tzinfo=KST)
        except ValueError:
            continue
    digits = "".join(ch for ch in raw if ch.isdigit())
    for length, fmt_ in ((14, "%Y%m%d%H%M%S"), (12, "%Y%m%d%H%M"),
                         (10, "%Y%m%d%H"), (8, "%Y%m%d"), (4, "%Y")):
        if len(digits) >= length:
            try:
                return datetime.strptime(digits[:length], fmt_).replace(tzinfo=KST)
            except ValueError:
                continue
    return None


# --------------------------------------------------------------------------- 설정

# 섹션별 인증키를 넣을 수 있는 환경변수.
#   포털 일반 인증키는 계정당 하나이므로 koroad/facility/kma/tago 는 같은 값이다.
#   ITS 는 국가교통정보센터에서 따로 발급받는 별도 키다.
KEY_ENV = {"koroad": "DATA_GO_KR_KEY", "facility": "DATA_GO_KR_KEY",
           "kma": "DATA_GO_KR_KEY", "tago": "DATA_GO_KR_KEY", "its": "ITS_KEY"}


def load_config(path=None) -> dict:
    """config.json → 없으면 config.public.json(키 없는 공개 설정) 순으로 읽고,
    환경변수에 키가 있으면 그쪽으로 덮어쓴다.

    저장소에 키를 커밋하지 않고도 다른 기계에서 그대로 돌리기 위한 구조다.
    """
    candidates = [path] if path else [
        os.path.join(BASE_DIR, "config.json"),
        os.path.join(BASE_DIR, "config.public.json"),
    ]
    chosen = next((c for c in candidates if c and os.path.exists(c)), None)
    if not chosen:
        example = os.path.join(BASE_DIR, "config.example.json")
        raise CollectError(
            "config.json 이 없습니다. config.example.json 을 복사해 API 키를 채워주세요."
            + chr(10)
            + '  copy "%s" "%s"' % (example, os.path.join(BASE_DIR, "config.json")))
    with open(chosen, "r", encoding="utf-8") as fp:
        cfg = json.load(fp)

    for section, env_name in KEY_ENV.items():
        value = (os.environ.get(env_name) or "").strip()
        if value and isinstance(cfg.get(section), dict):
            cfg[section]["key"] = value
    cfg["_config_path"] = chosen
    return cfg


def save_json(name: str, payload) -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, name)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)
    return path


def load_json(name: str, default=None):
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as fp:
            return json.load(fp)
    except (ValueError, OSError):
        return default


# --------------------------------------------------------------------------- HTTP

_SSL_CTX = ssl.create_default_context()


def http_get(url: str, params: dict | None = None, timeout: int = DEFAULT_TIMEOUT,
             retries: int = 2, insecure: bool = False) -> str:
    """GET 후 본문을 문자열로. 공공 API 는 간헐적으로 죽으므로 짧게 재시도한다."""
    if params:
        # serviceKey 는 이미 URL 인코딩된 값을 받는 경우가 많아 % 를 다시 인코딩하지 않는다.
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params, safe="%")
    ctx = _SSL_CTX
    if insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                raw = resp.read()
            for enc in ("utf-8", "euc-kr", "cp949"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", "replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            last = exc
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    detail = last
    if isinstance(last, urllib.error.HTTPError):
        detail = "HTTP %s %s" % (last.code, last.reason)
    elif isinstance(last, urllib.error.URLError):
        detail = "연결 실패 (%s)" % last.reason
    raise CollectError("요청 실패: %s — %s" % (safe_url(url.split("?")[0]), detail))


def http_json(url: str, params: dict | None = None, **kw):
    text = http_get(url, params, **kw)
    stripped = text.lstrip()
    if not stripped:
        raise CollectError("응답이 비어 있습니다.")
    if stripped[0] not in "{[":
        # 포털은 오류를 XML/HTML 로 돌려준다. 앞부분을 그대로 보여주는 편이 진단에 낫다.
        raise CollectError("JSON 이 아닌 응답: %s" % safe_url(stripped[:300]))
    try:
        return json.loads(stripped)
    except ValueError as exc:
        raise CollectError("JSON 파싱 실패: %s" % exc) from exc


def http_xml_rows(url: str, params: dict | None = None, row_tag: str = "item", **kw):
    """XML 응답에서 레코드 태그를 찾아 dict 목록으로. ITS 는 XML 로 주는 경우가 있다."""
    text = http_get(url, params, **kw)
    try:
        root = ET.fromstring(text.strip())
    except ET.ParseError as exc:
        raise CollectError("XML 파싱 실패: %s — %s" % (exc, safe_url(text[:200])))
    rows = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] != row_tag:
            continue
        row = {child.tag.rsplit("}", 1)[-1]: (child.text or "").strip() for child in node}
        if row:
            rows.append(row)
    return rows


# --------------------------------------------------------------------------- 파싱

def to_float(value, default=None):
    try:
        if value is None:
            return default
        text = str(value).strip().replace(",", "")
        if text in ("", "-", "null", "None"):
            return default
        return float(text)
    except (TypeError, ValueError):
        return default


def to_int(value, default=0):
    got = to_float(value, None)
    return default if got is None else int(round(got))


def pick(row: dict, *names, default=None):
    """응답 스키마가 소스마다 달라 후보 필드명을 순서대로 훑는다.
    대소문자·언더스코어를 무시하고 맞춘다."""
    if not isinstance(row, dict):
        return default
    lowered = {str(k).replace("_", "").lower(): v for k, v in row.items()}
    for name in names:
        key = str(name).replace("_", "").lower()
        if key in lowered and lowered[key] not in ("", None):
            return lowered[key]
    return default


def norm_lat_lon(lat, lon):
    """위경도 정규화. 뒤바뀐 값·다른 좌표계를 걸러낸다.

    포털 자료는 위경도 필드가 서로 뒤바뀌어 오는 경우가 잦고(la_crd/lo_crd),
    일부는 EPSG:5179 미터 좌표가 그대로 들어 있다. 한반도 범위를 벗어나면 버린다.
    """
    a, b = to_float(lat), to_float(lon)
    if a is None or b is None:
        return None, None
    if abs(a) > 1000 or abs(b) > 1000:
        return None, None                      # 미터 좌표(5179 등) — 여기서 다루지 않는다
    if 124 <= a <= 132 and 33 <= b <= 39:
        a, b = b, a                            # 위·경도가 뒤바뀐 채로 왔다
    if not (33 <= a <= 39 and 124 <= b <= 132):
        return None, None
    return round(a, 6), round(b, 6)


def in_sejong(lat, lon) -> bool:
    if lat is None or lon is None:
        return False
    x0, y0, x1, y1 = SEJONG_BBOX
    return x0 <= lon <= x1 and y0 <= lat <= y1


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def portal_rows(payload):
    """공공데이터포털 JSON 에서 item 목록을 꺼낸다. 껍데기가 서비스마다 다르다.

      response.body.items.item / response.body.items / items / data / list
    """
    if payload is None:
        return []
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    node = payload
    for key in ("response", "Response"):
        if isinstance(node, dict) and key in node:
            node = node[key]
    for key in ("body", "Body"):
        if isinstance(node, dict) and key in node:
            node = node[key]
    for key in ("items", "item", "data", "list", "rows"):
        if isinstance(node, dict) and key in node:
            node = node[key]
            if isinstance(node, dict) and "item" in node:
                node = node["item"]
            break
    if isinstance(node, dict):
        node = [node]
    if not isinstance(node, list):
        return []
    return [r for r in node if isinstance(r, dict)]


def portal_total(payload, fallback=0) -> int:
    """totalCount 를 찾아낸다. 페이지 넘김 판단용."""
    node = payload
    for key in ("response", "body"):
        if isinstance(node, dict) and key in node:
            node = node[key]
    if isinstance(node, dict):
        for key in ("totalCount", "totalcount", "total"):
            if key in node:
                return to_int(node[key], fallback)
    if isinstance(payload, dict):
        for key in ("totalCount", "totalcount", "total"):
            if key in payload:
                return to_int(payload[key], fallback)
    return fallback


def portal_error(payload) -> str | None:
    """포털이 HTTP 200 으로 돌려주는 오류(키 미승인·트래픽 초과 등)를 뽑아낸다."""
    if not isinstance(payload, dict):
        return None
    node = payload.get("response") or payload
    header = (node.get("header") if isinstance(node, dict) else None) or {}
    code = str(header.get("resultCode") or node.get("resultCode") or "").strip()
    msg = str(header.get("resultMsg") or node.get("resultMsg") or "").strip()
    ok = ("00", "0", "000", "normal_service", "normal_code", "success")
    if code and code.lower() not in ok:
        return "%s (%s)" % (msg or "포털 오류", code)
    return None


# --------------------------------------------------------------------------- 기상청 격자

# 기상청 동네예보 Lambert Conformal Conic 파라미터 (5km 격자)
_LCC = dict(RE=6371.00877, GRID=5.0, SLAT1=30.0, SLAT2=60.0,
            OLON=126.0, OLAT=38.0, XO=43, YO=136)


def latlon_to_grid(lat: float, lon: float) -> tuple[int, int]:
    """위경도 → 기상청 동네예보 격자 (nx, ny). 공식 dfs_xy_conv 이식."""
    p = _LCC
    DEGRAD = math.pi / 180.0
    re = p["RE"] / p["GRID"]
    slat1 = p["SLAT1"] * DEGRAD
    slat2 = p["SLAT2"] * DEGRAD
    olon = p["OLON"] * DEGRAD
    olat = p["OLAT"] * DEGRAD

    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = (sf ** sn) * math.cos(slat1) / sn
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re * sf / (ro ** sn)

    ra = math.tan(math.pi * 0.25 + lat * DEGRAD * 0.5)
    ra = re * sf / (ra ** sn)
    theta = lon * DEGRAD - olon
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn

    nx = int(ra * math.sin(theta) + p["XO"] + 0.5)
    ny = int(ro - ra * math.cos(theta) + p["YO"] + 0.5)
    return nx, ny

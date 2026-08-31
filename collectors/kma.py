# -*- coding: utf-8 -*-
"""⑤ 위험요인 레이어 — 기상청 단기예보 조회서비스 + 노면위험도 산출.

  실황  https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst
  예보  https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst
  특보  https://apis.data.go.kr/1360000/WthrWrnInfoService/getWthrWrnList  (별도 활용신청)

물환경 상황판의 같은 수집기를 그대로 가져오고, 교통용으로 `road_risk` 를 덧붙였다.
격자(nx, ny)는 설정의 위경도에서 공식 LCC 식으로 계산한다(common.latlon_to_grid).
"""
from __future__ import annotations

import urllib.parse
from datetime import timedelta

from .common import CollectError, http_json, latlon_to_grid, now_kst, to_float

FCST_BASE = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"
WARN_BASE = "https://apis.data.go.kr/1360000/WthrWrnInfoService"

PTY = {"0": "없음", "1": "비", "2": "비/눈", "3": "눈", "4": "소나기",
       "5": "빗방울", "6": "빗방울/눈날림", "7": "눈날림"}
SKY = {"1": "맑음", "3": "구름많음", "4": "흐림"}

# 단기예보 발표시각(정시 기준). 실제 배포는 +10분 뒤라 여유를 둔다.
_VILAGE_BASE_HOURS = [2, 5, 8, 11, 14, 17, 20, 23]


def _service_key(key: str) -> str:
    """포털은 인코딩/디코딩 두 형태의 키를 준다. 어느 쪽을 넣어도 동작하게 정규화."""
    key = key.strip()
    if "%" in key:                       # 이미 인코딩된 키
        return key
    return urllib.parse.quote(key, safe="")


def _items(payload) -> list:
    try:
        body = payload["response"]["body"]
    except (KeyError, TypeError):
        header = (payload or {}).get("response", {}).get("header", {})
        raise CollectError("응답 형식이 예상과 다릅니다: %s"
                           % (header or str(payload)[:200]))
    items = (body.get("items") or {}).get("item")
    if items is None:
        return []
    return items if isinstance(items, list) else [items]


def _check(payload):
    header = (payload or {}).get("response", {}).get("header", {})
    code = str(header.get("resultCode", "")).strip()
    if code and code not in ("00", "0"):
        raise CollectError("기상청 API 오류 %s: %s" % (code, header.get("resultMsg", "")))
    return payload


def _ncst_bases(dt, back=3):
    """시도할 기준시각 목록 — 최신부터.

    안내문은 정시 자료가 +40분경 배포된다고 하지만 실제로는 훨씬 일찍 나온다.
    그래서 무조건 한 시간 물러서지 않고 최신부터 시도해 값이 없을 때만 뒤로 간다.
    """
    top = dt.replace(minute=0, second=0, microsecond=0)
    return [((top - timedelta(hours=i)).strftime("%Y%m%d"),
             (top - timedelta(hours=i)).strftime("%H00")) for i in range(back)]


def _vilage_base(dt):
    probe_at = dt - timedelta(minutes=15)          # 배포 지연 보정
    for hour in reversed(_VILAGE_BASE_HOURS):
        if probe_at.hour >= hour:
            return probe_at.strftime("%Y%m%d"), "%02d00" % hour
    prev = probe_at - timedelta(days=1)
    return prev.strftime("%Y%m%d"), "2300"


def _pcp(text):
    """'강수없음' / '1.0mm' / '30.0~50.0mm' 를 숫자와 표시문자열로."""
    text = (text or "").strip()
    if not text or text in ("강수없음", "-", "0", "적설없음"):
        return 0.0, "없음"
    number = to_float(text.replace("mm", "").replace("cm", "").split("~")[0])
    return (number if number is not None else 0.0), text


def fetch_now(key: str, nx: int, ny: int) -> dict:
    values, base_date, base_time = {}, None, None
    last_error = None
    for base_date, base_time in _ncst_bases(now_kst()):
        try:
            payload = _check(http_json(FCST_BASE + "/getUltraSrtNcst", {
                "serviceKey": _service_key(key), "pageNo": 1, "numOfRows": 100,
                "dataType": "JSON", "base_date": base_date, "base_time": base_time,
                "nx": nx, "ny": ny,
            }))
        except CollectError as exc:
            last_error = exc
            continue
        values = {i.get("category"): i.get("obsrValue") for i in _items(payload)}
        if values.get("T1H") is not None:
            break
    if not values:
        raise last_error or CollectError("초단기실황 응답이 비어 있습니다.")
    return {
        "base": "%s-%s-%s %s:00" % (base_date[:4], base_date[4:6], base_date[6:8],
                                    base_time[:2]),
        "temp": to_float(values.get("T1H")),
        "rain_1h": to_float(values.get("RN1"), 0.0),
        "humidity": to_float(values.get("REH")),
        "wind": to_float(values.get("WSD")),
        "pty": PTY.get(str(values.get("PTY", "0")).strip(), "-"),
    }


def fetch_forecast(key: str, nx: int, ny: int, hours: int = 24) -> dict:
    base_date, base_time = _vilage_base(now_kst())
    payload = _check(http_json(FCST_BASE + "/getVilageFcst", {
        "serviceKey": _service_key(key), "pageNo": 1, "numOfRows": 1000,
        "dataType": "JSON", "base_date": base_date, "base_time": base_time,
        "nx": nx, "ny": ny,
    }))
    slots: dict[str, dict] = {}
    for item in _items(payload):
        when = "%s%s" % (item.get("fcstDate", ""), item.get("fcstTime", ""))
        if len(when) != 12:
            continue
        slot = slots.setdefault(when, {"t": when})
        category, value = item.get("category"), item.get("fcstValue")
        if category == "POP":
            slot["pop"] = to_float(value)
        elif category == "PCP":
            slot["pcp"], slot["pcp_text"] = _pcp(value)
        elif category == "TMP":
            slot["temp"] = to_float(value)
        elif category == "REH":
            slot["reh"] = to_float(value)
        elif category == "SKY":
            slot["sky"] = SKY.get(str(value).strip(), "-")
        elif category == "PTY":
            slot["pty"] = PTY.get(str(value).strip(), "-")

    ordered = [slots[k] for k in sorted(slots)][:hours]
    return {
        "base": "%s-%s-%s %s:00" % (base_date[:4], base_date[4:6], base_date[6:8],
                                    base_time[:2]),
        "slots": ordered,
        "rain_sum": round(sum(s.get("pcp") or 0.0 for s in ordered), 1),
        "pop_max": max((s.get("pop") or 0 for s in ordered), default=0),
        "temp_min": min((s["temp"] for s in ordered if s.get("temp") is not None),
                        default=None),
    }


def fetch_warnings(key: str, stn_id: str = "133") -> list:
    """기상특보 목록(선택). 실패해도 상황판 전체를 막지 않는다. 133 = 대전·세종."""
    today = now_kst()
    payload = _check(http_json(WARN_BASE + "/getWthrWrnList", {
        "serviceKey": _service_key(key), "pageNo": 1, "numOfRows": 20,
        "dataType": "JSON", "stnId": stn_id,
        "fromTmFc": (today - timedelta(days=2)).strftime("%Y%m%d"),
        "toTmFc": today.strftime("%Y%m%d"),
    }))
    out = []
    for item in _items(payload):
        out.append({
            "title": (item.get("title") or item.get("warnVar") or "").strip(),
            "time": str(item.get("tmFc") or "").strip(),
            "detail": (item.get("other") or item.get("command") or "").strip(),
        })
    return out


# --------------------------------------------------------------------------- 노면위험도

RISK_ORDER = ["none", "caution", "warn", "alert"]
RISK_LABEL = {"none": "양호", "caution": "주의", "warn": "경계", "alert": "위험"}


def road_risk(now: dict | None, forecast: dict | None) -> dict:
    """실황·예보에서 운전 노면 위험을 뽑아낸다.

    기상 자체가 아니라 '도로가 미끄러운가·안 보이는가'로 바꿔 읽는 계산이다.
    기준은 도로 결빙 대응 실무에서 통용되는 값을 썼고, 판단 근거를 함께 남긴다.
    이건 참고값이며 노면 온도를 직접 잰 값이 아니다.
    """
    level, reasons = "none", []
    if not now:
        return {"level": "unknown", "label": "자료없음", "reasons": [],
                "note": "기상 실황을 받지 못했습니다."}

    temp = now.get("temp")
    rain = now.get("rain_1h") or 0.0
    humid = now.get("humidity") or 0.0
    wind = now.get("wind") or 0.0
    pty = now.get("pty") or "없음"
    wet = rain > 0 or pty not in ("없음", "-")

    def bump(target, why):
        nonlocal level
        if RISK_ORDER.index(target) > RISK_ORDER.index(level):
            level = target
        reasons.append(why)

    # 결빙 — 노면 온도는 기온보다 먼저 떨어진다. 3℃ 를 경계로 본다.
    if temp is not None:
        if temp <= 0 and wet:
            bump("alert", "기온 %.1f℃ · 강수 중 — 노면 결빙 위험" % temp)
        elif temp <= 0:
            bump("warn", "기온 %.1f℃ — 살얼음(블랙아이스) 가능" % temp)
        elif temp <= 3 and (wet or humid >= 80):
            bump("warn", "기온 %.1f℃ · 습도 %.0f%% — 교량·터널입구 결빙 주의"
                 % (temp, humid))
        elif temp <= 3:
            bump("caution", "기온 %.1f℃ — 새벽 노면 결빙 가능" % temp)

    # 강수 — 제동거리·수막
    if rain >= 10:
        bump("alert", "시간강수 %.1fmm — 수막현상·시야 불량" % rain)
    elif rain >= 3:
        bump("warn", "시간강수 %.1fmm — 제동거리 증가" % rain)
    elif rain > 0:
        bump("caution", "강수 %.1fmm — 노면 젖음" % rain)

    # 안개 — 습도 높고 바람 없을 때
    if humid >= 95 and wind <= 2:
        bump("warn", "습도 %.0f%% · 풍속 %.1fm/s — 안개 저시정 가능" % (humid, wind))

    # 강풍 — 이륜차·화물차
    if wind >= 9:
        bump("warn", "풍속 %.1fm/s — 이륜차·고상차량 주의" % wind)

    # 예보로 앞을 본다. 지금은 괜찮아도 새벽에 얼 수 있다.
    ahead = ""
    if forecast:
        low = forecast.get("temp_min")
        rain_sum = forecast.get("rain_sum") or 0
        if low is not None and low <= 0:
            bump("caution" if level == "none" else level,
                 "향후 24시간 최저 %.0f℃ — 야간·새벽 결빙 대비" % low)
            ahead = "24시간 내 영하"
        elif rain_sum >= 10:
            ahead = "24시간 강수 %.0fmm" % rain_sum

    return {"level": level, "label": RISK_LABEL[level], "reasons": reasons,
            "ahead": ahead,
            "note": "기온·강수·습도로 추정한 참고값입니다. 노면 온도 실측이 아닙니다."}


def collect(key: str, cfg: dict) -> dict:
    lat = float(cfg.get("lat", 36.4800))
    lon = float(cfg.get("lon", 127.2890))
    nx, ny = (cfg.get("nx"), cfg.get("ny"))
    if not nx or not ny:
        nx, ny = latlon_to_grid(lat, lon)

    result = {"grid": {"nx": nx, "ny": ny, "lat": lat, "lon": lon},
              "now": None, "forecast": None, "warnings": [], "errors": []}
    try:
        result["now"] = fetch_now(key, nx, ny)
    except CollectError as exc:
        result["errors"].append("초단기실황: %s" % exc)
    try:
        result["forecast"] = fetch_forecast(key, nx, ny,
                                            int(cfg.get("forecast_hours", 24)))
    except CollectError as exc:
        result["errors"].append("단기예보: %s" % exc)
    if cfg.get("warnings", True):
        try:
            result["warnings"] = fetch_warnings(key, str(cfg.get("stn_id", "133")))
        except CollectError as exc:
            # 특보는 단기예보와 다른 서비스라 활용신청이 따로 필요하다.
            # 403 이면 키가 틀린 게 아니라 그 서비스에 권한이 없다는 뜻이다.
            if "403" in str(exc):
                result["errors"].append(
                    "기상특보(선택): 이 인증키에 권한이 없습니다. 공공데이터포털에서 "
                    "'기상청_기상특보 조회서비스'를 따로 활용신청하거나, "
                    "config 의 kma.warnings 를 false 로 두면 이 줄이 사라집니다.")
            else:
                result["errors"].append("기상특보(선택): %s" % exc)

    result["risk"] = road_risk(result["now"], result["forecast"])
    return result

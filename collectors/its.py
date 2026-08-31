# -*- coding: utf-8 -*-
"""② 실시간 소통·돌발 레이어 — ITS 국가교통정보센터 오픈API.

  소통  https://openapi.its.go.kr:9443/trafficInfo
  돌발  https://openapi.its.go.kr:9443/eventInfo
  CCTV  https://openapi.its.go.kr:9443/cctvInfo

세 가지를 반드시 알고 써야 한다.

1. **국내 IP 에서만 응답한다.** 해외에서는 연결 자체가 거부된다(ECONNREFUSED).
   물환경 상황판의 한강홍수통제소와 같은 제약이라, 수집은 국내 PC/NAS 에서 하고
   공개는 정적 HTML 서빙으로 분리한다.
2. **인증키가 공공데이터포털 키와 다르다.** ITS 에서 따로 발급받는다.
   개발계정은 1,000건/일이라 10분 주기로 세 서비스를 돌리면 하루 432건 — 들어간다.
   그래도 여유가 없으니 운영계정 신청을 권한다.
3. **고속도로·국도 중심이다.** 세종시가 관리하는 시도(市道)는 대부분 안 잡힌다.
   이 화면에서 '소통정보 없음'은 고장이 아니라 커버리지 문제일 수 있다.
"""
from __future__ import annotations

from .common import (SEJONG_BBOX, CollectError, http_get, http_json, http_xml_rows,
                     in_sejong, norm_lat_lon, parse_stamp, pick, safe_url, stamp,
                     to_float, to_int)

BASE = "https://openapi.its.go.kr:9443"

# 돌발 유형 코드 → 사람이 읽는 말. ITS 는 한글로 주기도 하고 코드로 주기도 한다.
EVENT_KIND = {"acc": "교통사고", "cor": "공사", "wea": "기상", "dis": "재난",
              "etc": "기타", "ete": "행사", "acc1": "교통사고",
              "교통사고": "교통사고", "공사": "공사", "기상": "기상",
              "재난": "재난", "행사": "행사", "기타": "기타"}

# 지도·목록에서 눈에 띄어야 하는 순서
KIND_RANK = {"교통사고": 0, "재난": 1, "기상": 2, "공사": 3, "행사": 4, "기타": 5}

# 소통 등급 — 표준링크 속도 기준. 도로 등급을 모르므로 보수적으로 잡는다.
def flow_grade(speed) -> str:
    v = to_float(speed)
    if v is None:
        return "unknown"
    if v >= 50:
        return "smooth"          # 원활
    if v >= 30:
        return "slow"            # 서행
    if v >= 15:
        return "delay"           # 지체
    return "jam"                 # 정체


FLOW_LABEL = {"smooth": "원활", "slow": "서행", "delay": "지체", "jam": "정체",
              "unknown": "자료없음"}


def _bbox(cfg: dict) -> dict:
    box = cfg.get("bbox") or list(SEJONG_BBOX)
    x0, y0, x1, y1 = [float(v) for v in box]
    return {"minX": x0, "maxX": x1, "minY": y0, "maxY": y1}


def _fetch(url: str, key: str, cfg: dict, extra: dict) -> list:
    """JSON 으로 먼저 받고, 껍데기가 다르면 XML 로 한 번 더 시도한다."""
    params = {"apiKey": key, "type": cfg.get("road_type") or "all",
              "getType": "json"}
    params.update(_bbox(cfg))
    params.update(extra or {})
    try:
        payload = http_json(url, params, timeout=int(cfg.get("timeout") or 20))
    except CollectError as exc:
        if "JSON 이 아닌" not in str(exc):
            raise
        params["getType"] = "xml"
        return http_xml_rows(url, params, "data",
                             timeout=int(cfg.get("timeout") or 20))
    body = payload.get("body") if isinstance(payload, dict) else None
    if isinstance(body, dict):
        items = body.get("items")
        if isinstance(items, list):
            return [r for r in items if isinstance(r, dict)]
        if isinstance(items, dict):
            return [items]
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return [r for r in payload["items"] if isinstance(r, dict)]
    header = (payload or {}).get("header") or {}
    if header.get("resultCode") not in (None, "", "00", 0):
        raise CollectError("ITS 오류 %s: %s — %s"
                           % (header.get("resultCode"), header.get("resultMsg"),
                              safe_url(url)))
    return []


def fetch_flow(key: str, cfg: dict) -> list:
    """표준링크별 속도·통행시간. 5분 주기로 갱신된다."""
    url = cfg.get("flow_endpoint") or (BASE + "/trafficInfo")
    rows = _fetch(url, key, cfg, {"drcType": cfg.get("drc_type") or "all"})
    out = []
    for row in rows:
        speed = to_float(pick(row, "speed", "spd"))
        if speed is None:
            continue
        link = str(pick(row, "linkId", "link_id", default="") or "")
        out.append({
            "link": link,
            "road": str(pick(row, "roadName", "road_name", "roadNm",
                             default="이름 미상") or ""),
            "rank": str(pick(row, "roadRank", "road_rank", default="") or ""),
            "speed": round(speed, 1),
            "travel_time": to_float(pick(row, "travelTime", "travel_time")),
            "grade": flow_grade(speed),
            "time": str(pick(row, "createdDate", "created_date", "date",
                             default="") or ""),
        })
    out.sort(key=lambda r: r["speed"])
    return out


def fetch_events(key: str, cfg: dict) -> list:
    """돌발상황 — 사고·공사·통제. 상황판의 '지금 이슈' 패널이 여기서 나온다."""
    url = cfg.get("event_endpoint") or (BASE + "/eventInfo")
    rows = _fetch(url, key, cfg, {"eventType": cfg.get("event_type") or "all"})
    out = []
    for row in rows:
        lat, lon = norm_lat_lon(pick(row, "coordY", "coord_y", "lat", "yCoord"),
                                pick(row, "coordX", "coord_x", "lon", "xCoord"))
        raw_kind = str(pick(row, "eventType", "event_type", "type",
                            default="기타") or "기타").strip().lower()
        kind = EVENT_KIND.get(raw_kind, EVENT_KIND.get(raw_kind[:3], "기타"))
        started = str(pick(row, "startDate", "start_date", default="") or "")
        out.append({
            "kind": kind,
            "detail": str(pick(row, "eventDetailType", "event_detail_type",
                               "eventDetail", default="") or ""),
            "message": str(pick(row, "message", "msg", "eventCn",
                                default="") or ""),
            "road": str(pick(row, "roadName", "road_name", "roadNm",
                             default="") or ""),
            "link": str(pick(row, "linkId", "link_id", default="") or ""),
            "lat": lat, "lon": lon,
            "start": started,
            "end": str(pick(row, "endDate", "end_date", default="") or ""),
            "blocked": to_int(pick(row, "lanesBlockType", "lanes_block_type"), 0),
            "in_sejong": in_sejong(lat, lon),
        })
    out.sort(key=lambda e: (KIND_RANK.get(e["kind"], 9),
                            -(parse_stamp(e["start"]) or parse_stamp("19700101")).timestamp()))
    return out


def fetch_cctv(key: str, cfg: dict) -> list:
    """CCTV 목록(선택). 화상 자체는 받지 않고 지점만 지도에 찍는다."""
    url = cfg.get("cctv_endpoint") or (BASE + "/cctvInfo")
    rows = _fetch(url, key, cfg, {"cctvType": str(cfg.get("cctv_type") or "1")})
    out = []
    for row in rows:
        lat, lon = norm_lat_lon(pick(row, "coordy", "coordY", "lat"),
                                pick(row, "coordx", "coordX", "lon"))
        if not in_sejong(lat, lon):
            continue
        out.append({
            "name": str(pick(row, "cctvname", "cctvName", "name",
                             default="CCTV") or ""),
            "lat": lat, "lon": lon,
            "url": str(pick(row, "cctvurl", "cctvUrl", default="") or ""),
        })
    return out


def collect(key: str, cfg: dict) -> dict:
    out = {"flow": [], "events": [], "cctv": [], "errors": [],
           "collected_at": stamp(), "bbox": _bbox(cfg)}

    try:
        out["flow"] = fetch_flow(key, cfg)
    except CollectError as exc:
        out["errors"].append("소통정보: %s%s" % (exc, _hint(exc)))
    try:
        out["events"] = fetch_events(key, cfg)
    except CollectError as exc:
        out["errors"].append("돌발상황: %s%s" % (exc, _hint(exc)))
    if cfg.get("cctv"):
        try:
            out["cctv"] = fetch_cctv(key, cfg)
        except CollectError as exc:
            out["errors"].append("CCTV(선택): %s" % exc)

    flow = out["flow"]
    speeds = [r["speed"] for r in flow]
    out["summary"] = {
        "links": len(flow),
        "avg_speed": round(sum(speeds) / len(speeds), 1) if speeds else None,
        "jam": sum(1 for r in flow if r["grade"] in ("jam", "delay")),
        "events": sum(1 for e in out["events"] if e["in_sejong"]),
        "accidents": sum(1 for e in out["events"]
                         if e["in_sejong"] and e["kind"] == "교통사고"),
    }
    return out


def _hint(exc) -> str:
    text = str(exc)
    if "연결 실패" in text or "timed out" in text or "refused" in text.lower():
        return ("  ← ITS 는 국내 IP 에서만 응답합니다. 해외 서버/VPN 에서는 "
                "수집되지 않습니다.")
    if "401" in text or "인증" in text:
        return "  ← ITS 인증키는 공공데이터포털 키와 다릅니다. its.go.kr 에서 발급받으세요."
    return ""


# --------------------------------------------------------------------------- probe

def probe(key: str, cfg: dict) -> list:
    reports = []
    for name, url in (("소통", cfg.get("flow_endpoint") or BASE + "/trafficInfo"),
                      ("돌발", cfg.get("event_endpoint") or BASE + "/eventInfo"),
                      ("CCTV", cfg.get("cctv_endpoint") or BASE + "/cctvInfo")):
        reports.append(probe_one(url, key, cfg, name))
    return reports


def probe_one(url: str, key: str, cfg: dict, name=None) -> dict:
    report = {"url": url, "layer": name, "ok": False, "count": 0,
              "sample": None, "error": None}
    params = {"apiKey": key, "type": cfg.get("road_type") or "all",
              "getType": "json", "eventType": "all", "drcType": "all"}
    params.update(_bbox(cfg))
    try:
        text = http_get(url, params, timeout=int(cfg.get("timeout") or 20), retries=0)
    except CollectError as exc:
        report["error"] = str(exc) + _hint(exc)
        return report
    head = text.lstrip()[:1]
    if head not in "{[":
        report["error"] = "JSON 이 아닌 응답: %s" % safe_url(text.strip()[:200])
        return report
    try:
        rows = _fetch(url, key, cfg, {"eventType": "all", "drcType": "all"})
    except CollectError as exc:
        report["error"] = str(exc)
        return report
    report["count"] = len(rows)
    report["ok"] = bool(rows)
    if rows:
        report["sample"] = {k: rows[0].get(k) for k in list(rows[0])[:12]}
    return report

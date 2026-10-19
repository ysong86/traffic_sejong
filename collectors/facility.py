# -*- coding: utf-8 -*-
"""④ 정적 시설 레이어 — 전국 표준데이터 + 세종시 직접 제공 API.

두 종류를 섮어 쓴다. 레이어마다 전국을 먼저 두드리고, 비어 있거나 미승인이면
세종시가 직접 올린 것으로 넘어간다. 황단보도처럼 전국 자료가 아예 없는 것도 있다.
나중에 전국 쪽이 승인되면 저절로 그쪽을 쓴다 — 설정을 고칠 필요가 없다.

  https://api.data.go.kr/openapi/{오퍼레이션}
      serviceKey, pageNo, numOfRows, type=json  (+ 필드명을 그대로 필터로 쓸 수 있다)

표준데이터는 전국 단위라 세종만 골라내야 한다. 두 단계로 좁힌다.

  1) `ctprvnNm=세종특별자치시` 처럼 시도명 필터를 붙여 요청한다(대부분 먹는다).
  2) 0건이면 필터 없이 훑으면서 주소·기관명에 '세종'이 든 행만 남긴다.
     전국 데이터를 다 훑는 건 비싸므로 max_pages 로 막아 둔다.

갱신이 드문 자료(월~연 단위)라 매번 받을 필요가 없다. run.py 가 캐시를 쓴다.
"""
from __future__ import annotations

from .common import (CollectError, http_json, in_sejong, norm_lat_lon, pick,
                     portal_error, portal_rows, portal_total, safe_url, to_float,
                     to_int)

BASE = "https://api.data.go.kr/openapi"

# 세종시가 직접 올린 오픈API. 전국 표준데이터와 **생김새가 다르다**.
#   쪽 넘김  pageIndex / pageUnit   (표준데이터는 pageNo / numOfRows)
#   응답     {"header":{...}, "body":{"items":[...]}}
#   좌표     la / lo
# 전국 자료에 세종이 빠져 있거나(횡단보도) 아직 승인이 안 난 레이어를 여기서
# 메운다. 이미 세종 것만 들어 있으므로 시도명으로 거를 필요도 없다.
SJ = "https://apis.data.go.kr/5690000"

# 세종 여부를 판단할 때 훑는 필드들 — 표준데이터마다 이름이 조금씩 다르다.
REGION_FIELDS = ("ctprvnNm", "sidoNm", "signguNm", "rdnmadr", "lnmadr",
                 "institutionNm", "adres", "roadNmAdres", "cn")

def _std(op):
    return {"url": BASE + "/" + op, "kind": "std"}


def _sj(service, op):
    return {"url": "%s/%s/%s" % (SJ, service, op), "kind": "sj"}


# sources 는 **차례대로 시도**한다. 앞엣것이 403(미승인)이거나 0건이면 뒤로 넘어간다.
# 전국 표준데이터를 앞에 두는 이유는 전국이 대개 더 촘촘하기 때문이고, 세종시 것을
# 뒤에 두는 이유는 전국이 막혀 있는 동안에도 화면이 비지 않게 하기 위해서다.
# 나중에 전국 쪽 활용신청이 승인되면 저절로 그쪽으로 돌아간다 — 손댈 것이 없다.
LAYERS = [
    {"id": "camera", "label": "무인교통단속카메라", "icon": "camera",
     "sources": [_std("tn_pubr_public_unmanned_traffic_camera_api")],
     "name_fields": ("itlpc", "instlLcNm", "spotNm", "rdnmadr"),
     "note_fields": (("regltSe", "단속구분"), ("lmttVe", "제한속도"),
                     ("itlpc", "설치장소"))},

    {"id": "child_zone", "label": "어린이보호구역", "icon": "zone-child",
     "sources": [_std("tn_pubr_public_child_prtc_zn_api"),
                 _sj("sjSchoolZoneInformation", "sj_00000660")],
     "name_fields": ("fcltyNm", "schoolNm", "instNm", "rdnmadr", "roadNmAddr"),
     "note_fields": (("fcltyKndNm", "시설종류"), ("cctvInstlYn", "CCTV"),
                     ("mtrPolcNm", "관할경찰서"), ("lmtVe", "제한속도"),
                     ("cmptncPolcsttnNm", "관할경찰서"))},

    # 2026-10 포털 데이터셋 페이지에서 실제 오퍼레이션명을 확인했다.
    # 이름을 지어내 두드리던 것(eldrl_dspsn_prtc_zn 등)은 전부 틀렸다 —
    # 표준데이터 이름은 규칙이 아니라 등록된 그대로다. 페이지에서 긁어와야 한다.
    {"id": "elder_zone", "label": "노인·장애인 보호구역", "icon": "zone-elder",
     "sources": [_std("tn_pubr_public_oldnddspsnprt_carea_api"),
                 _sj("sjProZone", "sj_00000220")],
     "name_fields": ("fcltyNm", "instNm", "rdnmadr", "roadNmAddr"),
     "note_fields": (("fcltyKndNm", "시설종류"), ("mtrPolcNm", "관할경찰서"),
                     ("lmtVe", "제한속도"), ("cmptncPolcsttnNm", "관할경찰서"),
                     ("cctvInstlCo", "CCTV 대수"))},

    # 횡단보도 — 전국 표준데이터가 아예 없다(2026-10 확인). 세종시가 직접 올린
    # 것으로만 채운다. 전국이 없다고 비워 두던 자리를 메운 셈이다.
    {"id": "crosswalk", "label": "횡단보도", "icon": "crosswalk",
     "sources": [_sj("sjCrosswalkInformation", "sj_00001170")],
     "name_fields": ("roadNmAddr", "addr", "rdnmadr", "lnmadr", "cwalkNm"),
     "note_fields": (("ctwlkKndNm", "종류"), ("tfcsfclInstlYn", "신호등"))},

    # 자전거도로 — 전국 표준데이터에 **세종 행이 없다**(2026-10-19 포털에서 확인).
    # 표준데이터 등록은 지자체 자율이라 빠진 곣이 생긴다. 세종시가 따로 올린 것도
    # 없어 비워 둔다 — 주소를 두면 화면에 영원히 실패로 남는데, 그건 사실과 다르다.
    {"id": "bike_road", "label": "자전거도로", "icon": "bike",
     "gone": "전국 표준데이터에 세종 자료 미등록",
     "sources": [],
     "name_fields": ("bcyclRoadNm", "rdnmadr", "lnmadr"),
     "note_fields": (("bcyclRoadSeNm", "구분"), ("roadLt", "연장(m)"))},

    # 신호등 — 보호구역·단속장비와 겹쳐 보면 '신호 없는 다발지'를 짚을 수 있다.
    {"id": "traffic_light", "label": "신호등", "icon": "light",
     "sources": [_std("tn_pubr_public_traffic_light_api"),
                 _sj("sjTrafficLightInforamtion", "sj_00000610")],
     "name_fields": ("itlpc", "instlLcNm", "roadRouteNm", "roadNmAddr", "addr"),
     "note_fields": (("tfcsfclKndNm", "종류"), ("instlTy", "설치형태"),
                     ("roadRouteNm", "도로"), ("tfclghtOrdr", "등화순서"),
                     ("pdstrnSgngnrEnnc", "음향신호기"))},

    # 도로안전표지 — 표지가 없는 곳과 사고다발지가 겹치면 바로 할 일이 나온다.
    {"id": "road_sign", "label": "도로안전표지", "icon": "sign",
     "sources": [_sj("sjRoadSign", "sj_00000270")],
     "name_fields": ("roadNmAddr", "addr", "sgnNm", "roadRouteNm"),
     "note_fields": (("sgnKndNm", "종류"), ("sgnSe", "구분"))},
]

LAYER_BY_ID = {row["id"]: row for row in LAYERS}


def _is_sejong(row: dict) -> bool:
    for field in REGION_FIELDS:
        value = str(row.get(field) or "")
        if "세종" in value:
            return True
    return False


def _page(url: str, key: str, page: int, rows: int, extra: dict | None = None):
    params = {"serviceKey": key, "pageNo": str(page), "numOfRows": str(rows),
              "type": "json"}
    params.update(extra or {})
    payload = http_json(url, params)
    err = portal_error(payload)
    if err:
        raise CollectError("%s — %s" % (err, safe_url(url)))
    return portal_rows(payload), portal_total(payload, 0)


def _page_sj(url: str, key: str, page: int, rows: int):
    """세종시 오픈API 한 쪽. 변수 이름도 응답 모양도 표준데이터와 다르다."""
    payload = http_json(url, {"serviceKey": key, "pageIndex": str(page),
                              "pageUnit": str(rows), "type": "json"})
    head = payload.get("header") or {}
    code = str(head.get("resultCode") or "")
    # 정상은 00. 나머지는 사유를 그대로 올린다 — 코드만 보고 짐작하면 틀린다.
    if code and code != "00":
        raise CollectError("%s %s — %s"
                           % (code, head.get("resultMsg") or "", safe_url(url)))
    body = payload.get("body") or {}
    return list(body.get("items") or []), to_int(head.get("totalCount"), 0)


def _fetch_sj(url: str, key: str, cfg: dict) -> list:
    """세종시 자료는 이미 세종 것뿐이라 걸러 낼 것이 없다. 쪽만 넘긴다."""
    rows_per_page = int(cfg.get("rows_per_page") or 500)
    max_pages = int(cfg.get("max_pages") or 30)
    out, page = [], 1
    while page <= max_pages:
        got, total = _page_sj(url, key, page, rows_per_page)
        if not got:
            break
        out.extend(got)
        if len(got) < rows_per_page or (total and page * rows_per_page >= total):
            break
        page += 1
    return out


def _fetch_layer(url: str, key: str, cfg: dict) -> list:
    """시도명 필터로 먼저 시도하고, 안 먹으면 전국을 훑어 '세종'만 남긴다."""
    rows_per_page = int(cfg.get("rows_per_page") or 500)
    max_pages = int(cfg.get("max_pages") or 30)
    filter_field = cfg.get("region_field") or "ctprvnNm"
    filter_value = cfg.get("region_value") or "세종특별자치시"

    try:
        got, _ = _page(url, key, 1, rows_per_page, {filter_field: filter_value})
        picked = [r for r in got if _is_sejong(r)]
        if picked:
            return picked
    except CollectError:
        pass                       # 필터를 못 받는 서비스다. 전수 훑기로 넘어간다.

    out, page = [], 1
    while page <= max_pages:
        got, total = _page(url, key, page, rows_per_page)
        if not got:
            break
        out.extend(r for r in got if _is_sejong(r))
        if len(got) < rows_per_page or (total and page * rows_per_page >= total):
            break
        page += 1
    return out


def _item(row: dict, layer: dict) -> dict | None:
    # 세종시 API 는 la / lo 다. 표준데이터와 이름이 달라 둘 다 훑는다.
    lat, lon = norm_lat_lon(pick(row, "latitude", "lat", "la", "la_crd", "yCrd"),
                            pick(row, "longitude", "lon", "lo", "lot", "lo_crd",
                                 "xCrd"))
    if not in_sejong(lat, lon):
        return None
    name = str(pick(row, *layer["name_fields"], default="") or layer["label"])
    notes = []
    for field, label in layer["note_fields"]:
        value = str(row.get(field) or "").strip()
        if value and value not in ("-", "0"):
            notes.append("%s %s" % (label, value))
    return {"layer": layer["id"], "layer_label": layer["label"],
            "icon": layer["icon"], "name": name.strip(),
            "lat": lat, "lon": lon, "notes": notes,
            "addr": str(pick(row, "rdnmadr", "lnmadr", "adres", default="") or ""),
            # 표준데이터가 스스로 밝히는 기준일자. 화면의 '자료 시점'은 우리가
            # 언제 받아왔는지가 아니라 이 날짜를 보여줘야 한다 — 월~연 단위로
            # 갱신되는 자료를 수집 시각으로 표시하면 방금 갱신된 것처럼 읽힌다.
            "ref_date": str(pick(row, "referenceDate", "refrnDate", "crtrYmd",
                                 "dataCrtrYmd", default="") or "")}


def collect(key: str, cfg: dict) -> dict:
    wanted = cfg.get("layers") or [row["id"] for row in LAYERS]
    overrides = cfg.get("endpoints") or {}
    out = {"layers": [], "items": [], "errors": [], "pending": [], "unavailable": []}

    for layer_id in wanted:
        layer = LAYER_BY_ID.get(layer_id)
        if not layer:
            continue

        # config.json 으로 주소를 덮어썼으면 그것만 쓴다(표준데이터 형식으로 본다).
        forced = str(overrides.get(layer_id) or "").strip()
        sources = ([{"url": forced, "kind": "std"}] if forced
                   else list(layer.get("sources") or []))
        if not sources:
            if layer.get("gone"):
                out["unavailable"].append("%s(%s)" % (layer["label"], layer["gone"]))
            else:
                out["pending"].append(layer["label"])
            continue

        # 차례대로 두드려 **처음 자료가 나오는 곳**을 쓴다. 앞엣것이 미승인(403)
        # 이거나 0건이면 조용히 뒤로 넘어간다. 전부 실패했을 때만 사유를 남긴다.
        rows, used, failures = [], None, []
        for source in sources:
            try:
                got = (_fetch_sj if source["kind"] == "sj" else _fetch_layer)(
                    source["url"], key, cfg)
            except CollectError as exc:
                failures.append(str(exc))
                continue
            if got:
                rows, used = got, source
                break
            failures.append("0건 — %s" % safe_url(source["url"]))

        if used is None:
            out["errors"].append("%s: %s" % (layer["label"], failures[-1]
                                             if failures else "자료 없음"))
            continue

        items = [i for i in (_item(r, layer) for r in rows) if i]
        ref = max((i["ref_date"] for i in items if i.get("ref_date")), default="")
        out["layers"].append({"id": layer["id"], "label": layer["label"],
                              "icon": layer["icon"], "count": len(items),
                              "raw": len(rows), "ref_date": ref,
                              # 어디서 받아왔는지 남긴다. 같은 레이어라도 전국이냐
                              # 세종시냐에 따라 촘촘함과 기준일이 달라진다.
                              "origin": "세종시" if used["kind"] == "sj" else "전국",
                              "endpoint": safe_url(used["url"])})
        out["items"].extend(items)

    # 레이어마다 기준일이 다르다. 가장 오래된 쪽이 이 겹 전체의 실제 신선도다.
    dates = [r["ref_date"] for r in out["layers"] if r.get("ref_date")]
    out["ref_date"] = min(dates) if dates else ""
    return out


# --------------------------------------------------------------------------- probe

def probe(key: str, cfg: dict) -> list:
    overrides = cfg.get("endpoints") or {}
    reports = []
    for layer in LAYERS:
        if str(overrides.get(layer["id"]) or "").strip():
            continue
        for source in layer.get("sources") or []:
            reports.append(probe_one(source["url"], key, cfg, layer["id"],
                                     source["kind"]))
    return reports


def probe_one(url: str, key: str, cfg: dict, layer_id=None, kind="std") -> dict:
    report = {"url": url, "layer": layer_id, "kind": kind, "ok": False,
              "count": 0, "sample": None, "error": None}
    try:
        rows, _ = (_page_sj(url, key, 1, 10) if kind == "sj"
                   else _page(url, key, 1, 10))
    except CollectError as exc:
        report["error"] = str(exc)
        return report
    report["count"] = len(rows)
    report["ok"] = bool(rows)
    if rows:
        report["sample"] = {k: rows[0].get(k) for k in list(rows[0])[:12]}
    return report

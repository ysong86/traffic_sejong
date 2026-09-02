# -*- coding: utf-8 -*-
"""④ 정적 시설 레이어 — 공공데이터포털 표준데이터.

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

# 세종 여부를 판단할 때 훑는 필드들 — 표준데이터마다 이름이 조금씩 다르다.
REGION_FIELDS = ("ctprvnNm", "sidoNm", "signguNm", "rdnmadr", "lnmadr",
                 "institutionNm", "adres", "roadNmAdres", "cn")

LAYERS = [
    {"id": "camera", "label": "무인교통단속카메라", "icon": "camera",
     "endpoint": BASE + "/tn_pubr_public_unmanned_traffic_camera_api",
     "candidates": [BASE + "/tn_pubr_public_unmanned_traffic_camera_api"],
     "name_fields": ("itlpc", "instlLcNm", "spotNm", "rdnmadr"),
     "note_fields": (("regltSe", "단속구분"), ("lmttVe", "제한속도"),
                     ("itlpc", "설치장소"))},

    {"id": "child_zone", "label": "어린이보호구역", "icon": "zone-child",
     "endpoint": BASE + "/tn_pubr_public_child_prtc_zn_api",
     "candidates": [BASE + "/tn_pubr_public_child_prtc_zn_api"],
     "name_fields": ("fcltyNm", "schoolNm", "instNm", "rdnmadr"),
     "note_fields": (("fcltyKndNm", "시설종류"), ("cctvInstlYn", "CCTV"),
                     ("mtrPolcNm", "관할경찰서"))},

    # --- 아래는 오퍼레이션명이 문서로 확인되지 않았다. probe 로 확정할 것.
    {"id": "elder_zone", "label": "노인·장애인 보호구역", "icon": "zone-elder",
     "endpoint": "", "candidates": [
         BASE + "/tn_pubr_public_eldrl_dspsn_prtc_zn_api",
         BASE + "/tn_pubr_public_senior_prtc_zn_api",
         BASE + "/tn_pubr_public_elderly_prtc_zn_api"],
     "name_fields": ("fcltyNm", "instNm", "rdnmadr"),
     "note_fields": (("fcltyKndNm", "시설종류"), ("mtrPolcNm", "관할경찰서"))},

    {"id": "crosswalk", "label": "횡단보도", "icon": "crosswalk",
     "endpoint": "", "candidates": [
         BASE + "/tn_pubr_public_cwalk_api",
         BASE + "/tn_pubr_public_crosswalk_api",
         BASE + "/tn_pubr_public_crswlk_api"],
     "name_fields": ("rdnmadr", "lnmadr", "cwalkNm"),
     "note_fields": (("ctwlkKndNm", "종류"), ("tfcsfclInstlYn", "신호등"))},

    {"id": "bike_road", "label": "자전거도로", "icon": "bike",
     "endpoint": "", "candidates": [
         BASE + "/tn_pubr_public_bcycl_road_api",
         BASE + "/tn_pubr_public_bicycle_road_api"],
     "name_fields": ("bcyclRoadNm", "rdnmadr", "lnmadr"),
     "note_fields": (("bcyclRoadSeNm", "구분"), ("roadLt", "연장(m)"))},
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
    lat, lon = norm_lat_lon(pick(row, "latitude", "lat", "la_crd", "yCrd"),
                            pick(row, "longitude", "lon", "lot", "lo_crd", "xCrd"))
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
    out = {"layers": [], "items": [], "errors": [], "pending": []}

    for layer_id in wanted:
        layer = LAYER_BY_ID.get(layer_id)
        if not layer:
            continue
        url = str(overrides.get(layer_id) or layer["endpoint"] or "").strip()
        if not url:
            out["pending"].append(layer["label"])
            continue
        try:
            rows = _fetch_layer(url, key, cfg)
        except CollectError as exc:
            out["errors"].append("%s: %s" % (layer["label"], exc))
            continue
        items = [i for i in (_item(r, layer) for r in rows) if i]
        ref = max((i["ref_date"] for i in items if i.get("ref_date")), default="")
        out["layers"].append({"id": layer["id"], "label": layer["label"],
                              "icon": layer["icon"], "count": len(items),
                              "raw": len(rows), "ref_date": ref,
                              "endpoint": safe_url(url)})
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
        if str(overrides.get(layer["id"]) or layer["endpoint"]).strip():
            continue
        for url in layer["candidates"]:
            reports.append(probe_one(url, key, cfg, layer["id"]))
    return reports


def probe_one(url: str, key: str, cfg: dict, layer_id=None) -> dict:
    report = {"url": url, "layer": layer_id, "ok": False, "count": 0,
              "sample": None, "error": None}
    try:
        rows, _ = _page(url, key, 1, 10)
    except CollectError as exc:
        report["error"] = str(exc)
        return report
    report["count"] = len(rows)
    report["ok"] = bool(rows)
    if rows:
        report["sample"] = {k: rows[0].get(k) for k in list(rows[0])[:12]}
    return report

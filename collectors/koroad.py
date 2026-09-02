# -*- coding: utf-8 -*-
"""① 사고·안전성과 레이어 — 도로교통공단(KOROAD) 교통사고 다발지역.

연 단위 자료다. 실시간이 아니라 '진단'용이며, 공표가 1~2년 늦다.
그래서 지정 연도부터 최대 `year_back` 년 거슬러 올라가며 값이 있는 해를 찾는다.

요청 규격 (공공데이터포털 B552061 계열, 전 레이어 공통)
    GET https://apis.data.go.kr/B552061/{서비스}/getRest{서비스}
        ServiceKey, searchYearCd, siDo, guGun, type=json, numOfRows, pageNo

siDo/guGun 은 법정동코드 앞 5자리를 2+3 으로 쪼갠 값이다(세종 36110 → 36 / 110).

엔드포인트가 확인된 레이어와 후보만 있는 레이어가 섞여 있다.
후보뿐인 것은 `run.py --probe --only koroad` 로 사용자 PC(국내 IP·본인 키)에서
확정한 뒤 config.json 에 적어 넣는다. 확정 전에는 조용히 건너뛴다.
"""
from __future__ import annotations

from .common import (CollectError, http_json, in_sejong, norm_lat_lon, now_kst,
                     pick, portal_error, portal_rows, portal_total, safe_url,
                     to_int)

BASE = "https://apis.data.go.kr/B552061"


def _ep(service: str, verb: str | None = None) -> str:
    return "%s/%s/getRest%s" % (BASE, service, verb or service[0].upper() + service[1:])


# id, 라벨, 분류, 확정 엔드포인트(없으면 None), 후보들
#   분류 vuln = 기본계획 5대 취약계층 지표에 직결되는 레이어
LAYERS = [
    {"id": "lg", "label": "전체 사고다발지", "group": "base", "weight": 1.0,
     "endpoint": _ep("frequentzoneLg", "FrequentzoneLg"),
     "candidates": [_ep("frequentzoneLg", "FrequentzoneLg")]},

    {"id": "schoolzone", "label": "스쿨존 어린이", "group": "vuln", "weight": 3.0,
     "endpoint": _ep("schoolzoneChild", "SchoolzoneChild"),
     "candidates": [_ep("schoolzoneChild", "SchoolzoneChild")]},

    # 무단횡단은 웹 문서에 이 주소로 적혀 있었지만 실제로는 400 을 준다.
    # (미승인이면 403 이 오므로 400 은 '그런 서비스가 없다'는 뜻이다.)
    # 확정 전까지는 후보로만 둔다.
    {"id": "jaywalk", "label": "보행자 무단횡단", "group": "vuln", "weight": 2.0,
     "endpoint": "", "candidates": [
         _ep("jaywalking", "Jaywalking"),
         _ep("frequentzoneJaywalking", "FrequentzoneJaywalking"),
         _ep("frequentzoneJaywalk", "FrequentzoneJaywalk")]},

    {"id": "freezing", "label": "결빙(도로 살얼음)", "group": "risk", "weight": 2.0,
     "endpoint": _ep("frequentzoneFreezing", "FrequentzoneFreezing"),
     "candidates": [_ep("frequentzoneFreezing", "FrequentzoneFreezing")]},

    # --- 아래는 요청주소가 공개 문서로 확인되지 않았다. probe 로 확정할 것.
    # 아래 둘은 2026-09-02 실제 키로 타진해 확정했다(세종 자료 응답 확인).
    {"id": "child", "label": "어린이 보행", "group": "vuln", "weight": 3.0,
     "endpoint": _ep("frequentzoneChild", "FrequentzoneChild"),
     "candidates": [_ep("frequentzoneChild", "FrequentzoneChild")]},

    {"id": "oldman", "label": "노인 보행", "group": "vuln", "weight": 3.0,
     "endpoint": _ep("frequentzoneOldman", "FrequentzoneOldman"),
     "candidates": [_ep("frequentzoneOldman", "FrequentzoneOldman")]},

    {"id": "pedestrian", "label": "보행자 전체", "group": "vuln", "weight": 2.5,
     "endpoint": "", "candidates": [
         _ep("frequentzonePedestrian", "FrequentzonePedestrian"),
         _ep("pedestrians", "Pedestrians"),
         _ep("frequentzoneWalk", "FrequentzoneWalk")]},

    # 자전거는 타진에서 403(미승인)이 왔다 — 주소는 맞고 활용신청만 남았다는 뜻이다.
    # 다른 후보들이 400(그런 서비스 없음)을 준 것과 대비된다.
    {"id": "bicycle", "label": "자전거", "group": "vuln", "weight": 2.0,
     "endpoint": _ep("frequentzoneBicycle", "FrequentzoneBicycle"),
     "candidates": [_ep("frequentzoneBicycle", "FrequentzoneBicycle")]},

    {"id": "motorcycle", "label": "이륜차", "group": "vuln", "weight": 2.0,
     "endpoint": "", "candidates": [
         _ep("frequentzoneMotorcycle", "FrequentzoneMotorcycle"),
         _ep("frequentzoneBicycleMotorcycle", "FrequentzoneBicycleMotorcycle"),
         _ep("motorcycle", "Motorcycle")]},

    {"id": "death", "label": "사망사고 지점", "group": "death", "weight": 5.0,
     "endpoint": "", "candidates": [
         _ep("frequentzoneDeath", "FrequentzoneDeath"),
         "%s/deathAccident/getRestDeathAccident" % BASE,
         "%s/accidentDeath/getRestAccidentDeath" % BASE]},
]

LAYER_BY_ID = {row["id"]: row for row in LAYERS}


def _rows(url: str, key: str, year: int, sido: str, gugun: str,
          rows_per_page: int = 100, extra: dict | None = None) -> list:
    """한 해·한 지자체의 다발지역을 전부 받아온다. 페이지가 넘어가면 이어 받는다."""
    out, page, total = [], 1, None
    while page <= 20:                                  # 시군구 하나에 20페이지면 충분하다
        params = {"ServiceKey": key, "searchYearCd": str(year), "siDo": sido,
                  "guGun": gugun, "type": "json",
                  "numOfRows": str(rows_per_page), "pageNo": str(page)}
        params.update(extra or {})
        payload = http_json(url, params)
        err = portal_error(payload)
        if err:
            # NODATA_ERROR(03) 는 고장이 아니다. 그 해 그 지역에 해당 유형의
            # 다발지가 없다는 뜻이므로 빈 결과로 돌려준다(결빙이 대표적이다).
            if "NODATA" in err.upper() or "(03)" in err:
                return out
            raise CollectError("%s — %s" % (err, safe_url(url)))
        got = portal_rows(payload)
        out.extend(got)
        if total is None:
            total = portal_total(payload, len(got))
        if len(got) < rows_per_page or len(out) >= (total or 0):
            break
        page += 1
    return out


def _spot(row: dict, layer: dict, year: int) -> dict | None:
    """응답 한 줄 → 상황판이 쓰는 지점 하나. 좌표가 못 쓰면 버린다."""
    lat, lon = norm_lat_lon(pick(row, "la_crd", "lat", "latitude", "yCrd", "ycrd"),
                            pick(row, "lo_crd", "lot", "lon", "longitude", "xCrd", "xcrd"))
    if lat is None:
        return None

    deaths = to_int(pick(row, "dth_dnv_cnt", "deathCnt", "dth"), 0)
    serious = to_int(pick(row, "se_dnv_cnt", "seriousCnt"), 0)
    slight = to_int(pick(row, "sl_dnv_cnt", "slightCnt"), 0)
    wound = to_int(pick(row, "wnd_dnv_cnt", "woundCnt"), 0)
    count = to_int(pick(row, "occrrnc_cnt", "accidentCnt", "acdnt_cnt"), 0)

    return {
        "layer": layer["id"],
        "layer_label": layer["label"],
        "group": layer["group"],
        "year": year,
        "id": str(pick(row, "afos_fid", "afos_id", "spot_cd", default="") or ""),
        "name": str(pick(row, "spot_nm", "spotNm", "name", default="이름 미상") or ""),
        "bjd": str(pick(row, "bjd_cd", "bjdCd", default="") or ""),
        "sido_sgg": str(pick(row, "sido_sgg_nm", "sidoSggNm", default="") or ""),
        "lat": lat, "lon": lon,
        "accidents": count,
        "deaths": deaths,
        "serious": serious,
        "slight": slight,
        "wounded": wound,
        # 사상자 = 사망 + 중상 + 경상 + 부상신고. 심각도는 사망에 가중을 준 통상 EPDO 축약.
        "casualties": deaths + serious + slight + wound,
        "severity": deaths * 12 + serious * 3 + slight * 1,
        "poly": _ring(pick(row, "geom_json", "geomJson")),
    }


def _ring(geom):
    """geom_json(문자열 또는 dict)에서 외곽 링 한 줄을 [[lon,lat], ...] 로 뽑는다.

    다발지역 폴리곤은 반경 150m 남짓의 작은 도형이라 링 하나면 충분하다.
    """
    import json as _json
    if not geom:
        return None
    raw = geom
    if isinstance(raw, str):
        try:
            raw = _json.loads(raw)
        except ValueError:
            return None
    if not isinstance(raw, dict):
        return None
    coords = raw.get("coordinates") or []
    kind = str(raw.get("type") or "").lower()
    try:
        if kind == "polygon":
            ring = coords[0]
        elif kind == "multipolygon":
            ring = coords[0][0]
        else:
            return None
        pts = [[round(float(p[0]), 6), round(float(p[1]), 6)] for p in ring]
    except (IndexError, TypeError, ValueError):
        return None
    return pts if len(pts) >= 3 else None


def collect(key: str, cfg: dict) -> dict:
    """설정에 켜진 레이어를 모두 받아온다. 한 레이어가 죽어도 나머지는 살린다."""
    sido = str(cfg.get("sido") or "36").strip()
    gugun = str(cfg.get("gugun") or "110").strip()
    wanted = cfg.get("layers") or [row["id"] for row in LAYERS]
    year_back = int(cfg.get("year_back") or 3)
    start_year = int(cfg.get("year") or (now_kst().year - 1))
    overrides = cfg.get("endpoints") or {}

    out = {"sido": sido, "gugun": gugun, "layers": [], "spots": [], "errors": [],
           "pending": [], "asked_year": start_year}

    for layer_id in wanted:
        layer = LAYER_BY_ID.get(layer_id)
        if not layer:
            continue
        url = str(overrides.get(layer_id) or layer["endpoint"] or "").strip()
        if not url:
            out["pending"].append(layer["label"])
            continue

        spots, used_year, last_err = [], None, None
        for back in range(year_back + 1):
            year = start_year - back
            try:
                rows = _rows(url, key, year, sido, gugun,
                             int(cfg.get("rows_per_page") or 100),
                             cfg.get("extra_params"))
            except CollectError as exc:
                last_err = str(exc)
                continue
            picked = [s for s in (_spot(r, layer, year) for r in rows) if s]
            # 시도·시군구로 이미 걸렀지만 좌표가 엉뚱한 행이 섞여 온다. 경계로 한 번 더.
            picked = [s for s in picked if in_sejong(s["lat"], s["lon"])]
            if picked:
                spots, used_year = picked, year
                break

        if spots:
            spots.sort(key=lambda s: (-s["severity"], -s["accidents"]))
            out["layers"].append({
                "id": layer["id"], "label": layer["label"], "group": layer["group"],
                "weight": layer["weight"], "year": used_year,
                "count": len(spots),
                "accidents": sum(s["accidents"] for s in spots),
                "deaths": sum(s["deaths"] for s in spots),
                "casualties": sum(s["casualties"] for s in spots),
                "endpoint": safe_url(url),
            })
            out["spots"].extend(spots)
        elif last_err:
            out["errors"].append("%s: %s" % (layer["label"], last_err))
        else:
            out["layers"].append({
                "id": layer["id"], "label": layer["label"], "group": layer["group"],
                "weight": layer["weight"], "year": None, "count": 0,
                "accidents": 0, "deaths": 0, "casualties": 0,
                "endpoint": safe_url(url),
            })

    years = [row["year"] for row in out["layers"] if row.get("year")]
    out["year"] = max(years) if years else None
    out["spots"].sort(key=lambda s: (-s["severity"], -s["accidents"]))
    return out


# --------------------------------------------------------------------------- probe

def probe(key: str, cfg: dict) -> list:
    """엔드포인트가 확인되지 않은 레이어의 후보를 하나씩 타진한다."""
    sido = str(cfg.get("sido") or "36").strip()
    gugun = str(cfg.get("gugun") or "110").strip()
    year = int(cfg.get("year") or (now_kst().year - 2))
    reports = []
    for layer in LAYERS:
        if str((cfg.get("endpoints") or {}).get(layer["id"]) or layer["endpoint"]).strip():
            continue                                    # 이미 확정된 레이어는 건너뛴다
        for url in layer["candidates"]:
            reports.append(probe_one(url, key, cfg, year, sido, gugun, layer["id"]))
    return reports


def probe_one(url: str, key: str, cfg: dict, year=None, sido=None, gugun=None,
              layer_id=None) -> dict:
    year = int(year or cfg.get("year") or (now_kst().year - 2))
    sido = str(sido or cfg.get("sido") or "36")
    gugun = str(gugun or cfg.get("gugun") or "110")
    report = {"url": url, "layer": layer_id, "ok": False, "count": 0,
              "sample": None, "error": None}
    try:
        rows = _rows(url, key, year, sido, gugun, 10, cfg.get("extra_params"))
    except CollectError as exc:
        report["error"] = str(exc)
        return report
    report["count"] = len(rows)
    report["ok"] = bool(rows)
    if rows:
        report["sample"] = {k: rows[0].get(k) for k in list(rows[0])[:12]}
    return report

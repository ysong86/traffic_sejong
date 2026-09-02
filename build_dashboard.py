# -*- coding: utf-8 -*-
"""수집 결과(dict) → 단일 HTML 상황판.

외부 자산을 링크하지 않는다. CSS·JS·SVG 를 한 파일에 넣어 어디에 갖다 놔도
그대로 열린다(GitHub Pages, 사내 공유폴더, 이메일 첨부).

화면의 뼈대는 자료의 성질을 따른다. 교통안전 자료는 갱신주기가 제각각이라
한 덩어리로 보여주면 거짓말이 된다. 그래서 세 층으로 갈라 둔다.

  실시간 (5~10분)   돌발상황 · 소통속도 · 노면위험
  연 단위 (1~2년 늦음)  사고다발지 · 사망사고 — '진단'이지 '지금'이 아니다
  정적   (월~연)     보호구역 · 단속카메라 — 배경이자 대조군

세 층을 겹쳐 읽을 때 나오는 것이 정책 지표다. 예: 다발지인데 단속장비가 없다.
"""
from __future__ import annotations

import json
import os
import urllib.parse

import sejong_map
from collectors.common import (BASE_DIR, haversine_km, now_kst, parse_stamp,
                               stamp, to_float)

OUT_PATH = os.path.join(BASE_DIR, "dashboard.html")

# 사고 레이어 색 — 화면 어디서나 같은 뜻으로 쓴다.
LAYER_COLOR = {
    "lg": "var(--acc-base)",
    "schoolzone": "var(--acc-school)",
    "child": "var(--acc-school)",
    "oldman": "var(--acc-vuln)",
    "pedestrian": "var(--acc-walk)",
    "jaywalk": "var(--acc-walk)",
    "bicycle": "var(--acc-vuln)",
    "motorcycle": "var(--acc-vuln)",
    "freezing": "var(--acc-freeze)",
    "death": "var(--acc-death)",
}
FACILITY_COLOR = {"camera": "var(--fac-camera)", "child_zone": "var(--fac-child)",
                  "elder_zone": "var(--fac-elder)", "crosswalk": "var(--fac-child)",
                  "bike_road": "var(--fac-elder)"}
EVENT_COLOR = {"교통사고": "var(--ev-acc)", "공사": "var(--ev-work)",
               "기상": "var(--ev-weather)", "재난": "var(--ev-acc)",
               "행사": "var(--ev-etc)", "기타": "var(--ev-etc)"}
FLOW_COLOR = {"smooth": "var(--flow-smooth)", "slow": "var(--flow-slow)",
              "delay": "var(--flow-delay)", "jam": "var(--flow-jam)",
              "unknown": "var(--st-unknown)"}
RISK_COLOR = {"none": "var(--st-normal)", "caution": "var(--st-watch)",
              "warn": "var(--st-warning)", "alert": "var(--st-alert)",
              "unknown": "var(--st-unknown)"}
FLOW_LABEL = {"smooth": "원활", "slow": "서행", "delay": "지체", "jam": "정체",
              "unknown": "자료없음"}

ACCENT = "var(--accent)"
NEUTRAL = "var(--st-unknown)"

# 다발지에서 이 거리 안에 단속장비가 없으면 '장비 없는 다발지'로 본다.
CAMERA_RADIUS_KM = 0.30


# --------------------------------------------------------------------------- 유틸

def esc(value) -> str:
    return (str("" if value is None else value).replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def fmt(value, digits=0, unit="", dash="—"):
    number = to_float(value)
    if number is None:
        return dash
    if digits == 0:
        return "%s%s" % (format(int(round(number)), ","), unit)
    return "%s%s" % (format(round(number, digits), ",.%df" % digits), unit)


def hhmm(when) -> str:
    parsed = parse_stamp(when)
    return parsed.strftime("%m-%d %H:%M") if parsed else str(when or "—")


def _pct(part, whole) -> float:
    return (100.0 * part / whole) if whole else 0.0


# --------------------------------------------------------------------------- SVG

def share_bar(parts, width=100) -> str:
    """구성비 한 줄 막대. parts = [(라벨, 값, 색), ...]"""
    total = sum(max(0, p[1]) for p in parts) or 1
    segments, offset = [], 0.0
    for label, value, color in parts:
        w = _pct(max(0, value), total)
        if w <= 0:
            continue
        segments.append('<rect x="%.2f%%" y="0" width="%.2f%%" height="10" '
                        'rx="2" fill="%s"><title>%s %s (%.0f%%)</title></rect>'
                        % (offset, w, color, esc(label), fmt(value), w))
        offset += w
    return ('<svg class="sharebar" viewBox="0 0 100 10" width="%d" height="10" '
            'preserveAspectRatio="none" style="width:100%%;height:10px">%s</svg>'
            % (width, "".join(segments)))


def bar_chart(rows, width=520, height=None, bar=17, gap=7) -> str:
    """가로 막대. rows = [(라벨, 값, 색, 부가설명), ...] — 값 내림차순으로 받는다."""
    rows = [r for r in rows if r[1] is not None]
    if not rows:
        return '<p class="note">표시할 값이 없습니다.</p>'
    top = max(r[1] for r in rows) or 1
    height = height or (len(rows) * (bar + gap) + 6)
    label_w = 128.0
    plot = width - label_w - 46
    body = []
    for i, (label, value, color, note) in enumerate(rows):
        y = i * (bar + gap)
        w = max(1.5, plot * (value / top))
        body.append(
            '<g><text class="bl" x="%.1f" y="%.1f" text-anchor="end">%s</text>'
            '<rect class="bt" x="%.1f" y="%.1f" width="%.1f" height="%d" rx="3" '
            'fill="%s"><title>%s %s</title></rect>'
            '<text class="bv" x="%.1f" y="%.1f">%s</text></g>'
            % (label_w - 8, y + bar * 0.75, esc(label),
               label_w, y, w, bar, color, esc(label), esc(note or fmt(value)),
               label_w + w + 6, y + bar * 0.75, esc(note or fmt(value))))
    return ('<svg class="chart barchart" viewBox="0 0 %d %d" '
            'style="width:100%%;height:auto" role="img">'
            '<style>.barchart .bl{fill:var(--fg-2);font-size:11.5px}'
            '.barchart .bv{fill:var(--muted);font-size:11px;'
            'font-variant-numeric:tabular-nums}</style>%s</svg>'
            % (width, height, "".join(body)))


# --------------------------------------------------------------------------- 집계

def _rings_of_dong(dong):
    return dong.get("rings") or []


def _in_ring(lon, lat, ring) -> bool:
    inside = False
    for i in range(len(ring) - 1):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[i + 1][0], ring[i + 1][1]
        if (y1 > lat) != (y2 > lat):
            cross = x1 + (lat - y1) * (x2 - x1) / ((y2 - y1) or 1e-12)
            if lon < cross:
                inside = not inside
    return inside


def _dong_finder():
    """좌표 → 읍면동 이름. 지도에 쓰는 것과 같은 경계를 쓴다.

    링을 매번 다 훑으면 지점 수 × 면 수 만큼 걸린다. 면마다 사각 경계를 미리
    구해 두고 그 안에 든 것만 실제로 검사한다.
    """
    admin = sejong_map.load_admin() or {}
    boxed = []
    for dong in admin.get("dongs") or []:
        rings = _rings_of_dong(dong)
        if not rings:
            continue
        lons = [p[0] for ring in rings for p in ring]
        lats = [p[1] for ring in rings for p in ring]
        boxed.append((min(lons), min(lats), max(lons), max(lats), dong, rings))

    def find(lat, lon):
        if lat is None or lon is None:
            return None
        for x0, y0, x1, y1, dong, rings in boxed:
            if not (x0 <= lon <= x1 and y0 <= lat <= y1):
                continue
            if any(_in_ring(lon, lat, ring) for ring in rings):
                return dong
        return None

    return find, [row[4] for row in boxed]


def enrich(data: dict) -> None:
    """화면이 바로 쓸 수 있게 파생값을 붙인다. 원자료는 건드리지 않는다.

      - 지점마다 읍면동 이름
      - 읍면동별 집계
      - '단속장비 없는 다발지' 미스매치
    """
    if data.get("_enriched"):
        return
    find, dongs = _dong_finder()

    koroad = data.get("koroad") or {}
    facility = data.get("facility") or {}
    its = data.get("its") or {}

    spots = koroad.get("spots") or []
    items = facility.get("items") or []
    events = [e for e in (its.get("events") or []) if e.get("in_sejong")]

    # 색상환은 지도와 같은 규칙을 쓴다(황금각). 표의 색 점이 지도의 면과 맞아야 한다.
    hues = sejong_map._hue_cycle(len(dongs))
    hue_of = {}
    order = sorted(dongs, key=lambda d: -(d.get("area") or 0))
    for index, dong in enumerate(order):
        hue_of[dong["name"]] = hues[index]

    buckets = {}
    for dong in dongs:
        buckets[dong["name"]] = {
            "name": dong["name"], "kind": dong.get("kind") or "dong",
            "hue": hue_of.get(dong["name"], 0),
            "spots": 0, "accidents": 0, "deaths": 0, "casualties": 0,
            "vuln": 0, "camera": 0, "zone": 0, "events": 0,
        }
    outside = {"name": "경계 밖·미상", "kind": "none", "hue": 0, "spots": 0,
               "accidents": 0, "deaths": 0, "casualties": 0, "vuln": 0,
               "camera": 0, "zone": 0, "events": 0}

    for spot in spots:
        dong = find(spot.get("lat"), spot.get("lon"))
        spot["dong"] = dong["name"] if dong else ""
        row = buckets.get(spot["dong"], outside)
        row["spots"] += 1
        row["accidents"] += spot.get("accidents") or 0
        row["deaths"] += spot.get("deaths") or 0
        row["casualties"] += spot.get("casualties") or 0
        if spot.get("group") == "vuln":
            row["vuln"] += 1

    cameras = []
    for item in items:
        dong = find(item.get("lat"), item.get("lon"))
        item["dong"] = dong["name"] if dong else ""
        row = buckets.get(item["dong"], outside)
        if item.get("layer") == "camera":
            row["camera"] += 1
            cameras.append(item)
        else:
            row["zone"] += 1

    for event in events:
        dong = find(event.get("lat"), event.get("lon"))
        event["dong"] = dong["name"] if dong else ""
        buckets.get(event["dong"], outside)["events"] += 1

    rows = [r for r in buckets.values() if
            r["spots"] or r["camera"] or r["zone"] or r["events"]]
    rows.sort(key=lambda r: (-r["casualties"], -r["accidents"], -r["spots"]))
    if outside["spots"] or outside["camera"] or outside["zone"]:
        rows.append(outside)
    data["dong_rows"] = rows
    data["dong_hues"] = hue_of

    # 미스매치 — 다발지 반경 안에 단속장비가 없는 곳.
    # 정책 제언으로 바로 이어지는 지표라 화면에 따로 뽑는다.
    gaps = []
    for spot in spots:
        lat, lon = spot.get("lat"), spot.get("lon")
        if lat is None or lon is None:
            continue
        near = min((haversine_km(lat, lon, c["lat"], c["lon"]) for c in cameras),
                   default=None)
        spot["camera_km"] = round(near, 2) if near is not None else None
        if cameras and (near is None or near > CAMERA_RADIUS_KM):
            gaps.append(spot)
    gaps.sort(key=lambda s: (-s.get("severity", 0), -s.get("accidents", 0)))
    data["camera_gaps"] = gaps
    data["camera_count"] = len(cameras)
    data["_enriched"] = True


# --------------------------------------------------------------------------- KPI

def summarize(data: dict) -> list:
    koroad = data.get("koroad") or {}
    its = data.get("its") or {}
    facility = data.get("facility") or {}
    kma = data.get("kma") or {}

    spots = koroad.get("spots") or []
    base = [s for s in spots if s.get("layer") == "lg"]
    vuln = [s for s in spots if s.get("group") == "vuln"]
    layers = koroad.get("layers") or []

    # 레이어마다 공표 시점이 다르다. 전체 다발지는 2023년인데 스쿨존은 2024년인
    # 식이다. 가장 최근 연도 하나로 뭉뚱그리면 '2024년 자료'라고 거짓말이 된다.
    # 그래서 지표마다 그 지표가 실제로 쓴 연도를 적는다.
    def _year_of(layer_id):
        row = next((r for r in layers if r.get("id") == layer_id), None)
        return row.get("year") if row else None

    def _year_note(years):
        got = sorted({y for y in years if y})
        if not got:
            return "연도 미상"
        if len(got) == 1:
            return "%d년 기준" % got[0]
        return "%d~%d년 기준" % (got[0], got[-1])

    base_note = _year_note([_year_of("lg")])
    vuln_note = _year_note([r.get("year") for r in layers
                            if r.get("group") == "vuln" and r.get("count")])
    all_note = _year_note([r.get("year") for r in layers if r.get("count")])

    summary = its.get("summary") or {}
    events = summary.get("events")
    accidents_now = summary.get("accidents") or 0
    avg_speed = summary.get("avg_speed")

    risk = kma.get("risk") or {}
    gaps = data.get("camera_gaps") or []
    cameras = data.get("camera_count") or 0

    deaths = sum(s.get("deaths") or 0 for s in spots)

    return [
        {"label": "사고다발지", "value": fmt(len(base), 0, "곳"),
         "sub": base_note + " · 사고 %s건" % fmt(sum(s["accidents"] for s in base)),
         "color": "var(--acc-base)"},
        {"label": "취약계층 다발지", "value": fmt(len(vuln), 0, "곳"),
         "sub": (vuln_note + " · 어린이·노인·보행"),
         "color": "var(--acc-vuln)"},
        {"label": "다발지 사망자", "value": fmt(deaths, 0, "명"),
         "sub": all_note + " · 전 레이어 합",
         "color": "var(--acc-death)"},
        {"label": "지금 돌발상황",
         "value": ("—" if events is None else fmt(events, 0, "건")),
         "sub": ("ITS 미연결" if events is None
                 else ("교통사고 %d건 포함" % accidents_now if accidents_now
                       else "사고 없음")),
         "color": "var(--ev-acc)" if accidents_now else NEUTRAL},
        {"label": "노면위험도", "value": risk.get("label") or "—",
         "sub": (risk.get("reasons") or [risk.get("note") or "기상 미연결"])[0][:34],
         "color": RISK_COLOR.get(risk.get("level"), NEUTRAL)},
        {"label": "장비 없는 다발지",
         "value": (fmt(len(gaps), 0, "곳") if cameras else "—"),
         "sub": ("반경 %dm 내 단속장비 없음" % int(CAMERA_RADIUS_KM * 1000)
                 if cameras else "단속카메라 자료 미연결"),
         "color": "var(--fac-camera)" if cameras else NEUTRAL},
    ]


# --------------------------------------------------------------------------- 지도 점

def _spot_size(spot) -> float:
    """사고 심각도에 따라 마커를 키운다. 면적이 아니라 지름으로 키우면
    큰 값이 과장돼 보이므로 제곱근을 쓴다."""
    severity = spot.get("severity") or 0
    return round(min(13.0, 4.6 + (severity ** 0.5) * 0.95), 2)


def build_points(data: dict) -> list:
    points = []
    koroad = data.get("koroad") or {}

    for index, spot in enumerate(koroad.get("spots") or []):
        color = LAYER_COLOR.get(spot.get("layer"), "var(--acc-base)")
        kind = "death" if spot.get("layer") == "death" else "spot"
        points.append({
            "id": "spot-%d" % index,
            "kind": kind,
            "group": spot.get("layer_label") or "사고다발지",
            "name": spot.get("name") or "이름 미상",
            "lat": spot.get("lat"), "lon": spot.get("lon"),
            "color": color, "size": _spot_size(spot),
            "value": "%s건" % fmt(spot.get("accidents")),
            "sort": -(spot.get("severity") or 0),
            "detail": detail_spot(spot),
        })

    facility = data.get("facility") or {}
    for index, item in enumerate(facility.get("items") or []):
        layer = item.get("layer") or ""
        points.append({
            "id": "fac-%d" % index,
            "kind": "camera" if layer == "camera" else "zone",
            "group": item.get("layer_label") or "시설",
            "name": item.get("name") or "이름 미상",
            "lat": item.get("lat"), "lon": item.get("lon"),
            "color": FACILITY_COLOR.get(layer, "var(--fac-camera)"),
            "size": 5.0,
            "value": (item.get("notes") or [""])[0][:14],
            "sort": 0,
            "detail": detail_facility(item),
        })

    its = data.get("its") or {}
    for index, event in enumerate(its.get("events") or []):
        if not event.get("in_sejong"):
            continue
        points.append({
            "id": "ev-%d" % index,
            "kind": "event",
            "group": "지금 돌발상황",
            "name": (event.get("message") or event.get("detail")
                     or event.get("kind") or "돌발상황")[:34],
            "lat": event.get("lat"), "lon": event.get("lon"),
            "color": EVENT_COLOR.get(event.get("kind"), "var(--ev-etc)"),
            "size": 7.0,
            "value": event.get("kind") or "",
            "sort": -1000,                       # 지금 벌어지는 일이 목록 맨 위
            "detail": detail_event(event),
        })

    points.sort(key=lambda p: (p["sort"], p["name"]))
    return points


# --------------------------------------------------------------------------- 상세

def _dhead(name, tag, color, sub) -> str:
    return ('<div class="dhead"><span class="dn">%s</span>'
            '<span class="dtag" style="--c:%s">%s</span></div>'
            '<div class="dsub">%s</div>' % (esc(name), color, esc(tag), esc(sub)))


def _dcell(key, value, unit="") -> str:
    return ('<div class="dcell"><div class="k">%s</div>'
            '<div class="v">%s<span style="font-size:12px;font-weight:400">%s</span>'
            '</div></div>' % (esc(key), esc(value), esc(unit)))


def detail_spot(spot: dict) -> str:
    color = LAYER_COLOR.get(spot.get("layer"), "var(--acc-base)")
    where = " · ".join(x for x in [spot.get("dong"), spot.get("sido_sgg")] if x)
    year = spot.get("year")
    cells = (_dcell("사고", fmt(spot.get("accidents")), "건")
             + _dcell("사망", fmt(spot.get("deaths")), "명")
             + _dcell("중상", fmt(spot.get("serious")), "명")
             + _dcell("경상", fmt(spot.get("slight")), "명")
             + _dcell("사상자", fmt(spot.get("casualties")), "명"))

    share = share_bar([
        ("사망", spot.get("deaths") or 0, "var(--st-serious)"),
        ("중상", spot.get("serious") or 0, "var(--st-warning)"),
        ("경상", spot.get("slight") or 0, "var(--st-watch)"),
        ("부상신고", spot.get("wounded") or 0, "var(--st-unknown)"),
    ])

    camera = ""
    near = spot.get("camera_km")
    if near is not None:
        if near > CAMERA_RADIUS_KM:
            camera = ('<div class="dnote" style="color:var(--st-warning)">'
                      '가장 가까운 무인단속장비가 <b>%.0fm</b> 떨어져 있습니다 '
                      '(기준 %dm). 장비 배치 검토 대상입니다.</div>'
                      % (near * 1000, int(CAMERA_RADIUS_KM * 1000)))
        else:
            camera = ('<div class="dnote">가장 가까운 무인단속장비 %.0fm.</div>'
                      % (near * 1000))

    return (_dhead(spot.get("name"), spot.get("layer_label") or "사고다발지",
                   color,
                   "%s%s" % (where or "세종특별자치시",
                             " · %d년 자료" % year if year else ""))
            + '<div class="dgrid">%s</div>' % cells
            + '<div class="dnote">피해 정도 구성</div>' + share
            + camera
            + '<div class="dnote">도로교통공단이 1년치 사고를 반경 150m 로 묶어 '
              '고른 지점입니다. <b>연 단위 자료</b>라 지금 상황이 아니라 '
              '누적된 위험을 뜻합니다.</div>')


def detail_facility(item: dict) -> str:
    color = FACILITY_COLOR.get(item.get("layer"), "var(--fac-camera)")
    notes = item.get("notes") or []
    body = ""
    if notes:
        body = ('<div class="dgrid">%s</div>'
                % "".join(_dcell(*(n.split(" ", 1) + [""])[:2]) if " " in n
                          else _dcell("정보", n) for n in notes[:4]))
    addr = item.get("addr") or ""
    return (_dhead(item.get("name"), item.get("layer_label") or "시설", color,
                   " · ".join(x for x in [item.get("dong"), addr] if x)
                   or "세종특별자치시")
            + body
            + '<div class="dnote">공공데이터포털 표준데이터입니다. '
              '갱신이 드물어(월~연 단위) 최근 설치분은 빠져 있을 수 있습니다.</div>')


def detail_event(event: dict) -> str:
    color = EVENT_COLOR.get(event.get("kind"), "var(--ev-etc)")
    lines = []
    if event.get("road"):
        lines.append(_dcell("도로", event["road"]))
    if event.get("blocked"):
        lines.append(_dcell("차단 차로", fmt(event["blocked"]), "개"))
    body = '<div class="dgrid">%s</div>' % "".join(lines) if lines else ""
    span = hhmm(event.get("start"))
    if event.get("end"):
        span += " ~ " + hhmm(event.get("end"))
    return (_dhead(event.get("message") or event.get("detail") or "돌발상황",
                   event.get("kind") or "돌발", color,
                   " · ".join(x for x in [event.get("dong"), span] if x))
            + body
            + ('<div class="dnote">%s</div>' % esc(event.get("detail"))
               if event.get("detail") else "")
            + '<div class="dnote">ITS 국가교통정보센터 실시간 돌발상황입니다. '
              '고속도로·국도 중심이라 시 관리도로는 잡히지 않을 수 있습니다.</div>')


# --------------------------------------------------------------------------- 지도 도구

MAP_LAYERS = [
    ("spot", "사고다발지"), ("death", "사망사고"), ("zone", "보호구역"),
    ("camera", "단속카메라"), ("event", "돌발상황"),
]
ROAD_CHIPS = [("expressway", "고속"), ("brt", "BRT"), ("arterial", "주간선"),
              ("sub", "보조간선"), ("collector", "집산·지선")]


DEFAULT_BASEMAP = {
    "provider": "osm",
    "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    "attribution": "© OpenStreetMap 기여자",
    "max_zoom": 18,
    "label": "배경지도",
}


def basemap_config(site: dict) -> dict:
    """배경지도 설정. url 이 비면 칩 자체가 나오지 않는다(= 바깥 요청 0)."""
    base = (site or {}).get("basemap")
    if base is None:
        return dict(DEFAULT_BASEMAP)
    if base is False or base == {}:
        return {}
    return {**DEFAULT_BASEMAP, **base}


def render_maptools(points: list, site: dict | None = None) -> str:
    """지도 위 도구줄 — 확대 버튼, 겹 토글, 도로 등급 토글, 읍면동·배경지도 표시.

    켠 상태는 브라우저에 기억된다. 매번 같은 겹을 다시 끄지 않아도 되게.
    """
    zoom = ('<div class="zoombtns">'
            '<button type="button" data-zoom="in" title="확대">+</button>'
            '<button type="button" data-zoom="out" title="축소">&#8722;</button>'
            '<button type="button" data-zoom="reset" title="원래대로">초기화</button>'
            '</div>')

    present = {p["kind"] for p in points}
    layer_chips = "".join(
        '<button type="button" class="ft on" data-layer="%s">%s</button>'
        % (key, esc(label)) for key, label in MAP_LAYERS if key in present)
    road_chips = "".join(
        '<button type="button" class="ft on" data-road="%s">%s</button>'
        % (key, esc(label)) for key, label in ROAD_CHIPS)
    extras = ('<button type="button" class="ft on" data-flag="dongname">'
              '읍면동 이름</button>'
              '<button type="button" class="ft" data-flag="adfill" '
              'title="읍면동을 전부 칠해 이웃을 구분합니다. 기본은 경계선만.">'
              '읍면동 채색</button>')
    base = basemap_config(site)
    if base.get("url"):
        # 이 칩을 켜야 타일을 받아온다. 켜기 전에는 바깥으로 요청이 나가지 않는다.
        extras += ('<button type="button" class="ft" data-flag="basemap" '
                   'title="배경에 실제 지도를 깝니다. 켜면 타일 서버로 요청이 '
                   '나갑니다(오프라인에서는 빈 배경).">%s</button>'
                   % esc(base.get("label") or "배경지도"))

    blocks = [zoom]
    if layer_chips:
        blocks.append('<div class="mtgroup"><span class="mt-label">겹</span>%s</div>'
                      % layer_chips)
    blocks.append('<div class="mtgroup"><span class="mt-label">도로</span>%s</div>'
                  % road_chips)
    blocks.append('<div class="mtgroup"><span class="mt-label">표시</span>%s</div>'
                  % extras)
    return '<div class="maptools">%s</div>' % "".join(blocks)


ZOOM_JS = r"""
(function(){
  var svg=document.querySelector('.map'); if(!svg) return;
  var g=svg.querySelector('.zoom'); if(!g) return;
  var vb=(svg.getAttribute('viewBox')||'0 0 560 620').split(/\s+/).map(Number);
  var W=vb[2], H=vb[3], MINK=1, MAXK=16;
  var SMALL_LABEL_ZOOM=2.2;
  var k=1, tx=0, ty=0, drag=null, moved=0;

  function clamp(){ k=Math.min(MAXK,Math.max(MINK,k));
    tx=Math.min(0,Math.max(W*(1-k),tx)); ty=Math.min(0,Math.max(H*(1-k),ty)); }

  // 축척 — 확대 배율에 맞춰 '깔끔한 거리'(1/2/5 x 10^n)를 골라 막대 길이를 맞춘다.
  var sb = svg.querySelector('.scalebar');
  var sbBar = sb && sb.querySelector('.sb-bar');
  var sbTick2 = sb && sb.querySelector('.sb-tick2');
  var sbLabel = sb && sb.querySelector('.sb-label');
  var MPU = sb ? parseFloat(sb.dataset.mpu) : 0;
  var SB_MAX = 140;

  function updateScale(){
    if(!sb || !MPU) return;
    var perUnit = MPU / k;
    var best = 1;
    for(var e=0; e<8; e++){
      for(var i=0; i<3; i++){
        var m = [1,2,5][i] * Math.pow(10, e);
        if(m / perUnit <= SB_MAX) best = m;
      }
    }
    var w = best / perUnit;
    var x0 = parseFloat(sb.dataset.x);
    sbBar.setAttribute('width', w.toFixed(1));
    sbTick2.setAttribute('x', (x0 + w - 1.6).toFixed(1));
    sbLabel.textContent = best >= 1000 ? (best/1000) + ' km' : best + ' m';
  }

  // 확대 보정. 선에는 non-scaling-stroke 가 걸려 있어 화면상 굵기가 고정이고,
  // 여기서 배율에 따라 아주 조금만 더한다(k^0.22, 최대 1.5배). 예전에 0.42 제곱에
  // 최대 2.8 이었는데 여전히 두꺼웠다 — 좁은 구역을 크게 볼 때 주인공은 그 안의
  // 사고지점과 배경지도이지 우리가 덧그린 도로선이 아니다.
  // 굵기를 줄이는 것만으로는 부족해서 색도 함께 뺀다(--zo).
  function updateWidths(){
    svg.style.setProperty('--zw', Math.min(1.5, Math.pow(k, 0.22)).toFixed(3));
    // 얼마나 뺄지는 배경지도가 켜져 있는지에 달렸다. 배경지도가 있으면 우리 도로선은
    // 실제 길 위에 겹친 참고선이라 과감히 빼도 되지만, 없으면 그게 유일한 기준이라
    // 같은 만큼 빼면 화면이 텅 빈다.
    var step = baseOn ? 0.15 : 0.085, floor = baseOn ? 0.42 : 0.66;
    var fade = 1 - step * (Math.log(Math.max(1, k)) / Math.LN2);   // 배율 2배마다 step
    svg.style.setProperty('--zo', Math.max(floor, fade).toFixed(3));
  }

  function apply(){ clamp();
    g.setAttribute('transform','translate('+tx.toFixed(2)+','+ty.toFixed(2)+') scale('+k.toFixed(4)+')');
    var inv=(1/k).toFixed(4);
    svg.querySelectorAll('.cs').forEach(function(e){
      e.setAttribute('transform','translate('+e.dataset.x+','+e.dataset.y+') scale('+inv+')'); });
    svg.classList.toggle('zoomed', k>1.01);
    // 작은 신도시 동의 이름은 충분히 확대했을 때만 띄운다.
    svg.classList.toggle('zoomed-in', k>=SMALL_LABEL_ZOOM);
    updateWidths(); updateScale(); scheduleBase(); }

  function toSvg(evt){ var m=svg.getScreenCTM(); if(!m) return null; m=m.inverse();
    return {x:evt.clientX*m.a+evt.clientY*m.c+m.e, y:evt.clientX*m.b+evt.clientY*m.d+m.f}; }
  function zoomAt(px,py,factor){ var nk=Math.min(MAXK,Math.max(MINK,k*factor));
    if(nk===k) return; tx=px-(px-tx)*(nk/k); ty=py-(py-ty)*(nk/k); k=nk; apply(); }

  svg.addEventListener('wheel', function(e){ e.preventDefault();
    var p=toSvg(e); if(!p) return; zoomAt(p.x,p.y,Math.exp(-e.deltaY*0.0016)); },
    {passive:false});
  svg.addEventListener('dblclick', function(e){ var p=toSvg(e); if(p) zoomAt(p.x,p.y,1.7); });

  // 포인터 캡처는 '실제로 끌기 시작한 뒤'에만 건다. pointerdown 에서 바로 잡으면
  // 클릭이 마커가 아니라 SVG 로 가버려서 지점 선택이 먹지 않는다.
  svg.addEventListener('pointerdown', function(e){
    if(e.button!==0) return;
    drag={x:e.clientX,y:e.clientY,tx:tx,ty:ty,captured:false}; moved=0; });
  svg.addEventListener('pointermove', function(e){ if(!drag) return;
    var rect=svg.getBoundingClientRect(); var per=W/(rect.width||1);
    var dx=(e.clientX-drag.x), dy=(e.clientY-drag.y);
    moved=Math.max(moved,Math.abs(dx)+Math.abs(dy));
    if(moved<=4) return;
    if(!drag.captured){
      drag.captured=true;
      try{ svg.setPointerCapture(e.pointerId); }catch(_){}
    }
    tx=drag.tx+dx*per; ty=drag.ty+dy*per; apply(); });
  function endDrag(e){ if(!drag) return;
    if(drag.captured){ try{ svg.releasePointerCapture(e.pointerId); }catch(_){} }
    drag=null; }
  svg.addEventListener('pointerup', endDrag);
  svg.addEventListener('pointercancel', endDrag);
  svg.addEventListener('click', function(e){ if(moved>6){ e.stopPropagation(); moved=0; } }, true);

  document.querySelectorAll('.zoombtns button').forEach(function(b){
    b.addEventListener('click', function(){
      var mode=b.dataset.zoom;
      if(mode==='reset'){ k=1; tx=0; ty=0; apply(); return; }
      zoomAt(W/2, H/2, mode==='in'?1.5:1/1.5); }); });

  // ------------------------------------------------------------ 배경지도
  // SVG 안에 슬리피 지도를 얹는다. 타일은 칩을 켜야 받아온다 — 끄고 있으면
  // 바깥으로 요청이 한 번도 나가지 않는다(오프라인·폐쇄망에서도 나머지는 그대로).
  //
  // 타일은 Web Mercator, 이 지도는 등장방형이라 좌표계가 다르다. 그래도 타일마다
  // 제 모서리를 이 투영으로 옮겨 놓으면 한 장 안에서 생기는 어긋남이 3m 남짓이라
  // 눈에 보이지 않는다. 투영 자체를 바꾸는 것보다 안전하다.
  var BASEMAP = window.__STBASE || {};
  var baseLayer = svg.querySelector('.basemap');
  var LON0=+svg.dataset.lon0, LAT1=+svg.dataset.lat1, KX=+svg.dataset.kx,
      PSCALE=+svg.dataset.scale, OFFX=+svg.dataset.offx, OFFY=+svg.dataset.offy;
  var tiles = new Map(), baseOn = false, baseTimer = null;

  function pxLon(lon){ return OFFX + (lon-LON0)*KX*PSCALE; }
  function pxLat(lat){ return OFFY + (LAT1-lat)*PSCALE; }
  function lonAt(x){ return LON0 + (x-OFFX)/(KX*PSCALE); }
  function latAt(y){ return LAT1 - (y-OFFY)/PSCALE; }
  function lon2t(lon,z){ return (lon+180)/360*Math.pow(2,z); }
  function lat2t(lat,z){ var r=lat*Math.PI/180;
    return (1-Math.log(Math.tan(r)+1/Math.cos(r))/Math.PI)/2*Math.pow(2,z); }
  function t2lon(x,z){ return x/Math.pow(2,z)*360-180; }
  function t2lat(y,z){ var n=Math.PI-2*Math.PI*y/Math.pow(2,z);
    return 180/Math.PI*Math.atan(0.5*(Math.exp(n)-Math.exp(-n))); }

  function clearTiles(){
    tiles.forEach(function(el){ el.remove(); });
    tiles.clear();
  }

  function drawBase(){
    if(!baseOn || !BASEMAP.url || !baseLayer) return;
    var rect = svg.getBoundingClientRect();

    // 지도 칸이 좁다고 타일 레벨을 떨어뜨리면 안 된다. 폭에 그대로 맞추면
    // 좁은 화면에서 z=12 같은 광역 레벨이 잡히는데, 그 축척의 타일에는 녹지와
    // 고속도로밖에 없어 배경이 텅 빈 것처럼 보인다. viewBox 를 바닥으로 삼고,
    // 실제로 더 크게 그려질 때만 더 선명한 레벨을 쓴다.
    var ratio = Math.max(1, (rect.width || W) / W);

    // 타일 한 장(256px)이 화면에서도 대략 256px 이 되는 레벨을 고른다.
    var z = Math.round(Math.log(360 * KX * PSCALE * k * ratio / 256) / Math.LN2);
    z = Math.max(9, Math.min(BASEMAP.max_zoom || 18, z));

    var lonMin=lonAt((0-tx)/k), lonMax=lonAt((W-tx)/k);
    var latMax=latAt((0-ty)/k), latMin=latAt((H-ty)/k);

    var x0,x1,y0,y1;
    for(;;){
      x0=Math.floor(lon2t(lonMin,z)); x1=Math.floor(lon2t(lonMax,z));
      y0=Math.floor(lat2t(latMax,z)); y1=Math.floor(lat2t(latMin,z));
      // 한 번에 너무 많이 받지 않는다. 넘치면 한 단계 물러선다.
      if((x1-x0+1)*(y1-y0+1) <= 240 || z <= 9) break;
      z--;
    }

    var want = {}, n = Math.pow(2,z);
    for(var ix=x0; ix<=x1; ix++){
      for(var iy=y0; iy<=y1; iy++){
        if(ix<0||iy<0||ix>=n||iy>=n) continue;
        var key = z+'/'+ix+'/'+iy;
        want[key] = 1;
        if(tiles.has(key)) continue;
        var ax=pxLon(t2lon(ix,z)),   ay=pxLat(t2lat(iy,z));
        var bx=pxLon(t2lon(ix+1,z)), by=pxLat(t2lat(iy+1,z));
        var img=document.createElementNS('http://www.w3.org/2000/svg','image');
        img.setAttribute('x', ax.toFixed(2));
        img.setAttribute('y', ay.toFixed(2));
        // 0.6 단위씩 겹쳐 둔다. 딱 맞추면 타일 사이에 실금이 보인다.
        img.setAttribute('width', (bx-ax+0.6).toFixed(2));
        img.setAttribute('height', (by-ay+0.6).toFixed(2));
        img.setAttribute('preserveAspectRatio','none');
        var url = String(BASEMAP.url).replace('{z}',z).replace('{x}',ix)
                    .replace('{y}',iy).replace('{s}','abc'[(ix+iy)%3]);
        img.setAttribute('href', url);
        img.setAttributeNS('http://www.w3.org/1999/xlink','xlink:href', url);
        baseLayer.appendChild(img);
        tiles.set(key, img);
      }
    }
    tiles.forEach(function(el,key){
      if(!want[key]){ el.remove(); tiles.delete(key); }
    });
  }

  function scheduleBase(){
    if(!baseOn) return;
    clearTimeout(baseTimer);
    baseTimer = setTimeout(drawBase, 130);      // 끄는 중에 수십 번 부르지 않게
  }

  var credit = svg.querySelector('.basemap-credit');
  if(credit && BASEMAP.attribution) credit.textContent = '배경지도 ' + BASEMAP.attribution;

  // 겹·도로·표시 토글. 켠 상태를 기억한다.
  var KEY='st-map', saved={};
  try{ saved=JSON.parse(localStorage.getItem(KEY)||'{}'); }catch(_){}
  function save(){ try{ localStorage.setItem(KEY, JSON.stringify(saved)); }catch(_){} }

  function bind(attr){
    document.querySelectorAll('.ft['+attr+']').forEach(function(b){
      var id=b.getAttribute(attr), name=attr+':'+id;
      var on = saved[name] !== false;
      b.classList.toggle('on', on);
      svg.classList.toggle('hide-'+id, !on);
      b.addEventListener('click', function(){
        var next = !b.classList.contains('on');
        b.classList.toggle('on', next);
        svg.classList.toggle('hide-'+id, !next);
        saved[name]=next; save();
      });
    });
  }
  bind('data-layer');
  bind('data-road');

  // 표시 칩. dongname 은 기본 켜짐(끄면 hide-), adfill 은 기본 꺼짐(켜면 show-).
  // 읍면동을 전부 칠하는 건 이웃 구분이 필요할 때 잠깐 쓰는 것이라 기본이 아니다.
  var FLAGS = {dongname: {cls:'hide-dongname', on:true, invert:true},
               adfill:   {cls:'show-ad',       on:false, invert:false},
               basemap:  {cls:'has-base',      on:false, invert:false}};
  document.querySelectorAll('.ft[data-flag]').forEach(function(b){
    var spec = FLAGS[b.dataset.flag]; if(!spec) return;
    var name='flag:'+b.dataset.flag;
    var on = (saved[name] === undefined) ? spec.on : !!saved[name];
    function paint(state){
      b.classList.toggle('on', state);
      svg.classList.toggle(spec.cls, spec.invert ? !state : state);
      if(b.dataset.flag === 'basemap'){
        baseOn = state;
        updateWidths();                 // 뺄 양이 배경지도 유무에 따라 달라진다
        if(state) drawBase(); else clearTiles();
      }
    }
    paint(on);
    b.addEventListener('click', function(){
      var next = !b.classList.contains('on');
      paint(next);
      saved[name]=next; save();
    });
  });

  // 읍면동을 누르면 그 면만 색이 들어오고, 아래 표의 같은 행도 함께 켜진다.
  var dongLayer = svg.querySelector('.dongs');
  function highlight(name){
    svg.querySelectorAll('.ad').forEach(function(a){
      var on = !!name && a.dataset.dong===name;
      a.classList.toggle('on', on);
      // 이웃 면이 나중에 그려지면 고른 면의 경계선을 덮는다. 맨 앞으로 옮긴다.
      if(on && dongLayer && a.nextElementSibling) dongLayer.appendChild(a);
    });
    svg.querySelectorAll('.dongname text').forEach(function(t){
      t.classList.toggle('on', !!name && t.dataset.dong===name); });
    document.querySelectorAll('tr[data-dong]').forEach(function(tr){
      tr.classList.toggle('on', !!name && tr.dataset.dong===name); });
  }
  svg.querySelectorAll('.ad').forEach(function(a){
    a.addEventListener('click', function(e){
      e.stopPropagation();
      highlight(a.classList.contains('on') ? null : a.dataset.dong); });
    a.addEventListener('keydown', function(e){
      if(e.key==='Enter'||e.key===' '){ e.preventDefault();
        highlight(a.classList.contains('on') ? null : a.dataset.dong); } });
  });
  document.querySelectorAll('tr[data-dong]').forEach(function(tr){
    tr.addEventListener('click', function(){
      highlight(tr.classList.contains('on') ? null : tr.dataset.dong); });
  });

  apply();
})();
"""


DOT_CLASS = {"spot": "dot", "death": "dot star", "camera": "dot sq",
             "zone": "dot dia", "event": "dot tri", "cctv": "dot sq"}


def render_explorer(data: dict) -> str:
    points = build_points(data)
    site = data.get("site") or {}
    # 배경지도 설정은 JS 가 읽는다. 여기서 한 번만 심는다.
    base_js = ('<script>window.__STBASE=%s;</script>'
               % json.dumps(basemap_config(site), ensure_ascii=False))
    if not points:
        # 지점이 없어도 읍면동 경계와 도로망은 보여준다. 지도까지 사라지면
        # 화면이 통째로 비어 무엇이 잘못됐는지 알 수 없다.
        return ('<div class="explorer nodata" data-view="explorer">'
                '<section class="panel mapwrap"><h2>세종시 지도'
                '<span class="src">읍면동 경계 · 도로 간·지선</span></h2>%s%s'
                '<p class="note" style="margin:11px 0 0">표시할 지점이 없습니다. '
                'API 인증키를 넣으면 사고다발지·보호구역·단속카메라·돌발상황이 '
                '이 지도에 표시됩니다.</p></section></div>%s<script>%s</script>'
                % (render_maptools([], site), sejong_map.render([]),
                   base_js, ZOOM_JS))

    first_id = points[0]["id"]
    groups = []
    for point in points:
        if point["group"] not in groups:
            groups.append(point["group"])

    listing = []
    for group in groups:
        members = [p for p in points if p["group"] == group]
        rows = "".join(
            '<button class="pick" data-id="%s" type="button">'
            '<span class="%s" style="background:%s"></span>'
            '<span class="nm">%s</span><span class="vv small">%s</span></button>'
            % (point["id"], DOT_CLASS.get(point["kind"], "dot"), point["color"],
               esc(point["name"]), esc(point["value"])) for point in members)
        opened = any(p["id"] == first_id for p in members)
        listing.append(
            '<div class="grp%s" data-grp="%s">'
            '<button class="grphead" type="button" aria-expanded="%s">'
            '<span class="tw"></span><span class="gn">%s</span>'
            '<span class="gc">%d</span></button>'
            '<div class="grpbody">%s</div></div>'
            % (" open" if opened else "", esc(group), "true" if opened else "false",
               esc(group), len(members), rows))

    details = {p["id"]: p["detail"] for p in points}
    payload = json.dumps(details, ensure_ascii=False).replace("</", "<\\/")

    return ('<div class="explorer" data-view="explorer">'
            '<section class="panel side"><h2>지점</h2>'
            '<p class="note">클릭하면 지도와 오른쪽 상세가 함께 바뀝니다.</p>%s</section>'
            '<section class="panel mapwrap"><h2>세종시 지도'
            '<span class="src">휠 확대 · 끌어서 이동 · 도로·읍면동에 커서</span></h2>'
            '%s%s</section>'
            '<section class="panel detail" id="detail"></section>'
            '</div>'
            '<script>(function(){var D=%s;'
            'var first=%s;'
            'function sel(id){if(!D[id])return;'
            'document.getElementById("detail").innerHTML=D[id];'
            'document.querySelectorAll(".pick").forEach(function(b){'
            'var on=b.dataset.id===id;b.classList.toggle("sel",on);'
            'if(on){var g=b.closest(".grp");'
            'if(g&&!g.classList.contains("open")){g.classList.add("open");'
            'g.querySelector(".grphead").setAttribute("aria-expanded","true");}}});'
            'document.querySelectorAll(".map .mk").forEach(function(m){'
            'm.classList.toggle("sel",m.dataset.id===id)});}'
            'document.querySelectorAll(".pick").forEach(function(b){'
            'b.addEventListener("click",function(){sel(b.dataset.id)})});'
            'document.querySelectorAll(".map .mk").forEach(function(m){'
            'm.addEventListener("click",function(e){e.stopPropagation();sel(m.dataset.id)});'
            'm.addEventListener("keydown",function(e){'
            'if(e.key==="Enter"||e.key===" "){e.preventDefault();sel(m.dataset.id)}})});'
            'document.querySelectorAll(".grphead").forEach(function(h){'
            'h.addEventListener("click",function(){'
            'var g=h.parentElement;var open=g.classList.toggle("open");'
            'h.setAttribute("aria-expanded",String(open));'
            'try{var k="st-groups";var st=JSON.parse(localStorage.getItem(k)||"{}");'
            'st[g.dataset.grp]=open;localStorage.setItem(k,JSON.stringify(st));}catch(e){}'
            '})});'
            'try{var st=JSON.parse(localStorage.getItem("st-groups")||"{}");'
            'document.querySelectorAll(".grp").forEach(function(g){'
            'if(st[g.dataset.grp]===undefined)return;'
            'g.classList.toggle("open",!!st[g.dataset.grp]);'
            'g.querySelector(".grphead").setAttribute("aria-expanded",String(!!st[g.dataset.grp]));'
            '});}catch(e){}'
            'sel(first);})();</script>%s<script>%s</script>'
            % ("".join(listing), render_maptools(points, site),
               sejong_map.render(points), payload,
               json.dumps(first_id), base_js, ZOOM_JS))


# --------------------------------------------------------------------------- 표·패널

def render_layers(data: dict) -> str:
    """유형별 사고다발지 요약 — 기본계획 취약계층 지표와 바로 맞물린다."""
    koroad = data.get("koroad") or {}
    layers = [row for row in (koroad.get("layers") or []) if row.get("count")]
    if not layers:
        pending = koroad.get("pending") or []
        note = ("아직 연결되지 않은 레이어: " + ", ".join(pending)) if pending else ""
        return ('<p class="note">사고다발지 자료가 없습니다. %s</p>' % esc(note))

    rows = "".join(
        '<tr><td><span class="adchip" style="--h:0;background:%s;border-color:%s">'
        '</span>%s</td><td class="num">%s</td><td class="num">%s</td>'
        '<td class="num%s">%s</td><td class="num">%s</td><td class="num">%s</td></tr>'
        % (LAYER_COLOR.get(row["id"], "var(--acc-base)"),
           LAYER_COLOR.get(row["id"], "var(--acc-base)"),
           esc(row["label"]), fmt(row["count"]), fmt(row["accidents"]),
           " bad" if row.get("deaths") else "", fmt(row.get("deaths")),
           fmt(row.get("casualties")),
           esc(str(row.get("year") or "—")))
        for row in sorted(layers, key=lambda r: -r["accidents"]))

    chart = bar_chart([
        (row["label"], row["accidents"],
         LAYER_COLOR.get(row["id"], "var(--acc-base)"),
         "%s건 / %s곳" % (fmt(row["accidents"]), fmt(row["count"])))
        for row in sorted(layers, key=lambda r: -r["accidents"])])

    pending = koroad.get("pending") or []
    tail = ""
    if pending:
        tail = ('<p class="note" style="margin-top:11px">아직 요청주소를 확정하지 '
                '못한 레이어: <b>%s</b>. <code>python run.py --probe --only koroad</code> '
                '로 확인한 뒤 <code>config.json</code> 의 '
                '<code>koroad.endpoints</code> 에 넣으면 함께 표시됩니다.</p>'
                % esc(", ".join(pending)))

    return ('%s<div class="scrollx" style="margin-top:14px"><table class="tt">'
            '<thead><tr><th>유형</th><th>지점</th><th>사고</th><th>사망</th>'
            '<th>사상자</th><th>기준연도</th></tr></thead><tbody>%s</tbody></table>'
            '</div>%s' % (chart, rows, tail))


def render_dongs(data: dict) -> str:
    """읍면동별 집계 — 지도의 면 색과 표의 색 점이 같다. 행을 누르면 지도가 켜진다."""
    rows = data.get("dong_rows") or []
    if not rows:
        return '<p class="note">읍면동에 배정할 지점이 없습니다.</p>'

    kind_label = {"eup": "읍", "myeon": "면", "dong": "동", "none": ""}
    body = "".join(
        '<tr data-dong="%s"><td><span class="adchip" style="--h:%d"></span>%s'
        '<span class="adkind">%s</span></td>'
        '<td class="num">%s</td><td class="num">%s</td>'
        '<td class="num%s">%s</td><td class="num">%s</td>'
        '<td class="num">%s</td><td class="num">%s</td>'
        '<td class="num%s">%s</td></tr>'
        % (esc(row["name"]), row["hue"], esc(row["name"]),
           kind_label.get(row["kind"], ""),
           fmt(row["spots"]), fmt(row["accidents"]),
           " bad" if row["deaths"] else "", fmt(row["deaths"]),
           fmt(row["casualties"]), fmt(row["vuln"]),
           fmt(row["camera"]),
           " warn" if (row["spots"] and not row["camera"]) else "",
           fmt(row["zone"]))
        for row in rows)

    return ('<div class="scrollx"><table class="tt">'
            '<thead><tr><th>읍면동</th><th>다발지</th><th>사고</th><th>사망</th>'
            '<th>사상자</th><th>취약계층<br>다발지</th><th>단속<br>카메라</th>'
            '<th>보호<br>구역</th></tr></thead><tbody>%s</tbody></table></div>'
            '<p class="note" style="margin-top:11px">행을 누르면 지도에서 그 '
            '읍면동이 도드라집니다. 색 점은 지도의 면 색과 같습니다.</p>' % body)


def render_flow(data: dict) -> str:
    """실시간 소통 — 느린 구간부터. 상황판에서 먼저 봐야 하는 쪽이 위다."""
    its = data.get("its") or {}
    flow = its.get("flow") or []
    if not flow:
        return ('<p class="note">소통정보가 없습니다. ITS 인증키가 없거나, '
                '세종시 관리도로가 ITS 표준링크에 포함되지 않았을 수 있습니다.</p>')

    top = max((r["speed"] for r in flow), default=1) or 1
    rows = "".join(
        '<div class="flowrow" style="--c:%s"><span class="rn" title="%s">%s</span>'
        '<span class="flowbar"><i style="width:%.1f%%"></i></span>'
        '<span class="sv">%s</span></div>'
        % (FLOW_COLOR.get(row["grade"], NEUTRAL), esc(row["road"]),
           esc(row["road"]), max(3.0, 100.0 * row["speed"] / top),
           fmt(row["speed"], 0, " km/h"))
        for row in flow[:16])

    summary = its.get("summary") or {}
    head = ('<p class="note">링크 %s개 · 평균 %s · 지체·정체 %s개 구간</p>'
            % (fmt(summary.get("links")), fmt(summary.get("avg_speed"), 1, " km/h"),
               fmt(summary.get("jam"))))
    legend = " · ".join("%s %s" % (FLOW_LABEL[k], v) for k, v in
                        [("smooth", "50↑"), ("slow", "30~50"),
                         ("delay", "15~30"), ("jam", "15↓")])
    return ('%s%s<p class="note" style="margin-top:11px">등급 기준(km/h) — %s. '
            '도로 등급을 구분하지 않은 보수적 기준입니다.</p>'
            % (head, rows, esc(legend)))


def render_events(data: dict) -> str:
    its = data.get("its") or {}
    events = [e for e in (its.get("events") or []) if e.get("in_sejong")]
    if not events:
        if its.get("errors"):
            return '<p class="note">돌발상황을 받지 못했습니다. 아래 수집 경고를 보십시오.</p>'
        return '<p class="note">현재 세종시 범위에 등록된 돌발상황이 없습니다.</p>'

    items = "".join(
        '<li style="--c:%s"><span class="evkind">%s</span>'
        '<span class="evmsg">%s</span><span class="evtime">%s</span>'
        '%s</li>'
        % (EVENT_COLOR.get(event.get("kind"), "var(--ev-etc)"),
           esc(event.get("kind") or "기타"),
           esc(event.get("message") or event.get("detail") or "내용 없음"),
           esc(hhmm(event.get("start"))),
           ('<span class="evsub">%s</span>'
            % esc(" · ".join(x for x in [event.get("dong"), event.get("road"),
                                         ("%d개 차로 차단" % event["blocked"])
                                         if event.get("blocked") else ""] if x)))
           if (event.get("dong") or event.get("road") or event.get("blocked"))
           else "")
        for event in events[:14])
    return '<ul class="evlist">%s</ul>' % items


def render_risk(data: dict) -> str:
    kma = data.get("kma") or {}
    risk = kma.get("risk") or {}
    now = kma.get("now") or {}
    level = risk.get("level") or "unknown"

    badge = ('<span class="riskbadge" style="--c:%s">노면위험 %s</span>'
             % (RISK_COLOR.get(level, NEUTRAL), esc(risk.get("label") or "자료없음")))

    cells = ""
    if now:
        cells = ('<div class="dgrid">%s%s%s%s</div>'
                 % (_dcell("기온", fmt(now.get("temp"), 1), "℃"),
                    _dcell("시간강수", fmt(now.get("rain_1h"), 1), "mm"),
                    _dcell("습도", fmt(now.get("humidity"), 0), "%"),
                    _dcell("풍속", fmt(now.get("wind"), 1), "m/s")))

    reasons = risk.get("reasons") or []
    why = ('<ul class="risk-why">%s</ul>'
           % "".join("<li>%s</li>" % esc(r) for r in reasons)) if reasons else ""

    ahead = ('<p class="note" style="margin-top:9px">예보 — %s</p>'
             % esc(risk.get("ahead"))) if risk.get("ahead") else ""

    warnings = kma.get("warnings") or []
    warn = ""
    if warnings:
        warn = ('<p class="note" style="margin-top:9px"><b>기상특보</b> — %s</p>'
                % esc(" / ".join(w.get("title") or "" for w in warnings[:3])))

    base = (now or {}).get("base") or ""
    return ('%s%s%s%s%s<p class="note" style="margin-top:11px">%s%s</p>'
            % (badge, cells, why, ahead, warn,
               esc(risk.get("note") or ""),
               (" 관측 %s." % esc(base)) if base else ""))


def render_mismatch(data: dict) -> str:
    """단속장비 없는 다발지 — 세 층을 겹쳐야 나오는 지표라 따로 뽑는다."""
    gaps = data.get("camera_gaps") or []
    cameras = data.get("camera_count") or 0
    if not cameras:
        return ('<p class="note">무인교통단속카메라 표준데이터가 연결되지 않아 '
                '대조할 수 없습니다. <code>config.json</code> 의 '
                '<code>facility.layers</code> 에 <code>camera</code> 가 있고 '
                '포털 인증키가 유효한지 확인하십시오.</p>')
    if not gaps:
        return ('<p class="note">모든 사고다발지 반경 %dm 안에 무인단속장비가 '
                '있습니다.</p>' % int(CAMERA_RADIUS_KM * 1000))

    rows = "".join(
        '<tr><td>%s<span class="adkind">%s</span></td>'
        '<td class="num">%s</td><td class="num">%s</td>'
        '<td class="num%s">%s</td><td class="num warn">%s</td></tr>'
        % (esc(spot.get("name")), esc(spot.get("dong") or ""),
           fmt(spot.get("accidents")), fmt(spot.get("casualties")),
           " bad" if spot.get("deaths") else "", fmt(spot.get("deaths")),
           ("%.0f m" % (spot["camera_km"] * 1000)) if spot.get("camera_km")
           is not None else "없음")
        for spot in gaps[:15])

    return ('<div class="scrollx"><table class="tt">'
            '<thead><tr><th>지점</th><th>사고</th><th>사상자</th><th>사망</th>'
            '<th>최근접 장비</th></tr></thead><tbody>%s</tbody></table></div>'
            '<p class="note" style="margin-top:11px">사고다발지 %s곳 가운데 '
            '<b>%s곳</b>이 반경 %dm 안에 무인단속장비가 없습니다. '
            '단속장비가 유일한 해법은 아니지만, 장비·시설 배치를 다시 볼 '
            '지점을 좁히는 데 씁니다.</p>'
            % (rows, fmt(len((data.get("koroad") or {}).get("spots") or [])),
               fmt(len(gaps)), int(CAMERA_RADIUS_KM * 1000)))


def render_facility(data: dict) -> str:
    facility = data.get("facility") or {}
    layers = facility.get("layers") or []
    if not layers:
        pending = facility.get("pending") or []
        return ('<p class="note">시설 자료가 없습니다.%s</p>'
                % (" 미확정: " + esc(", ".join(pending)) if pending else ""))
    rows = "".join(
        '<tr><td><span class="adchip" style="--h:0;background:%s;border-color:%s">'
        '</span>%s</td><td class="num">%s</td><td class="num">%s</td></tr>'
        % (FACILITY_COLOR.get(row["id"], "var(--fac-camera)"),
           FACILITY_COLOR.get(row["id"], "var(--fac-camera)"),
           esc(row["label"]), fmt(row["count"]), fmt(row.get("raw")))
        for row in layers)
    pending = facility.get("pending") or []
    tail = ""
    if pending:
        tail = ('<p class="note" style="margin-top:11px">요청주소 미확정: <b>%s</b>. '
                '<code>python run.py --probe --only facility</code> 로 확인하십시오.</p>'
                % esc(", ".join(pending)))
    return ('<div class="scrollx"><table class="tt">'
            '<thead><tr><th>시설</th><th>세종 시내</th><th>응답 행</th></tr></thead>'
            '<tbody>%s</tbody></table></div>%s' % (rows, tail))


# --------------------------------------------------------------------------- 신선도

# 층 — 갱신주기가 다른 자료를 한 줄에 늘어놓으면 거짓말이 된다.
#   cadence 는 원 제공주기(분), stale 은 이 값을 넘으면 낡았다고 표시할 기준(분).
TIERS = [
    ("실시간", [
        ("events", "돌발상황", 5, 30),
        ("flow", "소통속도", 5, 30),
        ("weather", "기상실황", 60, 180),
    ]),
    ("연 단위", [
        ("accident", "사고다발지", 365 * 1440, None),
    ]),
    ("정적", [
        ("facility", "보호구역·장비", 30 * 1440, None),
    ]),
]


def _age_text(when) -> tuple:
    """(표시문자열, 경과분). 경과분이 None 이면 시각을 알 수 없다는 뜻."""
    parsed = parse_stamp(when)
    if not parsed:
        return "—", None
    minutes = (now_kst() - parsed).total_seconds() / 60.0
    if minutes < 0:
        minutes = 0.0
    if minutes < 90:
        text = "%d분 전" % int(minutes)
    elif minutes < 60 * 48:
        text = "%d시간 전" % int(minutes / 60)
    elif minutes < 1440 * 60:
        text = "%d일 전" % int(minutes / 1440)
    elif minutes < 1440 * 365:
        # 다섯 달을 "0.5년 전"이라 쓰면 읽는 사람이 한 번 더 계산해야 한다.
        text = "%d개월 전" % max(2, int(minutes / (1440 * 30.4)))
    else:
        text = "%.1f년 전" % (minutes / (1440 * 365))
    return text, minutes


def freshness(data: dict) -> list:
    its = data.get("its") or {}
    kma = data.get("kma") or {}
    koroad = data.get("koroad") or {}
    facility = data.get("facility") or {}

    events = [e for e in (its.get("events") or []) if e.get("in_sejong")]
    flow = its.get("flow") or []

    # 사고다발지는 레이어마다 공표 연도가 다르다. 화면에는 가장 **오래된** 쪽을
    # 기준으로 잡는다 — "2024년 자료"라고 적어 놓고 그중 하나가 2023년이면
    # 그 지표는 한 해 낡은 것이다. 신선도는 가장 약한 고리로 말해야 정직하다.
    acc_years = sorted({r["year"] for r in (koroad.get("layers") or [])
                        if r.get("year") and r.get("count")})
    if acc_years:
        acc_text = ("%d년 기준" % acc_years[0] if len(acc_years) == 1
                    else "%d~%d년 기준" % (acc_years[0], acc_years[-1]))
        acc_stamp = "%d-12-31 00:00" % acc_years[0]
    else:
        acc_text, acc_stamp = "—", ""

    # 시설은 우리가 언제 받아왔는지가 아니라 자료가 밝히는 **기준일자**를 쓴다.
    # 월~연 단위로 갱신되는 자료를 수집 시각으로 적으면 방금 갱신된 것처럼 읽힌다.
    fac_ref = (facility.get("ref_date") or "").strip()

    stamps = {
        "events": (max((e.get("start") or "" for e in events), default="")
                   or (its.get("collected_at") if events else "")),
        "flow": (max((r.get("time") or "" for r in flow), default="")
                 or (its.get("collected_at") if flow else "")),
        "weather": (kma.get("now") or {}).get("base") or "",
        "accident": acc_stamp,
        "facility": fac_ref,
    }
    texts = {
        "events": ("%d건" % len(events)) if events else ("없음" if its.get("flow")
                                                         or not its.get("errors")
                                                         else "—"),
        "flow": ("%s개 링크" % fmt(len(flow))) if flow else "—",
        "weather": (fmt((kma.get("now") or {}).get("temp"), 1, "℃")
                    if kma.get("now") else "—"),
        "accident": acc_text,
        "facility": (("%s개소" % fmt(len(facility.get("items") or [])))
                     if facility.get("items") else "—"),
    }

    out = []
    for tier, rows in TIERS:
        for key, label, cadence, stale in rows:
            age, minutes = _age_text(stamps.get(key))
            state = ""
            if stale and minutes is not None:
                if minutes > stale * 3:
                    state = "dead"
                elif minutes > stale:
                    state = "stale"
            color = {"dead": "var(--st-alert)", "stale": "var(--st-warning)"}.get(
                state, "var(--st-normal)" if minutes is not None else NEUTRAL)
            out.append({"tier": tier, "key": key, "label": label,
                        "text": texts.get(key) or "—", "age": age,
                        "cadence": cadence, "state": state, "color": color})
    return out


def _cadence_text(minutes) -> str:
    if not minutes:
        return ""
    if minutes < 60:
        return "제공주기 %d분" % minutes
    if minutes < 1440:
        return "제공주기 %d시간" % (minutes // 60)
    if minutes < 1440 * 300:
        return "제공주기 %d일" % (minutes // 1440)
    return "제공주기 연 1회"


def render_freshness(data: dict) -> str:
    rows = freshness(data)
    chunks, seen = [], None
    for row in rows:
        # 시설의 '언제'는 우리가 받은 시각이 아니라 자료의 기준일자다. 그렇게 밝힌다.
        if row["key"] == "facility" and row["age"] != "—":
            row["age"] = "기준일 " + row["age"]
        if row["tier"] != seen:
            seen = row["tier"]
            chunks.append('<span class="tier">%s</span>' % esc(seen))
        chunks.append(
            '<div class="fr %s" style="--c:%s" title="%s"><span class="l">%s</span>'
            '<span class="t">%s</span><span class="a">%s</span></div>'
            % (row["state"], row["color"], esc(_cadence_text(row["cadence"])),
               esc(row["label"]), esc(row["text"]), esc(row["age"])))
    return ('<div class="freshbar" data-view="fresh">'
            '<span class="fresh-title">자료 시점</span>%s'
            '<span class="fresh-note">층마다 갱신주기가 다릅니다. '
            '돌발·소통은 5분, 기상실황은 1시간 주기입니다. '
            '사고다발지는 <b>연 단위 통계</b>로 공표가 1~2년 늦으므로 '
            '"지금"이 아니라 누적된 위험으로 읽으십시오.</span></div>'
            % "".join(chunks))


# --------------------------------------------------------------------------- 화면 뼈대

VIEW_SECTIONS = [
    ("kpi", "요약 지표"),
    ("fresh", "자료 시점"),
    ("alerts", "지금 이슈"),
    ("explorer", "지도 탐색"),
    ("dongs", "읍면동 집계"),
    ("layers", "유형별 다발지"),
    ("flow", "실시간 소통"),
    ("risk", "노면위험"),
    ("mismatch", "장비 미스매치"),
    ("facility", "시설 현황"),
]

VIEW_JS = r"""
(function(){
  var KEY='st-views';
  var saved={};
  try{ saved=JSON.parse(localStorage.getItem(KEY)||'{}'); }catch(e){}

  function setOn(id,on){
    document.querySelectorAll('[data-view="'+id+'"]').forEach(function(el){
      el.style.display = on ? '' : 'none'; });
    document.querySelectorAll('.vw[data-view-toggle="'+id+'"]').forEach(function(b){
      b.classList.toggle('on', on);
      b.setAttribute('aria-pressed', String(on)); });
  }
  document.querySelectorAll('.vw').forEach(function(b){
    var id=b.dataset.viewToggle;
    var on = saved[id] !== false;          // 저장값이 없으면 켜둔다
    setOn(id, on);
    b.addEventListener('click', function(){
      var next = !b.classList.contains('on');
      setOn(id, next);
      saved[id]=next;
      try{ localStorage.setItem(KEY, JSON.stringify(saved)); }catch(e){}
      window.dispatchEvent(new Event('resize'));
    });
  });
})();
"""

AUTOREFRESH_JS = r"""
(function(){
  var MIN = %d;
  if (!MIN) return;
  var el = document.querySelector('header.top .sub');
  var current = el ? el.textContent.trim() : '';

  // 통째로 새로고침하지 않고, 갱신 시각이 바뀐 것을 확인했을 때만 다시 읽는다.
  // GitHub Pages 가 max-age=600 을 보내므로 확인은 no-store, 재적재는 새 시각을
  // 질의문자열에 실어 캐시를 확실히 비켜간다.
  function check(){
    if (document.hidden) return;
    fetch(location.pathname + '?t=' + Date.now(), {cache: 'no-store'})
      .then(function(r){ return r.ok ? r.text() : null; })
      .then(function(html){
        if (!html) return;
        var m = html.match(/<span class="sub">([^<]*)<\/span>/);
        if (m && m[1].trim() && m[1].trim() !== current) {
          location.replace(location.pathname + '?v=' + encodeURIComponent(m[1].trim()));
        }
      })
      .catch(function(){});
  }
  setInterval(check, MIN * 60000);
  document.addEventListener('visibilitychange', function(){
    if (!document.hidden) check();          // 탭으로 돌아오면 바로 확인
  });
})();
"""

THEME_BOOT = ("<script>(function(){try{var t=localStorage.getItem('st-theme');"
              "document.documentElement.setAttribute('data-theme',"
              "t==='dark'?'dark':'light');}catch(e){}})();</script>")

THEME_TOGGLE = ('<div class="theme-toggle" role="group" aria-label="화면 테마">'
                '<button type="button" data-set-theme="light" aria-pressed="true">'
                '라이트</button>'
                '<button type="button" data-set-theme="dark" aria-pressed="false">'
                '다크</button></div>')

# 시스템이 다크여도 자동으로 어두워지지 않는다. 기본은 라이트, 선택만 기억한다.
THEME_JS = r"""
(function(){
  var root=document.documentElement;
  function apply(t){
    root.setAttribute('data-theme', t);
    document.querySelectorAll('[data-set-theme]').forEach(function(b){
      b.setAttribute('aria-pressed', String(b.dataset.setTheme===t)); });
    try{ localStorage.setItem('st-theme', t); }catch(e){}
  }
  document.querySelectorAll('[data-set-theme]').forEach(function(b){
    b.addEventListener('click', function(){ apply(b.dataset.setTheme); }); });
  apply(root.getAttribute('data-theme')==='dark' ? 'dark' : 'light');
})();
"""

HITS_JS = r"""
(function(){
  var img=document.querySelector('.hitsbadge'); if(!img) return;
  // 집계 서버가 죽거나 폐쇄망이면 깨진 그림 아이콘이 남는다.
  // 조회수는 있으면 좋은 것이지 화면의 본론이 아니므로 조용히 접는다.
  img.addEventListener('error', function(){
    var box = img.parentElement;
    if (box) box.style.display = 'none';
  });
})();
"""

COUNTER_JS = r"""
(function(){
  var box=document.getElementById('visitors'); if(!box) return;
  var cfg=JSON.parse(box.dataset.counter||'{}');
  var today=document.getElementById('cnt-today'), total=document.getElementById('cnt-total');
  function put(el,v){ if(el) el.textContent = (v===null||v===undefined) ? '—'
      : Number(v).toLocaleString('ko-KR'); }
  function num(x){ if(x===null||x===undefined) return null;
    if(typeof x==='object') x = x.count!==undefined ? x.count : x.total;
    var n=parseInt(String(x).replace(/[^0-9]/g,''),10); return isNaN(n)?null:n; }
  function get(url){
    var ctrl = (typeof AbortController!=='undefined') ? new AbortController() : null;
    if(ctrl) setTimeout(function(){ try{ctrl.abort();}catch(e){} }, 6000);
    return fetch(url,{mode:'cors', signal: ctrl?ctrl.signal:undefined})
      .then(function(r){ if(!r.ok) throw 0; return r.json(); }); }

  if(cfg.provider==='goatcounter' && cfg.code){
    var base='https://'+cfg.code+'.goatcounter.com/counter/'+encodeURIComponent(cfg.path||'/')+'.json';
    get(base).then(function(d){ put(total,num(d)); }).catch(function(){ put(total,null); });
    get(base+'?start=today').then(function(d){ put(today,num(d)); })
      .catch(function(){ put(today,null); });
  } else if(cfg.provider==='custom' && cfg.url){
    get(cfg.url).then(function(d){ put(today,num(d.today)); put(total,num(d.total)); })
      .catch(function(){ put(today,null); put(total,null); });
  }
})();
"""

CSS_FILE = os.path.join(BASE_DIR, "assets", "theme.css")

# 본문 서체. CDN 이 막힌 망에서는 조용히 시스템 서체로 떨어진다.
FONT_LINK = ('<link rel="preconnect" href="https://cdn.jsdelivr.net">'
             '<link rel="stylesheet" as="style" crossorigin '
             'href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/'
             'dist/web/variable/pretendardvariable-dynamic-subset.min.css">')

FALLBACK_CSS = """
body{font-family:system-ui,'Malgun Gothic',sans-serif;background:#f4f7fb;color:#0e2038}
.wrap{max-width:1200px;margin:0 auto;padding:24px}
.panel{background:#fff;border:1px solid #dbe4ee;border-radius:12px;padding:16px;margin:12px 0}
"""


def load_css() -> str:
    try:
        with open(CSS_FILE, "r", encoding="utf-8") as fp:
            return fp.read()
    except OSError:
        # 테마 파일이 없어도 읽을 수는 있게 최소한만 깔아 준다.
        return FALLBACK_CSS


def render_viewbar() -> str:
    chips = "".join(
        '<button type="button" class="vw on" data-view-toggle="%s" '
        'aria-pressed="true">%s</button>' % (key, esc(label))
        for key, label in VIEW_SECTIONS)
    return '<div class="viewbar"><span class="vw-label">보기</span>%s</div>' % chips


DEFAULT_CONTACT = {
    "org": "세종연구원 도시안전연구센터",
    "members": ["안용준 센터장", "송양호 책임연구위원",
                "주재성 전문연구위원", "최유라 전문연구위원"],
    "email": "ayj826@sri.re.kr",
    "role": "제작",
}


def render_contact(site: dict) -> str:
    """제작 기관·참여자와 대표 문의처.

    기관 한 줄, 참여자 한 줄, 문의 한 줄로 나눈다. 넷을 기관명 뒤에 이어 붙이면
    한 줄이 화면을 넘어가고 누가 기관이고 누가 사람인지 읽히지 않는다.
    `site.contact` 로 덮어쓸 수 있고, 옛 설정의 name/title 도 참여자로 받아준다.
    """
    contact = {**DEFAULT_CONTACT, **((site or {}).get("contact") or {})}
    org = (contact.get("org") or "").strip()

    members = [str(m).strip() for m in (contact.get("members") or []) if str(m).strip()]
    single = " ".join(x for x in [contact.get("name"), contact.get("title")] if x).strip()
    if single and single not in members:
        members.append(single)

    if not org and not members and not contact.get("email"):
        return ""

    lines = []
    if org:
        lines.append('<div class="made"><span class="k">%s</span>%s</div>'
                     % (esc(contact.get("role") or "제작"), esc(org)))
    if members:
        # 기관이 없으면 참여자 줄이 제작 줄을 대신한다.
        if org:
            lines.append('<div class="members">%s</div>'
                         % esc(" · ".join(members)))
        else:
            lines.append('<div class="made"><span class="k">%s</span>%s</div>'
                         % (esc(contact.get("role") or "제작"),
                            esc(" · ".join(members))))
    if contact.get("email"):
        lines.append('<div class="ask"><span class="k">문의</span>'
                     '<a href="mailto:%s">%s</a> 로 연락 주시기 바랍니다.</div>'
                     % (esc(contact["email"]), esc(contact["email"])))
    return '<div class="contact">%s</div>' % "".join(lines)


def render_counter(site: dict) -> str:
    """하단 조회수. 정적 페이지는 스스로 셀 수 없어 세어 주는 곳이 필요하다."""
    counter = (site or {}).get("counter") or {}
    provider = counter.get("provider", "none")
    if provider in ("", "none"):
        return ""
    label = counter.get("label") or "조회수"

    if provider == "hits":
        target = (counter.get("target") or "").strip()
        if not target:
            return ""
        src = ("https://hits.sh/%s.svg?view=today-total&style=flat-square"
               "&label=%s&color=0ea5e9&labelColor=64748b"
               % (urllib.parse.quote(target, safe="/"), urllib.parse.quote(label)))
        # loading="lazy" 를 쓰면 안 된다. 이 배지는 3,600px 짜리 페이지 맨 아래에
        # 있어서, 스크롤이 닿기 전에는 요청조차 나가지 않는다. 그 상태로 화면을
        # 갈무리하거나 통째로 렌더하는 뷰어에서는 '깨진 그림'으로 보인다.
        # 600바이트짜리 SVG 하나라 미룰 이유도 없다.
        return ('<div class="visitors"><img class="hitsbadge" src="%s" '
                'alt="%s 오늘/전체" height="20" decoding="async">'
                '<span class="vsub">오늘 / 전체</span></div><script>%s</script>'
                % (esc(src), esc(label), HITS_JS))

    payload = json.dumps({k: v for k, v in counter.items() if k != "provider"}
                         | {"provider": provider}, ensure_ascii=False)
    return ('<div class="visitors" id="visitors" data-counter=%s>'
            '<span class="vk">%s</span>'
            '<span>오늘</span><b id="cnt-today">…</b>'
            '<span>누적</span><b id="cnt-total">…</b></div>'
            '<script>%s</script>'
            % (json.dumps(payload), esc(label), COUNTER_JS))


def has_any_data(data: dict) -> bool:
    """어느 소스든 실제 값이 하나라도 들어왔는가."""
    return bool(((data.get("koroad") or {}).get("spots") or [])
                or ((data.get("its") or {}).get("flow") or [])
                or ((data.get("its") or {}).get("events") or [])
                or ((data.get("facility") or {}).get("items") or [])
                or ((data.get("kma") or {}).get("now")))


def render_errors(data: dict) -> str:
    lines = []
    for key, label in (("koroad", "도로교통공단"), ("its", "ITS 국가교통정보센터"),
                       ("facility", "표준데이터"), ("kma", "기상청")):
        for message in ((data.get(key) or {}).get("errors") or []):
            lines.append("<li><b>%s</b> — %s</li>" % (esc(label), esc(message)))
    if not lines:
        return ""
    return ('<section class="panel" data-view="errors"><h2>수집 경고</h2>'
            '<p class="note">아래 항목은 이번 수집에서 받아오지 못했습니다. '
            '나머지 화면은 정상입니다.</p>'
            '<ul style="margin:0;padding-left:18px;font-size:12.5px;'
            'color:var(--fg-2)">%s</ul></section>' % "".join(lines))


def render_sources(data: dict) -> str:
    """어떤 주소에서 받아온 값인지. 공개 화면에서는 기본으로 감춘다."""
    if not ((data.get("site") or {}).get("show_endpoints")):
        return ""
    lines = []
    for row in ((data.get("koroad") or {}).get("layers") or []):
        if row.get("endpoint"):
            lines.append("<li>%s — <code>%s</code></li>"
                         % (esc(row["label"]), esc(row["endpoint"])))
    for row in ((data.get("facility") or {}).get("layers") or []):
        if row.get("endpoint"):
            lines.append("<li>%s — <code>%s</code></li>"
                         % (esc(row["label"]), esc(row["endpoint"])))
    if not lines:
        return ""
    return ('<details class="sources"><summary>사용한 API 주소</summary>'
            '<ul>%s</ul></details>' % "".join(lines))


# --------------------------------------------------------------------------- 지금 이슈

def render_alerts(data: dict) -> str:
    """화면 맨 위에 올릴 '지금'만. 연 단위 통계는 여기 오지 않는다."""
    blocks = []

    its = data.get("its") or {}
    events = [e for e in (its.get("events") or []) if e.get("in_sejong")]
    urgent = [e for e in events if e.get("kind") in ("교통사고", "재난")]
    if urgent:
        items = "".join(
            "<li><b>%s</b> %s <span style=\"opacity:.72\">%s</span></li>"
            % (esc(event.get("kind")),
               esc(event.get("message") or event.get("detail") or ""),
               esc(hhmm(event.get("start")))) for event in urgent[:6])
        blocks.append('<div class="alerts warn"><h3>진행 중인 사고·재난 %d건</h3>'
                      '<ul style="margin:0;padding-left:18px">%s</ul></div>'
                      % (len(urgent), items))

    risk = (data.get("kma") or {}).get("risk") or {}
    if risk.get("level") in ("warn", "alert"):
        items = "".join("<li>%s</li>" % esc(r) for r in (risk.get("reasons") or [])[:4])
        blocks.append('<div class="alerts warn"><h3>노면위험 %s</h3>'
                      '<ul style="margin:0;padding-left:18px">%s</ul></div>'
                      % (esc(risk.get("label")), items))

    warnings = (data.get("kma") or {}).get("warnings") or []
    if warnings:
        items = "".join('<li>%s <span style="opacity:.7">(%s)</span></li>'
                        % (esc(w.get("title")), esc(w.get("time")))
                        for w in warnings[:5])
        blocks.append('<div class="alerts"><h3>기상특보</h3>'
                      '<ul style="margin:0;padding-left:18px">%s</ul></div>' % items)

    jam = [r for r in (its.get("flow") or []) if r.get("grade") == "jam"]
    if jam:
        items = "".join("<li>%s <b>%s</b></li>"
                        % (esc(r["road"]), fmt(r["speed"], 0, " km/h"))
                        for r in jam[:5])
        blocks.append('<div class="alerts"><h3>정체 구간 %d곳 '
                      '<span style="font-weight:400;font-size:11px">15km/h 미만'
                      '</span></h3><ul style="margin:0;padding-left:18px">%s</ul>'
                      '</div>' % (len(jam), items))

    if not blocks:
        return ""
    return '<div data-view="alerts">%s</div>' % "".join(blocks)


# --------------------------------------------------------------------------- 렌더

def render(data: dict) -> str:
    enrich(data)
    generated = data.get("generated_at") or stamp()
    demo = bool(data.get("demo"))

    kpis = "".join(
        '<div class="kpi" style="--c:%s"><div class="l">%s</div>'
        '<div class="v">%s</div><div class="s">%s</div></div>'
        % (k["color"], esc(k["label"]), esc(k["value"]), esc(k["sub"]))
        for k in summarize(data))

    if demo:
        banner = '<span class="badge demo">샘플 데이터</span>'
    elif has_any_data(data):
        banner = '<span class="badge live">실측 연동</span>'
    else:
        # 키가 없거나 전 소스가 실패한 상태. "실측 연동"이라고 쓰면 거짓말이 된다.
        banner = '<span class="badge demo">자료 없음</span>'

    # 샘플로 공개할 때 가장 먼저 읽혀야 하는 문구. 화면 맨 위, 굵게.
    # site.notice 로 문구를 바꿀 수 있다(실측 연동이 끝나면 배너 자체가 사라진다).
    site_cfg = data.get("site") or {}
    notice = (site_cfg.get("notice")
              or "이 화면의 수치는 실제 통계·관측값이 아닙니다. "
                 "샘플 데이터에 해당하며, 현재 실시간 자료를 연동하는 과정입니다.")

    note = ""
    if demo:
        note = ('<div class="alerts warn">'
                '<div class="notice">%s</div>'
                '<div class="sub">지도의 읍면동 경계·도로망과 지점 좌표는 실제 '
                '자료이며, 사고건수·소통속도·기상값만 예시입니다.</div>'
                '</div>' % esc(notice))
    elif not has_any_data(data):
        note = ('<div class="alerts warn"><h3>아직 수집된 자료가 없습니다</h3>'
                '<div>API 인증키가 설정되지 않았거나 모든 소스가 실패했습니다. '
                '아래 <b>수집 경고</b>에 소스별 사유가 적혀 있습니다. '
                '<code>config.json</code> 의 <code>koroad.key</code>·'
                '<code>facility.key</code>·<code>kma.key</code>(공공데이터포털 '
                '공통)와 <code>its.key</code>(ITS 별도 발급)를 확인하십시오.'
                '</div></div>')

    year = (data.get("koroad") or {}).get("year")
    year_note = ("도로교통공단 %d년 기준" % year) if year else "도로교통공단"

    return """<!doctype html>
<html lang="ko" data-theme="light"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>세종시 교통안전 상황판</title>
%s
<style>%s</style>%s</head><body><div class="wrap">
<header class="top">
  <h1>세종시 교통안전 상황판</h1>
  %s
  <span class="grow"></span>
  <span class="sub">갱신 %s</span>
  %s
</header>
%s
%s
%s
<div class="kpis" data-view="kpi">%s</div>
%s
%s
<div class="grid">
  <section class="panel" data-view="dongs"><h2>읍면동별 집계
    <span class="src">%s</span><span class="cad year">연 단위 · 정적</span></h2>
    <p class="note">사고다발지·시설을 읍면동 경계로 나눠 센 값입니다.</p>
    %s</section>
  <section class="panel" data-view="layers"><h2>유형별 사고다발지
    <span class="src">도로교통공단</span><span class="cad year">연 1회 · 공표 1~2년 지연</span></h2>
    <p class="note">연 단위 통계입니다. 취약계층 유형이 기본계획 지표와 맞물립니다.</p>
    %s</section>
  <section class="panel" data-view="flow"><h2>실시간 소통
    <span class="src">ITS 국가교통정보센터</span><span class="cad live">실시간 · 5분</span></h2>
    %s</section>
  <section class="panel" data-view="risk"><h2>노면위험
    <span class="src">기상청 실황·예보에서 산출</span><span class="cad live">실시간 · 1시간</span></h2>
    %s</section>
  <section class="panel" data-view="mismatch"><h2>단속장비 없는 사고다발지
    <span class="src">다발지 × 무인단속카메라</span><span class="cad year">연 단위 × 정적</span></h2>
    <p class="note">연 단위 사고자료와 정적 시설자료를 겹쳐 만든 지표입니다.</p>
    %s</section>
  <section class="panel" data-view="facility"><h2>안전시설 현황
    <span class="src">공공데이터포털 표준데이터</span><span class="cad static">정적 · 월~연 갱신</span></h2>
    %s</section>
</div>
%s
<footer>
  출처 — 도로교통공단 교통사고 다발지역·사망사고 정보(연 단위),
  ITS 국가교통정보센터 소통·돌발상황(실시간),
  공공데이터포털 표준데이터(무인교통단속카메라·보호구역),
  기상청 단기예보 조회서비스(실황·예보).<br>
  지도의 읍면동 경계·도로망·지점은 모두 실제 좌표입니다.
  경계와 도로망 © OpenStreetMap 기여자 (ODbL).<br>
  사고다발지는 <b>1년치 사고를 반경 150m 로 묶어</b> 고른 지점이며 공표가 1~2년
  늦습니다. 노면위험도는 기온·강수·습도에서 추정한 참고값으로 노면 온도 실측이
  아닙니다. 실제 교통통제·대응 판단은 관계기관 공식 발표를 따르십시오.<br>
  마지막 갱신 %s · 세종특별자치시 교통안전 상황판%s
  %s
  %s
</footer>
</div><script>%s</script></body></html>""" % (
        THEME_BOOT, load_css(), FONT_LINK, banner, esc(generated), THEME_TOGGLE,
        note, render_alerts(data), render_viewbar(), kpis,
        render_freshness(data),
        render_explorer(data),
        esc(year_note), render_dongs(data),
        render_layers(data),
        render_flow(data),
        render_risk(data),
        render_mismatch(data),
        render_facility(data),
        render_errors(data),
        esc(generated), render_sources(data),
        render_contact(data.get("site")), render_counter(data.get("site")),
        THEME_JS + VIEW_JS
        + (AUTOREFRESH_JS % int((data.get("site") or {}).get("refresh_minutes", 5))))


def write(data: dict, path: str = OUT_PATH) -> str:
    data.setdefault("generated_at", stamp(now_kst()))
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(render(data))
    return path

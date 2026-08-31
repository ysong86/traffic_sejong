# -*- coding: utf-8 -*-
"""세종시 읍면동 경계 + 도로 간·지선 + 사고다발지·시설·돌발 마커 SVG.

겹 구성 — 아래에서 위로
  1. 읍면동 면           assets/sejong_admin.json   (읍/면/동을 색으로 구분, 경계선 뚜렷하게)
  2. 도로망             assets/sejong_roads.json   (tools/make_roads.py, OSM)
  3. 시 외곽선
  4. 읍면동 이름         (작은 신도시 동은 확대해야 뜬다 — 안 그러면 서로 겹친다)
  5. 지점 마커           사고다발지 · 보호구역 · 단속카메라 · 돌발상황

확대/이동을 위해 1~5 는 `<g class="zoom">` 안에 넣는다. 글자와 마커는 class="cs"
(counter-scale) 를 달아 두어, JS 가 배율의 역수를 걸어 크기를 유지한다.
선 굵기는 vector-effect="non-scaling-stroke" 로 고정한다.

물환경 상황판의 같은 모듈에서 갈라져 나왔다. 다른 점은 두 가지다.
  - 하천 대신 도로. 등급이 다섯이라 굵기·색을 더 벌렸다.
  - 읍면동을 '배경'이 아니라 '읽는 대상'으로 올렸다. 면마다 색이 다르고
    경계선이 굵으며, 호버하면 그 면만 도드라진다.
"""
from __future__ import annotations

import json
import math
import os

from collectors.common import BASE_DIR

ADMIN_FILE = os.path.join(BASE_DIR, "assets", "sejong_admin.json")
ROADS_FILE = os.path.join(BASE_DIR, "assets", "sejong_roads.json")

# 도로 등급별 표현. w=기본 굵기, hover=호버 굵기, label=이 크기 이상이면 이름을 붙인다.
#
# 굵기는 등급을 읽을 수 있을 만큼만 벌린다. 처음엔 고속도로를 4.4 로 잡았는데
# 화면에서 도로가 도시를 덮어 버렸다. 이 지도의 주인공은 사고지점과 읍면동이고
# 도로는 그것을 어디에 놓을지 알려주는 뼈대다.
ROAD_STYLE = {
    "expressway": {"w": 2.4, "hover": 4.2, "opacity": 0.92, "label": 13.0,
                   "name": "고속·자동차전용"},
    "brt":        {"w": 2.1, "hover": 3.8, "opacity": 0.95, "label": 12.5,
                   "name": "BRT 축"},
    "arterial":   {"w": 1.6, "hover": 3.2, "opacity": 0.88, "label": 12.0,
                   "name": "주간선"},
    # 보조간선 아래로는 이름을 상시로 달지 않는다. 신도시 구간에 이름이 열 개씩
    # 겹쳐 도로도 지점도 안 보였다. 커서를 올리면 여전히 뜬다.
    "sub":        {"w": 1.0, "hover": 2.4, "opacity": 0.78, "label": 0,
                   "name": "보조간선"},
    "collector":  {"w": 0.6, "hover": 1.8, "opacity": 0.55, "label": 0,
                   "name": "집산·지선"},
}

# 이보다 짧은 도로(도, ≈1.1km)에는 상시 이름을 붙이지 않는다.
# 짧은 조각에 이름이 붙으면 실제 축을 가린다.
LABEL_MIN_LEN = 0.010
ROAD_ORDER = ["collector", "sub", "arterial", "brt", "expressway"]   # 그리는 순서
HIT_WIDTH = 11.0        # 투명 히트영역 굵기(기준 폭 560 대비). 얇은 지선도 잡히게.

# 마커 모양 — 종류를 색이 아니라 형태로도 갈라 둔다(색약 대응).
KIND_SHAPE = {"spot": "circle", "death": "star", "camera": "square",
              "zone": "diamond", "event": "triangle", "cctv": "square"}

# 읍면동 이름을 상시 표시할 최소 면적(도²).
# 신도시 행정동은 너무 작아 겹치므로 확대했을 때만 띄운다.
LABEL_ALWAYS_AREA = 0.0012
# 확대 배율이 이 값을 넘으면 작은 동의 이름도 띄운다(JS 가 판단).
SMALL_LABEL_ZOOM = 2.2


def _kind_of(name: str) -> str:
    """읍 / 면 / 동 구분. 세종은 1읍 9면 + 동지역 구성이다."""
    text = (name or "").strip()
    if text.endswith("읍"):
        return "eup"
    if text.endswith("면"):
        return "myeon"
    return "dong"


KIND_LABEL = {"eup": "읍", "myeon": "면", "dong": "동"}


# --------------------------------------------------------------------------- 자산

def _load(path, key):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fp:
            payload = json.load(fp)
    except (ValueError, OSError):
        return None
    return payload if payload.get(key) is not None else None


def load_admin():
    admin = _load(ADMIN_FILE, "dongs")
    if admin and not (admin.get("outline") or admin.get("dongs")):
        return None
    return admin


def load_roads():
    payload = _load(ROADS_FILE, "roads")
    return (payload or {}).get("roads") or []


# --------------------------------------------------------------------------- 투영

class Projection:
    """등장방형 + 위도 보정. 시 하나 크기에서는 왜곡이 눈에 띄지 않는다."""

    def __init__(self, lon0, lat0, lon1, lat1, width, height, pad=16):
        self.lon0, self.lon1 = lon0, lon1
        self.lat0, self.lat1 = lat0, lat1
        self.k = math.cos(math.radians((lat0 + lat1) / 2))

        span_x = (lon1 - lon0) * self.k or 1e-6
        span_y = (lat1 - lat0) or 1e-6
        self.scale = min((width - pad * 2) / span_x, (height - pad * 2) / span_y)
        self.off_x = (width - span_x * self.scale) / 2
        self.off_y = (height - span_y * self.scale) / 2

    def __call__(self, lon, lat):
        return (self.off_x + (lon - self.lon0) * self.k * self.scale,
                self.off_y + (self.lat1 - lat) * self.scale)

    def inside(self, lon, lat, slack=0.03):
        return (self.lon0 - slack <= lon <= self.lon1 + slack
                and self.lat0 - slack <= lat <= self.lat1 + slack)


def _bbox(admin, points):
    coords = [p for ring in (admin or {}).get("outline") or [] for p in ring]
    if not coords:
        coords = [p for dong in (admin or {}).get("dongs") or []
                  for ring in dong["rings"] for p in ring]
    if not coords:
        coords = [(p["lon"], p["lat"]) for p in points
                  if p.get("lon") is not None and p.get("lat") is not None]
    if not coords:
        return 127.13, 36.40, 127.41, 36.74
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return min(lons), min(lats), max(lons), max(lats)


def _path(projection, ring, close=True):
    parts = []
    for i, (lon, lat) in enumerate(ring):
        x, y = projection(lon, lat)
        parts.append("%s%.1f,%.1f" % ("M" if i == 0 else "L", x, y))
    if close:
        parts.append("Z")
    return "".join(parts)


def _in_rings(lon, lat, rings) -> bool:
    """레이 캐스팅. 시 경계 밖에 도로 이름이 떠 있는 걸 막는 데 쓴다."""
    inside = False
    for ring in rings:
        for i in range(len(ring) - 1):
            x1, y1 = ring[i][0], ring[i][1]
            x2, y2 = ring[i + 1][0], ring[i + 1][1]
            if (y1 > lat) != (y2 > lat):
                cross = x1 + (lat - y1) * (x2 - x1) / ((y2 - y1) or 1e-12)
                if lon < cross:
                    inside = not inside
    return inside


def _shape(kind, color, size):
    """원점(0,0) 기준 마커. 위치는 바깥 <g> 의 transform 이 잡는다(확대 시 역보정)."""
    if kind == "triangle":
        return ('<polygon points="0,%.1f %.1f,%.1f %.1f,%.1f" style="fill:%s" '
                'stroke-width="1"/>'
                % (-size * 1.15, -size, size * 0.75, size, size * 0.75, color))
    if kind == "square":
        return ('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="1.5" '
                'style="fill:%s" stroke-width="1"/>'
                % (-size * 0.8, -size * 0.8, size * 1.6, size * 1.6, color))
    if kind == "diamond":
        return ('<polygon points="0,%.1f %.1f,0 0,%.1f %.1f,0" style="fill:%s" '
                'stroke-width="1"/>' % (-size, size, size, -size, color))
    if kind == "star":
        pts = []
        for i in range(10):
            r = size * (1.25 if i % 2 == 0 else 0.52)
            a = math.radians(-90 + i * 36)
            pts.append("%.1f,%.1f" % (r * math.cos(a), r * math.sin(a)))
        return ('<polygon points="%s" style="fill:%s" stroke-width="1"/>'
                % (" ".join(pts), color))
    return ('<circle cx="0" cy="0" r="%.1f" style="fill:%s" stroke-width="1"/>'
            % (size, color))


def _cs_text(x, y, text, cls="cs", extra=""):
    """확대해도 크기가 유지되는 글자 (JS 가 scale(1/k) 을 덧붙인다)."""
    return ('<text class="%s" data-x="%.1f" data-y="%.1f" '
            'transform="translate(%.1f,%.1f)"%s>%s</text>'
            % (cls, x, y, x, y, extra, text))


def _esc(text) -> str:
    return (str(text or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# --------------------------------------------------------------------------- 렌더

def render(points, width=560, height=None, show_roads=True) -> str:
    admin = load_admin()
    lon0, lat0, lon1, lat1 = _bbox(admin, points)
    if height is None:
        # 자료 종횡비에 맞춰 높이를 잡는다. 고정하면 좌우에 빈 띠가 남는다.
        k = math.cos(math.radians((lat0 + lat1) / 2))
        ratio = (lat1 - lat0) / max((lon1 - lon0) * k, 1e-6)
        height = int(round(width * ratio)) + 42      # 하단 주석 줄 여유
    projection = Projection(lon0, lat0, lon1, lat1, width, height - 42, pad=16)
    scale = width / 560.0
    outline = (admin or {}).get("outline") or []

    defs, clip_ref = "", ""
    if outline:
        defs = ('<defs><clipPath id="cityclip">%s</clipPath></defs>'
                % "".join('<path d="%s"/>' % _path(projection, r) for r in outline))
        clip_ref = ' clip-path="url(#cityclip)"'

    # 0) 배경지도 자리 — 비워 둔다. 칩을 켜면 JS 가 여기에 타일 <image> 를 채운다.
    #    타일을 HTML 에 구워 넣지 않는 이유: 켜지 않으면 바깥으로 요청이 한 번도
    #    나가지 않아야 하고, 배율에 맞는 타일 레벨은 볼 때가 되어야 정해지기 때문이다.
    layers = ['<g class="basemap" aria-hidden="true"></g>']

    # 1) 읍면동 — 면마다 색을 돌려 쓰고 경계선을 굵게 둔다.
    #    색은 배경이 아니라 '어디가 어디인지'를 읽는 장치다.
    dongs = sorted((admin or {}).get("dongs") or [],
                   key=lambda d: -(d.get("area") or 0))
    dong_svg, dong_labels = [], []
    hues = _hue_cycle(len(dongs))
    for index, dong in enumerate(dongs):
        name = dong.get("name") or ""
        kind = _kind_of(name)
        paths = "".join('<path d="%s"/>' % _path(projection, ring)
                        for ring in dong["rings"])
        big = (dong.get("area") or 0) >= LABEL_ALWAYS_AREA
        dong_svg.append(
            '<g class="ad ad-%s" data-dong="%s" data-kind="%s" style="--h:%d" '
            'tabindex="0" role="button" aria-label="%s %s">'
            '<title>%s</title>%s</g>'
            % (kind, _esc(name), kind, hues[index], _esc(name),
               KIND_LABEL[kind], _esc(name), paths))
        if dong.get("label"):
            lx, ly = projection(*dong["label"])
            dong_labels.append(_cs_text(
                lx, ly, _esc(name), cls="cs adname%s" % ("" if big else " small"),
                extra=' text-anchor="middle" data-dong="%s"%s'
                      % (_esc(name), "" if big else ' data-minzoom="%.1f"'
                         % SMALL_LABEL_ZOOM)))
    if dong_svg:
        # 굵기는 CSS 변수로 넘긴다(--aw × --zw). non-scaling-stroke 는 여기 걸지
        # 않는다 — 상속되지 않아서 그룹에 적어 봐야 아무 일도 일어나지 않는다.
        # theme.css 가 그리는 요소마다 직접 건다.
        layers.append('<g class="dongs" style="--aw:%.2f" stroke-linejoin="round">'
                      '%s</g>' % (1.1 * scale, "".join(dong_svg)))

    # 2) 도로망 — 등급이 다섯이라 굵기와 색을 함께 벌렸다.
    #    호버하면 그 도로만 굵어지고 이름이 뜬다.
    road_groups, road_labels = [], []
    if show_roads:
        by_class = {}
        for road in load_roads():
            by_class.setdefault(road.get("cls") or "collector", []).append(road)
        for cls in ROAD_ORDER:
            style = ROAD_STYLE[cls]
            for road in by_class.get(cls) or []:
                lines = road.get("lines") or []
                if not lines:
                    continue
                # OSM 은 한 도로를 교차로마다 잘라 둔다. 세종 도로망은 696개 도로가
                # 4천여 조각으로 흩어져 있어, 조각마다 <path> 를 쓰면 좌표보다
                # 태그가 더 무겁다. 조각들을 한 d 속성 안의 여러 M...L... 로 합친다.
                geometry = "".join(_path(projection, line, close=False)
                                   for line in lines)
                # 투명한 히트영역은 형상을 한 번 더 적는 것이다. 수가 압도적으로 많은
                # 집산·지선에서만 생략하고, 대신 선 자체를 포인터 대상으로 삼는다.
                fat_hit = cls != "collector"
                hits = ('<path class="hit" d="%s"/>' % geometry) if fat_hit else ""
                strokes = ('<path class="ln" d="%s" stroke-opacity="%s"/>'
                           % (geometry, style["opacity"]))

                name = road.get("name") or ""
                spot = road.get("label")
                permanent = (bool(name) and bool(spot) and style["label"]
                             and (road.get("len") or 0) >= LABEL_MIN_LEN
                             and _in_rings(spot[0], spot[1], outline))
                hover_text = ""
                if name and spot and not permanent:
                    lx, ly = projection(*spot)
                    hover_text = _cs_text(lx + 6 * scale, ly - 6 * scale,
                                          _esc(name), cls="cs rdname")
                elif permanent:
                    lx, ly = projection(*spot)
                    road_labels.append(_cs_text(
                        lx + 5 * scale, ly - 5 * scale, _esc(name),
                        cls="cs", extra=' font-size="%.1f"'
                                        % (style["label"] * scale)))

                road_groups.append(
                    '<g class="rd%s" data-cls="%s" '
                    'style="--w:%.2f;--wh:%.2f;--hit:%.1f">'
                    '<title>%s</title>%s%s%s</g>'
                    % ("" if fat_hit else " rd-thin", cls,
                       style["w"] * scale, style["hover"] * scale,
                       HIT_WIDTH * scale,
                       _esc("%s · %s" % (name or "이름 미상", style["name"])),
                       hits, strokes, hover_text))
        if road_groups:
            # 클립은 그룹에 한 번만 건다. 조각마다 붙이면 그 속성만으로 200KB 가 넘는다.
            #
            # 굵기 고정(non-scaling-stroke)은 theme.css 가 .rd .ln / .rd .hit 에
            # 직접 건다. vector-effect 는 상속되지 않아 여기 적으면 무시된다.
            layers.append('<g class="roads"%s>%s</g>'
                          % (clip_ref, "".join(road_groups)))

    # 3) 시 외곽선
    for ring in outline:
        layers.append('<path class="cityline" d="%s" fill="none" '
                      'style="--cw:%.2f" stroke-linejoin="round" '
                      'vector-effect="non-scaling-stroke"/>'
                      % (_path(projection, ring), 1.6 * scale))

    # 4) 이름
    if road_labels:
        layers.append('<g class="rdlabel" style="pointer-events:none">%s</g>'
                      % "".join(road_labels))
    if dong_labels:
        layers.append('<g class="dongname" font-size="%.1f" font-weight="700" '
                      'style="pointer-events:none">%s</g>'
                      % (14.0 * scale, "".join(dong_labels)))

    # 5) 지점 마커
    markers, missing = [], 0
    for point in points:
        lat, lon = point.get("lat"), point.get("lon")
        if lat is None or lon is None or not projection.inside(lon, lat):
            missing += 1
            continue
        x, y = projection(lon, lat)
        size = float(point.get("size") or 6.5)
        # 이름표는 오른쪽에 붙이되, 오른쪽 끝 지점은 왼쪽으로 뒤집는다.
        flip = x > width * 0.72
        offset = (-1 if flip else 1) * 11 * scale
        anchor = "end" if flip else "start"
        # 지도 위 이름표는 짧게 자른다. 돌발상황 문구는 한 줄이 서른 자를 넘어
        # 지도를 가로질러 버린다. 온전한 이름은 왼쪽 목록과 오른쪽 상세에 있다.
        shown = point["name"]
        if len(shown) > 16:
            shown = shown[:15] + "…"
        label = ('<text class="mkname" x="%.1f" y="%.1f" text-anchor="%s">%s</text>'
                 % (offset, -8 * scale, anchor, _esc(shown)))
        markers.append(
            '<g class="mk cs" data-id="%s" data-x="%.1f" data-y="%.1f" '
            'data-kind="%s" transform="translate(%.1f,%.1f)" tabindex="0" '
            'role="button" aria-label="%s">'
            '<circle class="halo" cx="0" cy="0" r="%.1f" fill="%s" opacity="0"/>'
            '%s%s</g>'
            % (_esc(point["id"]), x, y, _esc(point.get("kind") or "spot"), x, y,
               _esc(point["name"]), (size + 7.5) * scale, point["color"],
               _shape(KIND_SHAPE.get(point.get("kind"), "circle"),
                      point["color"], size * scale),
               label))
    if markers:
        layers.append('<g class="markers">%s</g>' % "".join(markers))

    # 확대/이동 대상은 여기까지. 범례와 축척은 화면에 고정.
    zoomable = '<g class="zoom">%s</g>' % "".join(layers)

    legend = _legend(width, bool(road_groups))

    # 축척 — 확대하면 JS 가 길이와 숫자를 다시 계산한다.
    # 1 SVG 단위 = (1/scale)도 위도 = 111320/scale 미터. 가로도 cos(위도)를 이미
    # 반영해 두어 두 축의 거리 척도가 같다.
    meters_per_unit = 111320.0 / projection.scale
    bar_x, bar_y = width - 178, height - 42
    scalebar = (
        '<g class="scalebar" data-mpu="%.6f" data-x="%.1f" data-y="%.1f" '
        'style="pointer-events:none">'
        '<rect class="sb-bg" x="%.1f" y="%.1f" width="150" height="26" rx="7"/>'
        '<text class="sb-label" x="%.1f" y="%.1f" font-size="11">—</text>'
        '<rect class="sb-bar" x="%.1f" y="%.1f" width="60" height="4" rx="2"/>'
        '<rect class="sb-tick" x="%.1f" y="%.1f" width="1.6" height="9" rx="0.8"/>'
        '<rect class="sb-tick sb-tick2" x="%.1f" y="%.1f" width="1.6" height="9" rx="0.8"/>'
        '</g>'
        % (meters_per_unit, bar_x, bar_y,
           bar_x - 8, bar_y - 8,                 # 배경
           bar_x, bar_y + 2,                     # 라벨
           bar_x, bar_y + 8,                     # 막대
           bar_x, bar_y + 5.5,                   # 왼쪽 눈금
           bar_x + 58.4, bar_y + 5.5))           # 오른쪽 눈금(JS 가 옮긴다)

    missing_layers = []
    if not admin:
        missing_layers.append("읍면동 경계(assets/sejong_admin.json)")
    if show_roads and not road_groups:
        missing_layers.append("도로망(assets/sejong_roads.json — tools/make_roads.py)")
    note = ("누락된 자산: " + ", ".join(missing_layers) if missing_layers
            else "읍면동 경계·도로망·지점 모두 실제 좌표 · 도로망 © OpenStreetMap")
    footnote = ('<text class="footnote" x="14" y="%d" font-size="%.1f">%s</text>'
                % (height - 13, 12.5 * scale, note))
    if missing:
        footnote += ('<text class="footnote" x="14" y="%d" font-size="10">'
                     '좌표 없는 %d개소는 왼쪽 목록에만 표시</text>'
                     % (height - 28, missing))

    # 배경지도 타일을 제자리에 놓으려면 JS 도 이 투영을 그대로 계산할 수 있어야 한다.
    #   x = offx + (lon - lon0) * kx * scale
    #   y = offy + (lat1 - lat) * scale
    projected = (' data-lon0="%.6f" data-lat1="%.6f" data-kx="%.8f" '
                 'data-scale="%.4f" data-offx="%.3f" data-offy="%.3f"'
                 % (projection.lon0, projection.lat1, projection.k,
                    projection.scale, projection.off_x, projection.off_y))

    credit = ('<text class="basemap-credit" x="14" y="%d" font-size="10.5">'
              '배경지도 © OpenStreetMap 기여자</text>' % (height - 28))

    return ('<svg class="map" viewBox="0 0 %d %d"%s '
            'xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
            '%s%s%s%s%s%s</svg>'
            % (width, height, projected, defs, zoomable, legend, scalebar,
               footnote, credit))


def _hue_cycle(count: int) -> list:
    """이웃한 면이 비슷한 색이 되지 않도록 색상환을 성큼성큼 돈다.

    면 목록은 면적 내림차순이라 인접 순서가 아니다. 그래도 황금각(137.5°)으로
    돌리면 어느 순서로 늘어놓아도 이웃끼리 충분히 벌어진다.
    """
    return [int(round((i * 137.5) % 360)) for i in range(max(count, 1))]


def _legend(width: float, has_roads: bool) -> str:
    """우측 상단 범례 — 읍면동 구분과 도로 등급.

    읍면동은 기본적으로 경계선만 보인다. 색은 '고른 곳'을 알리는 용도라
    범례에서도 그렇게 적는다. 등급을 가르는 것은 선 모양(읍·면 실선 / 동 파선)이다.
    """
    lines = ['<text class="lg-h" x="0" y="0">읍면동 경계</text>']
    y = 15
    for kind, label in (("myeon", "읍 · 면"), ("dong", "동")):
        lines.append('<rect class="lg-ad lg-%s" x="0" y="%d" width="14" height="10" '
                     'rx="2"/><text x="21" y="%d">%s</text>' % (kind, y - 8, y, label))
        y += 17
    lines.append('<text class="lg-note" x="0" y="%d">누르면 그 면만 칠해짐</text>' % y)
    y += 14

    if has_roads:
        y += 6
        lines.append('<text class="lg-h" x="0" y="%d">도로</text>' % y)
        y += 15
        for cls in reversed(ROAD_ORDER):
            style = ROAD_STYLE[cls]
            lines.append('<rect class="lg-rd lg-%s" x="0" y="%.1f" width="16" '
                         'height="%.1f" rx="%.1f"/><text x="21" y="%d">%s</text>'
                         % (cls, y - 3 - style["w"] / 2, max(style["w"], 1.6),
                            max(style["w"] / 2, 0.8), y, style["name"]))
            y += 16
    height = y + 8
    box_w = 112
    return ('<g class="legend" transform="translate(%.1f,%.1f)" font-size="12.5" '
            'style="pointer-events:none">'
            '<rect class="lg-bg" x="-11" y="-22" width="%d" height="%d" rx="9"/>'
            '%s</g>'
            % (width - box_w - 14, 30, box_w, height, "".join(lines)))

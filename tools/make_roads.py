# -*- coding: utf-8 -*-
"""OSM Overpass 응답 → 상황판이 쓰는 도로망(assets/sejong_roads.json).

원본 받는 법 (세종시 범위):

  query.txt:
    [out:json][timeout:240];
    (
      way["highway"~"^(motorway|trunk|primary|secondary|tertiary)$"]
         (36.34,127.05,36.75,127.45);
    );
    out geom;

  curl -s -X POST --data-binary @query.txt \
       https://overpass-api.de/api/interpreter -o osm_roads.json

사용:
  python tools/make_roads.py <osm_roads.json> [출력경로]

등급 매김 — OSM highway 태그를 우리 다섯 등급으로 옮긴다.
  motorway, trunk            → expressway  고속·자동차전용
  primary                    → arterial    주간선
  secondary                  → sub         보조간선
  tertiary                   → collector   집산·지선
  (위 중 BRT 축으로 알려진 도로는 이름으로 골라 brt 로 올린다)

BRT 를 태그로 잡지 않고 이름으로 잡는 이유: 세종 BRT 는 별도 도로가 아니라
간선도로의 중앙 전용차로다. OSM 에서 일관되게 태깅돼 있지 않다.
"""
from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(HERE, "assets", "sejong_roads.json")

EPS = 0.00012          # 단순화 허용오차(도) ≈ 12m. 도로는 하천보다 곡선이 급하다.
MIN_LENGTH = 0.0012    # 이보다 짧은 조각(도, ≈120m)은 버린다 — 점처럼 보인다

# 등급별 허용오차. 간선은 형상을 살리고 지선은 과감히 줄인다.
EPS_OF = {"expressway": 0.00010, "brt": 0.00010, "arterial": 0.00012,
          "sub": 0.00020, "collector": 0.00035}

# 세종시 범위. Overpass 는 bbox 에 걸린 way 의 **전체** 형상을 돌려주므로
# (경부고속도로는 서울까지 이어진다) 여기서 잘라내지 않으면 자산이 커진다.
BBOX = (127.05, 36.34, 127.45, 36.75)   # lon0, lat0, lon1, lat1

CLASS_OF = {
    "motorway": "expressway", "motorway_link": "expressway",
    "trunk": "expressway", "trunk_link": "expressway",
    "primary": "arterial", "primary_link": "arterial",
    "secondary": "sub", "secondary_link": "sub",
    "tertiary": "collector", "tertiary_link": "collector",
}

# 세종 BRT(내부순환·대전·오송 축)가 지나는 간선. 이름으로 골라 등급을 올린다.
BRT_NAMES = ("한누리대로", "절재로", "갈매로", "도움로", "다솜로", "누리로")

ORDER = {"expressway": 0, "brt": 1, "arterial": 2, "sub": 3, "collector": 4}


def _perp(point, start, end):
    (px, py), (ax, ay), (bx, by) = point, start, end
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def simplify(points, eps=EPS):
    """Douglas–Peucker. 좌표 수를 줄이지 않으면 자산이 수 MB 가 된다."""
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue
        worst, index = -1.0, first
        for i in range(first + 1, last):
            distance = _perp(points[i], points[first], points[last])
            if distance > worst:
                worst, index = distance, i
        if worst > eps:
            keep[index] = True
            stack.append((first, index))
            stack.append((index, last))
    return [p for p, flag in zip(points, keep) if flag]


def in_bbox(point, slack=0.01):
    lon, lat = point
    lon0, lat0, lon1, lat1 = BBOX
    return (lon0 - slack <= lon <= lon1 + slack) and (lat0 - slack <= lat <= lat1 + slack)


def clip_to_bbox(line):
    """bbox 안에 든 구간들로 자른다. 경계에서 끊긴 티가 안 나게 바깥 점 하나씩 붙인다."""
    segments, current = [], []
    for i, point in enumerate(line):
        if in_bbox(point):
            if not current and i > 0:
                current.append(line[i - 1])      # 들어오는 쪽 바깥 점
            current.append(point)
        elif current:
            current.append(point)                # 나가는 쪽 바깥 점
            segments.append(current)
            current = []
    if len(current) >= 2:
        segments.append(current)
    return [seg for seg in segments if len(seg) >= 2]


def length_of(points):
    return sum(math.hypot(points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1])
               for i in range(len(points) - 1))


def base_class(tags: dict) -> str:
    return CLASS_OF.get((tags.get("highway") or "").strip(), "")


def is_brt(tags: dict) -> bool:
    """세종 BRT 는 별도 도로가 아니라 간선의 중앙 전용차로다.

    OSM 에 일관되게 태깅돼 있지 않아 이름으로도 함께 판정한다.
    """
    if tags.get("busway") or tags.get("busway:right") or tags.get("busway:left"):
        return True
    # 부분일치를 쓰면 '어울누리로'가 '누리로'에 걸린다. 이름 전체가 같을 때만 본다.
    return (tags.get("name") or "").strip() in BRT_NAMES


def road_key(tags: dict, cls: str) -> str:
    """같은 도로의 조각들을 묶는 열쇠. 이름이 없으면 노선번호, 그것도 없으면 등급.

    이름으로 묶는 게 중요하다. OSM 은 한 도로를 구간마다 다른 highway 값으로
    태깅해 둔 곳이 많아(한누리대로가 구간에 따라 tertiary), 조각별로 등급을
    매기면 같은 도로가 두세 등급에 흩어져 그려진다.
    """
    name = (tags.get("name") or "").strip()
    if name:
        return name
    ref = (tags.get("ref") or "").strip()
    if ref:
        return ref
    return "__%s" % cls


def build(src_path: str, out_path: str) -> dict:
    with open(src_path, "r", encoding="utf-8") as fp:
        raw = json.load(fp)

    grouped: dict[str, list] = {}
    tag_of: dict[str, dict] = {}
    class_of: dict[str, str] = {}
    brt_of: dict[str, bool] = {}
    for element in raw.get("elements") or []:
        geometry = element.get("geometry") or []
        if len(geometry) < 2:
            continue
        tags = element.get("tags") or {}
        base = base_class(tags)
        if not base:
            continue
        key = road_key(tags, base)
        tag_of.setdefault(key, tags)
        # 한 도로에 여러 등급이 섞여 있으면 가장 높은 등급으로 통일한다.
        if ORDER[base] < ORDER.get(class_of.get(key, "collector"), 9):
            class_of[key] = base
            tag_of[key] = tags                  # 이름·노선번호도 상위 구간 것을 쓴다
        class_of.setdefault(key, base)
        brt_of[key] = brt_of.get(key, False) or is_brt(tags)

        line = [(round(node["lon"], 6), round(node["lat"], 6)) for node in geometry]
        for segment in clip_to_bbox(line):
            if length_of(segment) < MIN_LENGTH:
                continue
            # 단순화는 등급이 확정된 뒤에 한다. 등급마다 허용오차가 다르기 때문이다.
            grouped.setdefault(key, []).append(segment)

    roads = []
    for key, lines in grouped.items():
        if not lines:
            continue
        cls = class_of.get(key, "collector")
        # BRT 는 등급이 아니라 기능이다. 자동차전용도로가 아닌 한 BRT 로 올린다.
        if brt_of.get(key) and cls != "expressway":
            cls = "brt"
        tags = tag_of.get(key) or {}
        name = (tags.get("name") or "").strip()
        ref = (tags.get("ref") or "").strip()
        # 이름 없는 집산도로 조각은 짧으면 화면만 지저분해진다.
        if not name and cls == "collector":
            lines = [ln for ln in lines if length_of(ln) >= MIN_LENGTH * 4]
            if not lines:
                continue
        # 등급이 낮을수록 거칠게 줄인다. 집산·지선이 전체의 6할이라
        # 여기서 아끼는 좌표가 그대로 상황판 파일 크기가 된다.
        lines = [simplify(ln, EPS_OF.get(cls, EPS)) for ln in lines]
        longest = max(lines, key=length_of)
        inside = [p for p in longest if in_bbox(p, slack=0.0)] or longest
        roads.append({
            "name": name or ref,
            "ref": ref,
            "cls": cls,
            "len": round(sum(length_of(ln) for ln in lines), 5),
            "label": [round(v, 6) for v in inside[len(inside) // 2]],
            "lines": [[[x, y] for x, y in ln] for ln in lines],
        })

    roads.sort(key=lambda r: (ORDER.get(r["cls"], 9), -r["len"]))

    payload = {
        "_source": "OpenStreetMap (ODbL) highway 데이터를 tools/make_roads.py 로 단순화",
        "_classes": {"expressway": "고속·자동차전용", "brt": "BRT 축",
                     "arterial": "주간선", "sub": "보조간선",
                     "collector": "집산·지선"},
        "roads": roads,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, separators=(",", ":"))
    return payload


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    target = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUT
    result = build(sys.argv[1], target)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    counts: dict = {}
    for road in result["roads"]:
        counts[road["cls"]] = counts.get(road["cls"], 0) + 1
    nodes = sum(len(ln) for r in result["roads"] for ln in r["lines"])
    print("도로 %d개 (구간 %d, 좌표 %d점)"
          % (len(result["roads"]),
             sum(len(r["lines"]) for r in result["roads"]), nodes))
    for cls in ("expressway", "brt", "arterial", "sub", "collector"):
        if counts.get(cls):
            names = [r["name"] for r in result["roads"]
                     if r["cls"] == cls and r["name"]][:6]
            print("  %-11s %3d개  %s"
                  % (result["_classes"][cls], counts[cls], ", ".join(names)))
    print("→ %s (%.0f KB)" % (target, os.path.getsize(target) / 1024))

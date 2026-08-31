# -*- coding: utf-8 -*-
"""OSM Overpass 응답 → 상황판이 쓰는 읍면동 경계도(assets/sejong_admin.json).

원본 받는 법 — 두 번 받아서 두 파일로 둔다.

  1) 시 외곽선
     [out:json][timeout:180];
     rel(2349795);            # 세종특별자치시 (admin_level=4)
     out geom;

  2) 읍면동
     [out:json][timeout:240];
     rel(area:3602349795)["boundary"="administrative"]["admin_level"~"^(8|9)$"];
     out geom;

  curl -s -X POST --data-binary @query.txt \
       https://overpass-api.de/api/interpreter -o osm_dongs.json

사용:
  python tools/make_admin.py <osm_dongs.json> <osm_city.json> [출력경로]

만들어지는 구조
  {"outline": [[[lon,lat],...]],
   "dongs": [{"name":"조치원읍","kind":"eup","rings":[[[lon,lat],...]],
              "label":[lon,lat],"area":0.0013}]}

주의 — 같은 이름이 두 번 나온다(법정동과 행정동이 같은 레벨에 태깅된 경우).
구성 way 가 많은 쪽(= 실제 경계를 온전히 가진 쪽)을 남긴다.
"""
from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(HERE, "assets", "sejong_admin.json")

EPS = 0.00010          # 단순화 허용오차(도) ≈ 10m. 경계는 도로보다 더 살려 둔다.
SNAP = 1e-7            # 링을 이을 때 같은 점으로 볼 오차


def _kind_of(name: str) -> str:
    text = (name or "").strip()
    if text.endswith("읍"):
        return "eup"
    if text.endswith("면"):
        return "myeon"
    return "dong"


def _perp(point, start, end):
    (px, py), (ax, ay), (bx, by) = point, start, end
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def simplify(points, eps=EPS):
    if len(points) < 4:
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


def _same(a, b) -> bool:
    return abs(a[0] - b[0]) < SNAP and abs(a[1] - b[1]) < SNAP


def assemble(ways) -> list:
    """조각난 way 들을 이어 붙여 닫힌 링 목록으로.

    OSM 경계 관계의 outer way 들은 순서도 방향도 제각각이다. 끝점이 맞는 조각을
    찾아 붙이고, 더 붙일 게 없으면 그 링을 닫는다.
    """
    pieces = []
    for way in ways:
        line = [(round(n["lon"], 6), round(n["lat"], 6))
                for n in (way.get("geometry") or []) if n]
        if len(line) >= 2:
            pieces.append(line)

    rings, used = [], [False] * len(pieces)
    for start in range(len(pieces)):
        if used[start]:
            continue
        used[start] = True
        chain = list(pieces[start])
        grew = True
        while grew:
            grew = False
            for i, piece in enumerate(pieces):
                if used[i]:
                    continue
                if _same(chain[-1], piece[0]):
                    chain.extend(piece[1:])
                elif _same(chain[-1], piece[-1]):
                    chain.extend(list(reversed(piece))[1:])
                elif _same(chain[0], piece[-1]):
                    chain = piece[:-1] + chain
                elif _same(chain[0], piece[0]):
                    chain = list(reversed(piece))[:-1] + chain
                else:
                    continue
                used[i] = True
                grew = True
        if len(chain) >= 4:
            if not _same(chain[0], chain[-1]):
                chain.append(chain[0])          # 살짝 안 닫힌 경계를 닫아 준다
            rings.append(simplify(chain))
    rings.sort(key=lambda r: -abs(area_of(r)))
    return rings


def area_of(ring) -> float:
    """신발끈 공식. 부호는 방향이므로 크기 비교엔 절댓값을 쓴다(단위: 도²)."""
    total = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def centroid(ring):
    """면적 가중 중심. 오목한 면에서는 밖으로 나갈 수 있어 호출 쪽에서 검사한다."""
    cx = cy = a = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(a) < 1e-12:
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return [sum(xs) / len(xs), sum(ys) / len(ys)]
    a *= 0.5
    return [cx / (6 * a), cy / (6 * a)]


def in_ring(point, ring) -> bool:
    lon, lat = point
    inside = False
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        if (y1 > lat) != (y2 > lat):
            cross = x1 + (lat - y1) * (x2 - x1) / ((y2 - y1) or 1e-12)
            if lon < cross:
                inside = not inside
    return inside


def label_point(relation, rings):
    """이름을 놓을 자리. 관계에 label 노드가 있으면 그게 제일 정확하다."""
    for member in relation.get("members") or []:
        if member.get("type") == "node" and member.get("role") == "label":
            lon, lat = member.get("lon"), member.get("lat")
            if lon is not None and lat is not None:
                return [round(lon, 6), round(lat, 6)]
    if not rings:
        return None
    biggest = rings[0]
    point = centroid(biggest)
    if in_ring(point, biggest):
        return [round(point[0], 6), round(point[1], 6)]
    # 오목해서 중심이 밖으로 나갔다. 가로 스캔선으로 안쪽 한 점을 찾는다.
    lats = sorted(p[1] for p in biggest)
    mid_lat = lats[len(lats) // 2]
    xs = sorted(p[0] for p in biggest)
    for frac in (0.5, 0.4, 0.6, 0.3, 0.7):
        cand = [xs[0] + (xs[-1] - xs[0]) * frac, mid_lat]
        if in_ring(cand, biggest):
            return [round(cand[0], 6), round(cand[1], 6)]
    return [round(point[0], 6), round(point[1], 6)]


def _outer_ways(relation):
    return [m for m in (relation.get("members") or [])
            if m.get("type") == "way" and m.get("role") in ("outer", "", None)]


def build(dongs_path: str, city_path: str, out_path: str) -> dict:
    with open(dongs_path, "r", encoding="utf-8") as fp:
        dong_raw = json.load(fp)

    # 같은 이름이 두 번 나오면 구성 way 가 많은 쪽을 남긴다.
    best: dict = {}
    for element in dong_raw.get("elements") or []:
        if element.get("type") != "relation":
            continue
        name = ((element.get("tags") or {}).get("name") or "").strip()
        if not name:
            continue
        ways = _outer_ways(element)
        if name not in best or len(ways) > len(_outer_ways(best[name])):
            best[name] = element

    dongs = []
    for name, relation in best.items():
        rings = assemble(_outer_ways(relation))
        if not rings:
            continue
        dongs.append({
            "name": name,
            "kind": _kind_of(name),
            "rings": [[[x, y] for x, y in ring] for ring in rings],
            "label": label_point(relation, rings),
            "area": round(sum(abs(area_of(r)) for r in rings), 8),
        })
    dongs.sort(key=lambda d: -d["area"])

    outline = []
    if city_path and os.path.exists(city_path):
        with open(city_path, "r", encoding="utf-8") as fp:
            city_raw = json.load(fp)
        for element in city_raw.get("elements") or []:
            if element.get("type") == "relation":
                outline = [[[x, y] for x, y in ring]
                           for ring in assemble(_outer_ways(element))]
                break
    if not outline and dongs:
        # 시 관계를 못 받았으면 가장 큰 면들의 합집합 대신 전체 링을 그대로 둔다.
        outline = [ring for dong in dongs for ring in dong["rings"]]

    payload = {
        "_source": "OpenStreetMap (ODbL) 행정경계를 tools/make_admin.py 로 조립·단순화",
        "outline": outline,
        "dongs": dongs,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, separators=(",", ":"))
    return payload


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    city = sys.argv[2] if len(sys.argv) > 2 else ""
    target = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_OUT
    result = build(sys.argv[1], city, target)
    kinds: dict = {}
    for dong in result["dongs"]:
        kinds[dong["kind"]] = kinds.get(dong["kind"], 0) + 1
    print("읍면동 %d개 (읍 %d · 면 %d · 동 %d), 외곽선 링 %d"
          % (len(result["dongs"]), kinds.get("eup", 0), kinds.get("myeon", 0),
             kinds.get("dong", 0), len(result["outline"])))
    print("  " + ", ".join(d["name"] for d in result["dongs"]))
    missing = [d["name"] for d in result["dongs"] if not d["label"]]
    if missing:
        print("  이름 자리 못 찾음:", ", ".join(missing))
    print("→ %s (%.0f KB)" % (target, os.path.getsize(target) / 1024))

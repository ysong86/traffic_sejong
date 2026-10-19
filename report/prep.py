# -*- coding: utf-8 -*-
"""그림마다 다시 계산하지 않도록, 파생 지표를 한 번만 만들어 둔다.

여기서 만드는 것
  spots   사고다발지 13곳 + 읍면동 + 최근접 단속장비·횡단보도·신호등 거리
  dongs   읍면동별 집계(다발지 수·사고·사상자·시설)
  layers  유형별 집계
  flow    ITS 소통 — **간선급만** 추린 것(이면도로를 섞으면 정체율이 부풀려진다)
"""
from __future__ import annotations

import collections

import base

# 다발지에서 이 거리 안에 시설이 없으면 '공백'으로 본다.
# 300m 는 상황판이 쓰는 값과 맞춘다 — 보고서와 화면의 숫자가 달라지면 안 된다.
GAP_KM = 0.30


def build() -> dict:
    d = base.data()
    adm = base.admin()
    dongs = adm["dongs"]

    spots = list((d.get("koroad") or {}).get("spots") or [])
    items = list((d.get("facility") or {}).get("items") or [])

    by_layer = collections.defaultdict(list)
    for it in items:
        by_layer[it["layer"]].append(it)

    def nearest(spot, layer):
        pool = by_layer.get(layer) or []
        if not pool:
            return None
        return min(base.km(spot["lat"], spot["lon"], f["lat"], f["lon"])
                   for f in pool)

    for s in spots:
        s["dong"] = base.dong_of(s["lon"], s["lat"], dongs)
        s["cam_km"] = nearest(s, "camera")
        s["crosswalk_km"] = nearest(s, "crosswalk")
        s["light_km"] = nearest(s, "traffic_light")
        s["sign_km"] = nearest(s, "road_sign")
        # 사고 1건당 사상자 — 같은 10건이라도 다친 사람 수가 다르다.
        s["per"] = (s["casualties"] / s["accidents"]) if s["accidents"] else 0.0
        # 중상 비중. 경상만 많은 곳과 중상이 몰린 곳은 처방이 다르다.
        hurt = (s.get("serious") or 0) + (s.get("slight") or 0) + (s.get("wounded") or 0)
        s["serious_rate"] = ((s.get("serious") or 0) / hurt) if hurt else 0.0
    spots.sort(key=lambda x: -x["accidents"])
    # 지점마다 번호를 붙인다. 지점명이 길어 지도에 그대로 쓰면 이름표가 서로
    # 겹친다. 그림 전체가 같은 번호를 쓰므로 그림 1의 ③과 그림 10의 ③이
    # 같은 곳이다 — 보고서에서 그림 사이를 오갈 때 이게 제일 편하다.
    for i, s in enumerate(spots, 1):
        s["no"] = i
        s["short"] = (s["name"].replace("세종 ", "")
                      .split("(")[-1].rstrip(")").replace(" 부근", ""))
        s["where"] = s["name"].replace("세종 ", "").split("(")[0].strip()

    # 읍면동 집계 — 시설도 같은 경계로 센다.
    agg = {}
    for s in spots:
        row = agg.setdefault(s["dong"], {"name": s["dong"], "spots": 0,
                                         "accidents": 0, "casualties": 0,
                                         "serious": 0})
        row["spots"] += 1
        row["accidents"] += s["accidents"]
        row["casualties"] += s["casualties"]
        row["serious"] += s.get("serious") or 0
    for it in items:
        name = base.dong_of(it["lon"], it["lat"], dongs)
        row = agg.setdefault(name, {"name": name, "spots": 0, "accidents": 0,
                                    "casualties": 0, "serious": 0})
        row[it["layer"]] = row.get(it["layer"], 0) + 1
    dong_rows = sorted(agg.values(), key=lambda r: (-r["accidents"], -r["spots"]))

    layers = [l for l in (d.get("koroad") or {}).get("layers") or []
              if l.get("count")]

    # ITS — 간선급만. 전체 표준링크로 정체율을 내면 이면도로가 섞여 부풀려진다.
    its = d.get("its") or {}
    flow = [r for r in (its.get("flow") or []) if r.get("speed")]

    fac_counts = {l["id"]: l["count"]
                  for l in (d.get("facility") or {}).get("layers") or []}

    return {"raw": d, "spots": spots, "dongs": dong_rows, "layers": layers,
            "items": items, "by_layer": by_layer, "flow": flow,
            "its": its, "fac": fac_counts,
            "gaps": [s for s in spots
                     if s["cam_km"] is not None and s["cam_km"] > GAP_KM]}

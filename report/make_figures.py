# -*- coding: utf-8 -*-
"""세종시 교통안전 기본계획 — 분석 그림 생성기.

    C:\\Python313\\python.exe -I report/make_figures.py

report/figures/*.png 와 report/index.html 을 만든다. 상황판이 모아 둔 실측
자료(data/latest.json)만 쓴다 — 보고서 숫자와 화면 숫자가 어긋나지 않게.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle

import base
import index_page
import prep
import trend_figures
from base import (BLUES, GRID, INK, INK2, INK3, SERIES, SERIES3, STATUS,
                  basemap, finish, scalebar)

# 유형을 세 묶음으로 줄인다. 산점도·지도처럼 모든 색이 한 화면에서 서로
# 비교되는 그림은 기준 팔레트가 3슬롯까지만 안전하다고 못박고 있다.
# 묶음 자체도 분석적으로 뜻이 있다 — 처방이 묶음마다 다르다.
GROUP = {
    "lg": ("전체 사고다발지", 0),
    "schoolzone": ("보행 취약계층", 1), "child": ("보행 취약계층", 1),
    "oldman": ("보행 취약계층", 1),
    "bicycle": ("자전거·법규위반", 2), "violation": ("자전거·법규위반", 2),
}
GROUP_NAMES = ["전체 사고다발지", "보행 취약계층", "자전거·법규위반"]

SRC = ("자료 — 도로교통공단 교통사고 다발지역 정보(2024~2025년 공표분), "
       "공공데이터포털 전국 표준데이터 및 세종특별자치시 제공 자료 / "
       "작성 세종연구원 도시안전연구센터")


def gkey(spot):
    return GROUP.get(spot.get("layer"), ("전체 사고다발지", 0))


def wrap(name: str) -> str:
    """지점명이 길어 축 라벨이 겹친다. 괄호 앞에서 끊는다."""
    return name.replace("세종 ", "").replace("(", "\n(")


def tag(s) -> str:
    """지도와 같은 번호를 막대·산점도에도 붙인다. 그림끼리 이어 읽힌다 —
    그림 1의 3번과 그림 10의 3번이 같은 곳이다."""
    return "%d. %s\n%s" % (s["no"], s["where"], s["short"])


def bars_value_labels(ax, rects, values, fmt="%d", dx=0, color=INK2, size=9.5):
    for r, v in zip(rects, values):
        ax.text(r.get_width() + dx, r.get_y() + r.get_height() / 2,
                fmt % v, va="center", ha="left", fontsize=size, color=color)


# ══════════════════════════════════════════════════════════════════════════

# 번호를 점 바로 옆에 두면 가까운 점끼리 이름표가 포개진다. 서로 150m 안에
# 있는 점들은 이름표를 시계 방향으로 흩뜨린다.
NUDGE = [(15, 11), (15, -14), (-19, 11), (-19, -14), (0, 20), (0, -24),
         (26, -2), (-30, -2)]


def numbers(ax, spots, color=INK):
    """확대 패널에서 점 옆에 번호만 적는다. 이름을 적으면 서로 겹친다."""
    used = []
    for s in sorted(spots, key=lambda x: -x["accidents"]):
        # 같은 교차로를 두 유형이 각각 다발지로 잡는 일이 흔하다(역전교차로가
        # 전체와 노인보행으로 두 번). 250m 안이면 이웃으로 보고 흩뜨린다.
        near = sum(1 for t in used
                   if base.km(s["lat"], s["lon"], t["lat"], t["lon"]) < 0.25)
        dx, dy = NUDGE[min(near, len(NUDGE) - 1)]
        ax.annotate(str(s["no"]), (s["lon"], s["lat"]),
                    textcoords="offset points", xytext=(dx, dy),
                    fontsize=9.5, fontweight="bold", color=color, zorder=9,
                    ha="center", va="center",
                    # 두 자리 숫자가 원 안에서 잘린다. 둥근 네모로 둔다.
                    bbox=dict(boxstyle="round,pad=0.26", fc="#ffffff",
                              ec=GRID, lw=0.8, alpha=0.96))
        used.append(s)


def listing(ax, spots, extra=None, head="사고다발지 (사고 건수 순)"):
    """번호 → 지점 목록. 지도와 자리를 다투지 않게 제 칸에 둔다."""
    ax.text(0.0, 0.985, head, transform=ax.transAxes, fontsize=10.5,
            fontweight="bold", color=INK2, va="top")
    for i, s in enumerate(spots):
        txt = "%2d. %s · %s %d건" % (s["no"], s["where"], s["short"],
                                    s["accidents"])
        if extra:
            txt += extra(s)
        ax.text(0.0, 0.942 - i * 0.0345, txt, transform=ax.transAxes,
                fontsize=9.2, color=INK2, va="top")


def map_panels(P, draw, title, subtitle, fname, handles, note="",
               show_list=True, extra=None):
    """지점 목록 + 전체 지도 + 확대 두 장. 점이 두 덩어리에 몰려 있어 쪼갠다."""
    fig = plt.figure(figsize=(14.2, 8.8))
    ax_list, ax_all, ax_a, ax_b = base.panel_layout(fig)

    basemap(ax_all)
    draw(ax_all, False)
    scalebar(ax_all)

    for (name, lat_min, lat_max), ax in zip(base.CLUSTERS, (ax_a, ax_b)):
        box = base.cluster_bounds(P["spots"], lat_min, lat_max)
        if not box:
            ax.axis("off")
            continue
        basemap(ax, road_classes=("expressway", "brt", "arterial", "sub"))
        draw(ax, True)
        base.zoom_to(ax, box, name)
        base.mark_box(ax_all, box, name)

    ax_list.legend(handles=handles, loc="lower left", frameon=False,
                   fontsize=10.5, bbox_to_anchor=(0.0, 0.0))
    if show_list:
        listing(ax_list, P["spots"], extra=extra)
    if note:
        ax_all.text(0.5, 0.012, note, transform=ax_all.transAxes, ha="center",
                    fontsize=9.5, color=INK3)
    return finish(fig, ax_all, title, subtitle, SRC, fname)


def fig01_hotspot_map(P):
    def draw(ax, zoom):
        for s in sorted(P["spots"], key=lambda x: -x["accidents"]):
            _, idx = gkey(s)
            r = (4.2 if zoom else 2.6) + (4.6 if zoom else 3.4) * (s["accidents"] ** 0.5)
            ax.scatter(s["lon"], s["lat"], s=r * r * 0.55, color=SERIES3[idx],
                       edgecolor="#ffffff", linewidth=1.6, zorder=6, alpha=0.92)
        # 이름표 대신 번호. 지점명이 길어 확대 패널에서도 서로 겹친다.
        if zoom:
            numbers(ax, P["spots"])

    handles = [Line2D([], [], marker="o", linestyle="", markersize=10,
                      markerfacecolor=SERIES3[i], markeredgecolor="#ffffff",
                      label=n) for i, n in enumerate(GROUP_NAMES)]
    return map_panels(
        P, draw, "세종시 교통사고 다발지역 분포",
        "도로교통공단이 지정한 사고다발지 13곳. 조치원읍 4곳과 신도심 생활권 "
        "9곳 두 덩어리로 갈린다 — 원인도 처방도 서로 다르다.",
        "다발지분포.png", handles, "원의 크기 = 사고 건수",
        extra=lambda s: " · 사상 %d명" % s["casualties"])


def fig02_dong(P):
    rows = [r for r in P["dongs"] if r["accidents"]][:12]
    rows.reverse()
    fig, ax = plt.subplots(figsize=(9.0, 5.4))
    y = range(len(rows))
    rects = ax.barh(list(y), [r["accidents"] for r in rows], height=0.62,
                    color=SERIES[0])
    bars_value_labels(ax, rects, [r["accidents"] for r in rows], dx=0.4)
    for i, r in enumerate(rows):
        ax.text(-0.6, i, "%d곳" % r["spots"], ha="right", va="center",
                fontsize=9.5, color=INK3)
    ax.set_yticks(list(y))
    ax.set_yticklabels([r["name"] for r in rows], fontsize=11)
    ax.set_xlabel("사고 건수(건)")
    ax.set_xlim(0, max(r["accidents"] for r in rows) * 1.18)
    ax.xaxis.grid(True, linestyle=":")
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.text(0.0, 1.02, "읍면동 이름 왼쪽 숫자는 그 안의 다발지 지점 수",
            transform=ax.transAxes, fontsize=9.5, color=INK3)
    return finish(fig, ax, "읍면동별 사고다발지 사고 건수",
                  "조치원읍 한 곳에 지점 4곳·사고 45건이 몰려 있다. "
                  "신도심은 지점이 흩어져 있고 지점당 건수가 작다.",
                  SRC, "읍면동별사고.png")


def fig03_type(P):
    rows = sorted(P["layers"], key=lambda l: -(l.get("accidents") or 0))
    fig, ax = plt.subplots(figsize=(9.4, 5.0))
    x = range(len(rows))
    w = 0.38
    a = ax.bar([i - w / 2 - 0.01 for i in x], [r["accidents"] for r in rows],
               width=w, color=SERIES[0], label="사고 건수")
    b = ax.bar([i + w / 2 + 0.01 for i in x], [r["casualties"] for r in rows],
               width=w, color=SERIES[1], label="사상자 수")
    for rects in (a, b):
        for r in rects:
            ax.text(r.get_x() + r.get_width() / 2, r.get_height() + 0.7,
                    "%d" % r.get_height(), ha="center", fontsize=9.5, color=INK2)
    ax.set_xticks(list(x))
    ax.set_xticklabels(["%s\n(%d곳)" % (r["label"].replace("(도로 살얼음)", ""),
                                        r["count"]) for r in rows], fontsize=10.5)
    ax.set_ylabel("건 · 명")
    ax.set_ylim(0, max(r["casualties"] for r in rows) * 1.22)
    ax.yaxis.grid(True, linestyle=":")
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.legend(frameon=False, fontsize=10.5, loc="upper right")
    return finish(fig, ax, "사고 유형별 다발지·사고·사상자",
                  "유형은 서로 겹친다(한 지점이 전체이면서 노인 보행일 수 있다). "
                  "겹침을 감안해도 보행 취약계층 유형이 지점 수의 절반을 넘는다.",
                  SRC, "유형별구성.png")


def fig04_spot_rank(P):
    rows = list(P["spots"])[:13]
    rows.reverse()
    fig, ax = plt.subplots(figsize=(9.6, 7.0))
    y = range(len(rows))
    h = 0.36
    a = ax.barh([i + h / 2 + 0.01 for i in y], [r["accidents"] for r in rows],
                height=h, color=SERIES[0], label="사고 건수")
    b = ax.barh([i - h / 2 - 0.01 for i in y], [r["casualties"] for r in rows],
                height=h, color=SERIES[1], label="사상자 수")
    bars_value_labels(ax, a, [r["accidents"] for r in rows], dx=0.25)
    bars_value_labels(ax, b, [r["casualties"] for r in rows], dx=0.25)
    ax.set_yticks(list(y))
    ax.set_yticklabels([tag(r) for r in rows], fontsize=9.0)
    ax.set_xlabel("건 · 명")
    ax.set_xlim(0, max(r["casualties"] for r in rows) * 1.16)
    ax.xaxis.grid(True, linestyle=":")
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.legend(frameon=False, fontsize=10.5, loc="lower right")
    return finish(fig, ax, "사고다발지 13곳 사고·사상자 순위",
                  "상위 3곳(나성동·조치원 역전교차로·죽림회전교차로)이 전체 "
                  "사고의 절반을 넘는다. 사업 대상을 좁히는 첫 근거다.",
                  SRC, "지점순위.png")


def fig05_severity(P):
    rows = [s for s in P["spots"] if s["casualties"]][:13]
    rows.reverse()
    fig, ax = plt.subplots(figsize=(9.6, 7.0))
    y = list(range(len(rows)))
    ser = [s.get("serious") or 0 for s in rows]
    sli = [s.get("slight") or 0 for s in rows]
    wnd = [s.get("wounded") or 0 for s in rows]
    # 상해정도는 순서가 있는 값이라 한 색상의 명도 단계로 쓴다(무지개 금지).
    c_ser, c_sli, c_wnd = BLUES[5], BLUES[3], BLUES[1]
    ax.barh(y, ser, height=0.6, color=c_ser, label="중상",
            edgecolor=base.SURFACE, linewidth=2)
    ax.barh(y, sli, height=0.6, left=ser, color=c_sli, label="경상",
            edgecolor=base.SURFACE, linewidth=2)
    ax.barh(y, wnd, height=0.6, left=[a + b for a, b in zip(ser, sli)],
            color=c_wnd, label="부상신고", edgecolor=base.SURFACE, linewidth=2)
    for i, s in enumerate(rows):
        total = (s.get("serious") or 0) + (s.get("slight") or 0) + (s.get("wounded") or 0)
        ax.text(total + 0.35, i, "중상 %d명 (%.0f%%)"
                % (s.get("serious") or 0, s["serious_rate"] * 100),
                va="center", fontsize=9.5,
                color=(STATUS["critical"] if s["serious_rate"] >= 0.5 else INK2))
    ax.set_yticks(y)
    ax.set_yticklabels([tag(s) for s in rows], fontsize=9.0)
    ax.set_xlabel("사상자 수(명)")
    ax.set_xlim(0, max((s.get("serious") or 0) + (s.get("slight") or 0)
                       + (s.get("wounded") or 0) for s in rows) * 1.45)
    ax.xaxis.grid(True, linestyle=":")
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.legend(frameon=False, fontsize=10.5, loc="lower right", ncols=3)
    return finish(fig, ax, "지점별 상해정도 구성",
                  "건수가 적어도 중상 비중이 100%인 지점이 둘 있다"
                  "(조치원 역전교차로 8명, 성지약국 5명). 건수만으로 "
                  "우선순위를 매기면 이런 곳이 뒤로 밀린다.",
                  SRC, "상해정도.png")


def fig06_freq_severity(P):
    """세로축은 '사고 1건당 사상자'가 아니라 **중상 비중**으로 잡는다.
    사상자/사고는 거의 모든 지점이 1.0 언저리라 변별이 안 되는데, 중상
    비중은 0%에서 100%까지 벌어져 심각도 차이를 그대로 드러낸다."""
    fig, ax = plt.subplots(figsize=(9.6, 6.8))
    med_x = sorted(s["accidents"] for s in P["spots"])[len(P["spots"]) // 2]
    ax.set_xlim(0, max(s["accidents"] for s in P["spots"]) * 1.17)
    ax.set_ylim(-7, 112)
    ax.axvline(med_x, color=GRID, linewidth=1.2, zorder=0)
    ax.axhline(50, color=GRID, linewidth=1.2, zorder=0)
    ax.text(med_x + 0.25, 110, "사고 건수 중앙값 %d건" % med_x,
            fontsize=9.5, color=INK3, va="top")
    ax.text(0.3, 51.5, "중상 비중 50%", fontsize=9.5, color=INK3,
            ha="left", va="bottom")

    placed = []
    for s in sorted(P["spots"], key=lambda x: -x["accidents"]):
        _, idx = gkey(s)
        here = (s["accidents"], s["serious_rate"] * 100)
        ax.scatter(here[0], here[1], s=70 + 34 * s["casualties"],
                   color=SERIES3[idx], edgecolor="#ffffff", linewidth=1.6,
                   alpha=0.92, zorder=5)
        clash = any(abs(here[0] - p[0]) <= 3.6 and abs(here[1] - p[1]) <= 9
                    for p in placed)
        placed.append(here)
        ax.annotate("%d. %s" % (s["no"], s["short"]), here,
                    textcoords="offset points",
                    xytext=(11, -18 if clash else 10),
                    fontsize=9.5, color=INK, zorder=6)
    ax.set_xlabel("사고 건수(건)  →  자주 난다")
    ax.set_ylabel("사상자 중 중상 비중(%)  →  크게 다친다", labelpad=12)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.grid(True, linestyle=":")
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.legend(handles=[Line2D([], [], marker="o", linestyle="", markersize=10,
                              markerfacecolor=SERIES3[i],
                              markeredgecolor="#ffffff", label=n)
                       for i, n in enumerate(GROUP_NAMES)],
              frameon=False, fontsize=10.5, loc="upper left",
              bbox_to_anchor=(0.50, 0.90))
    ax.text(0.995, 0.015, "원의 크기 = 사상자 수", transform=ax.transAxes,
            ha="right", fontsize=9.5, color=INK3)
    return finish(fig, ax, "빈도-심각도 진단",
                  "오른쪽은 자주 나는 곳, 위쪽은 한 번 나면 크게 다치는 곳이다. "
                  "둘은 거의 겹치지 않는다 — 빈도 대책(단속·신호 운영)과 심각도 "
                  "대책(속도 억제·구조 개선)을 따로 세워야 한다는 뜻이다.",
                  SRC, "빈도심각도.png")


def fig07_camera_gap(P):
    cams = P["by_layer"].get("camera") or []
    ok = [s for s in P["spots"]
          if s["cam_km"] is not None and s["cam_km"] <= prep.GAP_KM]
    gap = P["gaps"]

    def draw(ax, zoom):
        ax.scatter([c["lon"] for c in cams], [c["lat"] for c in cams],
                   s=14 if zoom else 7, color="#b9c7d6", edgecolor="none",
                   zorder=4)
        ax.scatter([s["lon"] for s in ok], [s["lat"] for s in ok],
                   s=130 if zoom else 80, color=SERIES[0],
                   edgecolor="#ffffff", linewidth=1.5, zorder=6)
        ax.scatter([s["lon"] for s in gap], [s["lat"] for s in gap],
                   s=240 if zoom else 150, color=STATUS["critical"],
                   edgecolor="#ffffff", linewidth=1.8, marker="D", zorder=7)
        if zoom:
            numbers(ax, P["spots"])

    handles = [
        Line2D([], [], marker="o", linestyle="", markersize=6,
               markerfacecolor="#b9c7d6", markeredgecolor="none",
               label="무인단속장비 %d대" % len(cams)),
        Line2D([], [], marker="o", linestyle="", markersize=10,
               markerfacecolor=SERIES[0], markeredgecolor="#ffffff",
               label="장비 있음 (300m 이내) %d곳" % len(ok)),
        Line2D([], [], marker="D", linestyle="", markersize=10,
               markerfacecolor=STATUS["critical"], markeredgecolor="#ffffff",
               label="장비 공백 (300m 밖) %d곳" % len(gap)),
    ]
    return map_panels(
        P, draw, "사고다발지와 무인단속장비의 공간 불일치",
        "다발지 13곳 중 2곳이 반경 300m 안에 단속장비가 없다. 둘 다 "
        "조치원읍이고, 둘 다 중상 비중이 높은 지점이다 — 단기 사업의 1순위 근거.",
        "단속장비공백.png", handles,
        extra=lambda s: (" · 장비 %.0fm%s"
                         % ((s["cam_km"] or 0) * 1000,
                            "  ◀ 공백" if s in gap else "")))


def fig08_facility_matrix(P):
    cols = [("cam_km", "camera", "무인단속장비"),
            ("crosswalk_km", "crosswalk", "횡단보도"),
            ("light_km", "traffic_light", "신호등"),
            ("sign_km", "road_sign", "안전표지")]
    rows = list(P["spots"])
    fig, ax = plt.subplots(figsize=(9.0, 7.4))
    cap = 1200.0                      # 1.2km 넘으면 '멀다'로 뭉뚱그린다

    # 그 권역에 등록된 시설이 하나도 없으면 '먼 것'이 아니라 '모르는 것'이다.
    # 9km 라는 숫자를 접근성으로 읽으면 엉뚱한 결론이 나온다.
    def covered(s, layer):
        north = s["lat"] > 36.56
        return any((f["lat"] > 36.56) == north
                   for f in (P["by_layer"].get(layer) or []))

    for i, s in enumerate(rows):
        for j, (key, layer, _lab) in enumerate(cols):
            v = s.get(key)
            if v is None or not covered(s, layer):
                ax.add_patch(plt.Rectangle((j + 0.03, i + 0.03), 0.94, 0.94,
                                           facecolor="#f0efec",
                                           edgecolor=base.SURFACE, linewidth=2,
                                           hatch="///"))
                ax.text(j + 0.5, i + 0.5, "자료 없음", ha="center", va="center",
                        fontsize=9.0, color=INK3)
                continue
            m = min(v * 1000, cap)
            t = m / cap
            # 순차 램프 — 멀수록 진하다. 가장 밝은 단계도 바탕과 구분된다.
            color = BLUES[min(len(BLUES) - 1, int(t * len(BLUES)))]
            ax.add_patch(plt.Rectangle((j + 0.03, i + 0.03), 0.94, 0.94,
                                       facecolor=color, edgecolor=base.SURFACE,
                                       linewidth=2))
            ax.text(j + 0.5, i + 0.5, "%.0f" % (v * 1000),
                    ha="center", va="center", fontsize=9.5,
                    color="#ffffff" if t > 0.55 else INK)
    ax.set_xlim(0, len(cols))
    ax.set_ylim(0, len(rows))
    ax.set_xticks([j + 0.5 for j in range(len(cols))])
    ax.set_xticklabels([c[2] for c in cols], fontsize=11)
    ax.xaxis.tick_top()
    ax.set_yticks([i + 0.5 for i in range(len(rows))])
    ax.set_yticklabels([tag(s) for s in rows], fontsize=9.0)
    ax.invert_yaxis()
    for side in ax.spines.values():
        side.set_visible(False)
    ax.tick_params(length=0)
    ax.text(0.0, -0.05, "칸 안 숫자 = 그 지점에서 가장 가까운 시설까지 거리(m), "
                        "진할수록 멀다. 빗금 칸은 그 권역에 등록된 자료가 "
                        "아예 없는 경우로, 시설이 없다는 뜻이 아니다(그림 11).",
            transform=ax.transAxes, fontsize=9.5, color=INK3)
    return finish(fig, ax, "사고다발지별 안전시설 접근성",
                  "지점마다 모자란 시설이 다르다 — 지점별 사업 내역을 짜는 바탕이다.",
                  SRC, "시설접근성.png")


def fig09_vuln_zone(P):
    zones = ((P["by_layer"].get("child_zone") or [])
             + (P["by_layer"].get("elder_zone") or []))
    walks = P["by_layer"].get("crosswalk") or []
    vuln = [s for s in P["spots"] if gkey(s)[1] == 1]
    other = [s for s in P["spots"] if gkey(s)[1] != 1]

    def draw(ax, zoom):
        ax.scatter([z["lon"] for z in zones], [z["lat"] for z in zones],
                   s=40 if zoom else 20, color="#d9e6f6",
                   edgecolor="#9fbcdf", linewidth=0.5, zorder=4)
        ax.scatter([w["lon"] for w in walks], [w["lat"] for w in walks],
                   s=26 if zoom else 10, marker="s", color="#ffffff",
                   edgecolor=SERIES3[2], linewidth=1.0, zorder=5)
        ax.scatter([s["lon"] for s in other], [s["lat"] for s in other],
                   s=85 if zoom else 55, color="#c9c7c0",
                   edgecolor="#ffffff", linewidth=1.2, zorder=6)
        ax.scatter([s["lon"] for s in vuln], [s["lat"] for s in vuln],
                   s=215 if zoom else 130, color=SERIES3[1],
                   edgecolor="#ffffff", linewidth=1.8, zorder=7)
        if zoom:
            numbers(ax, vuln)

    handles = [
        Line2D([], [], marker="o", linestyle="", markersize=8,
               markerfacecolor="#d9e6f6", markeredgecolor="#9fbcdf",
               label="어린이·노인 보호구역 %d개소" % len(zones)),
        Line2D([], [], marker="s", linestyle="", markersize=7,
               markerfacecolor="#ffffff", markeredgecolor=SERIES3[2],
               label="횡단보도 %d개소(세종시 등록분)" % len(walks)),
        Line2D([], [], marker="o", linestyle="", markersize=10,
               markerfacecolor=SERIES3[1], markeredgecolor="#ffffff",
               label="보행 취약계층 다발지 %d곳" % len(vuln)),
        Line2D([], [], marker="o", linestyle="", markersize=8,
               markerfacecolor="#c9c7c0", markeredgecolor="#ffffff",
               label="그 밖의 다발지"),
    ]
    return map_panels(
        P, draw, "보행 취약계층 다발지와 보호구역·횡단보도",
        "취약계층 다발지 8곳은 보호구역 %d개소 사이사이의 교차로에 생긴다 — "
        "구역을 더 지정하는 일보다 진입부 처리가 과제다. 조치원읍에 횡단보도 "
        "표시가 하나도 없는 것은 실제가 아니라 자료 공백이다(그림 11)."
        % len(zones), "취약계층_보호구역.png", handles,
        extra=lambda s: " · 사상 %d명" % s["casualties"])


def fig10_priority(P):
    fig, ax = plt.subplots(figsize=(9.6, 7.0))
    xs = [s["accidents"] for s in P["spots"]]
    ys = [(s["cam_km"] or 0) * 1000 for s in P["spots"]]
    cx = sorted(xs)[len(xs) // 2]
    cy = prep.GAP_KM * 1000

    ax.axvspan(cx, max(xs) * 1.2, ymin=0, ymax=1, color="#f6f5f2", zorder=0)
    ax.axvline(cx, color=GRID, linewidth=1.2, zorder=1)
    ax.axhline(cy, color=STATUS["critical"], linewidth=1.2, linestyle="--",
               zorder=1)

    quad = [(0.985, 0.97, "① 즉시 개선\n잦고 · 장비 없음", "right", "top"),
            (0.015, 0.97, "② 시설 보완\n드물고 · 장비 없음", "left", "top"),
            (0.985, 0.03, "③ 운영 강화\n잦고 · 장비 있음", "right", "bottom"),
            (0.015, 0.03, "④ 모니터링\n드물고 · 장비 있음", "left", "bottom")]
    for x, y, t, ha, va in quad:
        ax.text(x, y, t, transform=ax.transAxes, ha=ha, va=va, fontsize=10.5,
                color=INK3, linespacing=1.5)

    placed = []
    for s in P["spots"]:
        label, idx = gkey(s)
        ax.scatter(s["accidents"], (s["cam_km"] or 0) * 1000,
                   s=70 + 120 * (s.get("serious") or 0), color=SERIES3[idx],
                   edgecolor="#ffffff", linewidth=1.6, zorder=6, alpha=0.92)
        if s["accidents"] >= cx or (s["cam_km"] or 0) * 1000 > cy:
            # 가까운 점끼리 이름표가 포개진다. 이미 붙인 이름표와 가까우면
            # 아래로 내린다(가로 1건, 세로 30m 안을 '가깝다'로 본다).
            here = (s["accidents"], (s["cam_km"] or 0) * 1000)
            clash = any(abs(here[0] - p[0]) <= 1 and abs(here[1] - p[1]) <= 30
                        for p in placed)
            placed.append(here)
            ax.annotate("%d. %s" % (s["no"], s["short"]), here,
                        textcoords="offset points",
                        xytext=(10, -19 if clash else 9),
                        fontsize=9.5, color=INK, zorder=7)
    ax.text(0.4, cy + 9, "장비 공백 기준 300m", color=STATUS["critical"],
            fontsize=9.5, va="bottom")
    ax.set_xlabel("사고 건수(건)")
    ax.set_ylabel("최근접 단속장비 거리(m)", labelpad=20)
    ax.set_xlim(0, max(xs) * 1.2)
    ax.grid(True, linestyle=":")
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.legend(handles=[Line2D([], [], marker="o", linestyle="", markersize=10,
                              markerfacecolor=SERIES3[i],
                              markeredgecolor="#ffffff", label=n)
                       for i, n in enumerate(GROUP_NAMES)],
              frameon=False, fontsize=10.5, loc="center right")
    return finish(fig, ax, "사업 우선순위 매트릭스",
                  "가로는 '얼마나 잦은가', 세로는 '단속장비가 얼마나 먼가'. "
                  "①사분면이 단기 사업 대상이고, ②는 시설 투자, ③은 운영·"
                  "단속 조정, ④는 관찰 대상이다. 원 크기는 중상자 수다.",
                  SRC, "우선순위매트릭스.png")


def fig11_data_status(P):
    d = P["raw"]
    k = d.get("koroad") or {}
    f = d.get("facility") or {}
    rows = []
    for l in k.get("layers") or []:
        rows.append(("사고", l["label"], "연동" if l.get("count") else "자료 없음",
                     "%d곳 · %d건 (%s년 공표)" % (l["count"], l.get("accidents") or 0,
                                               l.get("year") or "-")))
    for txt in k.get("unavailable") or []:
        name, _, why = txt.partition("(")
        rows.append(("사고", name.strip(), "제공 안 됨", why.rstrip(")")))
    for l in f.get("layers") or []:
        rows.append(("시설", l["label"], "연동",
                     "%d개소 · %s · 기준 %s" % (l["count"], l.get("origin") or "",
                                             l.get("ref_date") or "-")))
    for txt in f.get("unavailable") or []:
        name, _, why = txt.partition("(")
        rows.append(("시설", name.strip(), "제공 안 됨", why.rstrip(")")))
    its = d.get("its") or {}
    rows.append(("실시간", "ITS 소통정보", "연동" if its.get("ok") else "대기",
                 "표준링크 %s개 · 평균 %s km/h"
                 % ((its.get("summary") or {}).get("links", "-"),
                    (its.get("summary") or {}).get("avg_speed", "-"))))

    color = {"연동": STATUS["good"], "제공 안 됨": STATUS["critical"],
             "자료 없음": STATUS["warning"], "대기": STATUS["warning"]}
    mark = {"연동": "●", "제공 안 됨": "×", "자료 없음": "▲", "대기": "▲"}

    fig, ax = plt.subplots(figsize=(10.4, 0.42 * len(rows) + 2.0))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, len(rows))
    ax.invert_yaxis()
    ax.axis("off")
    for i, (cat, name, state, note) in enumerate(rows):
        if i % 2 == 0:
            ax.add_patch(plt.Rectangle((0, i), 1, 1, facecolor="#f6f5f2",
                                       edgecolor="none"))
        ax.text(0.012, i + 0.5, cat, va="center", fontsize=10, color=INK3)
        ax.text(0.075, i + 0.5, name, va="center", fontsize=10.5, color=INK)
        ax.text(0.345, i + 0.5, "%s %s" % (mark[state], state), va="center",
                fontsize=10.5, color=color[state])
        ax.text(0.50, i + 0.5, note, va="center", fontsize=10, color=INK2)
    return finish(fig, ax, "기초자료 연동 현황",
                  "상태는 색만이 아니라 기호와 글자로도 적는다. "
                  "'제공 안 됨'은 더 찾으면 되는 것이 아니라 공공데이터포털이 "
                  "REST로 주지 않거나 세종 자료가 등록되지 않은 항목이다.",
                  SRC, "자료연동현황.png")


def fig11_data_gap(P):
    """사고는 조치원에 몰렸는데 시설 자료는 신도심에만 있다. 분석 결과가
    아니라 자료의 구멍인데, 이걸 구분해 적지 않으면 '조치원엔 시설이 없다'는
    엉뚱한 결론이 나온다."""
    north = [s for s in P["spots"] if s["lat"] > 36.56]
    rows = [
        ("사고다발지", len(north), len(P["spots"]) - len(north), False),
        ("사고 건수", sum(s["accidents"] for s in north),
         sum(s["accidents"] for s in P["spots"]) - sum(s["accidents"] for s in north), False),
        ("중상자", sum(s.get("serious") or 0 for s in north),
         sum(s.get("serious") or 0 for s in P["spots"])
         - sum(s.get("serious") or 0 for s in north), False),
    ]
    for key, label in [("camera", "무인단속장비"), ("child_zone", "어린이보호구역"),
                       ("traffic_light", "신호등"), ("crosswalk", "횡단보도"),
                       ("road_sign", "도로안전표지")]:
        pts = P["by_layer"].get(key) or []
        n = sum(1 for q in pts if q["lat"] > 36.56)
        rows.append((label, n, len(pts) - n, n == 0))

    fig, ax = plt.subplots(figsize=(10.2, 6.2))
    y = list(range(len(rows)))[::-1]
    tot = [max(r[1] + r[2], 1) for r in rows]
    left = [100.0 * r[1] / t for r, t in zip(rows, tot)]
    right = [100.0 * r[2] / t for r, t in zip(rows, tot)]
    ax.barh(y, left, height=0.6, color=SERIES[1], label="조치원읍 일원",
            edgecolor=base.SURFACE, linewidth=2)
    ax.barh(y, right, height=0.6, left=left, color=SERIES[0],
            label="신도심 생활권", edgecolor=base.SURFACE, linewidth=2)
    for i, (name, a, b, zero) in zip(y, rows):
        ax.text(2.0, i, "%d" % a, va="center", fontsize=10,
                color="#ffffff" if a else STATUS["critical"],
                fontweight="bold" if zero else "normal")
        ax.text(98.0, i, "%d" % b, va="center", ha="right", fontsize=10,
                color="#ffffff")
        if zero:
            ax.text(101.5, i, "◀ 조치원 등록 0건", va="center", fontsize=10,
                    color=STATUS["critical"], fontweight="bold")
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows], fontsize=11)
    ax.set_xlim(0, 100)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.xaxis.grid(True, linestyle=":")
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.legend(frameon=False, fontsize=10.5, loc="lower center",
              bbox_to_anchor=(0.5, -0.15), ncols=2)
    return finish(fig, ax, "사고는 조치원, 자료는 신도심",
                  "막대 안 숫자는 실제 개수다. 조치원읍은 사고 건수의 절반 "
                  "가까이를 차지하는데 횡단보도·도로안전표지 등록은 0건이다. "
                  "현장에 시설이 없다는 뜻이 아니라 공개자료에 올라 있지 "
                  "않다는 뜻이다 — 기본계획의 첫 과제는 이 공백을 메우는 "
                  "전수조사다.",
                  SRC, "자료공백.png")


# 추이가 먼저다. '세종 전체가 나아지고 있는가'에 답한 다음에야
# '어디가 위험한가'가 뜻을 갖는다.
FIGURES = trend_figures.FIGURES + [fig01_hotspot_map, fig02_dong, fig03_type, fig04_spot_rank,
           fig05_severity, fig06_freq_severity, fig07_camera_gap,
           fig08_facility_matrix, fig09_vuln_zone, fig10_priority,
           fig11_data_gap, fig11_data_status]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(base.FIGDIR, exist_ok=True)
    P = prep.build()
    print("자료 — 다발지 %d곳 · 시설 %d개소 · 읍면동 %d"
          % (len(P["spots"]), len(P["items"]), len(P["dongs"])))
    for fn in FIGURES:
        fn(P)
    index_page.write(base.MADE, (P["raw"].get("generated_at") or "")[:10],
                     (len(P["spots"]), len(P["items"])))
    print("끝. 그림 %d장 + index.html" % len(base.MADE))


if __name__ == "__main__":
    main()

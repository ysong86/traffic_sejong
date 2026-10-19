# -*- coding: utf-8 -*-
"""세종시 **전체** 교통사고의 연도별 추이 그림.

다발지역 그림들이 '어디가 위험한가'에 답한다면, 이쪽은 '세종 전체가 나아지고
있는가'에 답한다. 기본계획이 목표를 세우려면 이 축이 먼저다.
"""
from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

import base
from base import GRID, INK, INK2, INK3, SERIES, SERIES3, STATUS, finish

SRC = ("자료 — 도로교통공단 지자체별 대상 교통사고 통계(2017~2025년) / "
       "작성 세종연구원 도시안전연구센터")


def val(series, year, key):
    return (series.get(str(year)) or {}).get(key)


def _spark(ax, years, vals, color, ylab, fmt="%d", last_note=""):
    ax.plot(years, vals, color=color, linewidth=2.4, marker="o",
            markersize=7, markerfacecolor="#ffffff",
            markeredgecolor=color, markeredgewidth=2, zorder=5)
    # 처음과 끝에만 값을 적는다. 모든 점에 숫자를 달면 선이 안 보인다.
    for i in (0, len(years) - 1):
        ax.annotate(fmt % vals[i], (years[i], vals[i]),
                    textcoords="offset points", xytext=(0, 13),
                    ha="center", fontsize=10.5, fontweight="bold", color=INK)
    ax.set_title(ylab, fontsize=12, fontweight="bold", color=INK2, loc="left",
                 pad=30)
    ax.set_xticks(years[::2])
    ax.set_xlim(years[0] - 0.4, years[-1] + 0.4)
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.28 or 1
    ax.set_ylim(max(0, lo - pad), hi + pad * 1.25)
    ax.grid(True, axis="y", linestyle=":")
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(left=False)
    ax.set_yticks([])
    if last_note:
        ax.text(0.0, 1.012, last_note, transform=ax.transAxes, fontsize=10,
                color=INK3, va="bottom")


def fig_trend(P):
    """사고·사망·치사율을 **각각 제 축**에 그린다. 눈금이 다른 값을 한 그림에
    겹쳐 그리는 것(이중축)은 거의 언제나 읽는 사람을 속인다."""
    st = P["raw"].get("stat") or {}
    years = st.get("years") or []
    tot = (st.get("series") or {}).get("전체사고") or {}
    if not years:
        return None
    acc = [val(tot, y, "acc") or 0 for y in years]
    dth = [val(tot, y, "dth") or 0 for y in years]
    ftlt = [val(tot, y, "ftlt") or 0 for y in years]

    fig, axes = plt.subplots(1, 3, figsize=(14.0, 4.9))
    _spark(axes[0], years, acc, SERIES[0], "사고 건수(건)",
           last_note="%d → %d, %+.0f%%" % (acc[0], acc[-1],
                                           100.0 * (acc[-1] - acc[0]) / acc[0]))
    _spark(axes[1], years, dth, STATUS["critical"], "사망자(명)",
           last_note="%d → %d명" % (dth[0], dth[-1]))
    _spark(axes[2], years, ftlt, SERIES[2], "치사율(사고 100건당 사망자)",
           fmt="%.2f", last_note="%.2f → %.2f" % (ftlt[0], ftlt[-1]))
    # 머리말이 두 줄이라 위를 넉넉히 비워야 패널 제목과 안 겹친다.
    fig.subplots_adjust(wspace=0.16, bottom=0.12,
                        top=0.88 if base.BARE else 0.60)
    return finish(fig, None, "세종시 교통사고 추이",
                  "사고는 늘고 사망자·치사율은 줄었다. 도시가 커지며 통행량이 "
                  "는 것과 사고 한 건의 결과가 가벼워진 것이 같이 들어 있다 — "
                  "기본계획 목표는 건수가 아니라 사망자·치사율로 잡아야 한다.",
                  SRC, "사고추이.png")


def fig_type_change(P):
    """유형별로 얼마나 늘고 줄었는가. 기본계획이 어디에 힘을 실어야 하는지를
    한 장으로 보여 주는 그림이다."""
    st = P["raw"].get("stat") or {}
    years = st.get("years") or []
    series = st.get("series") or {}
    if len(years) < 2:
        return None
    y0, y1 = years[0], years[-1]

    rows = []
    for name, v in series.items():
        if name == "전체사고":
            continue
        a0, a1 = val(v, y0, "acc"), val(v, y1, "acc")
        if not a0 or a1 is None or a0 < 10:      # 표본이 너무 작으면 비율이 튄다
            continue
        rows.append((name, a0, a1, 100.0 * (a1 - a0) / a0))
    rows.sort(key=lambda r: r[3])

    fig, ax = plt.subplots(figsize=(10.4, 0.52 * len(rows) + 2.6))
    y = list(range(len(rows)))
    # 증감은 방향이 있는 값이라 두 색으로 가른다. 가운데는 0.
    colors = [STATUS["critical"] if r[3] > 0 else SERIES[0] for r in rows]
    ax.barh(y, [r[3] for r in rows], height=0.6, color=colors)
    for i, (name, a0, a1, pct) in zip(y, rows):
        off = 3 if pct > 0 else -3
        ax.text(pct + off, i, "%+.0f%%  (%d → %d건)" % (pct, a0, a1),
                va="center", ha="left" if pct > 0 else "right",
                fontsize=10, color=INK2)
    ax.axvline(0, color=INK3, linewidth=1.2)
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows], fontsize=11)
    lim = max(abs(r[3]) for r in rows) * 1.7
    ax.set_xlim(-lim * 0.55, lim)
    ax.set_xticks([])
    for side in ax.spines.values():
        side.set_visible(False)
    ax.tick_params(length=0)
    return finish(fig, ax, "사고 유형별 증감 (%d년 → %d년)" % (y0, y1),
                  "고령운전자 사고가 %d건에서 %d건으로 가장 크게 늘었다. "
                  "세종시 인구가 느는 동안에도 유형마다 방향이 달랐다 — "
                  "늘어난 쪽에 사업을 거는 것이 기본계획의 출발점이다."
                  % (val(series.get("고령운전자사고", {}), y0, "acc") or 0,
                     val(series.get("고령운전자사고", {}), y1, "acc") or 0),
                  SRC, "유형별증감.png")


def fig_vuln_trend(P):
    """취약계층 세 유형의 추이. 기본계획 지표와 바로 맞물린다."""
    st = P["raw"].get("stat") or {}
    years = st.get("years") or []
    series = st.get("series") or {}
    picks = [("고령자사고", "고령자"), ("보행자사고", "보행자"),
             ("어린이사고", "어린이")]
    if not years:
        return None

    fig, ax = plt.subplots(figsize=(10.6, 6.0))
    for i, (key, label) in enumerate(picks):
        v = series.get(key) or {}
        vals = [val(v, y, "acc") or 0 for y in years]
        ax.plot(years, vals, color=SERIES3[i], linewidth=2.6, marker="o",
                markersize=7, markerfacecolor="#ffffff",
                markeredgecolor=SERIES3[i], markeredgewidth=2, zorder=5)
        # 선 끝에 이름을 직접 붙인다. 범례를 오가며 읽지 않아도 되게.
        ax.annotate("  %s %d건" % (label, vals[-1]), (years[-1], vals[-1]),
                    textcoords="offset points", xytext=(8, 0), va="center",
                    fontsize=11, fontweight="bold", color=SERIES3[i])
    ax.set_xticks(years)
    ax.set_xlim(years[0] - 0.3, years[-1] + 1.6)
    ax.set_ylim(0, None)
    ax.set_ylabel("사고 건수(건)", labelpad=10)
    ax.grid(True, axis="y", linestyle=":")
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.legend(handles=[Line2D([], [], color=SERIES3[i], linewidth=2.6,
                              marker="o", markersize=7,
                              markerfacecolor="#ffffff",
                              markeredgecolor=SERIES3[i], label=lab)
                       for i, (_k, lab) in enumerate(picks)],
              frameon=False, fontsize=10.5, loc="upper left", ncols=3)
    return finish(fig, ax, "취약계층 사고 추이",
                  "셋 다 2022년을 지나며 뚜렷이 늘었다. 고령자 사고는 "
                  "2017년 %d건에서 %d년 %d건이 됐다 — 보호구역 지정만으로는 "
                  "잡히지 않는 흐름이다."
                  % (val(series.get("고령자사고", {}), years[0], "acc") or 0,
                     years[-1],
                     val(series.get("고령자사고", {}), years[-1], "acc") or 0),
                  SRC, "취약계층추이.png")


FIGURES = [fig_trend, fig_type_change, fig_vuln_trend]

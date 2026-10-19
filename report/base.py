# -*- coding: utf-8 -*-
"""기본계획 보고용 그림의 공통 바탕 — 색·글꼴·지도 투영·자료 읽기.

색은 **검증된 기준 팔레트를 그대로** 쓴다(슬롯 순서까지). 순서 자체가
색각이상 안전장치라, 보기 좋다고 섞으면 그 보장이 깨진다. 산점도·버블처럼
모든 쌍이 한 화면에 놓이는 그림은 문서가 정한 3슬롯 상한을 지킨다.

보고서에 붙일 그림이라 상호작용은 없다. 대신 범례와 직접 라벨로 식별이
색에만 기대지 않게 한다.
"""
from __future__ import annotations

import json
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIGDIR = os.path.join(HERE, "figures")

# ── 색 ────────────────────────────────────────────────────────────────────
SURFACE = "#fcfcfb"          # 검증이 이 표면색 기준이다. 흰색으로 바꾸지 말 것.
INK = "#0b0b0b"
INK2 = "#52514e"
INK3 = "#8a8880"
GRID = "#e6e5e1"

# 기준 팔레트의 고정 슬롯 순서. 인접쌍 기준으로 8슬롯까지 안전하다(막대·누적).
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
          "#e87ba4", "#008300", "#6250d6", "#e34948"]
# 모든 쌍이 동시에 보이는 그림(산점도·버블·지도)은 앞 3슬롯까지만.
SERIES3 = SERIES[:3]

STATUS = {"good": "#0ca30c", "warning": "#fab219",
          "serious": "#ec835a", "critical": "#d03b3b"}

# 연속값(크기·밀도)용 단일 색상 램프 — 밝은 쪽이 0에 가깝다.
BLUES = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"]


def _font():
    for name in ("malgun.ttf", "malgunbd.ttf"):
        path = os.path.join(r"C:\Windows\Fonts", name)
        if os.path.exists(path):
            fm.fontManager.addfont(path)
    return "Malgun Gothic"


FONT = _font()
plt.rcParams.update({
    "font.family": FONT,
    "axes.unicode_minus": False,       # 한글 글꼴엔 유니코드 마이너스가 없다
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "text.color": INK,
    "axes.labelcolor": INK2,
    "xtick.color": INK2,
    "ytick.color": INK2,
    "axes.edgecolor": GRID,
    "axes.linewidth": 0.8,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "font.size": 11,
})


# ── 자료 ──────────────────────────────────────────────────────────────────

def load(name: str):
    with open(os.path.join(ROOT, name), encoding="utf-8") as fp:
        return json.load(fp)


def data() -> dict:
    return load("data/latest.json")


def admin() -> dict:
    return load("assets/sejong_admin.json")


def roads() -> list:
    return load("assets/sejong_roads.json")["roads"]


# ── 지리 ──────────────────────────────────────────────────────────────────

def km(lat1, lon1, lat2, lon2) -> float:
    """두 점 사이 거리(km). 세종 정도 범위면 이 근사로 충분하다."""
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def in_ring(lon, lat, ring) -> bool:
    """광선 교차법. 읍면동 경계 안인지 본다."""
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > lat) != (y2 > lat):
            xx = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < xx:
                inside = not inside
    return inside


def dong_of(lon, lat, dongs) -> str:
    for d in dongs:
        for ring in d["rings"]:
            if in_ring(lon, lat, ring):
                return d["name"]
    return "경계 밖"


# ── 지도 그리기 ────────────────────────────────────────────────────────────

def basemap(ax, show_roads=True, road_classes=("expressway", "brt", "arterial")):
    """읍면동 경계와 주요 도로를 깔고 축을 잠근다.

    위도에 따라 경도 1도의 실제 길이가 줄어든다. 그대로 그리면 세종이 옆으로
    늘어나므로 가로세로비를 cos(위도)로 보정한다.
    """
    adm = admin()
    lat0 = 36.52
    ax.set_aspect(1.0 / math.cos(math.radians(lat0)))

    for ring in adm["outline"]:
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        ax.fill(xs, ys, facecolor="#ffffff", edgecolor="none", zorder=0)

    if show_roads:
        style = {"expressway": (1.5, "#cfcdc6"), "brt": (1.2, "#d8d6cf"),
                 "arterial": (0.9, "#e0dfd9"), "sub": (0.6, "#e8e7e2")}
        for road in roads():
            if road["cls"] not in road_classes:
                continue
            w, c = style.get(road["cls"], (0.6, "#e8e7e2"))
            for line in road["lines"]:
                ax.plot([p[0] for p in line], [p[1] for p in line],
                        color=c, linewidth=w, solid_capstyle="round", zorder=1)

    for d in adm["dongs"]:
        for ring in d["rings"]:
            xs = [p[0] for p in ring]
            ys = [p[1] for p in ring]
            ax.plot(xs + xs[:1], ys + ys[:1], color="#c9c7c0", linewidth=0.7,
                    zorder=2)

    for ring in adm["outline"]:
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        ax.plot(xs + xs[:1], ys + ys[:1], color="#9a988f", linewidth=1.4,
                zorder=3)

    ax.set_xlim(127.11, 127.43)
    ax.set_ylim(36.39, 36.75)
    ax.set_xticks([])
    ax.set_yticks([])
    for side in ax.spines.values():
        side.set_visible(False)
    return adm


# 사고다발지는 조치원읍과 신도심 두 덩어리에 몰려 있다. 시 전체를 한 장에
# 그리면 점이 두 점처럼 뭉쳐 이름표가 서로 겹친다. 전체 지도 한 장 + 확대
# 두 장으로 나눠 그린다 — 전체는 '어디인지', 확대는 '무엇인지'를 맡는다.
CLUSTERS = [("조치원읍 일원", 36.56, 90.0), ("신도심 생활권", -90.0, 36.56)]


def cluster_bounds(spots, lat_min, lat_max, pad=0.013):
    pts = [s for s in spots if lat_min <= s["lat"] <= lat_max]
    if not pts:
        return None
    lo = min(s["lon"] for s in pts) - pad
    hi = max(s["lon"] for s in pts) + pad
    la = min(s["lat"] for s in pts) - pad
    lb = max(s["lat"] for s in pts) + pad
    # 너무 납작하거나 홀쭉하면 보기 나쁘다. 최소 크기를 준다.
    if hi - lo < 0.030:
        c = (hi + lo) / 2
        lo, hi = c - 0.015, c + 0.015
    if lb - la < 0.024:
        c = (lb + la) / 2
        la, lb = c - 0.012, c + 0.012
    return lo, la, hi, lb


def panel_layout(fig):
    """왼쪽부터 지점 목록 · 전체 지도 · 확대 두 장.

    목록을 지도 위에 얹었더니 경계선과 이름표를 덮었다. 글과 그림이 자리를
    다투면 둘 다 진다 — 칸을 따로 준다.
    """
    gs = fig.add_gridspec(2, 3, width_ratios=[0.86, 1.18, 1.0], wspace=0.03,
                          hspace=0.06)
    ax_list = fig.add_subplot(gs[:, 0])
    ax_list.axis("off")
    return ax_list, fig.add_subplot(gs[:, 1]), fig.add_subplot(gs[0, 2]), \
        fig.add_subplot(gs[1, 2])


def zoom_to(ax, box, title=""):
    lo, la, hi, lb = box
    ax.set_xlim(lo, hi)
    ax.set_ylim(la, lb)
    for side in ax.spines.values():
        side.set_visible(True)
        side.set_color("#c9c7c0")
    if title:
        ax.text(0.02, 0.965, title, transform=ax.transAxes, va="top",
                fontsize=11, fontweight="bold", color=INK2, zorder=10,
                bbox=dict(boxstyle="round,pad=0.26", fc="#ffffff", ec="none",
                          alpha=0.88))


def mark_box(ax, box, label):
    """전체 지도 위에 확대 범위를 네모로 표시한다."""
    lo, la, hi, lb = box
    ax.add_patch(plt.Rectangle((lo, la), hi - lo, lb - la, fill=False,
                               edgecolor=INK2, linewidth=1.1,
                               linestyle=(0, (4, 2)), zorder=8))
    ax.text((lo + hi) / 2, lb + 0.006, label, ha="center", fontsize=10,
            color=INK2, zorder=8)


def scalebar(ax, km_len=5, x=127.135, y=36.405):
    """축척 막대. 지도에서 '얼마나 먼가'를 눈으로 가늠하게 한다."""
    deg = km_len / (111.32 * math.cos(math.radians(36.52)))
    ax.plot([x, x + deg], [y, y], color=INK2, linewidth=2.4,
            solid_capstyle="butt", zorder=9)
    ax.text(x + deg / 2, y + 0.006, "%d km" % km_len, ha="center",
            fontsize=9, color=INK2, zorder=9)


# ── 마무리 ────────────────────────────────────────────────────────────────

# 만든 그림 목록 — 끝에 index.html 을 짜는 데 쓴다.
MADE = []


def finish(fig, ax_or_none, title, subtitle="", source="", fname=""):
    # 번호는 만들어진 차례대로 붙인다 — 순서를 바꿔도 제목과 파일명이 따라온다.
    seq = len(MADE) + 1
    title = "[그림 %d] %s" % (seq, title)
    fname = "%02d_%s" % (seq, fname)
    """제목·부제·출처를 한 자리에서 붙이고 저장한다.

    출처를 그림 안에 박아 두는 이유 — 보고서에 그림만 떼어 가도 근거가 따라
    가야 한다. 떼어 낸 그림의 출처를 나중에 다시 찾는 일이 제일 번거롭다.
    """
    fig.suptitle(title, fontsize=15.5, fontweight="bold", color=INK,
                 x=0.012, ha="left", y=0.975)
    if subtitle:
        fig.text(0.012, 0.930, subtitle, fontsize=10.5, color=INK2, ha="left",
                 va="top", wrap=True)
    if source:
        fig.text(0.012, 0.012, source, fontsize=8.5, color=INK3, ha="left")
    path = os.path.join(FIGDIR, fname)
    fig.savefig(path, dpi=200, bbox_inches="tight", pad_inches=0.22)
    plt.close(fig)
    size = os.path.getsize(path) // 1024
    MADE.append({"title": title, "subtitle": subtitle, "file": fname,
                 "kb": size})
    print("  %-34s %4d KB" % (fname, size))
    return path

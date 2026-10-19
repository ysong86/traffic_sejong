# -*- coding: utf-8 -*-
"""그림 모음 페이지 — 보고서에 넣기 전에 한눈에 훑고 고르는 용도.

그림마다 제목·설명과 함께 **이 그림이 무슨 사업을 뒷받침하는가**를 적는다.
기본계획에서 그림이 하는 일은 예쁜 것이 아니라 사업을 정당화하는 것이다.
"""
from __future__ import annotations

import html
import os

import base

# 그림 → 그 그림이 받쳐 주는 사업.
#
# **번호가 아니라 파일 이름(슬러그)으로 묶는다.** 전에 번호로 묶었다가 그림
# 순서를 바꾸는 순간 설명이 통째로 한 칸씩 밀렸다. 번호는 만들어진 차례대로
# 자동으로 붙는 값이라 묶는 열쇠로 쓰면 안 된다.
USE = {
    "사고추이": ("기본계획 목표 설정",
              "건수는 늘고 치사율은 내렸다. 목표를 건수가 아니라 사망자·치사율로 "
              "잡아야 하는 근거."),
    "유형별증감": ("중점 과제 선정",
               "고령운전자 사고가 +284%로 가장 크게 늘었다. 어디에 힘을 실을지 "
               "가르는 그림."),
    "취약계층추이": ("취약계층 보호 사업",
                "고령·보행자·어린이 모두 2022년 이후 증가. 보호구역 지정만으로는 "
                "잡히지 않는 흐름."),
    "다발지분포": ("사업 대상지 선정",
               "13곳을 조치원·신도심 두 권역으로 나눠 권역별 사업을 따로 세운다."),
    "읍면동별사고": ("권역별 예산 배분",
                "조치원읍 한 곳에 사고의 48%가 몰린다. 균등 배분하면 안 된다는 근거."),
    "유형별구성": ("지점 사업 유형 결정",
               "보행 취약계층 유형이 지점의 과반. 차량 소통보다 보행 환경이 먼저다."),
    "지점순위": ("1차년도 집중 대상 3곳",
              "상위 3곳이 사고의 절반 이상. 사업 대상을 좁히는 근거."),
    "상해정도": ("사업 성격 구분",
              "중상 비중 100% 지점은 '건수 저감'이 아니라 '속도·충돌각도' 사업 대상."),
    "빈도심각도": ("대책 유형 분기",
               "빈도형과 심각도형이 겹치지 않는다. 단속 사업과 구조개선 사업을 "
               "나눠 편성."),
    "단속장비공백": ("무인단속장비 신설·이설",
                "300m 내 장비 없는 2곳 — 장비 사업의 직접 근거."),
    "시설접근성": ("지점별 사업 내역 작성",
               "지점마다 모자란 시설이 다르다. 내역서를 만드는 바탕."),
    "취약계층_보호구역": ("보호구역 진입부 개선",
                   "구역 추가 지정이 아니라 둘레 교차로 처리로 방향을 돌리는 근거."),
    "우선순위매트릭스": ("연차별 사업 배치",
                  "①즉시 개선 → ②시설 투자 → ③운영 강화 → ④모니터링으로 "
                  "연차를 가른다."),
    "자료공백": ("교통안전시설 전수조사",
              "사고가 가장 많은 조치원에 시설 자료가 0건. 1차년도 기초조사 사업."),
    "자료연동현황": ("자료 확보 과제",
                "부록. 어떤 자료가 되고 안 되는지, 왜 안 되는지를 밝혀 둔다."),
}


def slug(fname: str) -> str:
    """'04_다발지분포.png' → '다발지분포'. 번호와 확장자를 떼어 낸다."""
    return fname.split("_", 1)[-1].rsplit(".", 1)[0]


CSS = """
:root{--bg:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--ink3:#8a8880;
      --line:#e6e5e1;--accent:#2a78d6;--warn:#d03b3b}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
     font-family:"Malgun Gothic","맑은 고딕",system-ui,sans-serif;
     line-height:1.65;-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:40px 24px 80px}
h1{font-size:27px;font-weight:800;letter-spacing:-.03em;margin:0 0 6px}
.lead{color:var(--ink2);font-size:15px;margin:0 0 6px}
.meta{color:var(--ink3);font-size:13px;margin:0 0 30px}
.note{border:1px solid var(--line);border-left:3px solid var(--accent);
      background:#fff;border-radius:7px;padding:14px 18px;margin:0 0 34px;
      font-size:14px;color:var(--ink2)}
.note b{color:var(--ink)}
figure{margin:0 0 42px;border:1px solid var(--line);border-radius:10px;
       background:#fff;overflow:hidden}
figure img{display:block;width:100%;height:auto}
figcaption{padding:16px 20px 18px;border-top:1px solid var(--line)}
figcaption h2{font-size:17px;font-weight:700;margin:0 0 5px}
figcaption p{margin:0;color:var(--ink2);font-size:14px}
.use{margin-top:12px;padding-top:11px;border-top:1px dashed var(--line);
     font-size:13.5px;color:var(--ink2)}
.use b{color:var(--accent)}
.toc{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));
     gap:8px 18px;margin:0 0 36px;padding:0;list-style:none}
.toc a{color:var(--ink2);text-decoration:none;font-size:13.5px}
.toc a:hover{color:var(--accent);text-decoration:underline}
footer{margin-top:50px;padding-top:18px;border-top:1px solid var(--line);
       color:var(--ink3);font-size:12.5px}
@media print{.toc,.note{break-inside:avoid}figure{break-inside:avoid;border:none}}
"""


def write(made, stamp, counts):
    rows, toc = [], []
    for m in made:
        key = slug(m["file"])
        use = USE.get(key)
        anchor = m["file"][:2]
        toc.append('<li><a href="#f%s">%s</a></li>'
                   % (anchor, html.escape(m["title"])))
        used = ""
        if use:
            used = ('<div class="use"><b>%s</b> — %s</div>'
                    % (html.escape(use[0]), html.escape(use[1])))
        rows.append(
            '<figure id="f%s"><img src="figures/%s" alt="%s" loading="lazy">'
            '<figcaption><h2>%s</h2><p>%s</p>%s</figcaption></figure>'
            % (anchor, m["file"], html.escape(m["title"]),
               html.escape(m["title"]), html.escape(m["subtitle"]), used))

    doc = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>세종시 교통안전 기본계획 분석 그림</title>
<style>%s</style></head><body><div class="wrap">
<h1>세종시 교통안전 기본계획 — 분석 그림</h1>
<p class="lead">교통안전 상황판이 모아 둔 실측 자료로 만든 그림 %d장입니다.
그림마다 제목·설명과 함께 <b>어떤 사업을 뒷받침하는지</b>를 적었습니다.</p>
<p class="meta">자료 기준 %s · 사고다발지 %d곳 · 안전시설 %d개소 ·
작성 세종연구원 도시안전연구센터</p>

<div class="note">
<b>그림을 읽기 전에.</b> 모든 숫자는 공공데이터포털에서 받은 실측값이고
상황판 화면의 숫자와 같습니다. 다만 두 가지를 먼저 아셔야 합니다.<br><br>
① <b>사고 자료는 '다발지역'만 있습니다.</b> 도로교통공단이 공개하는 것은
일정 기준(반경 200m 안 일정 건수 이상)을 넘은 지점뿐이라, 세종시 전체
사고 건수가 아닙니다. 연도별 추이·시간대·연령대 분석은 '지자체별 교통사고
통계' API 활용신청이 승인되어야 가능합니다(그림 12).<br>
② <b>시설 자료에 지역 편중이 있습니다.</b> 횡단보도·도로안전표지는 세종시가
등록한 신도심 분만 있습니다. 조치원읍이 0건인 것은 현장에 없다는 뜻이
아닙니다(그림 11).
</div>

<ul class="toc">%s</ul>
%s
<footer>세종연구원 도시안전연구센터 · 문의 ayj826@sri.re.kr<br>
그림 원본은 <code>report/figures/</code> 에 PNG(200dpi)로 있습니다.
<code>python report/make_figures.py</code> 로 다시 만들 수 있습니다.</footer>
</div></body></html>""" % (CSS, len(made), stamp, counts[0], counts[1],
                           "".join(toc), "".join(rows))

    path = os.path.join(base.HERE, "index.html")
    with open(path, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(doc)
    print("  %-34s %4d KB" % ("index.html", os.path.getsize(path) // 1024))
    return path

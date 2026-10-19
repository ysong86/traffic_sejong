# -*- coding: utf-8 -*-
"""결과보고서 — 그림을 본문에 끼워 넣은 워드 문서.

    C:\\Python313\\python.exe -I report/make_report.py
      → report/세종시_교통안전_기본계획_분석결과보고서.docx

그림 목록(make_doc.py)과 다른 점
  목록은 캡션만 모은 것이고, 이쪽은 **읽히는 보고서**다. 현황 → 진단 →
  사업 도출 → 자료 한계 순으로 글이 흐르고 그림이 그 사이에 들어간다.

숫자는 모두 data/latest.json 에서 꺼내 쓴다. 보고서에 손으로 적은 숫자가
섞이면 다음에 자료가 바뀔 때 어디를 고쳐야 하는지 알 수 없게 된다.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

import base
import index_page
import make_doc
from make_doc import INK, INK2, INK3, _hangul, para, rule

ACCENT = RGBColor(0x1C, 0x5C, 0xAB)
WARN = RGBColor(0xB0, 0x2A, 0x2A)
FIG_WIDTH = Cm(16.2)          # 본문 폭에 맞춘다(A4, 좌우 여백 2.4cm)


def val(series, year, key):
    return (series.get(str(year)) or {}).get(key)


def heading(doc, text, size=15):
    p = para(doc, text, size, True, INK, 6)
    p.paragraph_format.space_before = Pt(18)
    return p


def bullet(doc, text, size=10.5):
    para(doc, "· " + text, size, False, INK2, 5, indent=0.45)


def figure(doc, made_by_slug, slug, note=""):
    """그림 + 캡션. 캡션은 그림 아래에 둔다(보고서 관례)."""
    m = made_by_slug.get(slug)
    if not m:
        return
    path = os.path.join(base.FIGDIR, m["file"])
    if not os.path.exists(path):
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)
    p.add_run().add_picture(path, width=FIG_WIDTH)

    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_after = Pt(4)
    r = cap.add_run(m["title"])
    r.font.size = Pt(10)
    r.font.bold = True
    r.font.color.rgb = INK
    _hangul(r)

    para(doc, m["subtitle"], 9.5, False, INK2, 4, align=WD_ALIGN_PARAGRAPH.CENTER)
    if note:
        para(doc, note, 10.5, False, INK2, 10)
    if m.get("source"):
        para(doc, m["source"], 8, False, INK3, 14,
             align=WD_ALIGN_PARAGRAPH.CENTER)


def build(P, made):
    by_slug = {index_page.slug(m["file"]): m for m in made}
    st = P["raw"].get("stat") or {}
    years = st.get("years") or []
    series = st.get("series") or {}
    tot = series.get("전체사고") or {}
    y0, y1 = (years[0], years[-1]) if years else (0, 0)

    def t(year, key):
        return val(tot, year, key)

    spots = P["spots"]
    north = [s for s in spots if s["lat"] > 36.56]
    acc_n = sum(s["accidents"] for s in north)
    acc_all = sum(s["accidents"] for s in spots)
    ser_n = sum(s.get("serious") or 0 for s in north)
    ser_all = sum(s.get("serious") or 0 for s in spots)

    doc = Document()
    for section in doc.sections:
        section.left_margin = section.right_margin = Cm(2.4)
        section.top_margin = section.bottom_margin = Cm(2.2)
    style = doc.styles["Normal"]
    style.font.name = make_doc.FONT
    style.font.size = Pt(10.5)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), make_doc.FONT)

    # ── 표지 ──────────────────────────────────────────────────────────
    para(doc, "세종시 교통안전 기본계획", 14, False, INK3, 2)
    para(doc, "교통사고 현황 분석 결과보고서", 22, True, INK, 8)
    para(doc, "공공데이터 기반 사고 진단과 사업 도출 근거", 12, False, INK2, 20)
    rule(doc)
    para(doc, "작성  세종연구원 도시안전연구센터", 10.5, False, INK2, 2)
    para(doc, "자료 기준  %s · 사고통계 %d~%d년 · 사고다발지 %d곳 · 안전시설 %d개소"
         % ((P["raw"].get("generated_at") or "")[:10], y0, y1,
            len(spots), len(P["items"])), 10, False, INK3, 2)
    para(doc, "문의  ayj826@sri.re.kr", 10, False, INK3, 16)

    # ── 요약 ──────────────────────────────────────────────────────────
    heading(doc, "요약")
    if years:
        bullet(doc, "세종시 교통사고는 %d년 %s건에서 %d년 %s건으로 %+.0f%% "
                    "늘었다. 같은 기간 사망자는 %s명에서 %s명으로, 치사율은 "
                    "%.2f에서 %.2f로 줄었다."
               % (y0, "{:,}".format(t(y0, "acc")), y1,
                  "{:,}".format(t(y1, "acc")),
                  100.0 * (t(y1, "acc") - t(y0, "acc")) / t(y0, "acc"),
                  t(y0, "dth"), t(y1, "dth"), t(y0, "ftlt"), t(y1, "ftlt")))
        bullet(doc, "건수가 늘어난 것은 도시가 커지며 통행량이 늘어난 결과를 "
                    "포함한다. 따라서 기본계획 목표는 사고 건수가 아니라 "
                    "사망자와 치사율로 잡는 것이 타당하다.")
        drv = series.get("고령운전자사고") or {}
        if val(drv, y0, "acc"):
            bullet(doc, "유형별로는 고령운전자 사고가 %d건에서 %d건으로 "
                        "%+.0f%% 늘어 가장 큰 폭의 증가를 보였다. 고령자·"
                        "고령보행자 사고도 함께 늘었다."
                   % (val(drv, y0, "acc"), val(drv, y1, "acc"),
                      100.0 * (val(drv, y1, "acc") - val(drv, y0, "acc"))
                      / val(drv, y0, "acc")))
    bullet(doc, "사고다발지 %d곳은 조치원읍 %d곳과 신도심 생활권 %d곳 두 "
                "덩어리로 나뉜다. 조치원읍이 사고의 %.0f%%, 중상자의 %.0f%%를 "
                "차지한다."
           % (len(spots), len(north), len(spots) - len(north),
              100.0 * acc_n / acc_all, 100.0 * ser_n / ser_all))
    bullet(doc, "그런데 조치원읍은 횡단보도·도로안전표지 공개자료가 0건이다. "
                "현장에 시설이 없다는 뜻이 아니라 자료가 등록되지 않았다는 "
                "뜻이며, 이 공백을 메우는 전수조사가 1차년도 과제가 된다.")

    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # ── 1. 현황 ───────────────────────────────────────────────────────
    heading(doc, "1. 교통사고 현황")
    para(doc, "세종시 전체 사고의 연도별 추이를 먼저 본다. 뒤에 나오는 "
              "사고다발지 분석은 ‘어디가 위험한가’에 답하지만, ‘세종이 "
              "나아지고 있는가’에는 이 통계만 답할 수 있다.", 10.5, False, INK, 8)
    figure(doc, by_slug, "사고추이",
           "사고 건수와 사망자가 서로 다른 방향으로 움직인다. 건수만 보면 "
           "악화로, 사망자만 보면 개선으로 읽힌다. 둘을 함께 놓고 치사율로 "
           "판단해야 한다.")
    figure(doc, by_slug, "유형별증감",
           "증가한 유형과 감소한 유형이 뚜렷이 갈린다. 뺑소니·무면허·"
           "어린이보행은 줄었고, 고령 관련 유형과 자전거가 크게 늘었다. "
           "사업의 무게를 어디에 둘지가 여기서 정해진다.")
    figure(doc, by_slug, "취약계층추이",
           "세 유형 모두 2022년을 지나며 증가로 돌아섰다. 보호구역 지정 "
           "확대만으로는 설명되지 않는 흐름이며, 고령 인구 증가와 생활권 "
           "확장이 함께 작용한 것으로 보인다.")

    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # ── 2. 다발지 진단 ────────────────────────────────────────────────
    heading(doc, "2. 사고다발지 진단")
    para(doc, "도로교통공단이 지정한 사고다발지 %d곳을 위치·건수·상해정도로 "
              "나누어 본다. 다발지는 일정 기준(반경 안 일정 건수 이상)을 넘은 "
              "지점만 추린 것이라 세종시 전체 사고와는 다른 자료다."
         % len(spots), 10.5, False, INK, 8)
    figure(doc, by_slug, "다발지분포",
           "두 덩어리의 성격이 다르다. 조치원읍은 역전·죽림 등 기존 시가지 "
           "교차로에, 신도심은 초등학교 주변에 몰린다. 같은 사업을 양쪽에 "
           "똑같이 적용할 수 없다는 뜻이다.")
    figure(doc, by_slug, "읍면동별사고",
           "조치원읍 한 곳이 다른 모든 읍면동을 합한 것과 비슷하다. 예산을 "
           "읍면동에 고르게 나누면 사고가 몰린 곳이 오히려 덜 받게 된다.")
    figure(doc, by_slug, "유형별구성")
    figure(doc, by_slug, "지점순위",
           "상위 3곳에 사고가 집중된다. 1차년도 사업 대상을 좁히는 가장 "
           "단순한 근거다.")
    figure(doc, by_slug, "상해정도",
           "건수 순위와 중상 순위가 어긋난다. 사고가 적어도 다친 사람이 모두 "
           "중상인 지점이 있어, 건수만으로 우선순위를 매기면 이런 곳이 뒤로 "
           "밀린다.")
    figure(doc, by_slug, "빈도심각도",
           "가로축(빈도)과 세로축(심각도)이 함께 높은 지점은 거의 없다. 잦은 "
           "곳에는 단속·신호 운영을, 심한 곳에는 속도 억제와 구조 개선을 "
           "적용해야 한다는 뜻이다.")

    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # ── 3. 시설 대조 ──────────────────────────────────────────────────
    heading(doc, "3. 안전시설과의 대조")
    para(doc, "사고가 난 곳에 무엇이 있고 무엇이 없는지를 본다. 사업 내역을 "
              "짜려면 이 대조가 필요하다.", 10.5, False, INK, 8)
    figure(doc, by_slug, "단속장비공백",
           "반경 300m 안에 무인단속장비가 없는 다발지가 %d곳이다. 단속장비가 "
           "유일한 해법은 아니지만, 장비 배치를 다시 볼 지점을 좁히는 데 쓴다."
           % len(P["gaps"]))
    figure(doc, by_slug, "시설접근성",
           "지점마다 모자란 시설이 다르다. 빗금 칸은 그 권역에 등록된 자료가 "
           "없는 경우로, 거리를 비교할 수 없다는 표시다.")
    figure(doc, by_slug, "취약계층_보호구역",
           "보호구역은 촘촘한데도 취약계층 다발지는 구역 안이 아니라 둘레 "
           "교차로에 생긴다. 구역을 더 지정하는 일보다 진입부 처리가 과제다.")

    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # ── 4. 사업 도출 ──────────────────────────────────────────────────
    heading(doc, "4. 사업 도출")
    figure(doc, by_slug, "우선순위매트릭스",
           "가로축은 사고 빈도, 세로축은 단속장비까지의 거리다. 네 사분면이 "
           "각각 다른 사업 성격에 대응한다.")
    para(doc, "사분면별 사업 방향", 12, True, INK, 6)
    for name, text in [
        ("① 즉시 개선 (잦고 · 장비 없음)",
         "단기 사업 1순위. 단속장비 신설·이설과 교차로 구조 개선을 함께 "
         "검토한다. 조치원 역전교차로가 여기에 해당한다."),
        ("② 시설 보완 (드물고 · 장비 없음)",
         "사고가 잦지는 않으나 시설이 비어 있다. 중장기 시설 투자 대상으로 "
         "두고 현장 점검을 먼저 한다."),
        ("③ 운영 강화 (잦고 · 장비 있음)",
         "시설은 있는데 사고가 잦다. 신설보다 신호 운영·단속 시간대 조정 "
         "같은 운영 개선이 먼저다."),
        ("④ 모니터링 (드물고 · 장비 있음)",
         "현 상태를 유지하며 연 단위로 관찰한다."),
    ]:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.left_indent = Cm(0.45)
        r = p.add_run(name + "  ")
        r.font.size = Pt(10.5)
        r.font.bold = True
        r.font.color.rgb = ACCENT
        _hangul(r)
        r2 = p.add_run(text)
        r2.font.size = Pt(10.5)
        r2.font.color.rgb = INK2
        _hangul(r2)

    para(doc, "그림별 사업 근거", 12, True, INK, 6)
    for m in made:
        use = index_page.USE.get(index_page.slug(m["file"]))
        if not use:
            continue
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.left_indent = Cm(0.45)
        r = p.add_run("%s  " % m["title"].split("]")[0].strip("[") + "  ")
        r.font.size = Pt(9.5)
        r.font.color.rgb = INK3
        _hangul(r)
        r2 = p.add_run("%s — %s" % (use[0], use[1]))
        r2.font.size = Pt(10)
        r2.font.color.rgb = INK2
        _hangul(r2)

    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # ── 5. 자료의 한계 ────────────────────────────────────────────────
    heading(doc, "5. 자료의 한계와 보완 과제")
    para(doc, "이 보고서의 숫자는 모두 공공데이터포털에서 받은 실측값이다. "
              "다만 자료 자체에 다음 한계가 있어, 해석할 때 함께 보아야 한다.",
         10.5, False, INK, 8)
    figure(doc, by_slug, "자료공백",
           "사고는 조치원에 몰렸는데 시설 자료는 신도심에만 있다. 현장에 "
           "시설이 없다는 뜻이 아니라 공개자료에 등록되지 않았다는 뜻이다.")
    for text in [
        "사고 자료는 성격이 다른 두 가지다. ‘지자체별 교통사고 통계’는 세종시 "
        "전체 사고이고, ‘교통사고 다발지역’은 기준을 넘은 지점만 추린 것이다. "
        "두 숫자를 더하거나 직접 비교해서는 안 된다.",
        "다발지 그림의 사망자 0명은 다발지 %d곳 안에서 사망사고가 없었다는 "
        "뜻이며, 세종시 사망자가 0명이라는 뜻이 아니다(%d년 %s명)."
        % (len(spots), y1, t(y1, "dth") if years else "-"),
        "횡단보도·도로안전표지는 세종시가 등록한 신도심 분만 있다. 조치원읍 "
        "0건은 자료 공백이다. 교통안전시설 전수조사가 필요한 직접적 이유다.",
        "실시간 소통정보(ITS)는 기본계획 분석에 쓰지 않았다. 연 단위 진단과 "
        "성격이 달라 같은 표에 놓을 수 없다.",
    ]:
        bullet(doc, text)

    heading(doc, "보완이 필요한 자료", 12)
    for name, why in [
        ("세종시 횡단보도·도로안전표지 현황", "조치원읍 등록분 확보(전수조사)"),
        ("자전거도로 현황", "전국 표준데이터에 세종 자료 미등록"),
        ("보행자·이륜차·음주운전·화물차 다발지역",
         "공공데이터포털이 지도 겹침(WMS)으로만 제공해 수치를 받을 수 없음"),
        ("사망사고 지점", "전용 데이터셋이 없어 다발지의 사망자 수로 대신함"),
    ]:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.left_indent = Cm(0.45)
        r = p.add_run("· %s  " % name)
        r.font.size = Pt(10.5)
        r.font.color.rgb = INK
        _hangul(r)
        r2 = p.add_run(why)
        r2.font.size = Pt(10)
        r2.font.color.rgb = WARN
        _hangul(r2)

    figure(doc, by_slug, "자료연동현황")

    path = os.path.join(base.HERE, "세종시_교통안전_기본계획_분석결과보고서.docx")
    doc.save(path)
    return path


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    import make_figures
    import prep
    P = prep.build()
    base.MADE.clear()
    for fn in make_figures.FIGURES:
        fn(P)
    path = build(P, base.MADE)
    print("  %-46s %4d KB" % (os.path.basename(path),
                              os.path.getsize(path) // 1024))


if __name__ == "__main__":
    main()

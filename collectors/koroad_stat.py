# -*- coding: utf-8 -*-
"""지자체별 대상 교통사고 통계 — 세종시 **전체** 사고의 연도별 추이.

왜 따로 두나
  다발지역(frequentzone*) 은 기준을 넘은 지점만 준다. 세종은 열몇 곳뿐이라
  '어디가 위험한가'에는 답해도 '세종 전체가 나아지고 있는가'에는 답하지
  못한다. 기본계획이 목표를 세우려면 후자가 있어야 한다.

  https://apis.data.go.kr/B552061/lgStat/getRestLgStat
      ServiceKey, searchYearCd, siDo, guGun, type=json, numOfRows, pageNo

**지역코드가 다발지역 API 와 다르다.** 다발지역은 법정동코드를 2+3 으로 쪼갠
36/110 인데, 이쪽은 도로교통공단 자체 4자리 코드라 세종이 2700/2701 이다.
(서울 강남구가 1100/1116 인 체계. 법정동코드와는 아무 관계가 없다.)
2026-10 에 코드를 하나씩 두드려 찾아낸 값이니 함부로 바꾸지 말 것.
"""
from __future__ import annotations

from .common import (CollectError, http_json, now_kst, portal_error,
                     portal_rows, safe_url, to_float, to_int)

URL = "https://apis.data.go.kr/B552061/lgStat/getRestLgStat"

# 화면·보고서에서 이 차례로 보여 준다. 전체사고를 맨 앞에 둔다.
ORDER = ["전체사고", "보행자사고", "고령자사고", "어린이사고", "야간사고",
         "고령운전자사고", "고령보행자사고", "어린이보행사고",
         "스쿨존내어린이사고", "자전거사고", "개인형이동수단(PM)사고",
         "무면허사고", "뺑소니사고"]


def _rows(key: str, year: int, sido: str, gugun: str, timeout: int) -> list:
    payload = http_json(URL, {"ServiceKey": key, "searchYearCd": str(year),
                              "siDo": sido, "guGun": gugun, "type": "json",
                              "numOfRows": "50", "pageNo": "1"},
                        timeout=timeout)
    err = portal_error(payload)
    if err:
        # 자료가 없는 해는 오류가 아니다. 해마다 공표 시점이 달라 흔하다.
        if "NODATA" in str(err).upper():
            return []
        raise CollectError("%s — %s" % (err, safe_url(URL)))
    return portal_rows(payload)


def collect(key: str, cfg: dict) -> dict:
    sido = str(cfg.get("stat_sido") or "2700").strip()
    gugun = str(cfg.get("stat_gugun") or "2701").strip()
    back = int(cfg.get("stat_years") or 9)
    timeout = int(cfg.get("timeout") or 20)
    this_year = now_kst().year

    out = {"sido": sido, "gugun": gugun, "years": [], "series": {},
           "errors": [], "region": ""}
    seen = {}

    for year in range(this_year, this_year - back - 1, -1):
        try:
            rows = _rows(key, year, sido, gugun, timeout)
        except CollectError as exc:
            out["errors"].append(str(exc))
            break
        if not rows:
            continue
        out["region"] = out["region"] or str(rows[0].get("sido_sgg_nm") or "")
        for r in rows:
            kind = str(r.get("acc_cl_nm") or "").strip()
            if not kind:
                continue
            # JSON 은 키를 문자열로만 담는다. 여기서 int 로 넣어 두면
            # 캐시를 한 번 거친 뒤 조회가 전부 빗나간다 — 처음부터 문자열로.
            seen.setdefault(kind, {})[str(year)] = {
                "acc": to_int(r.get("acc_cnt"), 0),
                "dth": to_int(r.get("dth_dnv_cnt"), 0),
                "inj": to_int(r.get("injpsn_cnt"), 0),
                # 치사율 = 사고 100건당 사망자. 건수가 줄어도 이게 오르면
                # 나아진 게 아니다 — 목표 지표로 같이 봐야 한다.
                "ftlt": to_float(r.get("ftlt_rate")),
                "per_pop": to_float(r.get("pop_100k")),
                "per_car": to_float(r.get("car_10k")),
            }

    years = sorted({int(y) for v in seen.values() for y in v})
    out["years"] = years
    out["series"] = {k: seen[k] for k in ORDER if k in seen}
    for k in sorted(seen):                      # 목록에 없던 유형도 뒤에 붙인다
        out["series"].setdefault(k, seen[k])

    total = out["series"].get("전체사고") or {}
    if years and total.get(str(years[-1])):
        last = total[str(years[-1])]
        out["latest"] = {"year": years[-1], "acc": last["acc"],
                         "dth": last["dth"], "inj": last["inj"],
                         "ftlt": last["ftlt"]}
    return out


def describe(data: dict) -> str:
    years = data.get("years") or []
    if not years:
        return "자료 없음"
    latest = data.get("latest") or {}
    return "%d~%d년 · %d년 사고 %s건 · 사망 %s명" % (
        years[0], years[-1], latest.get("year", years[-1]),
        latest.get("acc", "-"), latest.get("dth", "-"))

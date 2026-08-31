# -*- coding: utf-8 -*-
"""세종시 교통안전 상황판 — 실행기.

  python run.py --demo                샘플 데이터로 화면만 확인 (API 키 불필요)
  python run.py --collect --open      실측 수집 후 상황판 생성·열기
  python run.py --dashboard           마지막 수집 결과로 HTML 만 다시 생성
  python run.py --probe               요청주소 미확정 API 를 발급받은 키로 타진
  python run.py --probe --only koroad --url "<주소>" --save

수집은 **국내 IP 에서** 해야 한다. ITS 국가교통정보센터가 해외에서 응답하지 않는다.
그래서 수집·화면생성은 PC(또는 사내 NAS)에서 하고, 공개는 정적 HTML 서빙으로
분리한다. 세종시 물환경 상황판과 같은 구조다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 윈도우 콘솔은 기본이 cp949 라 API 오류 메시지에 섞인 문자(—, ℃ 등)에서
# UnicodeEncodeError 로 죽는다. 출력만 UTF-8 로 고정하고 못 쓰는 글자는 대체한다.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import build_dashboard
from collectors import demo, facility, its, kma, koroad
from collectors.common import (BASE_DIR, CollectError, load_config, load_json,
                               now_kst, save_json, stamp)

LATEST = "latest.json"

SOURCES = [
    ("koroad", "도로교통공단", koroad.collect,
     lambda d: "다발지 %d곳 / 레이어 %d"
               % (len(d.get("spots") or []), len(d.get("layers") or []))),
    ("its", "ITS 소통·돌발", its.collect,
     lambda d: "링크 %d / 돌발 %d"
               % (len(d.get("flow") or []), len(d.get("events") or []))),
    ("facility", "안전시설", facility.collect,
     lambda d: "시설 %d개소" % len(d.get("items") or [])),
    ("kma", "기상청", kma.collect,
     lambda d: "실황 %s · 노면 %s" % ("O" if d.get("now") else "X",
                                     (d.get("risk") or {}).get("label", "-"))),
]


def collect(cfg: dict) -> dict:
    """네 소스를 각각 수집한다. 한 곳이 죽어도 나머지는 살린다."""
    data = {"generated_at": stamp(now_kst()), "demo": False}

    for key, label, func, describe in SOURCES:
        section = cfg.get(key) or {}
        api_key = (section.get("key") or "").strip()
        if not api_key or api_key.startswith("여기에"):
            data[key] = {"errors": ["%s 인증키가 config.json 에 없습니다." % label]}
            print("  - %-12s 건너뜀 (인증키 없음)" % label)
            continue
        print("  - %-12s 수집 중..." % label, end="", flush=True)
        try:
            data[key] = func(api_key, section)
            print(" %s" % describe(data[key]))
        except CollectError as exc:
            data[key] = {"errors": [str(exc)]}
            print(" 실패: %s" % exc)
        except Exception as exc:                  # 예상 못 한 예외도 상황판에 남긴다
            data[key] = {"errors": ["예상치 못한 오류: %r" % exc]}
            print(" 오류: %r" % exc)
    return data


PROBE_TARGETS = {
    "koroad": ("도로교통공단 사고다발지", koroad, "koroad.endpoints"),
    "facility": ("표준데이터 안전시설", facility, "facility.endpoints"),
    "its": ("ITS 소통·돌발", its, "its.*_endpoint"),
}


def probe(cfg: dict, only=None, url=None, save=False) -> int:
    """요청주소가 문서로 확인되지 않은 API 를 발급받은 키로 타진한다.

    확인된 주소는 --save 로 config.json 에 적어 둔다. 이후에는 그 주소만 부른다.
    """
    targets = {only: PROBE_TARGETS[only]} if only in PROBE_TARGETS else PROBE_TARGETS
    if url and len(targets) != 1:
        print("--url 은 --only 와 함께 써주세요 (예: --only koroad).")
        return 1
    any_ok = False

    for key_name, (label, module, config_path) in targets.items():
        section = cfg.get(key_name) or {}
        api_key = (section.get("key") or "").strip()
        print("\n=== %s ===" % label)
        if not api_key or api_key.startswith("여기에"):
            print("  %s.key 가 없습니다. 인증키를 넣고 다시 실행해주세요." % key_name)
            continue

        winners = {}
        reports = ([module.probe_one(url, api_key, section)] if url
                   else module.probe(api_key, section))
        for report in reports:
            name = report["url"].rsplit("/", 1)[-1]
            layer = report.get("layer") or ""
            if report["ok"]:
                print("  [OK]   %-12s %-42s %d건" % (layer, name, report["count"]))
                filled = {k: v for k, v in (report["sample"] or {}).items()
                          if v not in (None, "")}
                print("         예: %s" % json.dumps(filled, ensure_ascii=False)[:180])
                winners.setdefault(layer, report["url"])
            else:
                print("  [--]   %-12s %-42s %s"
                      % (layer, name, str(report["error"] or "레코드 0건")[:120]))

        if winners:
            any_ok = True
            print("\n  사용 가능:")
            for layer, found in winners.items():
                print("    %-12s %s" % (layer, found))
            if save and key_name in ("koroad", "facility"):
                if _save_endpoints(cfg, key_name, winners):
                    print("  config.json 의 %s.endpoints 에 기록했습니다." % key_name)
                else:
                    print("  config.json 에 기록하지 못했습니다. 직접 넣어주세요.")
            else:
                print("  config.json 의 %s 에 넣으면 이후엔 이 주소만 호출합니다."
                      % config_path)

    if not any_ok:
        print("\n응답한 후보가 없습니다. 확인할 것:")
        print("  1) 공공데이터포털에서 해당 API 활용신청이 '승인' 상태인지")
        print("  2) 인증키 Encoding/Decoding 값을 정확히 붙여넣었는지")
        print("  3) ITS 는 국내 IP 에서만 응답한다 (해외/VPN 이면 타임아웃)")
        print("  4) 포털 상세페이지의 실제 '요청주소'를 --url 로 직접 지정")
        return 1
    return 0


def _save_endpoints(cfg: dict, section: str, winners: dict) -> bool:
    """확인된 주소를 config.json 에 적어 둔다. 없으면 만들지 않고 알려만 준다."""
    target = cfg.get("_config_path") or os.path.join(BASE_DIR, "config.json")
    if not os.path.exists(target) or not target.endswith("config.json"):
        return False
    try:
        with open(target, "r", encoding="utf-8") as fp:
            saved = json.load(fp)
        block = saved.setdefault(section, {}).setdefault("endpoints", {})
        for layer, url in winners.items():
            if layer:
                block[layer] = url
        with open(target, "w", encoding="utf-8") as fp:
            json.dump(saved, fp, ensure_ascii=False, indent=2)
        return True
    except (OSError, ValueError):
        return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="세종시 교통안전 상황판")
    parser.add_argument("--collect", action="store_true", help="API 에서 실측 수집")
    parser.add_argument("--demo", action="store_true", help="샘플 데이터로 화면 확인")
    parser.add_argument("--dashboard", action="store_true", help="캐시로 HTML 만 재생성")
    parser.add_argument("--probe", action="store_true", help="요청주소 타진")
    parser.add_argument("--only", default=None,
                        choices=["koroad", "facility", "its"],
                        help="--probe 대상을 하나로 한정")
    parser.add_argument("--url", default=None,
                        help="포털에서 복사한 요청주소 하나만 시험 (--only 와 함께)")
    parser.add_argument("--save", action="store_true",
                        help="확인된 주소를 config.json 에 기록")
    parser.add_argument("--open", action="store_true", help="생성 후 브라우저로 열기")
    parser.add_argument("--out", default=None,
                        help="배포용 디렉터리. <디렉터리>/index.html 로도 함께 저장")
    parser.add_argument("--config", default=None, help="설정 파일 경로")
    args = parser.parse_args(argv)

    if not any([args.collect, args.demo, args.dashboard, args.probe]):
        args.demo = True                       # 아무 인수 없이 실행하면 샘플로 보여준다
        print("(인수 없음 → --demo 로 실행합니다)\n")

    if args.probe:
        return probe(load_config(args.config), args.only, args.url, args.save)

    if args.demo:
        data = demo.build()
        data["generated_at"] = stamp(now_kst())
        try:                       # 카운터 같은 표시 설정은 데모에서도 그대로 보여준다
            data["site"] = (load_config(args.config) or {}).get("site") or {}
        except CollectError:
            data["site"] = {}
    elif args.collect:
        cfg = load_config(args.config)
        print("수집 시작 %s" % stamp(now_kst()))
        data = collect(cfg)
        data["site"] = cfg.get("site") or {}
        save_json(LATEST, data)
    else:
        data = load_json(LATEST)
        if not data:
            print("data/latest.json 이 없습니다. 먼저 --collect 또는 --demo 를 "
                  "실행해주세요.")
            return 1
        # 표시 설정(문의처·조회수 등)은 수집 시점에 얼려두지 않고 매번 다시 읽는다.
        try:
            data["site"] = (load_config(args.config) or {}).get("site") or {}
        except CollectError:
            pass

    path = build_dashboard.write(data)
    if args.out:
        os.makedirs(args.out, exist_ok=True)
        site_path = os.path.join(args.out, "index.html")
        build_dashboard.write(data, site_path)
        print("배포본 → %s" % site_path)
    print("\n상황판 생성 → %s" % path)
    if args.open:
        webbrowser.open("file:///" + path.replace("\\", "/"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CollectError as exc:
        print("\n%s" % exc)
        sys.exit(1)

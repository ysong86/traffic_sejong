# -*- coding: utf-8 -*-
"""시놀로지 NAS 등 리눅스 환경용 수집·배포기 — git 없이 GitHub API 로 올린다.

왜 NAS 인가
  ITS 국가교통정보센터 API 는 해외 IP 에 응답하지 않는다(연결 거부). GitHub Actions
  로는 소통·돌발상황을 받을 수 없어 국내 IP 에서 수집해야 한다. 집·사무실 PC 는
  절전에 들어가면 멈추므로 24시간 켜져 있는 NAS 가 그 자리에 맞다.
  물환경 상황판(sejong_water)의 같은 파일과 같은 구조다.

왜 git 을 안 쓰나
  NAS 에 git 이 없을 수 있고, 있어도 자격증명 관리가 번거롭다. GitHub API 로
  올리면 표준 라이브러리만으로 끝난다.

왜 커밋 하나만 남기나
  Contents API 로 파일을 PUT 하면 올릴 때마다 커밋이 하나씩 쌓인다. 10분 주기면
  하루 144개다. 화면 파일이 700KB 라 몇 달이면 저장소가 무거워진다(물환경 상황판이
  이 방식으로 며칠 만에 9MB 를 넘겼다). 그래서 **부모 없는 커밋 하나**를 만들어
  가지를 통째로 덮어쓴다 — PC 용 publish.ps1 이 amend 로 하던 것과 같은 결과다.
  이력은 소스 가지(main)에 있으므로 여기서 잃을 것이 없다.
  이 경로가 실패하면 예전 방식(Contents API)으로 자동으로 물러선다.

준비
  1. NAS 에 소스를 둔다. 저장소가 공개라 클론이 가장 간단하다.
       git clone https://github.com/ysong86/traffic_sejong.git
     git 이 없으면 GitHub 에서 zip 을 내려받아 풀어도 된다.

  2. GitHub 토큰 발급 — https://github.com/settings/tokens?type=beta
     Repository access: traffic_sejong 하나만. Permissions: Contents = Read and write.
     (다른 권한은 주지 말 것. 이 토큰이 하는 일은 파일 하나 덮어쓰기가 전부다.)

  3. NAS 에 config.json 을 만든다. 저장소에는 없다(키가 들어가므로 gitignore).
     config.example.json 을 복사해 API 키를 채우고 아래를 넣는다.

       "deploy": {
         "repo": "ysong86/traffic_sejong",
         "branch": "gh-pages",
         "path": "index.html",
         "token": "github_pat_..."
       }

     토큰을 파일에 두기 싫으면 환경변수 GITHUB_TOKEN 으로 줘도 된다.

  4. DSM 제어판 → 작업 스케줄러 → 생성 → 예약 작업 → 사용자 정의 스크립트
     일정: 매일, 10분 간격 반복
     사용자: 본인 계정(root 일 필요 없다)
     명령:
       cd /volume1/<경로>/traffic_sejong && python3 tools/publish_nas.py

동작 확인
  python3 tools/publish_nas.py --dry-run     수집·생성만 하고 올리지 않는다
  python3 tools/publish_nas.py --demo        샘플로 만들어 올린다(연결 점검용)

인증키가 아직 없으면 자동으로 샘플을 올린다. config.json 에 키를 넣는 순간
다음 주기부터 저절로 실측으로 바뀐다 — 스케줄러를 다시 손댈 필요가 없다.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build_dashboard  # noqa: E402
from collectors import demo  # noqa: E402
from collectors.common import (CollectError, load_config, now_kst, save_json,  # noqa: E402
                               stamp)
from run import SOURCES, collect  # noqa: E402

API = "https://api.github.com"


def _request(method: str, url: str, token: str, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer %s" % token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "sejong-traffic-dashboard",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body) if body else {}


def current_sha(repo: str, path: str, branch: str, token: str):
    """이미 올라간 파일의 sha. 없으면 None(첫 업로드)."""
    url = "%s/repos/%s/contents/%s?ref=%s" % (API, repo, path, branch)
    try:
        return _request("GET", url, token).get("sha")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def upload(repo: str, path: str, branch: str, token: str, content: bytes,
           message: str) -> str:
    payload = {
        "message": message,
        "content": base64.b64encode(content).decode("ascii"),
        "branch": branch,
    }
    sha = current_sha(repo, path, branch, token)
    if sha:
        payload["sha"] = sha
    url = "%s/repos/%s/contents/%s" % (API, repo, path)
    result = _request("PUT", url, token, payload)
    return (result.get("commit") or {}).get("sha", "")[:7]


# --------------------------------------------------------------------------- 단일 커밋

def _blob(repo: str, token: str, content: bytes) -> str:
    return _request("POST", "%s/repos/%s/git/blobs" % (API, repo), token, {
        "content": base64.b64encode(content).decode("ascii"),
        "encoding": "base64",
    })["sha"]


def publish_flat(repo: str, branch: str, token: str, files: dict,
                 message: str) -> str:
    """가지를 **커밋 하나짜리**로 다시 쓴다. 올릴 때마다 이력을 갈아엎는 셈이다.

    files 는 {경로: 바이트}. 여기 없는 파일은 가지에서 사라진다 — 화면 하나만
    서빙하는 가지라 그게 맞다.
    """
    tree = [{"path": path, "mode": "100644", "type": "blob",
             "sha": _blob(repo, token, content)}
            for path, content in sorted(files.items())]
    tree_sha = _request("POST", "%s/repos/%s/git/trees" % (API, repo), token,
                        {"tree": tree})["sha"]
    commit = _request("POST", "%s/repos/%s/git/commits" % (API, repo), token,
                      {"message": message, "tree": tree_sha, "parents": []})
    ref = "%s/repos/%s/git/refs/heads/%s" % (API, repo, branch)
    try:
        _request("PATCH", ref, token, {"sha": commit["sha"], "force": True})
    except urllib.error.HTTPError as exc:
        if exc.code != 422:                     # 422 = 가지가 아직 없다
            raise
        _request("POST", "%s/repos/%s/git/refs" % (API, repo), token,
                 {"ref": "refs/heads/%s" % branch, "sha": commit["sha"]})
    return commit["sha"][:7]


def has_keys(cfg: dict) -> bool:
    """인증키가 하나라도 실제로 들어 있는가. 자리표시자는 없는 것으로 본다."""
    for name, _label, _func, _describe in SOURCES:
        key = ((cfg.get(name) or {}).get("key") or "").strip()
        if key and not key.startswith("여기에"):
            return True
    return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="NAS 수집·배포")
    parser.add_argument("--dry-run", action="store_true",
                        help="수집·생성만, 업로드 안 함")
    parser.add_argument("--demo", action="store_true",
                        help="인증키가 있어도 샘플로 만든다")
    parser.add_argument("--config", default=None)
    args = parser.parse_args(argv)

    # 윈도우에서 시험할 때 콘솔이 cp949 라 오류 메시지에서 죽는 것을 막는다.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    cfg = load_config(args.config)

    if args.demo or not has_keys(cfg):
        if not args.demo:
            print("인증키가 없어 샘플 데이터로 만듭니다."
                  " config.json 에 키를 넣으면 다음 주기부터 실측으로 바뀝니다.")
        data = demo.build()
        data["generated_at"] = stamp(now_kst())
        data["site"] = cfg.get("site") or {}
    else:
        print("수집 시작 %s" % stamp(now_kst()))
        data = collect(cfg)
        data["site"] = cfg.get("site") or {}
        save_json("latest.json", data)

    html = build_dashboard.render(data).encode("utf-8")
    print("상황판 생성 %d KB" % (len(html) // 1024))

    if args.dry_run:
        out = os.path.join(os.path.dirname(build_dashboard.OUT_PATH), "site")
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "index.html"), "wb") as fp:
            fp.write(html)
        print("--dry-run: site/index.html 로만 저장했습니다.")
        return 0

    deploy = cfg.get("deploy") or {}
    token = (os.environ.get("GITHUB_TOKEN") or deploy.get("token") or "").strip()
    repo = deploy.get("repo") or ""
    if not token or not repo:
        print("deploy.repo 와 토큰이 필요합니다. 파일 첫머리 주석을 보세요.")
        return 1

    branch = deploy.get("branch") or "gh-pages"
    path = deploy.get("path") or "index.html"
    message = "상황판 갱신 %s" % stamp(now_kst())
    # .nojekyll 은 GitHub Pages 의 Jekyll 처리를 끈다(밑줄로 시작하는 파일 보호).
    files = {path: html, ".nojekyll": b""}

    try:
        try:
            short = publish_flat(repo, branch, token, files, message)
        except urllib.error.HTTPError as exc:
            # 단일 커밋 경로가 막히면(권한·API 변경 등) 예전 방식으로 물러선다.
            # 이력이 쌓이더라도 화면이 멈추는 것보다는 낫다.
            print("단일 커밋 실패(HTTP %s) — Contents API 로 물러섭니다." % exc.code)
            if current_sha(repo, ".nojekyll", branch, token) is None:
                upload(repo, ".nojekyll", branch, token, b"", "Jekyll 처리 끄기")
            short = upload(repo, path, branch, token, html, message)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        print("업로드 실패 HTTP %s — %s" % (exc.code, detail))
        if exc.code in (401, 403):
            print("  토큰이 만료됐거나 이 저장소에 Contents=Read and write 권한이 없습니다.")
        return 1
    except urllib.error.URLError as exc:
        print("업로드 실패: %s" % exc.reason)
        return 1

    print("배포 완료 (%s) — https://%s.github.io/%s/"
          % (short, repo.split("/")[0], repo.split("/")[-1]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CollectError as exc:
        print(exc)
        sys.exit(1)

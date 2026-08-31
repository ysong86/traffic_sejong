# 세종시 교통안전 상황판

세종시의 교통안전을 한 화면에서 읽기 위한 정적 상황판입니다.
수집기가 공공 API 를 훑어 `dashboard.html` 한 파일을 만듭니다. 그 파일만 있으면
어디서든 열립니다 — 서버도, 빌드도, 인터넷 연결도 필요 없습니다.

세종시 물환경 상황판(`sejong_water`)과 같은 구조로 만들었습니다.

```
python run.py --demo               샘플로 화면 확인 (API 키 불필요)
python run.py --collect --open     실측 수집 후 생성·열기
python run.py --dashboard          마지막 수집 결과로 HTML 만 재생성
python run.py --probe --only koroad --save    요청주소 미확정 API 타진
```

윈도우에서 `python` 은 깨진 스토어 스텁일 수 있습니다. `C:\Python313\python.exe`
를 직접 부르십시오.

---

## 이 상황판이 푸는 문제

교통안전 자료는 **갱신주기가 제각각**입니다. 사고통계는 연 단위이고 공표가
1~2년 늦는데, 돌발상황은 5분마다 바뀝니다. 이걸 한 덩어리로 늘어놓으면
"지금 사고가 49건"처럼 읽혀 거짓말이 됩니다.

그래서 자료를 세 층으로 갈라 두었습니다.

| 층 | 무엇 | 주기 | 어떻게 읽나 |
|---|---|---|---|
| **실시간** | 돌발상황 · 소통속도 · 노면위험 | 5~60분 | 지금 벌어지는 일 |
| **연 단위** | 사고다발지 · 사망사고 | 연 1회, 공표 1~2년 지연 | 누적된 위험(진단) |
| **정적** | 보호구역 · 단속카메라 | 월~연 | 배경이자 대조군 |

화면 상단의 `자료 시점` 줄이 이 세 층을 그대로 보여줍니다.

세 층을 **겹쳐 읽을 때** 정책 지표가 나옵니다. 예를 들어 연 단위 다발지와
정적 단속장비를 겹치면 "사고는 잦은데 장비가 없는 지점"이 나옵니다.
화면의 `단속장비 없는 사고다발지` 패널이 그것입니다.

---

## 화면 구성

```
헤더 (갱신시각 · 라이트/다크)
지금 이슈      진행 중인 사고·재난, 노면위험 경계, 기상특보, 정체구간
보기 칩        블록별 on/off (브라우저에 기억됨)
요약 지표 6개
자료 시점      실시간 / 연 단위 / 정적 — 층별 신선도
지점 목록 · 지도 · 상세      (세 칸)
읍면동별 집계 | 유형별 사고다발지
실시간 소통   | 노면위험
장비 미스매치 | 안전시설 현황
수집 경고 · 출처 · 문의처
```

### 지도

- **읍면동 31개**를 면마다 다른 색으로 칠하고 경계선을 굵게 둡니다.
  색은 뜻이 없습니다 — 이웃한 면이 같은 색이 되지 않도록 색상환을
  황금각(137.5°)으로 돌린 것뿐입니다. 뜻이 있는 것은 **선 모양**입니다:
  읍·면은 실선, 동은 파선.
- 면을 누르면 그 면만 도드라지고 아래 `읍면동별 집계` 표의 같은 행도 함께
  켜집니다. 반대로 표의 행을 눌러도 지도가 켜집니다.
- 작은 신도시 동은 이름이 서로 겹치므로 **2.2배 이상 확대했을 때** 뜹니다.
- **도로 간·지선**을 다섯 등급으로 그립니다 — 고속·자동차전용 / BRT 축 /
  주간선 / 보조간선 / 집산·지선. 도로에 커서를 올리면 굵어지고 이름이 뜹니다.
- 휠로 확대, 끌어서 이동, 더블클릭 확대. 축척 막대가 배율에 맞춰 다시 계산됩니다.
- **확대하면 선이 얇아지고 옅어집니다.** 굵기는 배율의 0.22 제곱만큼만 따라
  굵어지고(최대 1.5배), 색은 배율이 두 배 될 때마다 빠집니다. 좁은 구역을 크게
  볼 때 봐야 하는 것은 그 안의 사고지점과 배경지도이지 우리가 덧그린 도로선이
  아니기 때문입니다. 빼는 양은 배경지도 유무에 따라 다릅니다 — 배경지도가 있으면
  0.42까지, 없으면 0.66까지만 뺍니다(없을 땐 그게 유일한 기준이므로).

  > 구현 주의 — `vector-effect="non-scaling-stroke"` 는 **상속되지 않습니다.**
  > `<g>` 에 걸어 두면 아무 일도 일어나지 않아 선이 배율만큼 그대로 굵어집니다.
  > `theme.css` 에서 `.rd .ln` / `.ad path` 처럼 **그리는 요소마다** 겁니다.
- 지도 위 칩으로 겹(사고다발지·보호구역·단속카메라·돌발상황)과 도로 등급을
  켜고 끌 수 있습니다. 켠 상태는 브라우저에 기억됩니다.

### 배경지도

`배경지도` 칩을 켜면 실제 지도가 배경에 깔립니다. 시 경계 밖(조치원 북쪽 오송,
남쪽 대전)까지 보여서 "지금 보고 있는 곳이 어디인지"를 바로 알 수 있습니다.

- **켜야만 타일 서버로 요청이 나갑니다.** 끄고 있으면 이 페이지는 바깥으로
  아무것도 부르지 않습니다(폐쇄망·오프라인에서도 나머지는 그대로 동작).
- 타일은 Web Mercator, 이 지도는 등장방형이라 좌표계가 다릅니다. 그래도 타일마다
  제 모서리를 이 지도의 투영으로 옮겨 놓기 때문에 한 장 안에서 생기는 어긋남이
  3m 남짓이라 눈에 보이지 않습니다. 투영 자체를 바꾸는 것보다 안전한 방법입니다.
- 배경을 깔면 읍면동 면은 비우고 경계선만 진하게 올립니다. 고른 면의 색은
  그대로 남습니다.
- 다크 테마에서는 타일을 반전시켜 어두운 지도로 씁니다.

**공개 운영 시 주의** — 기본값인 `tile.openstreetmap.org` 는 자원봉사자가 운영하는
서버입니다. 대외 서비스로 상시 운영할 거면 국토교통부 **VWorld** 로 바꾸십시오.
[vworld.kr](https://www.vworld.kr) 에서 인증키를 받고 **사용할 도메인을 등록**한 뒤
`config.json` 의 `site.basemap` 을 이렇게 두면 됩니다.

```json
"basemap": {
  "provider": "vworld",
  "url": "https://api.vworld.kr/req/wmts/1.0.0/여기에_VWORLD_키/Base/{z}/{y}/{x}.png",
  "attribution": "© VWorld 국토교통부",
  "max_zoom": 18
}
```

`url` 을 빈 문자열로 두면 칩 자체가 사라집니다.

---

## 붙은 자료

### ① 사고·안전성과 — 도로교통공단 (연 단위)

`apis.data.go.kr/B552061/{서비스}/getRest{서비스}`
파라미터: `ServiceKey, searchYearCd, siDo, guGun, type=json, numOfRows, pageNo`

`siDo`/`guGun` 은 법정동코드 앞 5자리를 2+3 으로 쪼갠 값입니다 (세종 36110 → 36 / 110).

| 레이어 | 요청주소 | 상태 |
|---|---|---|
| 전체 사고다발지 | `frequentzoneLg/getRestFrequentzoneLg` | 확인됨 |
| 스쿨존 어린이 | `schoolzoneChild/getRestSchoolzoneChild` | 확인됨 |
| 보행자 무단횡단 | `jaywalking/getRestJaywalking` | 확인됨 |
| 결빙 | `frequentzoneFreezing/getRestFrequentzoneFreezing` | 확인됨 |
| 어린이 보행 · 노인 보행 · 보행자 · 자전거 · 이륜차 · 사망사고 | 후보 여러 개 | **probe 필요** |

확인되지 않은 레이어는 조용히 건너뜁니다. 아래로 확정하십시오.

```
C:\Python313\python.exe run.py --probe --only koroad --save
```

응답한 주소가 `config.json` 의 `koroad.endpoints` 에 자동으로 기록되고,
이후에는 그 주소만 호출합니다. 포털 상세페이지에서 요청주소를 직접 복사했다면:

```
C:\Python313\python.exe run.py --probe --only koroad --url "<주소>" --save
```

지정 연도부터 `year_back` 년 거슬러 올라가며 값이 있는 해를 찾습니다.
공표가 늦기 때문입니다.

### ② 실시간 소통·돌발 — ITS 국가교통정보센터

```
소통  https://openapi.its.go.kr:9443/trafficInfo
돌발  https://openapi.its.go.kr:9443/eventInfo
CCTV  https://openapi.its.go.kr:9443/cctvInfo
```

**세 가지를 알고 써야 합니다.**

1. **국내 IP 에서만 응답합니다.** 해외에서는 연결 자체가 거부됩니다.
   물환경 상황판의 한강홍수통제소와 같은 제약이라, 수집은 국내 PC/NAS 에서
   하고 공개는 정적 서빙으로 분리합니다. GitHub Actions 로는 불가능합니다.
2. **인증키가 공공데이터포털 키와 다릅니다.** its.go.kr 에서 따로 발급받습니다.
   개발계정은 1,000건/일이라 10분 주기로 두 서비스면 하루 288건 — 들어갑니다.
   CCTV 까지 켜면 빠듯하니 운영계정 신청을 권합니다.
3. **고속도로·국도 중심입니다.** 세종시가 관리하는 시도(市道)는 대부분 잡히지
   않습니다. 이 화면의 "소통정보 없음"은 고장이 아니라 커버리지 문제일 수 있습니다.

### ③ 정적 시설 — 공공데이터포털 표준데이터

`api.data.go.kr/openapi/{오퍼레이션}`

| 시설 | 오퍼레이션 | 상태 |
|---|---|---|
| 무인교통단속카메라 | `tn_pubr_public_unmanned_traffic_camera_api` | 확인됨 |
| 어린이보호구역 | `tn_pubr_public_child_prtc_zn_api` | 확인됨 |
| 노인·장애인 보호구역 · 횡단보도 · 자전거도로 | 후보 여러 개 | **probe 필요** |

전국 자료라 세종만 골라야 합니다. `ctprvnNm=세종특별자치시` 필터로 먼저 시도하고,
필터가 안 먹으면 전수를 훑어 주소·기관명에 '세종'이 든 행만 남깁니다.
전수 훑기는 `max_pages` 로 막아 둡니다.

### ④ 위험요인 — 기상청 단기예보

실황·예보를 받아 **노면위험도**로 바꿔 읽습니다. 기상 그 자체가 아니라
"도로가 미끄러운가·안 보이는가"를 판단합니다.

| 조건 | 등급 |
|---|---|
| 기온 ≤ 0℃ + 강수 중 | 위험 |
| 기온 ≤ 0℃ | 경계 (블랙아이스) |
| 기온 ≤ 3℃ + (강수 or 습도 ≥ 80%) | 경계 (교량·터널입구) |
| 시간강수 ≥ 10mm | 위험 (수막·시야) |
| 시간강수 ≥ 3mm | 경계 (제동거리) |
| 습도 ≥ 95% + 풍속 ≤ 2m/s | 경계 (안개) |
| 풍속 ≥ 9m/s | 경계 (이륜차·고상차량) |

판단 근거를 화면에 함께 적습니다. **노면 온도 실측이 아니라 참고값**이라는
사실도 같이 적습니다.

기상특보는 별도 활용신청이 필요합니다(`기상청_기상특보 조회서비스`).
신청 전에는 `config.json` 의 `kma.warnings` 를 `false` 로 두십시오.

---

## 인증키

공공데이터포털 일반 인증키는 **계정당 하나**라 `koroad` · `facility` · `kma` 는
같은 값입니다. `its` 만 다릅니다.

```
config.example.json  →  config.json 으로 복사하고 key 를 채우세요
```

키는 `config.json` 에만 둡니다(gitignore). 저장소에는 키 없는
`config.public.json` 이 들어갑니다. 환경변수 `DATA_GO_KR_KEY` · `ITS_KEY`
로 넘겨도 됩니다. 로그와 화면에서는 `collectors.common.safe_url()` 이 키를 가립니다.

---

## 자산 만들기

지도에 쓰는 경계·도로망은 OpenStreetMap 에서 받아 단순화한 것입니다.
이미 `assets/` 에 들어 있으니 다시 만들 필요는 없습니다. 갱신하려면:

```bash
# 1) 읍면동 경계 (세종 = OSM relation 2349795, area id = 3602349795)
#    [out:json][timeout:240];
#    rel(area:3602349795)["boundary"="administrative"]["admin_level"~"^(8|9)$"];
#    out geom;
#
# 2) 시 외곽선
#    [out:json][timeout:180]; rel(2349795); out geom;
#
# 3) 도로망
#    [out:json][timeout:240];
#    (way["highway"~"^(motorway|trunk|primary|secondary|tertiary)$"]
#        (36.34,127.05,36.75,127.45););
#    out geom;

curl -s -X POST --data-binary @query.txt https://overpass-api.de/api/interpreter -o osm.json

C:\Python313\python.exe tools\make_admin.py osm_dongs.json osm_city.json
C:\Python313\python.exe tools\make_roads.py osm_roads.json
```

`make_roads.py` 는 **이름 단위로 묶은 뒤 최상위 등급**을 줍니다. OSM 은 한 도로를
구간마다 다른 `highway` 값으로 태깅해 둔 곳이 많아(한누리대로가 구간에 따라
`tertiary`), 조각별로 등급을 매기면 같은 도로가 두세 등급에 흩어져 그려집니다.

BRT 는 이름으로 고릅니다. 세종 BRT 는 별도 도로가 아니라 간선의 중앙
전용차로여서 OSM 에 일관되게 태깅돼 있지 않기 때문입니다.

---

## 배포

수집이 국내 IP 를 요구하므로 **수집은 PC(또는 사내 NAS), 공개는 정적 서빙**으로
나눕니다.

```
tools\publish.ps1           수집 → site\index.html → gh-pages 로 force push
tools\install_startup.ps1   관리자 권한 없이 10분마다 실행 (시작프로그램)
tools\install_startup.ps1 -Remove   해제
```

`gh-pages` 는 **커밋 하나만** 두고 amend 로 덮어씁니다. 파일 하나가 660KB 라
매번 새 커밋을 쌓으면 저장소가 금방 기가 단위로 불어납니다.

즉시 멈추려면 `data\PAUSED` 파일을 만드십시오(권한 불필요). 지우면 다시 돕니다.

배포 전에 할 것:
1. `git init` 후 `git remote add origin ...`
2. GitHub 저장소 Settings → Pages → Source = **gh-pages 브랜치**
3. `tools\publish.ps1` 의 `$siteUrl` 채우기
4. `config.json` 의 `site.counter.target` 을 실제 공개주소로 맞추기

### 조회수

화면 오른쪽 아래에 **오늘 / 전체**가 표시됩니다. 정적 페이지는 스스로 셀 수 없어
바깥에서 세어 줍니다. 기본은 [hits.sh](https://hits.sh) 배지 —
가입이 필요 없고 바로 뜹니다.

```json
"counter": {
  "provider": "hits",
  "target": "ysong86.github.io/traffic_sejong",
  "label": "조회수"
}
```

`target` 은 hits.sh 가 쓰는 **집계 열쇠**입니다. 저장소·주소가 정해지면 실제
공개주소로 맞추십시오 — 나중에 바꾸면 그 시점부터 다시 셉니다.

라벨이 '방문자 수'가 아니라 **'조회수'**인 이유: hits.sh 는 새로고침마다 올라갑니다.
새로고침을 빼고 진짜 방문자를 세려면 `tools\counter-worker.js` 를 Cloudflare
Workers 에 올리고(`COUNT_MODE=unique`) 이렇게 바꾸십시오.

```json
"counter": { "provider": "custom", "url": "<워커 주소>", "label": "방문자 수" }
```

이 상황판은 5분마다 스스로 갱신을 확인하지만 페이지를 다시 읽는 것은 갱신 시각이
바뀌었을 때뿐이라, 자동갱신 때문에 조회수가 부풀지는 않습니다.

---

## 파일

```
run.py                 실행기
build_dashboard.py     수집 결과 → HTML 한 파일
sejong_map.py          읍면동·도로·마커 SVG
collectors/
  common.py            HTTP·설정·좌표·기상격자
  koroad.py            ① 사고다발지 (연 단위)
  its.py               ② 소통·돌발 (실시간)
  facility.py          ③ 표준데이터 시설 (정적)
  kma.py               ④ 기상 + 노면위험도 산출
  demo.py              샘플
assets/
  theme.css            라이트/다크 토큰. 지도 SVG 도 같은 토큰을 참조한다
  sejong_admin.json    읍면동 31개 + 시 외곽선 (OSM)
  sejong_roads.json    도로 696개 / 5등급 (OSM)
tools/
  make_admin.py        Overpass → 읍면동 경계 자산
  make_roads.py        Overpass → 도로망 자산
  publish.ps1          수집 → 생성 → gh-pages
  install_startup.ps1  10분 자동 실행
  counter-worker.js    (선택) 순방문자 집계용 Cloudflare Worker
```

---

## 읽을 때 주의할 것

- **사고다발지는 "지금"이 아닙니다.** 1년치 사고를 반경 150m 로 묶어 고른
  지점이고, 공표가 1~2년 늦습니다.
- **노면위험도는 추정입니다.** 기온·강수·습도에서 계산한 참고값이고 노면 온도
  실측이 아닙니다.
- **ITS 소통정보의 빈칸은 커버리지 문제일 수 있습니다.** 시 관리도로는
  표준링크에 대부분 없습니다.
- **표준데이터는 갱신이 드뭅니다.** 최근 설치된 단속장비·보호구역은 빠져 있을
  수 있습니다.
- 지도의 면 색은 **뜻이 없습니다.** 이웃 구분용입니다.

실제 교통통제·대응 판단은 관계기관 공식 발표를 따르십시오.

---

제작 — 세종연구원 도시안전연구센터
안용준 센터장 · 송양호 책임연구위원 · 주재성 전문연구위원 · 최유라 전문연구위원
문의 — ayj826@sri.re.kr
경계·도로망 © OpenStreetMap 기여자 (ODbL)

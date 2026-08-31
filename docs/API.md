# 세종시 교통안전 상황판 — 필요한 API·사이트 전체 목록

이 상황판이 부르는 것, 부를 예정인 것, 그리고 운영에 필요한 바깥 서비스를 한자리에.
**상태** 칸의 뜻은 이렇습니다.

| 표시 | 뜻 |
|---|---|
| **확정** | 요청주소를 문서로 확인했고 코드에 박혀 있음. 키만 있으면 바로 붙음 |
| **타진** | 요청주소가 공개 문서로 확인되지 않음. 후보를 코드에 넣어 뒀고 `--probe` 로 확정 |
| **예정** | 아직 코드에 없음. 붙이려면 개발이 필요 |
| **협의** | 공개 API 가 없어 기관 협의가 필요 |

---

## 0. 인증키 — 몇 개를 받아야 하나

**두 개**입니다.

| 키 | 발급처 | 쓰는 곳 | 비고 |
|---|---|---|---|
| 공공데이터포털 일반 인증키 | [data.go.kr](https://www.data.go.kr) | ①·③·④ 전부 | **계정당 하나**. 이미 물환경 상황판에서 쓰는 그 키 |
| ITS 인증키 | [its.go.kr/opendata](https://www.its.go.kr/opendata) | ② | 포털 키와 **별개**. 개발계정 1,000건/일 |

포털은 키가 하나여도 **데이터셋마다 '활용신청'을 따로** 해야 합니다. 신청이
승인되지 않은 데이터셋은 같은 키로 불러도 거부됩니다. 아래 목록의 링크를 열고
각각 활용신청을 누르시면 됩니다. 대부분 자동승인이라 몇 분이면 됩니다.

`config.json` 에 넣는 자리:

```json
"koroad":   { "key": "포털 인증키" },
"facility": { "key": "포털 인증키" },
"kma":      { "key": "포털 인증키" },
"its":      { "key": "ITS 인증키" }
```

---

## ① 사고·안전성과 — 도로교통공단 (연 단위, 진단용)

공통 요청 형식:

```
GET https://apis.data.go.kr/B552061/{서비스}/getRest{서비스}
    ServiceKey, searchYearCd, siDo, guGun, type=json, numOfRows, pageNo
```

`siDo`/`guGun` 은 법정동코드 앞 5자리를 2+3 으로 쪼갠 값입니다 — **세종 36110 → 36 / 110**.

| 지표 | 데이터셋 | 요청주소 | 상태 |
|---|---|---|---|
| 전체 사고다발지 | [지자체별 교통사고 다발지역 (15057467)](https://www.data.go.kr/data/15057467/openapi.do) | `frequentzoneLg/getRestFrequentzoneLg` | **확정** |
| 스쿨존 어린이 | [스쿨존어린이사고다발지역 (15058311)](https://www.data.go.kr/data/15058311/openapi.do) | `schoolzoneChild/getRestSchoolzoneChild` | **확정** |
| 보행자 무단횡단 | [무단횡단 교통사고 다발지역 (15058578)](https://www.data.go.kr/data/15058578/openapi.do) | `jaywalking/getRestJaywalking` | **확정** |
| 결빙(도로 살얼음) | [결빙 교통사고 다발지역 (15058135)](https://www.data.go.kr/data/15058135/openapi.do) | `frequentzoneFreezing/getRestFrequentzoneFreezing` | **확정** |
| 자전거 | [자전거 교통사고 다발지역 (15056681)](https://www.data.go.kr/data/15056681/openapi.do) | 후보 `frequentzoneBicycle` 외 | 타진 |
| 어린이 보행 | 도로교통공단 어린이 보행사고 다발지역 | 후보 `frequentzoneChild` 외 2 | 타진 |
| 노인 보행 | 도로교통공단 노인 보행사고 다발지역 | 후보 `frequentzoneOldman` 외 2 | 타진 |
| 보행자 전체 | 도로교통공단 보행자 사고다발지역 | 후보 `frequentzonePedestrian` 외 2 | 타진 |
| 이륜차 | 도로교통공단 이륜차 사고다발지역 | 후보 `frequentzoneMotorcycle` 외 2 | 타진 |
| 사망사고 지점 | [사망 교통사고 정보 (15059126)](https://www.data.go.kr/data/15059126/openapi.do) | 후보 3개 | 타진 |

타진은 국내 IP·본인 키로 이렇게 합니다. 응답한 주소가 `config.json` 의
`koroad.endpoints` 에 자동으로 적힙니다.

```bash
C:\Python313\python.exe run.py --probe --only koroad --save
```

포털 상세페이지에서 요청주소를 직접 복사해 오셨다면:

```bash
C:\Python313\python.exe run.py --probe --only koroad --url "<붙여넣기>" --save
```

**참고 사이트**

- [KOROAD 교통사고분석시스템(TAAS) 오픈API 포털](https://opendata.koroad.or.kr) —
  API 명세와 응답 예시가 포털보다 자세합니다. 요청주소를 확인할 때 여기부터 보십시오.
- [전국교통사고다발지역 표준데이터 (15029185)](https://www.data.go.kr/data/15029185/standard.do) —
  전국 동일 스키마. 타 시도와 견줄 때 씁니다. (예정)

**읽을 때 주의** — 1년치 사고를 반경 150m 로 묶어 고른 지점이고, 공표가 **1~2년 늦습니다.**
"지금"이 아니라 누적된 위험입니다.

---

## ② 실시간 소통·돌발 — ITS 국가교통정보센터

| 지표 | 요청주소 | 상태 |
|---|---|---|
| 소통정보(표준링크 속도) | `https://openapi.its.go.kr:9443/trafficInfo` | **확정** |
| 돌발상황(사고·공사·통제) | `https://openapi.its.go.kr:9443/eventInfo` | **확정** |
| CCTV 지점 | `https://openapi.its.go.kr:9443/cctvInfo` | 확정(기본 꺼둠) |

- 발급: [its.go.kr/opendata](https://www.its.go.kr/opendata) · 개발자센터 [openapi.its.go.kr](http://openapi.its.go.kr)
- 표준노드링크(공간 기준체계): [nodelink.its.go.kr](https://nodelink.its.go.kr) —
  사고자료를 도로망에 얹을 때 기준이 됩니다. (예정)

**반드시 알고 쓸 것 세 가지**

1. **국내 IP 에서만 응답합니다.** 해외에서는 연결 자체가 거부됩니다(실제로 확인).
   GitHub Actions 로는 수집이 불가능해, 수집은 국내 PC/NAS 에서 하고 공개는
   정적 서빙으로 나눴습니다. 물환경 상황판의 한강홍수통제소와 같은 제약입니다.
2. **개발계정은 1,000건/일.** 10분 주기로 소통·돌발 두 개면 하루 288건이라 들어갑니다.
   CCTV 까지 켜면 빠듯하니 **운영계정 신청**을 권합니다.
3. **고속도로·국도 중심입니다.** 세종시가 관리하는 시도(市道)는 대부분 잡히지
   않습니다. 화면의 "소통정보 없음"은 고장이 아니라 커버리지 문제일 수 있습니다.

포털에도 [국토교통부_교통소통정보(15040463)](https://www.data.go.kr/data/15040463/openapi.do),
[돌발상황정보(15040465)](https://www.data.go.kr/data/15040465/openapi.do) 가 있지만
**유형이 LINK** 라 결국 위 ITS 주소로 연결됩니다. 포털 키로는 못 씁니다.

---

## ③ 정적 시설 — 공공데이터포털 표준데이터

```
GET https://api.data.go.kr/openapi/{오퍼레이션}
    serviceKey, pageNo, numOfRows, type=json   (+ 응답 필드명을 그대로 필터로)
```

| 시설 | 데이터셋 | 오퍼레이션 | 상태 |
|---|---|---|---|
| 무인교통단속카메라 | [전국무인교통단속카메라표준데이터 (15028200)](https://www.data.go.kr/data/15028200/standard.do) | `tn_pubr_public_unmanned_traffic_camera_api` | **확정** |
| 어린이보호구역 | [전국 어린이보호구역 (15012891)](https://www.data.go.kr/data/15012891/standard.do) | `tn_pubr_public_child_prtc_zn_api` | **확정** |
| 노인·장애인 보호구역 | [전국노인장애인보호구역표준데이터 (15034532)](https://www.data.go.kr/data/15034532/openapi.do) | 후보 3개 | 타진 |
| 횡단보도 | 전국횡단보도표준데이터 | 후보 3개 | 타진 |
| 자전거도로 | [전국자전거도로표준데이터 (15100063)](https://www.data.go.kr/data/15100063/standard.do) | 후보 2개 | 타진 |
| CCTV | 전국CCTV표준데이터 | — | 예정 |

```bash
C:\Python313\python.exe run.py --probe --only facility --save
```

전국 자료라 세종만 골라야 합니다. `ctprvnNm=세종특별자치시` 필터를 먼저 쓰고,
안 먹으면 전수를 훑어 주소·기관명에 '세종'이 든 행만 남깁니다(`max_pages` 로 제한).

**왜 필요한가** — 사고다발지와 겹쳐 **"단속장비 없는 다발지"** 같은 미스매치 지표를
만듭니다. 정책 제언으로 바로 이어지는 부분이라 이 상황판의 핵심 화면 중 하나입니다.

---

## ④ 위험요인 — 기상청

| 지표 | 데이터셋 | 요청주소 | 상태 |
|---|---|---|---|
| 초단기실황 | [기상청 단기예보 조회서비스](https://www.data.go.kr/data/15084084/openapi.do) | `1360000/VilageFcstInfoService_2.0/getUltraSrtNcst` | **확정** |
| 단기예보 | 〃 | `1360000/VilageFcstInfoService_2.0/getVilageFcst` | **확정** |
| 기상특보 | 기상청_기상특보 조회서비스 | `1360000/WthrWrnInfoService/getWthrWrnList` | 확정(**별도 활용신청**) |

기상특보는 단기예보와 **다른 서비스**라 따로 신청해야 합니다. 신청 전에는
`config.json` 의 `kma.warnings` 를 `false` 로 두십시오(403 경고가 사라집니다).
세종은 특보구역 `stnId = 133`(대전·세종)입니다.

실황·예보를 그대로 보여주지 않고 **노면위험도**로 바꿔 읽습니다 — 기온 ≤ 3℃ +
습도/강수면 결빙 주의, 시간강수 ≥ 3mm 면 제동거리, 습도 ≥ 95% + 무풍이면 안개.
**노면 온도 실측이 아닌 추정치**라는 것을 화면에도 적어 두었습니다.

---

## ⑤ 아직 안 붙인 것

| 대상 | 어디서 | 왜 / 상태 |
|---|---|---|
| 버스 위치·도착·노선·정류소 | [국토교통부 TAGO (data.go.kr)](https://www.data.go.kr/tcs/dss/selectDataSetList.do?keyword=TAGO) | BRT 정시성 지표용. 포털 키로 가능 · **예정** |
| 세종 BIS(시내버스 정보) | 세종도시교통공사 | 공개 API 없음 · **협의** |
| 세종시 빅데이터 개방형 플랫폼 | [bigdata.sejong.go.kr](https://bigdata.sejong.go.kr) | 시 자체 자료 · **협의** |
| 스마트시티 통합플랫폼 연계 | 세종시 | 돌발·CCTV 실시간 연계 · **협의** |
| 표준노드링크 | [nodelink.its.go.kr](https://nodelink.its.go.kr) | 사고↔도로망 매칭 기준 · **예정** |

---

## ⑥ 지도 자산 (API 아님, 만들 때만 씀)

| 대상 | 어디서 | 쓰임 |
|---|---|---|
| 읍면동 경계 31개 | [Overpass API](https://overpass-api.de) — 세종 relation `2349795`, area `3602349795` | `tools/make_admin.py` → `assets/sejong_admin.json` |
| 도로망 696개 5등급 | 〃 (`highway=motorway\|trunk\|primary\|secondary\|tertiary`) | `tools/make_roads.py` → `assets/sejong_roads.json` |

이미 `assets/` 에 들어 있어 평소에는 부를 일이 없습니다. 경계가 바뀌거나 도로가
신설됐을 때만 다시 만듭니다. 자세한 질의문은 README 참조.
© OpenStreetMap 기여자 (ODbL) — 화면에 출처를 표시합니다.

---

## ⑦ 운영에 쓰는 바깥 서비스

| 서비스 | 주소 | 쓰임 | 키 |
|---|---|---|---|
| GitHub Pages | [github.com](https://github.com) | 화면 공개(정적 서빙) | 계정 |
| hits.sh | [hits.sh](https://hits.sh) | 조회수(오늘/전체) 배지 | 불필요 |
| OpenStreetMap 타일 | `tile.openstreetmap.org` | 배경지도(기본값) | 불필요 |
| **VWorld** | [vworld.kr](https://www.vworld.kr) | 배경지도(**공개 운영 시 권장**) | 키 + **도메인 등록** |
| Cloudflare Workers | [workers.cloudflare.com](https://workers.cloudflare.com) | (선택) 순방문자 집계 | 계정 |

**배경지도는 공개 전에 정하십시오.** 기본값인 openstreetmap.org 타일은 자원봉사자가
운영하는 서버라 대외 서비스 상시 운영에는 맞지 않습니다. VWorld 로 바꾸는 방법은
README 의 '배경지도' 절에 있습니다.

---

## 신청 체크리스트

공공데이터포털에 로그인해 아래를 차례로 활용신청하시면 됩니다. 인증키는 하나입니다.

- [ ] 지자체별 교통사고 다발지역 (15057467)
- [ ] 스쿨존어린이사고다발지역 (15058311)
- [ ] 보행자무단횡단사고다발지역 (15058578)
- [ ] 결빙 교통사고 다발지역 (15058135)
- [ ] 자전거 교통사고 다발지역 (15056681)
- [ ] 사망 교통사고 정보 (15059126)
- [ ] 어린이·노인·보행자·이륜차 사고다발지역 (KOROAD 포털에서 이름 확인 후)
- [ ] 전국무인교통단속카메라표준데이터 (15028200)
- [ ] 전국 어린이보호구역 (15012891)
- [ ] 전국노인장애인보호구역표준데이터 (15034532)
- [ ] 전국자전거도로표준데이터 (15100063)
- [ ] 기상청 단기예보 조회서비스
- [ ] 기상청 기상특보 조회서비스 *(선택)*

포털과 별개로:

- [ ] **ITS 인증키** 발급 ([its.go.kr/opendata](https://www.its.go.kr/opendata)) — 운영계정 신청 권장
- [ ] **VWorld 인증키** + 도메인 등록 *(배경지도를 공개 운영할 경우)*

키를 넣은 뒤 순서:

```bash
copy config.example.json config.json      # 키를 채운다
C:\Python313\python.exe run.py --probe --save     # 미확정 주소를 확정
C:\Python313\python.exe run.py --collect --open   # 실측으로 한 번 확인
```

화면 하단의 **수집 경고**에 어떤 데이터셋이 아직 미승인인지 그대로 나옵니다.

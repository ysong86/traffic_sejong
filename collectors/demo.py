# -*- coding: utf-8 -*-
"""샘플 데이터 — API 키 없이 화면 구성을 확인하기 위한 것.

여기 숫자는 **실제 관측·통계가 아니다.** 화면 상단에 그렇게 표시된다.
좌표만은 세종시 실제 지점 근처로 잡아 두었다. 지도 배치를 눈으로 확인해야
쓸모가 있기 때문이다.
"""
from __future__ import annotations

from .common import now_kst, stamp

_SPOTS = [
    # (레이어, 이름, 위도, 경도, 사고, 사망, 중상, 경상)
    ("lg", "조치원읍 조치원사거리 부근", 36.6009, 127.2960, 14, 1, 5, 12),
    ("lg", "한누리대로 정부세종청사 북측", 36.5040, 127.2600, 11, 0, 3, 14),
    ("lg", "금남면 용포리 국도1호선", 36.4382, 127.2870, 9, 1, 4, 7),
    ("lg", "연서면 봉암리 교차로", 36.5720, 127.2450, 8, 0, 2, 9),
    ("lg", "부강면 부강리 국도4호선", 36.5290, 127.3800, 7, 1, 3, 5),
    ("schoolzone", "조치원대동초 앞", 36.6045, 127.2977, 5, 0, 1, 6),
    ("schoolzone", "도담동 도담초 앞", 36.5115, 127.2510, 4, 0, 0, 5),
    ("schoolzone", "아름동 가락초 앞", 36.5195, 127.2380, 3, 0, 1, 3),
    ("jaywalk", "조치원역 앞 무단횡단", 36.6001, 127.2965, 6, 1, 2, 4),
    ("jaywalk", "한솔동 첫마을3단지 앞", 36.4830, 127.2620, 4, 0, 2, 3),
    ("freezing", "장군면 금암리 곡선구간", 36.4930, 127.2140, 5, 1, 2, 3),
    ("freezing", "전동면 청람리 고갯길", 36.6480, 127.2400, 4, 0, 2, 2),
    ("oldman", "조치원읍 상리 시장 앞", 36.5980, 127.2930, 7, 1, 3, 4),
    ("oldman", "연동면 명학리 마을 앞", 36.5410, 127.3300, 4, 1, 1, 2),
    ("bicycle", "세종호수공원 북측 자전거도로", 36.4990, 127.2570, 5, 0, 2, 4),
]

_CAMERAS = [
    ("한누리대로 새롬동 구간", 36.4905, 127.2565, "속도 · 제한 60"),
    ("조치원 정 리 국도1호선", 36.6120, 127.2950, "속도 · 제한 70"),
    ("금남면 용포리", 36.4400, 127.2880, "신호·과속 · 제한 60"),
    ("보람동 시청 앞", 36.4795, 127.2890, "속도 · 제한 50"),
]

_ZONES = [
    ("조치원대동초등학교", 36.6047, 127.2980, "child"),
    ("도담초등학교", 36.5118, 127.2513, "child"),
    ("가락초등학교", 36.5198, 127.2383, "child"),
    ("한솔초등학교", 36.4838, 127.2626, "child"),
    ("연서면 노인복지관", 36.5715, 127.2455, "elder"),
    ("조치원 노인종합복지관", 36.5975, 127.2941, "elder"),
]

_EVENTS = [
    ("교통사고", "차대차 추돌", "경부고속도로 부강 부근 상행 2차로 통제",
     36.5300, 127.3760, 2),
    ("공사", "포장 보수", "한누리대로 도담동 구간 야간 차로 축소",
     36.5090, 127.2540, 1),
    ("기상", "안개", "금강 교량부 저시정 주의", 36.4870, 127.2880, 0),
]

_FLOW = [
    ("한누리대로(북)", "brt", 22.4), ("한누리대로(남)", "brt", 41.0),
    ("국도1호선 조치원", "sub", 33.6), ("국도36호선 연서", "sub", 52.1),
    ("경부고속도로 남세종", "expressway", 88.3),
    ("서울세종고속도로 장군", "expressway", 94.7),
    ("대덕대로 금남", "arterial", 47.2), ("가로수로 도담", "arterial", 28.9),
    ("시청대로 보람", "collector", 19.5), ("절재로 새롬", "brt", 36.8),
]


def _spot(index, layer, name, lat, lon, count, death, serious, slight):
    labels = {"lg": "전체 사고다발지", "schoolzone": "스쿨존 어린이",
              "jaywalk": "보행자 무단횡단", "freezing": "결빙(도로 살얼음)",
              "oldman": "노인 보행", "bicycle": "자전거"}
    groups = {"lg": "base", "schoolzone": "vuln", "jaywalk": "vuln",
              "freezing": "risk", "oldman": "vuln", "bicycle": "vuln"}
    return {
        "layer": layer, "layer_label": labels[layer], "group": groups[layer],
        "year": now_kst().year - 2, "id": "demo-%02d" % index, "name": name,
        "bjd": "36110", "sido_sgg": "세종특별자치시",
        "lat": lat, "lon": lon,
        "accidents": count, "deaths": death, "serious": serious,
        "slight": slight, "wounded": 0,
        "casualties": death + serious + slight,
        "severity": death * 12 + serious * 3 + slight,
        "poly": None,
    }


def build() -> dict:
    year = now_kst().year - 2
    spots = [_spot(i, *row) for i, row in enumerate(_SPOTS)]

    layers = {}
    for spot in spots:
        row = layers.setdefault(spot["layer"], {
            "id": spot["layer"], "label": spot["layer_label"],
            "group": spot["group"], "weight": 1.0, "year": year,
            "count": 0, "accidents": 0, "deaths": 0, "casualties": 0,
            "endpoint": "(샘플)"})
        row["count"] += 1
        row["accidents"] += spot["accidents"]
        row["deaths"] += spot["deaths"]
        row["casualties"] += spot["casualties"]

    facility_items = []
    for name, lat, lon, note in _CAMERAS:
        facility_items.append({"layer": "camera", "layer_label": "무인교통단속카메라",
                               "icon": "camera", "name": name, "lat": lat, "lon": lon,
                               "notes": [note], "addr": "세종특별자치시"})
    for name, lat, lon, kind in _ZONES:
        label = "어린이보호구역" if kind == "child" else "노인·장애인 보호구역"
        facility_items.append({"layer": "%s_zone" % kind, "layer_label": label,
                               "icon": "zone-%s" % kind, "name": name,
                               "lat": lat, "lon": lon, "notes": [],
                               "addr": "세종특별자치시"})

    facility_layers = {}
    for item in facility_items:
        row = facility_layers.setdefault(item["layer"], {
            "id": item["layer"], "label": item["layer_label"],
            "icon": item["icon"], "count": 0, "raw": 0, "endpoint": "(샘플)"})
        row["count"] += 1
        row["raw"] += 1

    events = [{"kind": kind, "detail": detail, "message": msg, "road": "",
               "link": "", "lat": lat, "lon": lon,
               "start": stamp(now_kst()), "end": "", "blocked": blocked,
               "in_sejong": True}
              for kind, detail, msg, lat, lon, blocked in _EVENTS]

    grade = {"expressway": "smooth", "brt": "delay", "arterial": "slow",
             "sub": "slow", "collector": "delay"}
    flow = []
    for name, cls, speed in _FLOW:
        if speed >= 50:
            g = "smooth"
        elif speed >= 30:
            g = "slow"
        elif speed >= 15:
            g = "delay"
        else:
            g = "jam"
        flow.append({"link": "", "road": name, "rank": cls, "speed": speed,
                     "travel_time": None, "grade": g, "time": stamp(now_kst())})
    flow.sort(key=lambda r: r["speed"])
    speeds = [r["speed"] for r in flow]

    now = {"base": stamp(now_kst())[:14] + "00", "temp": 1.4, "rain_1h": 0.4,
           "humidity": 88.0, "wind": 2.6, "pty": "비"}
    forecast = {"base": stamp(now_kst())[:14] + "00", "slots": [],
                "rain_sum": 6.0, "pop_max": 70, "temp_min": -1.0}
    from .kma import road_risk

    return {
        "demo": True,
        "generated_at": stamp(now_kst()),
        "koroad": {"sido": "36", "gugun": "110", "year": year,
                   "asked_year": year,
                   "layers": sorted(layers.values(), key=lambda r: -r["accidents"]),
                   "spots": sorted(spots, key=lambda s: -s["severity"]),
                   "errors": [], "pending": ["보행자 전체", "이륜차", "사망사고 지점"]},
        "its": {"flow": flow, "events": events, "cctv": [], "errors": [],
                "collected_at": stamp(now_kst()),
                "summary": {"links": len(flow),
                            "avg_speed": round(sum(speeds) / len(speeds), 1),
                            "jam": sum(1 for r in flow
                                       if r["grade"] in ("jam", "delay")),
                            "events": len(events),
                            "accidents": sum(1 for e in events
                                             if e["kind"] == "교통사고")}},
        "facility": {"layers": sorted(facility_layers.values(),
                                      key=lambda r: -r["count"]),
                     "items": facility_items, "errors": [],
                     "pending": ["횡단보도", "자전거도로"]},
        "kma": {"grid": {"nx": 66, "ny": 103, "lat": 36.48, "lon": 127.289},
                "now": now, "forecast": forecast,
                "warnings": [{"title": "대설 예비특보 (세종)", "time": "202612120600",
                              "detail": "야간 도로 결빙 우려"}],
                "errors": [], "risk": road_risk(now, forecast)},
    }

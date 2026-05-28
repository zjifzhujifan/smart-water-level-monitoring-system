from __future__ import annotations

import math
import random
from datetime import datetime, timedelta
from typing import Any


def sample_devices() -> list[dict[str, Any]]:
    return [
        {
            "id": 1,
            "deviceCode": "WL-001",
            "deviceName": "1号水位监测站",
            "location": "河道上游D区",
            "status": 1,
            "warningLevel": 80.0,
            "dangerLevel": 100.0,
            "lastDataTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        {
            "id": 4,
            "deviceCode": "WL-004",
            "deviceName": "4号水位监测站",
            "location": "实验室水桶",
            "status": 1,
            "warningLevel": 43.33,
            "dangerLevel": 57.77,
            "lastDataTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    ]


def make_record(device: dict[str, Any], index: int, total: int) -> dict[str, Any]:
    rng = random.Random(int(device["id"]) * 10000 + index)
    warning = float(device.get("warningLevel") or 80)
    danger = float(device.get("dangerLevel") or 100)
    base = warning * 0.65
    wave = math.sin(index / 10) * warning * 0.1
    drift = (index / max(total, 1)) * warning * 0.25
    noise = rng.uniform(-2.5, 2.5)
    level = max(0, round(base + wave + drift + noise, 2))
    if index % 57 == 0:
        level = round(danger + rng.uniform(1, 8), 2)
    elif index % 31 == 0:
        level = round(warning + rng.uniform(1, 5), 2)
    status = 2 if level >= danger else 1 if level >= warning else 0
    collect_time = datetime.now() - timedelta(minutes=(total - index) * 3)
    return {
        "id": 100000 + index,
        "deviceId": device["id"],
        "deviceCode": device["deviceCode"],
        "waterLevel": level,
        "rawValue": int(max(0, 120 - level)),
        "status": status,
        "collectTime": collect_time.strftime("%Y-%m-%d %H:%M:%S"),
        "receiveTime": (collect_time + timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S"),
    }


def history(device: dict[str, Any], count: int = 120) -> list[dict[str, Any]]:
    return [make_record(device, i + 1, count) for i in range(count)]


def alarms_from_records(device: dict[str, Any], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    alarms: list[dict[str, Any]] = []
    for record in records:
        if int(record.get("status", 0)) == 0:
            continue
        alarm_type = int(record["status"])
        alarms.append(
            {
                "id": int(device["id"]) * 1000000 + 200000 + int(record["id"]),
                "deviceId": device["id"],
                "deviceCode": device["deviceCode"],
                "alarmType": alarm_type,
                "alarmLevel": record["waterLevel"],
                "thresholdValue": device["dangerLevel"] if alarm_type == 2 else device["warningLevel"],
                "alarmMessage": "模拟危险报警" if alarm_type == 2 else "模拟预警报警",
                "alarmTime": record["collectTime"],
                "isResolved": 0 if alarm_type == 2 else int(int(record["id"]) % 3 == 0),
            }
        )
    return alarms

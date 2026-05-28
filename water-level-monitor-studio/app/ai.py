from __future__ import annotations

from collections import Counter
from statistics import mean, pstdev
from typing import Any


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def water_stats(records: list[dict[str, Any]]) -> dict[str, float | int]:
    levels = [_num(record.get("waterLevel")) for record in records]
    if not levels:
        return {
            "count": 0,
            "max": 0.0,
            "min": 0.0,
            "avg": 0.0,
            "std": 0.0,
            "normal": 0,
            "warning": 0,
            "danger": 0,
        }
    status_count = Counter(int(record.get("status", 0)) for record in records)
    return {
        "count": len(levels),
        "max": round(max(levels), 2),
        "min": round(min(levels), 2),
        "avg": round(mean(levels), 2),
        "std": round(pstdev(levels), 2) if len(levels) > 1 else 0.0,
        "normal": status_count.get(0, 0),
        "warning": status_count.get(1, 0),
        "danger": status_count.get(2, 0),
    }


def detect_anomalies(records: list[dict[str, Any]]) -> dict[str, Any]:
    levels = [_num(record.get("waterLevel")) for record in records]
    if len(levels) < 4:
        return {"count": 0, "indices": [], "mean": 0.0, "std": 0.0, "slope": 0.0, "delta": 0.0}
    avg = mean(levels)
    spread = pstdev(levels) if len(levels) > 1 else 0.0
    threshold = avg + max(spread * 2, 4)
    indices = [index for index, level in enumerate(levels) if level >= threshold]
    recent = levels[-10:] if len(levels) >= 10 else levels
    previous = levels[-20:-10] if len(levels) >= 20 else levels[: max(0, len(levels) - len(recent))]
    recent_avg = mean(recent) if recent else avg
    previous_avg = mean(previous) if previous else avg
    delta = round(recent_avg - previous_avg, 2)
    slope = round((levels[-1] - levels[0]) / max(len(levels) - 1, 1), 4)
    return {
        "count": len(indices),
        "indices": indices,
        "mean": round(avg, 2),
        "std": round(spread, 2),
        "slope": slope,
        "delta": delta,
    }


def risk_level(device: dict[str, Any] | None, stats: dict[str, Any], alarms: list[dict[str, Any]]) -> tuple[str, str]:
    if not device:
        return "未知", "缺少设备信息，无法评估风险。"
    danger = _num(device.get("dangerLevel"), 100)
    warning = _num(device.get("warningLevel"), 80)
    max_level = _num(stats.get("max"))
    unresolved = sum(1 for alarm in alarms if int(alarm.get("isResolved", 0)) == 0)
    if max_level >= danger or any(int(a.get("alarmType", 0)) == 2 and int(a.get("isResolved", 0)) == 0 for a in alarms):
        return "高风险", "存在危险水位或未处理危险报警，需要优先现场确认。"
    if max_level >= warning or unresolved > 0:
        return "中风险", "水位接近或达到预警线，建议提高巡检频率并核对阈值设置。"
    return "低风险", "当前样本主要处于正常范围，可保持常规监测。"


def generate_ai_report(
    device: dict[str, Any] | None,
    records: list[dict[str, Any]],
    alarms: list[dict[str, Any]],
) -> str:
    stats = water_stats(records)
    anomaly = detect_anomalies(records)
    level, reason = risk_level(device, stats, alarms)
    device_name = device.get("deviceName") if device else "未选择设备"
    device_code = device.get("deviceCode") if device else "-"
    unresolved = sum(1 for alarm in alarms if int(alarm.get("isResolved", 0)) == 0)
    warning_count = sum(1 for alarm in alarms if int(alarm.get("alarmType", 0)) == 1)
    danger_count = sum(1 for alarm in alarms if int(alarm.get("alarmType", 0)) == 2)

    lines = [
        f"AI 智能运维分析报告 - {device_name}（{device_code}）",
        "",
        "一、数据概况",
        f"本次分析共读取水位记录 {stats['count']} 条，最高水位 {stats['max']} cm，最低水位 {stats['min']} cm，平均水位 {stats['avg']} cm，标准差 {stats['std']} cm。",
        f"状态分布方面，正常记录 {stats['normal']} 条，预警记录 {stats['warning']} 条，危险记录 {stats['danger']} 条。",
        f"异常检测结果：识别出 {anomaly['count']} 个异常采样点，近期趋势斜率 {anomaly['slope']:+.4f}，近两段均值差 {anomaly['delta']:+.2f} cm。",
        "",
        "二、报警情况",
        f"当前筛选范围内共关联报警 {len(alarms)} 条，其中预警报警 {warning_count} 条、危险报警 {danger_count} 条，未处理报警 {unresolved} 条。",
        "",
        "三、风险判断",
        f"综合水位峰值、报警类型和处理状态，系统给出的风险等级为：{level}。{reason}",
        "",
        "四、处置建议",
    ]

    if level == "高风险":
        lines.extend(
            [
                "1. 优先检查现场水位是否仍处于危险阈值附近，必要时启动人工处置或排水设备。",
                "2. 检查 ESP32、HC-SR04 和供电线路，确认数据不是由传感器安装松动或回波异常造成。",
                "3. 对未处理报警进行确认，避免报警记录长期积压影响后续判断。",
            ]
        )
    elif level == "中风险":
        lines.extend(
            [
                "1. 增加对该设备的观察频率，重点关注水位是否持续接近预警阈值。",
                "2. 复核设备阈值是否与当前容器高度和现场环境一致。",
                "3. 若短时间内连续出现预警，可检查传感器固定角度和水面波动情况。",
            ]
        )
    else:
        lines.extend(
            [
                "1. 当前设备运行状态整体稳定，保持常规巡检即可。",
                "2. 建议定期导出历史数据，持续观察平均水位和波动范围。",
                "3. 保持设备端彩屏、蜂鸣器和上传接口联调记录，便于后续追溯。",
            ]
        )
    return "\n".join(lines)


def build_analysis_summary(records: list[dict[str, Any]], device: dict[str, Any] | None = None) -> dict[str, Any]:
    stats = water_stats(records)
    anomaly = detect_anomalies(records)
    values = [_num(record.get("waterLevel")) for record in records]
    warning = _num(device.get("warningLevel")) if device else 0.0
    danger = _num(device.get("dangerLevel")) if device else 0.0
    latest = values[-1] if values else 0.0
    return {
        "stats": stats,
        "anomaly": anomaly,
        "latest": latest,
        "warning_margin": round(max(warning - latest, 0), 2),
        "danger_margin": round(max(danger - latest, 0), 2),
        "trend": anomaly["slope"],
    }


def classify_alarm_causes(
    device: dict[str, Any] | None,
    records: list[dict[str, Any]],
    alarms: list[dict[str, Any]],
) -> str:
    stats = water_stats(records)
    anomaly = detect_anomalies(records)
    causes: list[str] = []
    if stats["danger"] > 0:
        causes.append("水位超过危险阈值，优先判断为真实高水位风险。")
    if anomaly["count"] > 0 and stats["std"] >= 8:
        causes.append("存在尖峰异常且标准差偏大，可能与传感器抖动、水面波动或安装角度有关。")
    if alarms and all(int(alarm.get("isResolved", 0)) == 0 for alarm in alarms[:3]):
        causes.append("近期报警未处理比例较高，可能存在人工确认滞后。")
    if device and int(device.get("status", 1)) == 0:
        causes.append("设备处于离线状态，需检查 ESP32 供电、WiFi 和后端地址。")
    if not causes:
        causes.append("当前未发现明显异常原因，建议保持常规巡检并继续观察趋势。")
    return "报警原因分类：\n" + "\n".join(f"{index + 1}. {item}" for index, item in enumerate(causes))


def generate_test_conclusion(
    device: dict[str, Any] | None,
    records: list[dict[str, Any]],
    alarms: list[dict[str, Any]],
) -> str:
    stats = water_stats(records)
    anomaly = detect_anomalies(records)
    device_name = device.get("deviceName") if device else "当前设备"
    unresolved = sum(1 for alarm in alarms if int(alarm.get("isResolved", 0)) == 0)
    return "\n".join(
        [
            f"测试结论 - {device_name}",
            f"本轮测试读取水位记录 {stats['count']} 条，最高水位 {stats['max']} cm，最低水位 {stats['min']} cm，平均水位 {stats['avg']} cm。",
            f"报警验证方面，预警记录 {stats['warning']} 条，危险记录 {stats['danger']} 条，关联未处理报警 {unresolved} 条。",
            f"数据质量方面，异常点 {anomaly['count']} 个，趋势斜率 {anomaly['slope']:+.4f}，标准差 {stats['std']} cm。",
            "综合判断：系统能够完成水位采集、阈值判断、报警展示、历史查询和智能分析，满足桌面端监测与联调演示要求。",
        ]
    )


def answer_question(question: str, device: dict[str, Any] | None, records: list[dict[str, Any]], alarms: list[dict[str, Any]]) -> str:
    q = question.strip()
    if not q:
        return "请输入需要分析的问题。"
    stats = water_stats(records)
    if "上传" in q or "失败" in q or "接口" in q:
        return "建议先检查三点：设备编号是否存在于 device 表、ESP32 的 SERVER_URL 是否指向当前后端 IP、后端 /api/water-level/upload 是否可访问。若使用 WL-004，需要确认设备管理中已经存在该设备。"
    if "波动" in q or "不稳定" in q or "抖动" in q:
        return "水位波动通常与液面扰动、容器边缘反射、传感器角度和供电稳定性有关。建议固定 HC-SR04 安装位置，增加多次测距取中值，并适当调低 EMA 平滑系数。"
    if "报警" in q or "危险" in q or "预警" in q:
        unresolved = sum(1 for alarm in alarms if int(alarm.get("isResolved", 0)) == 0)
        return f"当前样本中最高水位为 {stats['max']} cm，未处理报警 {unresolved} 条。建议先处理未确认报警，再结合预警阈值和危险阈值判断是否需要现场处置。"
    if "趋势" in q or "分析" in q:
        return f"当前平均水位 {stats['avg']} cm，标准差 {stats['std']} cm。若标准差持续增大，说明水位波动增强；若最高水位接近危险阈值，应提高监测频率。"
    name = device.get("deviceName") if device else "当前设备"
    return f"已基于 {name} 的历史记录生成判断：最高水位 {stats['max']} cm、平均水位 {stats['avg']} cm、报警 {len(alarms)} 条。建议结合实时监控页和报警中心进一步核对。"

from __future__ import annotations

import json
import random
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QDateTime, QSize, QTimer, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateTimeEdit,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QDoubleSpinBox,
    QStackedWidget,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.ai import (
    answer_question,
    build_analysis_summary,
    classify_alarm_causes,
    generate_ai_report,
    generate_test_conclusion,
    water_stats,
)
from app.api_client import ApiError, WaterMonitorApi
from app.cache import LocalCache
from app.config import AppConfig
from app.exporter import export_records_csv, export_records_excel, export_text_pdf
from app.simulator import alarms_from_records, history as simulated_history, sample_devices
from app.ui.icons import nav_icon
from app.ui.widgets import MetricCard, Panel, StatusPill, TimeSeriesChart, set_table_data
from app.ws_client import StompSockJsClient


def records_from_page(page: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(page, list):
        return page
    if not isinstance(page, dict):
        return []
    records = page.get("records")
    if isinstance(records, list):
        return records
    return []


def level_status(status: int | None) -> tuple[str, str]:
    if status == 2:
        return "危险", "danger"
    if status == 1:
        return "预警", "warning"
    return "正常", "normal"


def alarm_type_label(value: Any) -> str:
    try:
        alarm_type = int(value)
    except (TypeError, ValueError):
        return str(value or "未知")
    return {1: "预警报警", 2: "危险报警"}.get(alarm_type, "未知报警")


def resolved_label(value: Any) -> str:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        resolved = 0
    return "已处理" if resolved == 1 else "未处理"


def same_id(left: Any, right: Any) -> bool:
    try:
        return int(left) == int(right)
    except (TypeError, ValueError):
        return False


def int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def role_label(role: str) -> str:
    return {"admin": "管理员", "debugger": "调试员", "viewer": "访客"}.get(role, role)


def level_values(records: list[dict[str, Any]]) -> list[float]:
    values: list[float] = []
    for record in reversed(records):
        try:
            values.append(float(record.get("waterLevel", 0)))
        except (TypeError, ValueError):
            values.append(0)
    return values


class BasePage(QWidget):
    def __init__(self, window: "MainWindow", title: str, subtitle: str = "") -> None:
        super().__init__()
        self.window = window
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(18, 18, 18, 18)
        self.root.setSpacing(14)
        heading = QLabel(title)
        heading.setObjectName("Title")
        self.root.addWidget(heading)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("SubTitle")
            self.root.addWidget(sub)


class DashboardPage(BasePage):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window, "实时监控工作台", "查看设备当前水位、在线状态和最近趋势")
        self.device_combo = QComboBox()
        self.device_combo.currentIndexChanged.connect(self.on_device_changed)
        top = Panel()
        top_layout = QHBoxLayout(top)
        top_layout.addWidget(QLabel("监测设备"))
        top_layout.addWidget(self.device_combo, 1)
        self.connection = StatusPill("未连接", "offline")
        top_layout.addWidget(self.connection)
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.window.refresh_all)
        top_layout.addWidget(refresh)
        self.root.addWidget(top)

        cards = QGridLayout()
        self.current = MetricCard("当前水位", "- cm", "等待数据")
        self.status = MetricCard("状态", "-", "阈值判定")
        self.warning = MetricCard("预警阈值", "- cm", "设备配置")
        self.danger = MetricCard("危险阈值", "- cm", "设备配置")
        cards.addWidget(self.current, 0, 0)
        cards.addWidget(self.status, 0, 1)
        cards.addWidget(self.warning, 0, 2)
        cards.addWidget(self.danger, 0, 3)
        self.root.addLayout(cards)

        self.chart = TimeSeriesChart("最近水位趋势")
        self.root.addWidget(self.chart, 1)

        insight_grid = QGridLayout()
        summary_panel = Panel()
        summary_layout = QVBoxLayout(summary_panel)
        summary_layout.addWidget(QLabel("运行摘要"))
        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setFixedHeight(116)
        summary_layout.addWidget(self.summary)
        chain_panel = Panel()
        chain_layout = QVBoxLayout(chain_panel)
        chain_layout.addWidget(QLabel("硬件链路诊断"))
        self.chain = QTextEdit()
        self.chain.setReadOnly(True)
        self.chain.setFixedHeight(116)
        chain_layout.addWidget(self.chain)
        insight_grid.addWidget(summary_panel, 0, 0)
        insight_grid.addWidget(chain_panel, 0, 1)
        self.root.addLayout(insight_grid)

        self.recent_table = QTableWidget()
        self.recent_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.root.addWidget(self.recent_table)

    def on_device_changed(self) -> None:
        device_id = self.device_combo.currentData()
        if device_id:
            self.window.set_current_device(device_id)

    def set_devices(self, devices: list[dict[str, Any]], current_id: int | None) -> None:
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for device in devices:
            self.device_combo.addItem(
                f"{device.get('deviceCode')} - {device.get('deviceName')}",
                int(device.get("id")),
            )
        if current_id:
            index = self.device_combo.findData(current_id)
            if index >= 0:
                self.device_combo.setCurrentIndex(index)
        self.device_combo.blockSignals(False)

    def refresh(
        self,
        device: dict[str, Any] | None,
        latest: dict[str, Any] | None,
        records: list[dict[str, Any]],
        online: bool,
    ) -> None:
        self.connection.set_kind("normal" if online else "offline", "在线接口" if online else "离线/缓存")
        if not device:
            return
        source = "来自本地模拟数据" if self.window.simulation_mode else "来自后端状态字段"
        update_text = "模拟数据已更新" if self.window.simulation_mode else "实时数据已更新"
        warning = float(device.get("warningLevel") or 0)
        danger = float(device.get("dangerLevel") or 0)
        current_level = latest.get("waterLevel") if latest else "-"
        status_int = latest.get("status") if latest else None
        text, kind = level_status(status_int)
        self.current.set_value(f"{current_level} cm", latest.get("collectTime", "暂无最新数据") if latest else "暂无最新数据")
        self.current.set_kind(kind if latest else "offline")
        self.status.set_value(text, source)
        self.status.set_kind(kind)
        self.warning.set_value(f"{warning:.2f} cm", "达到后生成预警")
        self.warning.set_kind("warning")
        self.danger.set_value(f"{danger:.2f} cm", "达到后生成危险报警")
        self.danger.set_kind("danger")
        self.connection.set_kind(kind if latest else ("normal" if online else "offline"), update_text if latest else "等待数据")
        self.chart.set_series(level_values(records), warning, danger)
        self.update_insights(device, latest, records, online, warning, danger)
        set_table_data(
            self.recent_table,
            [
                ("deviceCode", "设备"),
                ("waterLevel", "水位(cm)"),
                ("rawValue", "原始值"),
                ("status", "状态"),
                ("collectTime", "采集时间"),
            ],
            records[:12],
        )

    def update_insights(
        self,
        device: dict[str, Any],
        latest: dict[str, Any] | None,
        records: list[dict[str, Any]],
        online: bool,
        warning: float,
        danger: float,
    ) -> None:
        stats = water_stats(records)
        values = level_values(records)
        latest_level = float_value(latest.get("waterLevel") if latest else None)
        trend = latest_level - values[-10] if len(values) >= 10 else 0.0
        trend_text = "上升" if trend > 1 else "下降" if trend < -1 else "平稳"
        margin_warning = max(warning - latest_level, 0)
        margin_danger = max(danger - latest_level, 0)
        self.summary.setPlainText(
            "\n".join(
                [
                    f"设备：{device.get('deviceCode')} / {device.get('deviceName')}",
                    f"样本：{stats['count']} 条，正常 {stats['normal']} 条，预警 {stats['warning']} 条，危险 {stats['danger']} 条。",
                    f"趋势：近 10 个采样点整体{trend_text}，变化 {trend:+.2f} cm。",
                    f"余量：距预警线 {margin_warning:.2f} cm，距危险线 {margin_danger:.2f} cm。",
                ]
            )
        )
        raw_value = latest.get("rawValue", "-") if latest else "-"
        source_text = "REST + WebSocket" if online else "本地缓存 / 离线模拟"
        self.chain.setPlainText(
            "\n".join(
                [
                    f"ESP32：deviceCode={device.get('deviceCode')}，在线状态={'在线' if int_value(device.get('status')) == 1 else '离线'}。",
                    f"HC-SR04：最近原始值 {raw_value}，换算水位 {latest_level:.2f} cm。",
                    f"通信链路：{source_text}，刷新周期 8 秒。",
                    f"报警逻辑：水位 >= {warning:.2f} cm 预警，>= {danger:.2f} cm 危险。",
                ]
            )
        )


class BigScreenPage(BasePage):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window, "监控大屏", "汇总设备、报警、趋势和风险态势")
        grid = QGridLayout()
        self.device_total = MetricCard("设备总数", kind="info")
        self.online_total = MetricCard("在线设备", kind="normal")
        self.unresolved_total = MetricCard("未处理报警", kind="warning")
        self.risk_level = MetricCard("综合风险", kind="normal")
        grid.addWidget(self.device_total, 0, 0)
        grid.addWidget(self.online_total, 0, 1)
        grid.addWidget(self.unresolved_total, 0, 2)
        grid.addWidget(self.risk_level, 0, 3)
        self.root.addLayout(grid)

        self.chart = TimeSeriesChart("主设备水位趋势")
        self.root.addWidget(self.chart, 1)

        lower = QGridLayout()
        self.alarm_table = QTableWidget()
        self.device_table = QTableWidget()
        lower.addWidget(self.alarm_table, 0, 0)
        lower.addWidget(self.device_table, 0, 1)
        self.root.addLayout(lower, 1)

    def refresh(self) -> None:
        devices = self.window.devices
        alarms = self.window.load_alarms(None)
        unresolved = [alarm for alarm in alarms if int_value(alarm.get("isResolved")) == 0]
        danger_count = sum(1 for alarm in unresolved if int_value(alarm.get("alarmType")) == 2)
        online_count = sum(1 for device in devices if int_value(device.get("status")) == 1)
        risk = "高风险" if danger_count else "中风险" if unresolved else "低风险"
        self.device_total.set_value(len(devices), "当前设备")
        self.online_total.set_value(online_count, "在线运行")
        self.unresolved_total.set_value(len(unresolved), "需要确认")
        self.unresolved_total.set_kind("danger" if danger_count else "warning" if unresolved else "normal")
        self.risk_level.set_value(risk, "按未处理报警评估")
        self.risk_level.set_kind("danger" if risk == "高风险" else "warning" if risk == "中风险" else "normal")
        device = self.window.device_by_id(self.window.current_device_id)
        records = self.window.load_history(self.window.current_device_id, page_size=180) if device else []
        self.chart.set_series(
            level_values(records),
            float_value(device.get("warningLevel")) if device else None,
            float_value(device.get("dangerLevel")) if device else None,
        )
        set_table_data(
            self.alarm_table,
            [
                ("deviceCode", "设备"),
                ("alarmType", "类型"),
                ("alarmLevel", "水位"),
                ("isResolved", "状态"),
                ("alarmTime", "时间"),
            ],
            alarms[:12],
        )
        set_table_data(
            self.device_table,
            [
                ("deviceCode", "设备"),
                ("deviceName", "名称"),
                ("status", "状态"),
                ("warningLevel", "预警"),
                ("dangerLevel", "危险"),
            ],
            devices,
        )


class DevicesPage(BasePage):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window, "设备管理", "查看设备编号、阈值、位置和最近上报时间")
        cards = QGridLayout()
        self.total = MetricCard("设备总数")
        self.online = MetricCard("在线设备")
        self.offline = MetricCard("离线设备")
        self.risk = MetricCard("最高危险阈值")
        cards.addWidget(self.total, 0, 0)
        cards.addWidget(self.online, 0, 1)
        cards.addWidget(self.offline, 0, 2)
        cards.addWidget(self.risk, 0, 3)
        self.root.addLayout(cards)

        self.table = QTableWidget()
        self.table.currentCellChanged.connect(self.show_detail)
        self.table.setMinimumHeight(220)
        self.table.setMaximumHeight(320)
        self.root.addWidget(self.table)
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setFixedHeight(120)
        self.root.addWidget(self.detail)
        self.root.addStretch()
        self.devices: list[dict[str, Any]] = []

    def refresh(self, devices: list[dict[str, Any]]) -> None:
        self.devices = devices
        online_count = sum(1 for device in devices if int(device.get("status", 0)) == 1)
        offline_count = len(devices) - online_count
        danger_values = [float(device.get("dangerLevel") or 0) for device in devices]
        self.total.set_value(len(devices), "当前已加载设备")
        self.total.set_kind("info")
        self.online.set_value(online_count, "状态为在线")
        self.online.set_kind("normal")
        self.offline.set_value(offline_count, "状态为离线")
        self.offline.set_kind("warning" if offline_count else "normal")
        self.risk.set_value(f"{max(danger_values or [0]):.2f} cm", "设备危险阈值上限")
        self.risk.set_kind("danger")
        set_table_data(
            self.table,
            [
                ("id", "ID"),
                ("deviceCode", "设备编号"),
                ("deviceName", "设备名称"),
                ("location", "位置"),
                ("status", "在线状态"),
                ("warningLevel", "预警阈值"),
                ("dangerLevel", "危险阈值"),
                ("lastDataTime", "最近上报"),
            ],
            devices,
        )
        if devices:
            self.table.selectRow(0)
            self.show_detail(0, 0, -1, -1)

    def show_detail(self, current_row: int, current_column: int, previous_row: int, previous_column: int) -> None:
        if current_row < 0 or current_row >= len(self.devices):
            return
        device = self.devices[current_row]
        text = "\n".join(
            [
                f"设备编号：{device.get('deviceCode')}",
                f"设备名称：{device.get('deviceName')}",
                f"安装位置：{device.get('location')}",
                f"在线状态：{'在线' if int(device.get('status', 0)) == 1 else '离线'}",
                f"阈值配置：预警 {float(device.get('warningLevel') or 0):.2f} cm / 危险 {float(device.get('dangerLevel') or 0):.2f} cm",
                f"最近上报：{device.get('lastDataTime') or '暂无'}",
            ]
        )
        self.detail.setPlainText(text)


class HistoryPage(BasePage):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window, "历史数据查询", "按设备和时间范围查看历史记录，并支持导出")
        filter_box = Panel()
        layout = QHBoxLayout(filter_box)
        self.device_combo = QComboBox()
        self.start_time = QDateTimeEdit(QDateTime.currentDateTime().addDays(-7))
        self.end_time = QDateTimeEdit(QDateTime.currentDateTime())
        for editor in (self.start_time, self.end_time):
            editor.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
            editor.setCalendarPopup(True)
        query = QPushButton("查询")
        query.setObjectName("Primary")
        query.clicked.connect(self.query)
        export_csv = QPushButton("导出 CSV")
        export_csv.clicked.connect(lambda: self.export("csv"))
        export_excel = QPushButton("导出 Excel")
        export_excel.clicked.connect(lambda: self.export("excel"))
        export_json = QPushButton("导出 JSON")
        export_json.clicked.connect(lambda: self.export("json"))
        layout.addWidget(QLabel("设备"))
        layout.addWidget(self.device_combo, 1)
        layout.addWidget(QLabel("开始"))
        layout.addWidget(self.start_time)
        layout.addWidget(QLabel("结束"))
        layout.addWidget(self.end_time)
        layout.addWidget(query)
        layout.addWidget(export_csv)
        layout.addWidget(export_excel)
        layout.addWidget(export_json)
        self.root.addWidget(filter_box)

        stats_grid = QGridLayout()
        self.result_count = MetricCard("查询记录", kind="info")
        self.result_max = MetricCard("最高水位", kind="danger")
        self.result_min = MetricCard("最低水位", kind="normal")
        self.result_abnormal = MetricCard("异常记录", kind="warning")
        stats_grid.addWidget(self.result_count, 0, 0)
        stats_grid.addWidget(self.result_max, 0, 1)
        stats_grid.addWidget(self.result_min, 0, 2)
        stats_grid.addWidget(self.result_abnormal, 0, 3)
        self.root.addLayout(stats_grid)

        self.chart = TimeSeriesChart("查询结果曲线")
        self.root.addWidget(self.chart, 1)
        self.table = QTableWidget()
        self.root.addWidget(self.table, 1)
        self.records: list[dict[str, Any]] = []

    def set_devices(self, devices: list[dict[str, Any]], current_id: int | None) -> None:
        self.device_combo.clear()
        for device in devices:
            self.device_combo.addItem(f"{device.get('deviceCode')} - {device.get('deviceName')}", int(device["id"]))
        if current_id:
            index = self.device_combo.findData(current_id)
            if index >= 0:
                self.device_combo.setCurrentIndex(index)

    def query(self) -> None:
        device_id = self.device_combo.currentData()
        self.records = self.window.load_history(
            device_id,
            self.start_time.dateTime().toString("yyyy-MM-dd HH:mm:ss"),
            self.end_time.dateTime().toString("yyyy-MM-dd HH:mm:ss"),
            page_size=500,
        )
        device = self.window.device_by_id(device_id)
        stats = water_stats(self.records)
        abnormal = stats["warning"] + stats["danger"]
        self.result_count.set_value(stats["count"], "当前时间范围")
        self.result_max.set_value(f"{stats['max']} cm", "样本峰值")
        self.result_min.set_value(f"{stats['min']} cm", "样本低位")
        self.result_abnormal.set_value(abnormal, "预警和危险记录")
        self.result_abnormal.set_kind("danger" if stats["danger"] else "warning" if abnormal else "normal")
        self.chart.set_series(
            level_values(self.records),
            float(device.get("warningLevel") or 0) if device else None,
            float(device.get("dangerLevel") or 0) if device else None,
        )
        set_table_data(
            self.table,
            [
                ("id", "ID"),
                ("deviceCode", "设备"),
                ("waterLevel", "水位"),
                ("rawValue", "原始值"),
                ("status", "状态"),
                ("collectTime", "采集时间"),
                ("receiveTime", "接收时间"),
            ],
            self.records,
        )

    def export(self, fmt: str) -> None:
        if not self.records:
            QMessageBox.information(self, "无数据", "请先查询历史数据。")
            return
        if fmt == "excel":
            path, _ = QFileDialog.getSaveFileName(self, "导出 Excel", "water_level_history.xlsx", "Excel (*.xlsx)")
        elif fmt == "json":
            path, _ = QFileDialog.getSaveFileName(self, "导出 JSON", "water_level_history.json", "JSON (*.json)")
        else:
            path, _ = QFileDialog.getSaveFileName(self, "导出 CSV", "water_level_history.csv", "CSV (*.csv)")
        if not path:
            return
        keys = ["id", "deviceCode", "waterLevel", "rawValue", "status", "collectTime", "receiveTime"]
        if fmt == "excel":
            export_records_excel(path, self.records, keys, ["ID", "设备", "水位", "原始值", "状态", "采集时间", "接收时间"])
        elif fmt == "json":
            Path(path).write_text(json.dumps(self.records, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            export_records_csv(path, self.records, keys)
        self.window.add_log("INFO", f"历史数据已导出: {path}")


class AlarmPage(BasePage):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window, "报警中心", "查看、筛选并处理预警和危险报警")
        actions = Panel()
        layout = QHBoxLayout(actions)
        self.device_combo = QComboBox()
        self.type_combo = QComboBox()
        self.type_combo.addItem("全部类型", None)
        self.type_combo.addItem("预警报警", 1)
        self.type_combo.addItem("危险报警", 2)
        self.only_unresolved = QPushButton("仅未处理")
        self.only_unresolved.setCheckable(True)
        self.only_unresolved.clicked.connect(self.query)
        resolve_all = QPushButton("一键处理")
        resolve_all.clicked.connect(self.resolve_all)
        sync_pending = QPushButton("同步待处理")
        sync_pending.clicked.connect(self.sync_pending)
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.query)
        layout.addWidget(QLabel("设备"))
        layout.addWidget(self.device_combo, 1)
        layout.addWidget(QLabel("类型"))
        layout.addWidget(self.type_combo)
        layout.addWidget(self.only_unresolved)
        layout.addWidget(refresh)
        layout.addWidget(sync_pending)
        layout.addStretch()
        layout.addWidget(resolve_all)
        self.root.addWidget(actions)

        cards = QGridLayout()
        self.total = MetricCard("报警总数")
        self.unresolved = MetricCard("未处理")
        self.warning_count = MetricCard("预警")
        self.danger_count = MetricCard("危险")
        self.pending_count = MetricCard("待同步")
        for column, card in enumerate(
            [self.total, self.unresolved, self.warning_count, self.danger_count, self.pending_count]
        ):
            cards.addWidget(card, 0, column)
            cards.setColumnStretch(column, 1)
        self.root.addLayout(cards)

        self.table = QTableWidget()
        self.table.currentCellChanged.connect(self.show_detail)
        self.table.setMinimumHeight(260)
        self.table.setMaximumHeight(360)
        self.root.addWidget(self.table)

        bottom = QGridLayout()
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setFixedHeight(126)
        self.operator = QLineEdit("admin")
        self.operator.setPlaceholderText("处理人")
        self.remark = QLineEdit()
        self.remark.setPlaceholderText("处理备注，例如：现场复核并已恢复")
        resolve_one = QPushButton("处理选中报警")
        resolve_one.setObjectName("Primary")
        resolve_one.clicked.connect(self.resolve_selected)
        process_selected = QPushButton("处理并记录")
        process_selected.clicked.connect(self.resolve_and_record)
        bottom.addWidget(self.detail, 0, 0, 2, 1)
        bottom.addWidget(self.operator, 0, 1)
        bottom.addWidget(self.remark, 1, 1)
        bottom.addWidget(resolve_one, 0, 2)
        bottom.addWidget(process_selected, 1, 2)
        self.root.addLayout(bottom)
        self.actions_table = QTableWidget()
        self.actions_table.setFixedHeight(140)
        self.root.addWidget(self.actions_table)
        self.root.addStretch()
        self.alarms: list[dict[str, Any]] = []
        self.filtered_alarms: list[dict[str, Any]] = []

        self.device_combo.currentIndexChanged.connect(self.query)
        self.type_combo.currentIndexChanged.connect(self.query)

    def set_devices(self, devices: list[dict[str, Any]], current_id: int | None) -> None:
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        self.device_combo.addItem("全部设备", None)
        for device in devices:
            self.device_combo.addItem(f"{device.get('deviceCode')} - {device.get('deviceName')}", int(device["id"]))
        if current_id:
            index = self.device_combo.findData(current_id)
            if index >= 0:
                self.device_combo.setCurrentIndex(index)
        self.device_combo.blockSignals(False)

    def query(self) -> None:
        self.alarms = self.window.load_alarms(0 if self.only_unresolved.isChecked() else None)
        device_id = self.device_combo.currentData()
        alarm_type = self.type_combo.currentData()
        self.filtered_alarms = [
            alarm
            for alarm in self.alarms
            if (device_id is None or same_id(alarm.get("deviceId"), device_id))
            and (alarm_type is None or same_id(alarm.get("alarmType"), alarm_type))
        ]
        unresolved_count = sum(1 for alarm in self.filtered_alarms if int_value(alarm.get("isResolved")) == 0)
        warning_count = sum(1 for alarm in self.filtered_alarms if int_value(alarm.get("alarmType")) == 1)
        danger_count = sum(1 for alarm in self.filtered_alarms if int_value(alarm.get("alarmType")) == 2)
        self.total.set_value(len(self.filtered_alarms), "当前筛选范围")
        self.total.set_kind("info")
        self.unresolved.set_value(unresolved_count, "需要人工确认")
        self.unresolved.set_kind("danger" if unresolved_count else "normal")
        self.warning_count.set_value(warning_count, "达到预警阈值")
        self.warning_count.set_kind("warning" if warning_count else "normal")
        self.danger_count.set_value(danger_count, "达到危险阈值")
        self.danger_count.set_kind("danger" if danger_count else "normal")
        pending_count = len(self.window.cache.pending_alarm_actions())
        self.pending_count.set_value(pending_count, "离线或失败待同步")
        self.pending_count.set_kind("warning" if pending_count else "normal")
        set_table_data(
            self.table,
            [
                ("id", "ID"),
                ("deviceCode", "设备"),
                ("alarmType", "类型"),
                ("alarmLevel", "水位"),
                ("thresholdValue", "阈值"),
                ("isResolved", "已处理"),
                ("alarmTime", "报警时间"),
                ("alarmMessage", "描述"),
            ],
            self.filtered_alarms,
        )
        if self.filtered_alarms:
            self.table.selectRow(0)
            self.show_detail(0, 0, -1, -1)
        else:
            self.detail.setPlainText("当前筛选条件下暂无报警记录。")
        self.refresh_actions()

    def resolve_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.filtered_alarms):
            QMessageBox.information(self, "未选择", "请选择一条报警记录。")
            return
        alarm_id = int(self.filtered_alarms[row]["id"])
        self.window.resolve_alarm(alarm_id, self.operator.text().strip(), self.remark.text().strip())
        self.query()

    def resolve_and_record(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.filtered_alarms):
            QMessageBox.information(self, "未选择", "请选择一条报警记录。")
            return
        alarm_id = int(self.filtered_alarms[row]["id"])
        self.window.resolve_alarm(alarm_id, self.operator.text().strip(), self.remark.text().strip())
        self.refresh_actions()

    def resolve_all(self) -> None:
        self.window.resolve_all_alarms(self.operator.text().strip(), self.remark.text().strip())
        self.query()

    def sync_pending(self) -> None:
        synced = self.window.sync_pending_actions()
        QMessageBox.information(self, "同步结果", f"已同步 {synced} 条待处理记录。")
        self.query()

    def show_detail(self, current_row: int, current_column: int, previous_row: int, previous_column: int) -> None:
        if current_row < 0 or current_row >= len(self.filtered_alarms):
            return
        alarm = self.filtered_alarms[current_row]
        related_actions = [item for item in self.window.cache.alarm_actions(50) if int_value(item.get("alarm_id")) == int_value(alarm.get("id"))]
        latest_action = related_actions[0] if related_actions else None
        text = "\n".join(
            [
                f"报警编号：{alarm.get('id')}",
                f"设备编号：{alarm.get('deviceCode')}",
                f"报警类型：{alarm_type_label(alarm.get('alarmType'))}",
                f"水位/阈值：{float(alarm.get('alarmLevel') or 0):.2f} cm / {float(alarm.get('thresholdValue') or 0):.2f} cm",
                f"处理状态：{resolved_label(alarm.get('isResolved'))}",
                f"报警时间：{alarm.get('alarmTime') or '暂无'}",
                f"最近处理：{latest_action.get('created_at') if latest_action else '暂无'}",
                f"处理人：{latest_action.get('operator') if latest_action else '暂无'}",
                f"备注：{latest_action.get('remark') if latest_action else '暂无'}",
                f"处理建议：先确认现场水位，再检查 ESP32、HC-SR04、供电和网络链路，必要时执行排水或人工复核。",
            ]
        )
        self.detail.setPlainText(text)

    def refresh_actions(self) -> None:
        set_table_data(
            self.actions_table,
            [
                ("created_at", "时间"),
                ("action", "动作"),
                ("alarm_id", "报警ID"),
                ("operator", "处理人"),
                ("remark", "备注"),
                ("is_synced", "已同步"),
            ],
            self.window.cache.alarm_actions(20),
        )


class AnalysisPage(BasePage):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window, "数据分析中心", "统计指标、移动平均、趋势分析和风险评估")
        top = Panel()
        layout = QHBoxLayout(top)
        self.device_combo = QComboBox()
        self.window_size = QSpinBox()
        self.window_size.setRange(2, 30)
        self.window_size.setValue(5)
        run = QPushButton("生成分析")
        run.setObjectName("Primary")
        run.clicked.connect(self.run_analysis)
        layout.addWidget(QLabel("设备"))
        layout.addWidget(self.device_combo, 1)
        layout.addWidget(QLabel("平滑窗口"))
        layout.addWidget(self.window_size)
        layout.addWidget(run)
        self.root.addWidget(top)

        grid = QGridLayout()
        self.count = MetricCard("记录数")
        self.avg = MetricCard("平均水位")
        self.max_level = MetricCard("最大水位")
        self.std = MetricCard("标准差")
        self.anomaly_count = MetricCard("异常点")
        self.trend = MetricCard("趋势斜率")
        self.danger_margin = MetricCard("危险余量")
        self.latest = MetricCard("最近水位")
        grid.addWidget(self.count, 0, 0)
        grid.addWidget(self.avg, 0, 1)
        grid.addWidget(self.max_level, 0, 2)
        grid.addWidget(self.std, 0, 3)
        grid.addWidget(self.anomaly_count, 1, 0)
        grid.addWidget(self.trend, 1, 1)
        grid.addWidget(self.danger_margin, 1, 2)
        grid.addWidget(self.latest, 1, 3)
        self.root.addLayout(grid)
        self.chart = TimeSeriesChart("分析曲线")
        self.root.addWidget(self.chart, 1)
        self.report = QTextEdit()
        self.report.setReadOnly(True)
        self.root.addWidget(self.report, 1)

    def set_devices(self, devices: list[dict[str, Any]], current_id: int | None) -> None:
        self.device_combo.clear()
        for device in devices:
            self.device_combo.addItem(f"{device.get('deviceCode')} - {device.get('deviceName')}", int(device["id"]))
        if current_id:
            index = self.device_combo.findData(current_id)
            if index >= 0:
                self.device_combo.setCurrentIndex(index)

    def run_analysis(self) -> None:
        device_id = self.device_combo.currentData()
        device = self.window.device_by_id(device_id)
        records = self.window.load_history(device_id, page_size=500)
        analysis = build_analysis_summary(records, device)
        stats = analysis["stats"]
        values = level_values(records)
        smooth = self.moving_average(values, self.window_size.value())
        self.count.set_value(stats["count"])
        self.count.set_kind("info")
        self.avg.set_value(f"{stats['avg']} cm")
        self.avg.set_kind("normal")
        self.max_level.set_value(f"{stats['max']} cm")
        max_kind = "danger" if device and stats["max"] >= float_value(device.get("dangerLevel")) else "warning" if device and stats["max"] >= float_value(device.get("warningLevel")) else "normal"
        self.max_level.set_kind(max_kind)
        self.std.set_value(f"{stats['std']} cm")
        self.std.set_kind("warning" if stats["std"] >= 8 else "normal")
        self.anomaly_count.set_value(analysis["anomaly"]["count"])
        self.anomaly_count.set_kind("danger" if analysis["anomaly"]["count"] else "normal")
        self.trend.set_value(f"{analysis['trend']:+.4f}")
        self.trend.set_kind("warning" if abs(analysis["trend"]) > 0.02 else "normal")
        self.danger_margin.set_value(f"{analysis['danger_margin']:.2f} cm")
        self.danger_margin.set_kind("danger" if analysis["danger_margin"] <= 5 else "warning" if analysis["danger_margin"] <= 15 else "normal")
        self.latest.set_value(f"{analysis['latest']:.2f} cm")
        self.latest.set_kind("info")
        self.chart.set_series(
            values,
            float(device.get("warningLevel") or 0) if device else None,
            float(device.get("dangerLevel") or 0) if device else None,
            smooth,
        )
        alarms = self.window.load_alarms(None)
        alarms = [alarm for alarm in alarms if same_id(alarm.get("deviceId"), device_id)]
        report = generate_ai_report(device, records, alarms)
        self.report.setPlainText(
            report
            + "\n\n附加分析："
            + f"\n- 最近水位 {analysis['latest']:.2f} cm"
            + f"\n- 趋势斜率 {analysis['trend']:+.4f}"
            + f"\n- 异常点数量 {analysis['anomaly']['count']}"
            + f"\n- 距危险阈值余量 {analysis['danger_margin']:.2f} cm"
        )

    @staticmethod
    def moving_average(values: list[float], window: int) -> list[float]:
        result: list[float] = []
        for i in range(len(values)):
            start = max(0, i - window + 1)
            result.append(round(sum(values[start : i + 1]) / (i - start + 1), 2))
        return result


class AiPage(BasePage):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window, "AI 智能分析中心", "自动生成运维报告、报警建议和硬件联调问答")
        actions = Panel()
        layout = QHBoxLayout(actions)
        self.device_combo = QComboBox()
        generate = QPushButton("生成智能报告")
        generate.setObjectName("Primary")
        generate.clicked.connect(self.generate)
        causes = QPushButton("报警原因分类")
        causes.clicked.connect(self.generate_causes)
        conclusion = QPushButton("生成测试结论")
        conclusion.clicked.connect(self.generate_conclusion)
        export = QPushButton("导出文本")
        export.clicked.connect(self.export_text)
        export_pdf = QPushButton("导出 PDF")
        export_pdf.clicked.connect(self.export_pdf)
        layout.addWidget(QLabel("设备"))
        layout.addWidget(self.device_combo, 1)
        layout.addWidget(generate)
        layout.addWidget(causes)
        layout.addWidget(conclusion)
        layout.addWidget(export)
        layout.addWidget(export_pdf)
        self.root.addWidget(actions)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.root.addWidget(self.output, 2)

        presets = Panel()
        preset_layout = QHBoxLayout(presets)
        for label, question in [
            ("上传失败排查", "设备上传失败应该检查哪些地方？"),
            ("水位波动分析", "HC-SR04 水位波动不稳定怎么办？"),
            ("报警处置建议", "出现危险报警后应该怎么处理？"),
            ("趋势风险判断", "当前水位趋势是否存在风险？"),
        ]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, q=question: self.ask_preset(q))
            preset_layout.addWidget(button)
        preset_layout.addStretch()
        self.root.addWidget(presets)

        qa = QGroupBox("硬件联调问答")
        qa_layout = QVBoxLayout(qa)
        self.question = QLineEdit()
        self.question.setPlaceholderText("例如：WL-004 上传失败怎么办？HC-SR04 测距波动大怎么办？")
        ask = QPushButton("提问")
        ask.clicked.connect(self.ask)
        qa_layout.addWidget(self.question)
        qa_layout.addWidget(ask)
        self.root.addWidget(qa)

    def set_devices(self, devices: list[dict[str, Any]], current_id: int | None) -> None:
        self.device_combo.clear()
        for device in devices:
            self.device_combo.addItem(f"{device.get('deviceCode')} - {device.get('deviceName')}", int(device["id"]))
        if current_id:
            index = self.device_combo.findData(current_id)
            if index >= 0:
                self.device_combo.setCurrentIndex(index)

    def context(self) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
        device_id = self.device_combo.currentData()
        device = self.window.device_by_id(device_id)
        records = self.window.load_history(device_id, page_size=500)
        alarms = [alarm for alarm in self.window.load_alarms(None) if same_id(alarm.get("deviceId"), device_id)]
        return device, records, alarms

    def generate(self) -> None:
        device, records, alarms = self.context()
        self.output.setPlainText(generate_ai_report(device, records, alarms))

    def generate_causes(self) -> None:
        device, records, alarms = self.context()
        old = self.output.toPlainText()
        self.output.setPlainText(f"{old}\n\n{classify_alarm_causes(device, records, alarms)}".strip())

    def generate_conclusion(self) -> None:
        device, records, alarms = self.context()
        old = self.output.toPlainText()
        self.output.setPlainText(f"{old}\n\n{generate_test_conclusion(device, records, alarms)}".strip())

    def ask(self) -> None:
        device, records, alarms = self.context()
        reply = answer_question(self.question.text(), device, records, alarms)
        old = self.output.toPlainText()
        self.output.setPlainText(f"{old}\n\n用户问题：{self.question.text()}\nAI 建议：{reply}".strip())

    def ask_preset(self, question: str) -> None:
        self.question.setText(question)
        self.ask()

    def export_text(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "导出 AI 报告", "ai_report.txt", "Text (*.txt)")
        if path:
            Path(path).write_text(self.output.toPlainText(), encoding="utf-8")
            self.window.add_log("INFO", f"AI 报告已导出: {path}")

    def export_pdf(self) -> None:
        text = self.output.toPlainText()
        if not text:
            QMessageBox.information(self, "无内容", "请先生成智能报告。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出 AI PDF 报告", "ai_report.pdf", "PDF (*.pdf)")
        if path:
            export_text_pdf(path, "水位监测 AI 智能运维报告", text)
            self.window.add_log("INFO", f"AI PDF 报告已导出: {path}")


class HardwarePage(BasePage):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window, "硬件联调工具", "模拟 ESP32 上传 JSON，查看设备端字段是否与后端匹配")
        workspace = QGridLayout()
        form_box = Panel()
        form = QFormLayout(form_box)
        self.device_combo = QComboBox()
        self.device_code = QLineEdit("WL-004")
        self.water_level = QDoubleSpinBox()
        self.water_level.setRange(0, 500)
        self.water_level.setDecimals(2)
        self.water_level.setValue(42.0)
        self.raw_value = QSpinBox()
        self.raw_value.setRange(0, 1000)
        self.raw_value.setValue(78)
        self.warning = QDoubleSpinBox()
        self.warning.setRange(0, 500)
        self.warning.setDecimals(2)
        self.warning.setValue(43.33)
        self.danger = QDoubleSpinBox()
        self.danger.setRange(0, 500)
        self.danger.setDecimals(2)
        self.danger.setValue(57.77)
        form.addRow("设备模板", self.device_combo)
        form.addRow("deviceCode", self.device_code)
        form.addRow("waterLevel", self.water_level)
        form.addRow("rawValue", self.raw_value)
        form.addRow("warningLevel", self.warning)
        form.addRow("dangerLevel", self.danger)
        workspace.addWidget(form_box, 0, 0)

        preview_box = Panel()
        preview_layout = QVBoxLayout(preview_box)
        preview_layout.addWidget(QLabel("请求体预览"))
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        preview_layout.addWidget(self.preview)
        workspace.addWidget(preview_box, 0, 1)
        workspace.setColumnStretch(0, 1)
        workspace.setColumnStretch(1, 2)
        self.root.addLayout(workspace)

        actions = Panel()
        action_layout = QHBoxLayout(actions)
        random_btn = QPushButton("随机生成")
        random_btn.clicked.connect(self.random_payload)
        preview_btn = QPushButton("刷新预览")
        preview_btn.clicked.connect(self.update_preview)
        send = QPushButton("模拟上传到后端")
        send.setObjectName("Primary")
        send.clicked.connect(self.upload)
        action_layout.addWidget(random_btn)
        action_layout.addWidget(preview_btn)
        action_layout.addStretch()
        action_layout.addWidget(send)
        self.root.addWidget(actions)

        payload_grid = QGridLayout()
        self.payload_status = MetricCard("报文判定")
        self.payload_margin = MetricCard("阈值余量")
        self.payload_target = MetricCard("通信目标")
        self.payload_size = MetricCard("报文大小")
        payload_grid.addWidget(self.payload_status, 0, 0)
        payload_grid.addWidget(self.payload_margin, 0, 1)
        payload_grid.addWidget(self.payload_target, 0, 2)
        payload_grid.addWidget(self.payload_size, 0, 3)
        self.root.addLayout(payload_grid)

        validate_box = Panel()
        validate_layout = QVBoxLayout(validate_box)
        validate_layout.addWidget(QLabel("字段校验"))
        self.validation = QTextEdit()
        self.validation.setReadOnly(True)
        self.validation.setFixedHeight(110)
        validate_layout.addWidget(self.validation)
        self.root.addWidget(validate_box)

        info_box = Panel()
        info_layout = QVBoxLayout(info_box)
        info_layout.addWidget(QLabel("设备端字段说明"))
        self.protocol = QTextEdit()
        self.protocol.setReadOnly(True)
        self.protocol.setFixedHeight(108)
        self.protocol.setPlainText(
            "deviceCode：设备唯一编号，需要与后端设备表一致。\n"
            "waterLevel：换算后的水位高度，单位 cm，由 HC-SR04 测距结果换算得到。\n"
            "rawValue：设备端保留的原始采样值，用于排查传感器波动和标定误差。\n"
            "warningLevel / dangerLevel：上传时携带的阈值，可用于联调后端报警生成逻辑。"
        )
        info_layout.addWidget(self.protocol)
        self.root.addWidget(info_box)

        self.history_table = QTableWidget()
        self.root.addWidget(self.history_table, 1)
        self.result = QTextEdit()
        self.result.setReadOnly(True)
        self.result.setFixedHeight(120)
        self.result.setPlainText("上传结果会在这里显示。离线演示模式下只记录本地校验结果；后端联调模式下会显示接口返回或异常信息。")
        self.root.addWidget(self.result)
        self.upload_rows: list[dict[str, Any]] = []
        self.refresh_upload_history()

        self.device_combo.currentIndexChanged.connect(self.on_device_changed)
        self.device_code.textChanged.connect(self.update_preview)
        self.water_level.valueChanged.connect(self.update_preview)
        self.raw_value.valueChanged.connect(self.update_preview)
        self.warning.valueChanged.connect(self.update_preview)
        self.danger.valueChanged.connect(self.update_preview)
        self.update_preview()

    def set_devices(self, devices: list[dict[str, Any]], current_id: int | None) -> None:
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for device in devices:
            self.device_combo.addItem(f"{device.get('deviceCode')} - {device.get('deviceName')}", int(device["id"]))
        if current_id:
            index = self.device_combo.findData(current_id)
            if index >= 0:
                self.device_combo.setCurrentIndex(index)
        self.device_combo.blockSignals(False)
        self.on_device_changed()

    def on_device_changed(self) -> None:
        device = self.window.device_by_id(self.device_combo.currentData())
        if not device:
            return
        self.device_code.setText(str(device.get("deviceCode") or ""))
        self.warning.setValue(float(device.get("warningLevel") or 0))
        self.danger.setValue(float(device.get("dangerLevel") or 0))
        self.update_preview()

    def payload(self) -> dict[str, Any]:
        return {
            "deviceCode": self.device_code.text().strip(),
            "waterLevel": round(self.water_level.value(), 2),
            "rawValue": self.raw_value.value(),
            "warningLevel": round(self.warning.value(), 2),
            "dangerLevel": round(self.danger.value(), 2),
        }

    def update_preview(self) -> None:
        payload = self.payload()
        payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
        self.preview.setPlainText(
            "POST /api/water-level/upload\n"
            "Content-Type: application/json\n\n"
            + payload_json
        )
        level = float_value(payload.get("waterLevel"))
        warning = float_value(payload.get("warningLevel"))
        danger = float_value(payload.get("dangerLevel"))
        if level >= danger:
            status_text, status_kind = "危险", "danger"
            margin = 0.0
        elif level >= warning:
            status_text, status_kind = "预警", "warning"
            margin = max(danger - level, 0)
        else:
            status_text, status_kind = "正常", "normal"
            margin = max(warning - level, 0)
        self.payload_status.set_value(status_text, "按当前阈值计算")
        self.payload_status.set_kind(status_kind)
        self.payload_margin.set_value(f"{margin:.2f} cm", "距离下一阈值")
        self.payload_margin.set_kind("danger" if margin <= 1 and status_text != "危险" else "info")
        self.payload_target.set_value("后端接口" if not self.window.simulation_mode else "离线预览", "/api/water-level/upload")
        self.payload_target.set_kind("info" if not self.window.simulation_mode else "offline")
        self.payload_size.set_value(f"{len(payload_json.encode('utf-8'))} B", "JSON UTF-8")
        self.payload_size.set_kind("normal")
        issues = []
        if not payload["deviceCode"]:
            issues.append("deviceCode 不能为空")
        if payload["warningLevel"] >= payload["dangerLevel"]:
            issues.append("warningLevel 必须小于 dangerLevel")
        if payload["waterLevel"] < 0:
            issues.append("waterLevel 不能小于 0")
        if payload["rawValue"] < 0:
            issues.append("rawValue 不能小于 0")
        if not issues:
            issues.append("当前报文字段完整，阈值关系正常，可直接上传。")
        self.validation.setPlainText("\n".join(f"- {item}" for item in issues))

    def random_payload(self) -> None:
        warning = self.warning.value()
        danger = self.danger.value()
        target = random.choice(["normal", "warning", "danger"])
        if target == "danger":
            level = random.uniform(max(danger, warning), max(danger + 8, warning + 8))
        elif target == "warning":
            level = random.uniform(warning + 0.5, max(danger - 0.5, warning + 1))
        else:
            level = random.uniform(0, max(warning - 1, 1))
        self.water_level.setValue(round(level, 2))
        self.raw_value.setValue(max(0, int(120 - level)))
        self.update_preview()

    def upload(self) -> None:
        payload = self.payload()
        if self.window.simulation_mode:
            self.result.setPlainText("离线演示模式未提交后端，已完成设备端协议预览：\n" + json.dumps(payload, ensure_ascii=False, indent=2))
            self.add_upload_history(payload, "离线预览", "未访问后端")
            self.window.add_log("INFO", f"离线模式生成硬件联调报文: {payload['deviceCode']}")
            return
        try:
            response = self.window.api.upload_simulated(**{
                "device_code": payload["deviceCode"],
                "water_level": payload["waterLevel"],
                "raw_value": payload["rawValue"],
                "warning_level": payload["warningLevel"],
                "danger_level": payload["dangerLevel"],
            })
        except ApiError as exc:
            self.result.setPlainText(f"上传失败：{exc}\n\n请求体：\n{json.dumps(payload, ensure_ascii=False, indent=2)}")
            self.add_upload_history(payload, "失败", str(exc))
            self.window.add_log("ERROR", f"模拟上传失败: {exc}")
            return
        self.result.setPlainText(json.dumps(response, ensure_ascii=False, indent=2))
        self.add_upload_history(payload, "成功", "后端已接收")
        self.window.add_log("INFO", f"模拟上传成功: {payload['deviceCode']}")
        self.window.refresh_all()

    def add_upload_history(self, payload: dict[str, Any], status: str, message: str) -> None:
        self.upload_rows.insert(
            0,
            {
                "time": QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss"),
                "deviceCode": payload.get("deviceCode"),
                "waterLevel": payload.get("waterLevel"),
                "rawValue": payload.get("rawValue"),
                "status": status,
                "message": message,
            },
        )
        self.upload_rows = self.upload_rows[:20]
        self.refresh_upload_history()

    def refresh_upload_history(self) -> None:
        set_table_data(
            self.history_table,
            [
                ("time", "时间"),
                ("deviceCode", "设备"),
                ("waterLevel", "水位"),
                ("rawValue", "原始值"),
                ("status", "结果"),
                ("message", "说明"),
            ],
            self.upload_rows,
        )


class VirtualEsp32Page(BasePage):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window, "虚拟 ESP32", "自动模拟设备端定时上传、断网恢复和异常水位")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.counter = 0
        self.rows: list[dict[str, Any]] = []

        top = Panel()
        layout = QHBoxLayout(top)
        self.device_combo = QComboBox()
        self.interval = QSpinBox()
        self.interval.setRange(1, 60)
        self.interval.setValue(3)
        self.base_level = QDoubleSpinBox()
        self.base_level.setRange(0, 300)
        self.base_level.setValue(45.0)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["平稳", "缓慢上涨", "波动", "异常尖峰"])
        start = QPushButton("启动")
        start.setObjectName("Primary")
        start.clicked.connect(self.start)
        stop = QPushButton("停止")
        stop.clicked.connect(self.stop)
        one = QPushButton("上传一次")
        one.clicked.connect(self.tick)
        layout.addWidget(QLabel("设备"))
        layout.addWidget(self.device_combo, 1)
        layout.addWidget(QLabel("间隔"))
        layout.addWidget(self.interval)
        layout.addWidget(QLabel("基准水位"))
        layout.addWidget(self.base_level)
        layout.addWidget(QLabel("曲线"))
        layout.addWidget(self.mode_combo)
        layout.addWidget(start)
        layout.addWidget(stop)
        layout.addWidget(one)
        self.root.addWidget(top)

        cards = QGridLayout()
        self.state = MetricCard("模拟状态", "停止", "虚拟设备未运行", "offline")
        self.sent = MetricCard("已上传", "0", "本轮会话")
        self.last_level = MetricCard("最近水位", "- cm", "等待上传")
        self.last_result = MetricCard("最近结果", "-", "等待上传")
        cards.addWidget(self.state, 0, 0)
        cards.addWidget(self.sent, 0, 1)
        cards.addWidget(self.last_level, 0, 2)
        cards.addWidget(self.last_result, 0, 3)
        self.root.addLayout(cards)

        self.chart = TimeSeriesChart("虚拟设备上传曲线")
        self.root.addWidget(self.chart, 1)
        self.table = QTableWidget()
        self.table.setMinimumHeight(190)
        self.table.setMaximumHeight(260)
        self.root.addWidget(self.table)
        self.root.addStretch()
        set_table_data(
            self.table,
            [
                ("deviceCode", "设备"),
                ("waterLevel", "水位"),
                ("rawValue", "原始值"),
                ("status", "状态"),
                ("collectTime", "时间"),
                ("result", "结果"),
            ],
            [],
        )

    def set_devices(self, devices: list[dict[str, Any]], current_id: int | None) -> None:
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for device in devices:
            self.device_combo.addItem(f"{device.get('deviceCode')} - {device.get('deviceName')}", int(device["id"]))
        if current_id:
            index = self.device_combo.findData(current_id)
            if index >= 0:
                self.device_combo.setCurrentIndex(index)
        self.device_combo.blockSignals(False)

    def start(self) -> None:
        self.timer.start(self.interval.value() * 1000)
        self.state.set_value("运行中", f"{self.interval.value()} 秒一次")
        self.state.set_kind("normal")

    def stop(self) -> None:
        self.timer.stop()
        self.state.set_value("停止", "虚拟设备未运行")
        self.state.set_kind("offline")

    def next_level(self, device: dict[str, Any]) -> float:
        base = self.base_level.value()
        mode = self.mode_combo.currentText()
        if mode == "缓慢上涨":
            return round(base + self.counter * 0.8, 2)
        if mode == "波动":
            return round(base + random.uniform(-8, 8), 2)
        if mode == "异常尖峰" and self.counter % 5 == 0:
            return round(float_value(device.get("dangerLevel")) + random.uniform(2, 12), 2)
        return round(base + random.uniform(-1.5, 1.5), 2)

    def tick(self) -> None:
        device = self.window.device_by_id(self.device_combo.currentData())
        if not device:
            return
        self.counter += 1
        level = max(0.0, self.next_level(device))
        warning = float_value(device.get("warningLevel"))
        danger = float_value(device.get("dangerLevel"))
        status = 2 if level >= danger else 1 if level >= warning else 0
        payload = {
            "id": int(QDateTime.currentMSecsSinceEpoch() % 1000000000),
            "deviceId": int_value(device.get("id")),
            "deviceCode": device.get("deviceCode"),
            "waterLevel": level,
            "rawValue": max(0, int(120 - level)),
            "status": status,
            "collectTime": QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss"),
            "receiveTime": QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss"),
        }
        result = "离线缓存"
        if self.window.simulation_mode:
            self.window.cache.save_water_levels([payload])
        else:
            try:
                self.window.api.upload_simulated(
                    device_code=str(payload["deviceCode"]),
                    water_level=level,
                    raw_value=int(payload["rawValue"]),
                    warning_level=warning,
                    danger_level=danger,
                )
                result = "后端成功"
            except ApiError as exc:
                result = f"失败: {exc}"
            self.window.cache.save_water_levels([payload])
        self.rows.insert(0, {**payload, "result": result})
        self.rows = self.rows[:120]
        self.sent.set_value(self.counter, "本轮会话")
        self.last_level.set_value(f"{level:.2f} cm", payload["collectTime"])
        self.last_level.set_kind("danger" if status == 2 else "warning" if status == 1 else "normal")
        self.last_result.set_value(result[:18], "上传链路")
        self.last_result.set_kind("danger" if "失败" in result else "normal")
        self.chart.set_series(level_values(self.rows), warning, danger)
        set_table_data(
            self.table,
            [
                ("deviceCode", "设备"),
                ("waterLevel", "水位"),
                ("rawValue", "原始值"),
                ("status", "状态"),
                ("collectTime", "时间"),
                ("result", "结果"),
            ],
            self.rows[:30],
        )
        self.window.add_log("INFO", f"虚拟 ESP32 上传: {payload['deviceCode']} {level:.2f} cm")


class LogPage(BasePage):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window, "系统日志", "记录接口调用、缓存降级、模拟上传和导出事件")
        actions = Panel()
        layout = QHBoxLayout(actions)
        self.level_combo = QComboBox()
        self.level_combo.addItems(["全部", "INFO", "WARN", "ERROR"])
        refresh = QPushButton("刷新日志")
        refresh.clicked.connect(self.refresh)
        clear = QPushButton("清空日志")
        clear.setObjectName("Danger")
        clear.clicked.connect(self.clear)
        export = QPushButton("导出 CSV")
        export.clicked.connect(self.export)
        layout.addWidget(QLabel("级别"))
        layout.addWidget(self.level_combo)
        layout.addWidget(refresh)
        layout.addStretch()
        layout.addWidget(export)
        layout.addWidget(clear)
        self.root.addWidget(actions)

        cards = QGridLayout()
        self.total = MetricCard("日志总数")
        self.info = MetricCard("INFO")
        self.warn = MetricCard("WARN")
        self.error = MetricCard("ERROR")
        cards.addWidget(self.total, 0, 0)
        cards.addWidget(self.info, 0, 1)
        cards.addWidget(self.warn, 0, 2)
        cards.addWidget(self.error, 0, 3)
        self.root.addLayout(cards)

        self.table = QTableWidget()
        self.root.addWidget(self.table, 1)
        self.logs: list[dict[str, Any]] = []
        self.level_combo.currentIndexChanged.connect(self.refresh)

    def refresh(self) -> None:
        level = self.level_combo.currentText()
        self.logs = self.window.cache.logs(level=level)
        all_logs = self.window.cache.logs(limit=1000)
        self.total.set_value(len(all_logs), "本地缓存日志")
        self.total.set_kind("info")
        self.info.set_value(sum(1 for item in all_logs if item.get("level") == "INFO"), "普通事件")
        self.info.set_kind("normal")
        self.warn.set_value(sum(1 for item in all_logs if item.get("level") == "WARN"), "降级或连接异常")
        self.warn.set_kind("warning")
        self.error.set_value(sum(1 for item in all_logs if item.get("level") == "ERROR"), "失败事件")
        self.error.set_kind("danger")
        set_table_data(
            self.table,
            [("created_at", "时间"), ("level", "级别"), ("message", "内容")],
            self.logs,
        )

    def clear(self) -> None:
        reply = QMessageBox.question(self, "确认清空", "确定要清空本地系统日志吗？")
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.window.cache.clear_logs()
        self.refresh()

    def export(self) -> None:
        if not self.logs:
            QMessageBox.information(self, "无数据", "当前筛选条件下没有日志。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出系统日志", "system_logs.csv", "CSV (*.csv)")
        if not path:
            return
        export_records_csv(path, self.logs, ["created_at", "level", "message"])
        self.window.add_log("INFO", f"系统日志已导出: {path}")
        self.refresh()


class MaintenancePage(BasePage):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window, "数据库维护", "查看缓存体积、表记录数量，并执行清理和压缩")
        actions = Panel()
        layout = QHBoxLayout(actions)
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.refresh)
        clean_logs = QPushButton("清理旧日志")
        clean_logs.clicked.connect(self.cleanup_logs)
        clean_water = QPushButton("清理旧水位")
        clean_water.clicked.connect(self.cleanup_water)
        vacuum = QPushButton("压缩数据库")
        vacuum.clicked.connect(self.vacuum)
        layout.addWidget(refresh)
        layout.addWidget(clean_logs)
        layout.addWidget(clean_water)
        layout.addWidget(vacuum)
        layout.addStretch()
        self.root.addWidget(actions)

        cards = QGridLayout()
        self.size = MetricCard("缓存大小", kind="info")
        self.tables = MetricCard("数据表", kind="info")
        self.records = MetricCard("总记录", kind="normal")
        self.cleaned = MetricCard("最近清理", "0", "等待操作", "offline")
        cards.addWidget(self.size, 0, 0)
        cards.addWidget(self.tables, 0, 1)
        cards.addWidget(self.records, 0, 2)
        cards.addWidget(self.cleaned, 0, 3)
        self.root.addLayout(cards)

        self.table = QTableWidget()
        self.root.addWidget(self.table, 1)
        self.refresh()

    def refresh(self) -> None:
        counts = self.window.cache.table_counts()
        total = sum(counts.values())
        size_mb = self.window.cache.database_size_bytes() / 1024 / 1024
        self.size.set_value(f"{size_mb:.2f} MB", self.window.cache.path.name)
        self.tables.set_value(len(counts), "SQLite 表")
        self.records.set_value(total, "全部缓存记录")
        rows = [{"table": table, "count": count} for table, count in counts.items()]
        set_table_data(self.table, [("table", "数据表"), ("count", "记录数")], rows)

    def cleanup_logs(self) -> None:
        removed = self.window.cache.cleanup_logs(keep=500)
        self.cleaned.set_value(removed, "已删除旧日志")
        self.cleaned.set_kind("warning" if removed else "normal")
        self.window.add_log("INFO", f"数据库维护清理旧日志 {removed} 条")
        self.refresh()

    def cleanup_water(self) -> None:
        removed = self.window.cache.cleanup_water_levels(keep=1000)
        self.cleaned.set_value(removed, "已删除旧水位")
        self.cleaned.set_kind("warning" if removed else "normal")
        self.window.add_log("INFO", f"数据库维护清理旧水位 {removed} 条")
        self.refresh()

    def vacuum(self) -> None:
        self.window.cache.vacuum()
        self.cleaned.set_value("完成", "SQLite VACUUM")
        self.cleaned.set_kind("normal")
        self.window.add_log("INFO", "数据库压缩完成")
        self.refresh()


class HealthPage(BasePage):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window, "系统自检", "检查运行环境、缓存、接口、实时推送和待同步任务")
        actions = Panel()
        layout = QHBoxLayout(actions)
        run = QPushButton("运行自检")
        run.setObjectName("Primary")
        run.clicked.connect(self.run_checks)
        backup = QPushButton("备份缓存")
        backup.clicked.connect(self.backup_cache)
        restore = QPushButton("恢复缓存")
        restore.clicked.connect(self.restore_cache)
        export = QPushButton("导出报告")
        export.clicked.connect(self.export_report)
        layout.addWidget(run)
        layout.addWidget(backup)
        layout.addWidget(restore)
        layout.addWidget(export)
        layout.addStretch()
        self.root.addWidget(actions)

        cards = QGridLayout()
        self.total = MetricCard("检查项", kind="info")
        self.passed = MetricCard("通过", kind="normal")
        self.warned = MetricCard("提示", kind="warning")
        self.failed = MetricCard("失败", kind="danger")
        cards.addWidget(self.total, 0, 0)
        cards.addWidget(self.passed, 0, 1)
        cards.addWidget(self.warned, 0, 2)
        cards.addWidget(self.failed, 0, 3)
        self.root.addLayout(cards)

        self.table = QTableWidget()
        self.root.addWidget(self.table, 1)
        self.report = QTextEdit()
        self.report.setReadOnly(True)
        self.report.setFixedHeight(180)
        self.root.addWidget(self.report)
        self.rows: list[dict[str, Any]] = []
        self.run_checks()

    def add_check(self, name: str, status: str, detail: str) -> None:
        self.rows.append({"name": name, "status": status, "detail": detail})

    def run_checks(self) -> None:
        self.rows = []
        cache_path = self.window.cache.path
        self.add_check("Python 运行环境", "通过", sys.executable)
        self.add_check("缓存文件", "通过" if cache_path.exists() else "失败", str(cache_path))
        self.add_check("缓存目录可写", "通过" if cache_path.parent.exists() and cache_path.parent.is_dir() else "失败", str(cache_path.parent))
        self.add_check("设备加载", "通过" if self.window.devices else "失败", f"{len(self.window.devices)} 台设备")
        self.add_check("运行模式", "提示" if self.window.simulation_mode else "通过", "离线演示" if self.window.simulation_mode else "后端联调")
        pending = len(self.window.cache.pending_alarm_actions())
        self.add_check("待同步任务", "提示" if pending else "通过", f"{pending} 条")
        self.add_check("实时推送", "提示" if self.window.simulation_mode else ("通过" if self.window.ws_client and self.window.ws_client.isRunning() else "提示"), self.window.last_sync_text)
        self.add_check("日志记录", "通过", f"{len(self.window.cache.logs(1000))} 条")
        if self.window.simulation_mode:
            self.add_check("后端接口", "提示", "离线演示模式未访问后端")
        else:
            try:
                devices = self.window.api.devices()
            except ApiError as exc:
                self.add_check("后端接口", "失败", str(exc))
            else:
                self.add_check("后端接口", "通过", f"读取到 {len(devices)} 台设备")

        passed = sum(1 for row in self.rows if row["status"] == "通过")
        warned = sum(1 for row in self.rows if row["status"] == "提示")
        failed = sum(1 for row in self.rows if row["status"] == "失败")
        self.total.set_value(len(self.rows), "当前自检项")
        self.passed.set_value(passed, "可以正常工作")
        self.warned.set_value(warned, "需要关注")
        self.failed.set_value(failed, "需要修复")
        set_table_data(
            self.table,
            [("name", "检查项"), ("status", "状态"), ("detail", "详情")],
            self.rows,
        )
        self.report.setPlainText(self.build_report())

    def build_report(self) -> str:
        lines = [
            "Water Level Monitor Studio 系统自检报告",
            f"生成时间：{QDateTime.currentDateTime().toString('yyyy-MM-dd HH:mm:ss')}",
            f"运行模式：{'离线演示' if self.window.simulation_mode else '后端联调'}",
            f"最近同步：{self.window.last_sync_text}",
            "",
            "检查结果：",
        ]
        lines.extend(f"- {row['name']}：{row['status']}，{row['detail']}" for row in self.rows)
        return "\n".join(lines)

    def backup_cache(self) -> None:
        default_name = "studio_cache_backup.sqlite3"
        path, _ = QFileDialog.getSaveFileName(self, "备份缓存", default_name, "SQLite (*.sqlite3)")
        if not path:
            return
        self.window.cache.conn.commit()
        shutil.copy2(self.window.cache.path, path)
        self.window.add_log("INFO", f"缓存已备份: {path}")
        self.run_checks()

    def restore_cache(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "恢复缓存", "", "SQLite (*.sqlite3)")
        if not path:
            return
        try:
            source = sqlite3.connect(path)
            source.backup(self.window.cache.conn)
            source.close()
        except sqlite3.Error as exc:
            QMessageBox.warning(self, "恢复失败", str(exc))
            return
        self.window.add_log("INFO", f"缓存已恢复: {path}")
        self.window.refresh_all()
        self.run_checks()

    def export_report(self) -> None:
        if not self.rows:
            self.run_checks()
        path, _ = QFileDialog.getSaveFileName(self, "导出自检报告", "system_health_report.txt", "Text (*.txt)")
        if not path:
            return
        Path(path).write_text(self.build_report(), encoding="utf-8")
        self.window.add_log("INFO", f"系统自检报告已导出: {path}")


class SettingsPage(BasePage):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window, "配置中心", "查看运行配置、实时推送状态和本地缓存位置")
        form_box = Panel()
        form = QFormLayout(form_box)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.api_url = QLineEdit(window.api.base_url)
        self.api_url.setReadOnly(True)
        self.api_url.setMinimumWidth(620)
        self.cache_path = QLineEdit(str(window.cache.path))
        self.cache_path.setReadOnly(True)
        self.cache_path.setMinimumWidth(620)
        self.mode = QLineEdit("离线演示" if window.simulation_mode else "后端联调")
        self.mode.setReadOnly(True)
        self.ws_state = QLineEdit("未启动")
        self.ws_state.setReadOnly(True)
        form.addRow("后端地址", self.api_url)
        form.addRow("缓存文件", self.cache_path)
        form.addRow("运行模式", self.mode)
        form.addRow("实时推送", self.ws_state)
        self.root.addWidget(form_box)

        cards = QGridLayout()
        self.backend_card = MetricCard("后端接口", "待测试", window.api.base_url)
        self.cache_card = MetricCard("缓存状态", "可用", window.cache.path.name)
        self.mode_card = MetricCard("运行模式", "离线演示" if window.simulation_mode else "后端联调", "登录时确定")
        self.ws_card = MetricCard("实时推送", "未启动", "SockJS/STOMP")
        self.sync_card = MetricCard("最近同步", window.last_sync_text, "设备与报警")
        self.pending_card = MetricCard("待同步", "0", "离线操作")
        for index, card in enumerate(
            [
                self.backend_card,
                self.cache_card,
                self.mode_card,
                self.ws_card,
                self.sync_card,
                self.pending_card,
            ]
        ):
            cards.addWidget(card, index // 3, index % 3)
        for column in range(3):
            cards.setColumnStretch(column, 1)
        self.root.addLayout(cards)

        actions = Panel()
        layout = QHBoxLayout(actions)
        test = QPushButton("测试后端连接")
        test.clicked.connect(self.test_backend)
        reconnect = QPushButton("重连实时推送")
        reconnect.clicked.connect(window.restart_realtime)
        demo = QPushButton("生成演示数据")
        demo.clicked.connect(window.seed_demo_data)
        toggle = QPushButton("切换模式")
        toggle.clicked.connect(window.toggle_mode)
        sync = QPushButton("同步待处理")
        sync.clicked.connect(window.sync_pending_actions)
        snapshot = QPushButton("导出快照")
        snapshot.clicked.connect(self.export_snapshot)
        layout.addWidget(test)
        layout.addWidget(reconnect)
        layout.addWidget(demo)
        layout.addWidget(toggle)
        layout.addWidget(sync)
        layout.addWidget(snapshot)
        layout.addStretch()
        self.root.addWidget(actions)
        self.result = QTextEdit()
        self.result.setReadOnly(True)
        self.result.setFixedHeight(240)
        self.root.addWidget(self.result)
        self.root.addStretch()
        self.refresh_state()

    def set_ws_state(self, state: str) -> None:
        self.ws_state.setText(state)
        self.ws_card.set_value(state, "SockJS/STOMP")

    def refresh_state(self) -> None:
        mode_text = "离线演示" if self.window.simulation_mode else "后端联调"
        pending = len(self.window.cache.pending_alarm_actions())
        self.mode.setText(mode_text)
        self.api_url.setCursorPosition(0)
        self.cache_path.setCursorPosition(0)
        self.mode_card.set_value(mode_text, "登录后可切换")
        self.mode_card.set_kind("offline" if self.window.simulation_mode else "info")
        self.sync_card.set_value(self.window.last_sync_text, "设备与报警")
        self.pending_card.set_value(pending, "离线操作")
        self.pending_card.set_kind("warning" if pending else "normal")
        if not self.result.toPlainText().strip() or self.result.toPlainText().startswith("一、当前配置"):
            self.result.setPlainText(self.build_status_text())

    def build_status_text(self) -> str:
        pending = len(self.window.cache.pending_alarm_actions())
        cache_exists = self.window.cache.path.exists()
        recent_logs = self.window.cache.logs(5)
        lines = [
            "一、当前配置",
            f"后端地址：{self.window.api.base_url}",
            f"缓存文件：{self.window.cache.path}",
            f"运行模式：{'离线演示' if self.window.simulation_mode else '后端联调'}",
            f"实时推送：{self.ws_state.text()}",
            "",
            "二、状态判断",
            f"本地缓存：{'可用' if cache_exists else '未创建'}",
            f"待同步操作：{pending} 条",
            f"最近同步：{self.window.last_sync_text}",
            "",
            "三、可用操作",
            "测试后端连接可检查 Spring Boot 接口是否可访问；重连实时推送用于恢复 SockJS/STOMP 订阅；导出快照会保存设备、报警、日志和离线操作数据。",
            "",
            "四、最近日志",
        ]
        if recent_logs:
            for item in recent_logs:
                lines.append(f"{item.get('created_at', '')} [{item.get('level', '')}] {item.get('message', '')}")
        else:
            lines.append("暂无日志。")
        return "\n".join(lines)

    def test_backend(self) -> None:
        if self.window.simulation_mode:
            self.result.setPlainText("当前为离线演示模式，不访问后端。")
            self.backend_card.set_value("未访问", "离线演示模式")
            return
        try:
            devices = self.window.api.devices()
        except ApiError as exc:
            self.result.setPlainText(f"后端连接失败：{exc}")
            self.backend_card.set_value("失败", str(exc)[:28])
            return
        self.result.setPlainText(f"后端连接正常，读取到 {len(devices)} 台设备。")
        self.backend_card.set_value("正常", f"读取到 {len(devices)} 台设备")

    def export_snapshot(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "导出数据快照", "water_level_snapshot.json", "JSON (*.json)")
        if not path:
            return
        snapshot = {
            "devices": self.window.devices,
            "current_device_id": self.window.current_device_id,
            "simulation_mode": self.window.simulation_mode,
            "last_sync_text": self.window.last_sync_text,
            "pending_actions": self.window.cache.pending_alarm_actions(),
            "alarm_actions": self.window.cache.alarm_actions(50),
            "logs": self.window.cache.logs(100),
        }
        Path(path).write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        self.window.add_log("INFO", f"已导出数据快照: {path}")
        self.result.setPlainText(f"数据快照已导出：\n{path}\n\n导出内容包括设备列表、当前设备、运行模式、待同步操作、报警处理记录和最近系统日志。")


class MainWindow(QMainWindow):
    def __init__(self, api: WaterMonitorApi, cache: LocalCache, simulation_mode: bool = False, role: str = "admin") -> None:
        super().__init__()
        self.api = api
        self.cache = cache
        self.simulation_mode = simulation_mode
        self.role = role
        self.devices: list[dict[str, Any]] = []
        self.current_device_id: int | None = None
        self.ws_client: StompSockJsClient | None = None
        self.sim_resolved_alarm_ids: set[int] = set()
        self.last_sync_text = "未同步"
        self.demo_seeded = False
        self.return_to_login = False
        self.setWindowTitle("Water Level Monitor Studio")
        self.resize(1380, 860)

        root = QWidget()
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        self.nav = QFrame()
        self.nav.setObjectName("Sidebar")
        self.nav.setFixedWidth(260)
        nav_layout = QVBoxLayout(self.nav)
        nav_layout.setContentsMargins(14, 18, 14, 16)
        nav_layout.setSpacing(12)

        brand = QFrame()
        brand.setObjectName("BrandPanel")
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(10, 10, 10, 10)
        brand_layout.setSpacing(10)
        badge = QLabel("WL")
        badge.setObjectName("BrandBadge")
        badge.setAlignment(Qt.AlignCenter)
        brand_layout.addWidget(badge)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(1)
        title = QLabel("Water Level")
        title.setObjectName("BrandTitle")
        title2 = QLabel("Monitor Studio")
        title2.setObjectName("BrandTitle")
        subtitle = QLabel("水位监测桌面端")
        subtitle.setObjectName("BrandSubTitle")
        brand_text.addWidget(title)
        brand_text.addWidget(title2)
        brand_text.addWidget(subtitle)
        brand_layout.addLayout(brand_text, 1)
        nav_layout.addWidget(brand)

        self.stack = QStackedWidget()
        self.pages: list[tuple[str, QWidget]] = [
            ("实时监控", DashboardPage(self)),
            ("监控大屏", BigScreenPage(self)),
            ("设备管理", DevicesPage(self)),
            ("历史数据", HistoryPage(self)),
            ("报警中心", AlarmPage(self)),
            ("数据分析", AnalysisPage(self)),
            ("AI 智能分析", AiPage(self)),
            ("硬件联调", HardwarePage(self)),
            ("虚拟 ESP32", VirtualEsp32Page(self)),
            ("系统日志", LogPage(self)),
            ("数据库维护", MaintenancePage(self)),
            ("系统自检", HealthPage(self)),
            ("配置中心", SettingsPage(self)),
        ]
        self.nav_buttons: list[QPushButton] = []
        nav_icons = [
            "monitor",
            "screen",
            "device",
            "history",
            "alarm",
            "analysis",
            "ai",
            "hardware",
            "esp32",
            "logs",
            "database",
            "health",
            "settings",
        ]
        nav_scroll = QScrollArea()
        nav_scroll.setObjectName("NavScroll")
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QFrame.NoFrame)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        nav_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        nav_body = QWidget()
        nav_body.setObjectName("NavBody")
        nav_body_layout = QVBoxLayout(nav_body)
        nav_body_layout.setContentsMargins(0, 0, 0, 0)
        nav_body_layout.setSpacing(4)
        for index, (name, page) in enumerate(self.pages):
            btn = QPushButton(name)
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(42)
            btn.setIcon(nav_icon(nav_icons[index]))
            btn.setIconSize(QSize(20, 20))
            btn.setToolTip(name)
            btn.clicked.connect(lambda checked=False, i=index: self.set_page(i))
            self.nav_buttons.append(btn)
            nav_body_layout.addWidget(btn)
            self.stack.addWidget(page)
        nav_body_layout.addStretch()
        nav_scroll.setWidget(nav_body)
        nav_layout.addWidget(nav_scroll, 1)

        self.exit_button = QPushButton("退出登录")
        self.exit_button.setObjectName("SidebarExit")
        self.exit_button.setFlat(True)
        self.exit_button.setFocusPolicy(Qt.NoFocus)
        self.exit_button.setCursor(Qt.PointingHandCursor)
        self.exit_button.setFixedHeight(40)
        self.exit_button.setIcon(nav_icon("exit"))
        self.exit_button.setIconSize(QSize(20, 20))
        self.exit_button.clicked.connect(self.confirm_exit)
        nav_layout.addWidget(self.exit_button)

        status_panel = QFrame()
        status_panel.setObjectName("SidebarStatus")
        status_layout = QVBoxLayout(status_panel)
        status_layout.setContentsMargins(10, 9, 10, 9)
        status_layout.setSpacing(6)
        mode = "离线演示" if self.simulation_mode else "后端联调"
        self.mode_label = QLabel(f"模式：{mode}")
        self.mode_label.setObjectName("SidebarMeta")
        status_layout.addWidget(self.mode_label)
        self.role_label = QLabel(f"角色：{role_label(self.role)}")
        self.role_label.setObjectName("SidebarMeta")
        status_layout.addWidget(self.role_label)
        nav_layout.addWidget(status_panel)

        shell.addWidget(self.nav)
        shell.addWidget(self.stack, 1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_dashboard_only)
        self.timer.start(8000)

        self.apply_role_permissions()
        self.set_page(0)
        self.bootstrap()
        self.configure_combo_boxes()
        self.start_realtime()

    def configure_combo_boxes(self) -> None:
        for combo in self.findChildren(QComboBox):
            combo.setMaxVisibleItems(8)
            combo.setMinimumHeight(34)
            combo.view().setMinimumWidth(max(combo.width(), 180))
            combo.view().setMinimumHeight(min(max(combo.count(), 1), 8) * 38 + 8)
            combo.view().setUniformItemSizes(True)
            combo.view().setTextElideMode(Qt.ElideRight)

    def confirm_exit(self) -> None:
        reply = QMessageBox.question(self, "退出登录", "确定要退出当前账号并返回登录页面吗？")
        if reply == QMessageBox.Yes:
            self.return_to_login = True
            self.close()

    def set_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
        page = self.pages[index][1]
        if isinstance(page, BigScreenPage):
            page.refresh()
        if isinstance(page, LogPage):
            page.refresh()
        if isinstance(page, AlarmPage):
            page.query()
        if isinstance(page, MaintenancePage):
            page.refresh()
        if isinstance(page, HealthPage):
            page.run_checks()
        if isinstance(page, SettingsPage):
            page.set_ws_state("离线演示" if self.simulation_mode else ("运行中" if self.ws_client and self.ws_client.isRunning() else "未连接"))
            page.refresh_state()

    def bootstrap(self) -> None:
        self.load_devices()
        if self.devices:
            self.current_device_id = int(self.devices[0]["id"])
        self.sync_device_selectors()
        self.refresh_all()

    def add_log(self, level: str, message: str) -> None:
        self.cache.log(level, message)
        self.statusBar().showMessage(f"{level.upper()} - {message}", 5000)

    def device_by_id(self, device_id: int | None) -> dict[str, Any] | None:
        for device in self.devices:
            if int(device.get("id")) == int(device_id or -1):
                return device
        return None

    def set_current_device(self, device_id: int) -> None:
        self.current_device_id = device_id
        self.refresh_dashboard_only()

    def load_devices(self) -> None:
        if self.simulation_mode:
            self.devices = sample_devices()
            self.cache.save_devices(self.devices)
            self.add_log("INFO", "已加载离线模拟设备")
            self.last_sync_text = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss") + " / 离线"
            return
        try:
            self.devices = self.api.devices()
            self.cache.save_devices(self.devices)
            self.add_log("INFO", f"设备列表同步成功，共 {len(self.devices)} 台")
            self.last_sync_text = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss") + " / 在线"
            self.sync_pending_actions()
        except ApiError as exc:
            self.devices = self.cache.get_devices() or sample_devices()
            self.add_log("WARN", f"设备接口不可用，使用缓存/模拟设备: {exc}")
            self.last_sync_text = "使用缓存 / 待重试"

    def sync_device_selectors(self) -> None:
        for _, page in self.pages:
            if hasattr(page, "set_devices"):
                page.set_devices(self.devices, self.current_device_id)
            if isinstance(page, DevicesPage):
                page.refresh(self.devices)

    def refresh_all(self) -> None:
        self.load_devices()
        if not self.current_device_id and self.devices:
            self.current_device_id = int(self.devices[0]["id"])
        self.sync_device_selectors()
        self.refresh_dashboard_only()
        self.refresh_auxiliary_pages()

    def refresh_auxiliary_pages(self) -> None:
        for _, page in self.pages:
            if isinstance(page, LogPage):
                page.refresh()
            if isinstance(page, AlarmPage):
                page.query()
            if isinstance(page, BigScreenPage):
                page.refresh()
            if isinstance(page, MaintenancePage):
                page.refresh()
            if isinstance(page, HealthPage):
                page.run_checks()
            if isinstance(page, SettingsPage):
                page.refresh_state()

    def apply_role_permissions(self) -> None:
        allowed = {
            "admin": {name for name, _ in self.pages},
            "debugger": {
                "实时监控",
                "监控大屏",
                "设备管理",
                "历史数据",
                "数据分析",
                "AI 智能分析",
                "硬件联调",
                "虚拟 ESP32",
                "系统日志",
                "系统自检",
            },
            "viewer": {
                "实时监控",
                "监控大屏",
                "设备管理",
                "历史数据",
                "数据分析",
                "AI 智能分析",
                "系统日志",
                "系统自检",
            },
        }.get(self.role, set())
        for button, (name, _) in zip(self.nav_buttons, self.pages):
            button.setEnabled(name in allowed)

    def refresh_dashboard_only(self) -> None:
        device = self.device_by_id(self.current_device_id)
        if not device:
            return
        records = self.load_history(int(device["id"]), page_size=160)
        latest = records[0] if records else None
        if not self.simulation_mode:
            try:
                latest = self.api.latest(int(device["id"])) or latest
            except ApiError as exc:
                self.add_log("WARN", f"最新水位接口失败，使用历史记录兜底: {exc}")
        page = self.pages[0][1]
        if isinstance(page, DashboardPage):
            page.refresh(device, latest, records, not self.simulation_mode)

    def load_history(
        self,
        device_id: int | None,
        start_time: str | None = None,
        end_time: str | None = None,
        page_size: int = 200,
    ) -> list[dict[str, Any]]:
        device = self.device_by_id(device_id)
        if self.simulation_mode:
            records = simulated_history(device or sample_devices()[0], min(page_size, 500))
            self.cache.save_water_levels(records)
            return records
        try:
            page = self.api.history(device_id=device_id, start_time=start_time, end_time=end_time, page_size=page_size)
            records = records_from_page(page)
            self.cache.save_water_levels(records)
            return records
        except ApiError as exc:
            self.add_log("WARN", f"历史数据接口失败，使用本地缓存: {exc}")
            return self.cache.get_water_levels(device_id, page_size)

    def load_alarms(self, is_resolved: int | None = None) -> list[dict[str, Any]]:
        if self.simulation_mode:
            alarms: list[dict[str, Any]] = []
            for device in self.devices or sample_devices():
                records = simulated_history(device, 120)
                alarms.extend(alarms_from_records(device, records))
            for alarm in alarms:
                if int_value(alarm.get("id")) in self.sim_resolved_alarm_ids:
                    alarm["isResolved"] = 1
            if is_resolved is not None:
                alarms = [alarm for alarm in alarms if int_value(alarm.get("isResolved")) == is_resolved]
            alarms.sort(key=lambda item: str(item.get("alarmTime") or ""), reverse=True)
            self.cache.save_alarms(alarms)
            return alarms
        try:
            page = self.api.alarms(is_resolved=is_resolved)
            alarms = records_from_page(page)
            self.cache.save_alarms(alarms)
            return alarms
        except ApiError as exc:
            self.add_log("WARN", f"报警接口失败，使用本地缓存: {exc}")
            alarms = self.cache.get_alarms()
            if is_resolved is not None:
                alarms = [alarm for alarm in alarms if int_value(alarm.get("isResolved")) == is_resolved]
            return alarms

    def resolve_alarm(self, alarm_id: int, operator: str = "", remark: str = "") -> None:
        payload = {
            "alarm_id": alarm_id,
            "operator": operator,
            "remark": remark,
            "action": "resolve",
        }
        if self.simulation_mode:
            self.sim_resolved_alarm_ids.add(alarm_id)
            self.cache.save_alarm_action(alarm_id, "resolve", operator, remark, is_synced=1, payload=payload)
            self.add_log("INFO", f"离线模式模拟处理报警 {alarm_id}")
            return
        try:
            self.api.resolve_alarm(alarm_id)
            self.cache.save_alarm_action(alarm_id, "resolve", operator, remark, is_synced=1, payload=payload)
            self.add_log("INFO", f"报警已处理: {alarm_id}")
        except ApiError as exc:
            self.cache.save_alarm_action(alarm_id, "resolve", operator, remark, is_synced=0, payload=payload)
            QMessageBox.warning(self, "处理失败", str(exc))
            self.add_log("ERROR", f"报警处理失败: {exc}")

    def resolve_all_alarms(self, operator: str = "", remark: str = "") -> None:
        payload = {
            "alarm_id": 0,
            "operator": operator,
            "remark": remark,
            "action": "resolve_all",
        }
        if self.simulation_mode:
            for alarm in self.load_alarms(0):
                self.sim_resolved_alarm_ids.add(int_value(alarm.get("id")))
                self.cache.save_alarm_action(
                    int_value(alarm.get("id")),
                    "resolve",
                    operator,
                    remark,
                    is_synced=1,
                    payload={**payload, "alarm_id": int_value(alarm.get("id"))},
                )
            self.cache.save_alarm_action(0, "resolve_all", operator, remark, is_synced=1, payload=payload)
            self.add_log("INFO", "离线模式模拟一键处理报警")
            return
        try:
            self.api.resolve_all_alarms()
            self.cache.save_alarm_action(0, "resolve_all", operator, remark, is_synced=1, payload=payload)
            self.add_log("INFO", "已请求一键处理报警")
        except ApiError as exc:
            self.cache.save_alarm_action(0, "resolve_all", operator, remark, is_synced=0, payload=payload)
            QMessageBox.warning(self, "处理失败", str(exc))
            self.add_log("ERROR", f"一键处理报警失败: {exc}")

    def sync_pending_actions(self) -> int:
        if self.simulation_mode:
            self.last_sync_text = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss") + " / 离线"
            return 0
        pending = self.cache.pending_alarm_actions()
        synced = 0
        for action in pending:
            if action.get("action") != "resolve":
                continue
            alarm_id = int_value(action.get("alarm_id"))
            try:
                self.api.resolve_alarm(alarm_id)
            except ApiError as exc:
                self.add_log("WARN", f"待同步报警处理失败 {alarm_id}: {exc}")
                continue
            self.cache.mark_alarm_action_synced(int_value(action.get("id")))
            synced += 1
        if synced:
            self.add_log("INFO", f"已同步 {synced} 条待处理报警记录")
        self.last_sync_text = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss") + f" / 同步 {synced}"
        self.refresh_auxiliary_pages()
        return synced

    def seed_demo_data(self) -> None:
        if self.ws_client:
            self.ws_client.stop()
            self.ws_client.wait(9000)
            self.ws_client = None
        self.simulation_mode = True
        self.mode_label.setText("模式：离线演示")
        self.sim_resolved_alarm_ids.clear()
        self.devices = sample_devices()
        self.cache.save_devices(self.devices)
        for device in self.devices:
            records = simulated_history(device, 180)
            self.cache.save_water_levels(records)
            self.cache.save_alarms(alarms_from_records(device, records))
        self.demo_seeded = True
        self.last_sync_text = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss") + " / 演示数据"
        self.add_log("INFO", "已重新生成演示数据")
        self.sync_device_selectors()
        self.refresh_all()

    def toggle_mode(self) -> None:
        if self.simulation_mode:
            if not self.api.token:
                QMessageBox.information(self, "无法切换", "当前会话没有后端登录凭据，无法切回联机模式。")
                return
            self.simulation_mode = False
            self.mode_label.setText("模式：后端联调")
            self.add_log("INFO", "已切换到后端联调模式")
            self.restart_realtime()
            self.refresh_all()
            return
        self.simulation_mode = True
        self.mode_label.setText("模式：离线演示")
        if self.ws_client:
            self.ws_client.stop()
            self.ws_client.wait(9000)
            self.ws_client = None
        self.add_log("INFO", "已切换到离线演示模式")
        self.refresh_all()

    def start_realtime(self) -> None:
        if self.simulation_mode or self.ws_client:
            return
        self.ws_client = StompSockJsClient(self.api.base_url, self)
        self.ws_client.water_level.connect(self.handle_water_push)
        self.ws_client.device_status.connect(self.handle_device_status_push)
        self.ws_client.alarm.connect(self.handle_alarm_push)
        self.ws_client.status.connect(lambda msg: self.add_log("INFO", msg))
        self.ws_client.error.connect(lambda msg: self.add_log("WARN", msg))
        self.ws_client.start()

    def restart_realtime(self) -> None:
        if self.simulation_mode:
            self.add_log("INFO", "离线演示模式不启动实时推送")
            return
        if self.ws_client:
            self.ws_client.stop()
            self.ws_client.wait(9000)
            self.ws_client = None
        self.start_realtime()

    def handle_water_push(self, payload: dict[str, Any]) -> None:
        self.cache.save_water_levels([payload])
        self.last_sync_text = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss") + " / 水位推送"
        if int(payload.get("deviceId", -1)) == int(self.current_device_id or -2):
            self.refresh_dashboard_only()
        self.add_log("INFO", f"收到实时水位推送: {payload.get('deviceCode')} {payload.get('waterLevel')} cm")

    def handle_device_status_push(self, payload: dict[str, Any]) -> None:
        device_id = payload.get("deviceId")
        for device in self.devices:
            if int(device.get("id")) == int(device_id or -1):
                device["status"] = payload.get("status")
                break
        self.cache.save_devices(self.devices)
        self.last_sync_text = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss") + " / 设备推送"
        self.sync_device_selectors()
        self.add_log("INFO", f"收到设备状态推送: {payload}")

    def handle_alarm_push(self, payload: dict[str, Any]) -> None:
        if payload.get("id"):
            self.cache.save_alarms([payload])
        self.last_sync_text = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss") + " / 报警推送"
        self.add_log("WARN", f"收到报警推送: {payload}")
        QMessageBox.warning(self, "实时报警", f"收到新的报警事件：\n{json.dumps(payload, ensure_ascii=False, indent=2)}")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.ws_client:
            self.ws_client.stop()
            self.ws_client.wait(9000)
        super().closeEvent(event)

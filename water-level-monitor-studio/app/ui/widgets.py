from __future__ import annotations

from typing import Any

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class Panel(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")


class MetricCard(Panel):
    COLORS = {
        "normal": "#54d18c",
        "info": "#37d5ff",
        "warning": "#ffca5f",
        "danger": "#ff6b7a",
        "offline": "#9aa7b8",
    }

    def __init__(self, title: str, value: str = "-", hint: str = "", kind: str = "normal") -> None:
        super().__init__()
        self.title_label = QLabel(title)
        self.title_label.setObjectName("SubTitle")
        self.value_label = QLabel(value)
        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("SubTitle")
        self.set_kind(kind)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.hint_label)

    def set_value(self, value: Any, hint: str | None = None) -> None:
        self.value_label.setText(str(value))
        if hint is not None:
            self.hint_label.setText(hint)

    def set_kind(self, kind: str) -> None:
        color = self.COLORS.get(kind, "#ffffff")
        self.value_label.setStyleSheet(f"font-size: 26px; font-weight: 700; color: {color};")


class StatusPill(QLabel):
    COLORS = {
        "normal": ("#0f3d2c", "#54d18c"),
        "warning": ("#4a3613", "#ffca5f"),
        "danger": ("#4d1720", "#ff6b7a"),
        "offline": ("#313846", "#9aa7b8"),
    }

    def __init__(self, text: str = "正常", kind: str = "normal") -> None:
        super().__init__(text)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(24)
        self.set_kind(kind, text)

    def set_kind(self, kind: str, text: str | None = None) -> None:
        bg, fg = self.COLORS.get(kind, self.COLORS["normal"])
        if text is not None:
            self.setText(text)
        self.setStyleSheet(
            f"background:{bg}; color:{fg}; border-radius:12px; padding:2px 10px; font-weight:600;"
        )


class TimeSeriesChart(Panel):
    def __init__(self, title: str = "") -> None:
        super().__init__()
        self.title = QLabel(title)
        self.title.setObjectName("SubTitle")
        self.plot = pg.PlotWidget()
        self.plot.setBackground("#111827")
        self.plot.showGrid(x=True, y=True, alpha=0.18)
        self.plot.getAxis("left").setTextPen("#90a1bd")
        self.plot.getAxis("bottom").setTextPen("#90a1bd")
        self.plot.setLabel("bottom", "采样序号")
        self.plot.setLabel("left", "水位", units="cm")
        self.plot.setLimits(xMin=0)
        self.plot.setMenuEnabled(False)
        self.plot.addLegend(offset=(10, 10))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        if title:
            layout.addWidget(self.title)
        layout.addWidget(self.plot)

    def set_series(
        self,
        values: list[float],
        warning: float | None = None,
        danger: float | None = None,
        smooth: list[float] | None = None,
    ) -> None:
        self.plot.clear()
        if not values:
            return
        x = list(range(len(values)))
        self.plot.plot(x, values, pen=pg.mkPen("#37d5ff", width=2), name="实际水位")
        if smooth:
            self.plot.plot(
                list(range(len(smooth))),
                smooth,
                pen=pg.mkPen("#6ee7a8", width=2, style=Qt.DashLine),
                name="移动平均",
            )
        if warning is not None:
            line = pg.InfiniteLine(pos=warning, angle=0, pen=pg.mkPen("#ffca5f", width=1, style=Qt.DashLine))
            self.plot.addItem(line)
        if danger is not None:
            line = pg.InfiniteLine(pos=danger, angle=0, pen=pg.mkPen("#ff6b7a", width=1, style=Qt.DashLine))
            self.plot.addItem(line)
        self.plot.setLimits(xMin=0, xMax=max(len(values) - 1, 1))
        self.plot.setXRange(0, max(len(values) - 1, 1), padding=0)


def _status_text(value: Any, row: dict[str, Any]) -> str:
    try:
        status = int(value)
    except (TypeError, ValueError):
        return "" if value is None else str(value)
    if "waterLevel" in row or "rawValue" in row:
        return {0: "正常", 1: "预警", 2: "危险"}.get(status, str(value))
    return {0: "离线", 1: "在线"}.get(status, str(value))


def _alarm_type_text(value: Any) -> str:
    try:
        alarm_type = int(value)
    except (TypeError, ValueError):
        return "" if value is None else str(value)
    return {1: "预警报警", 2: "危险报警"}.get(alarm_type, str(value))


def _resolved_text(value: Any) -> str:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return "" if value is None else str(value)
    return "已处理" if resolved == 1 else "未处理"


def _format_value(key: str, value: Any, row: dict[str, Any]) -> str:
    if value is None:
        return ""
    if key == "status":
        return _status_text(value, row)
    if key == "alarmType":
        return _alarm_type_text(value)
    if key == "isResolved":
        return _resolved_text(value)
    if key == "is_synced":
        try:
            synced = int(value)
        except (TypeError, ValueError):
            return "" if value is None else str(value)
        return "已同步" if synced == 1 else "待同步"
    if key in {"waterLevel", "alarmLevel", "thresholdValue", "warningLevel", "dangerLevel"}:
        try:
            return f"{float(value):.2f}"
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _cell_colors(key: str, value: Any, row: dict[str, Any]) -> tuple[str | None, str | None]:
    text = _format_value(key, value, row)
    if key == "status":
        if text == "正常" or text == "在线":
            return "#54d18c", "#10291f"
        if text == "预警":
            return "#ffca5f", "#322817"
        if text == "危险":
            return "#ff6b7a", "#351821"
        if text == "离线":
            return "#9aa7b8", "#242b36"
        if text == "通过":
            return "#54d18c", "#10291f"
        if text == "提示":
            return "#ffca5f", "#322817"
        if text == "失败":
            return "#ff6b7a", "#351821"
        if "成功" in text or "预览" in text:
            return "#54d18c", "#10291f"
        if "失败" in text:
            return "#ff6b7a", "#351821"
    if key == "alarmType":
        if text == "预警报警":
            return "#ffca5f", "#322817"
        if text == "危险报警":
            return "#ff6b7a", "#351821"
    if key == "isResolved":
        return ("#54d18c", "#10291f") if text == "已处理" else ("#ffca5f", "#322817")
    if key == "level":
        if str(value).upper() == "INFO":
            return "#54d18c", "#10291f"
        if str(value).upper() == "WARN":
            return "#ffca5f", "#322817"
        if str(value).upper() == "ERROR":
            return "#ff6b7a", "#351821"
    if key == "action":
        if str(value) == "resolve_all":
            return "#37d5ff", "#10242c"
        return "#54d18c", "#10291f"
    if key == "is_synced":
        return ("#54d18c", "#10291f") if str(value) in {"1", "True", "true", "已同步"} else ("#ffca5f", "#322817")
    if key == "result" or key == "uploadStatus":
        if "成功" in text or "预览" in text:
            return "#54d18c", "#10291f"
        if "失败" in text:
            return "#ff6b7a", "#351821"
    return None, None


def set_table_data(table: QTableWidget, columns: list[tuple[str, str]], rows: list[dict[str, Any]]) -> None:
    table.setUpdatesEnabled(False)
    table.clear()
    table.setColumnCount(len(columns))
    table.setHorizontalHeaderLabels([label for _, label in columns])
    table.setRowCount(len(rows))
    table.setAlternatingRowColors(True)
    table.setShowGrid(True)
    table.setWordWrap(False)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setStretchLastSection(True)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
    table.viewport().setStyleSheet("background: #111827;")
    palette = table.palette()
    palette.setColor(QPalette.Base, QColor("#111827"))
    palette.setColor(QPalette.AlternateBase, QColor("#151f31"))
    palette.setColor(QPalette.Text, QColor("#dce6f8"))
    table.setPalette(palette)
    for r, row in enumerate(rows):
        for c, (key, _) in enumerate(columns):
            value = row.get(key, "")
            item = QTableWidgetItem(_format_value(key, value, row))
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            item.setTextAlignment(Qt.AlignCenter if key not in {"message", "alarmMessage", "detail"} else Qt.AlignVCenter | Qt.AlignLeft)
            fg, bg = _cell_colors(key, value, row)
            if fg:
                item.setForeground(QBrush(QColor(fg)))
            if bg:
                item.setBackground(QBrush(QColor(bg)))
            table.setItem(r, c, item)
    table.setUpdatesEnabled(True)


def hbox(*widgets: QWidget, margins: tuple[int, int, int, int] = (0, 0, 0, 0), spacing: int = 10) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    for widget in widgets:
        layout.addWidget(widget)
    return layout

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF


def nav_icon(kind: str, size: int = 22) -> QIcon:
    icon = QIcon()
    icon.addPixmap(_draw_icon(kind, size, "#91a2bc"), QIcon.Normal, QIcon.Off)
    icon.addPixmap(_draw_icon(kind, size, "#37d5ff"), QIcon.Normal, QIcon.On)
    icon.addPixmap(_draw_icon(kind, size, "#dce6f8"), QIcon.Active, QIcon.Off)
    icon.addPixmap(_draw_icon(kind, size, "#37d5ff"), QIcon.Active, QIcon.On)
    icon.addPixmap(_draw_icon(kind, size, "#4d5b70"), QIcon.Disabled, QIcon.Off)
    icon.addPixmap(_draw_icon(kind, size, "#4d5b70"), QIcon.Disabled, QIcon.On)
    return icon


def _draw_icon(kind: str, size: int, color: str) -> QPixmap:
    ratio = 2
    pixmap = QPixmap(size * ratio, size * ratio)
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor(color), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))

    canvas = 24.0
    scale = size / canvas
    painter.scale(scale, scale)

    if kind == "monitor":
        painter.drawRoundedRect(QRectF(4, 5, 16, 11), 2, 2)
        painter.drawLine(QPointF(10, 19), QPointF(14, 19))
        painter.drawLine(QPointF(12, 16), QPointF(12, 19))
    elif kind == "screen":
        painter.drawRoundedRect(QRectF(3, 4, 18, 16), 2, 2)
        painter.drawLine(QPointF(3, 10), QPointF(21, 10))
        painter.drawLine(QPointF(10, 10), QPointF(10, 20))
        painter.drawLine(QPointF(15, 10), QPointF(15, 20))
    elif kind == "device":
        painter.drawRoundedRect(QRectF(5, 4, 14, 16), 2, 2)
        for y in (8, 12, 16):
            painter.drawLine(QPointF(8, y), QPointF(16, y))
    elif kind == "history":
        painter.drawRoundedRect(QRectF(5, 4, 14, 16), 2, 2)
        painter.drawArc(QRectF(8, 8, 8, 8), 20 * 16, 300 * 16)
        painter.drawLine(QPointF(12, 9), QPointF(12, 12))
        painter.drawLine(QPointF(12, 12), QPointF(15, 13))
    elif kind == "alarm":
        painter.drawPolygon(QPolygonF([QPointF(12, 4), QPointF(21, 20), QPointF(3, 20)]))
        painter.drawLine(QPointF(12, 9), QPointF(12, 14))
        painter.drawPoint(QPointF(12, 17))
    elif kind == "analysis":
        painter.drawLine(QPointF(4, 19), QPointF(20, 19))
        for x, height in ((7, 7), (12, 11), (17, 15)):
            painter.drawRoundedRect(QRectF(x - 1.5, 19 - height, 3, height), 1, 1)
    elif kind == "ai":
        painter.drawEllipse(QPointF(12, 12), 3.2, 3.2)
        for point in (QPointF(6, 7), QPointF(18, 7), QPointF(6, 17), QPointF(18, 17)):
            painter.drawEllipse(point, 2.2, 2.2)
            painter.drawLine(QPointF(12, 12), point)
    elif kind == "hardware":
        painter.drawEllipse(QPointF(7, 12), 2.7, 2.7)
        painter.drawEllipse(QPointF(17, 7), 2.7, 2.7)
        painter.drawEllipse(QPointF(17, 17), 2.7, 2.7)
        painter.drawLine(QPointF(9.5, 11), QPointF(14.5, 8))
        painter.drawLine(QPointF(9.5, 13), QPointF(14.5, 16))
    elif kind == "esp32":
        painter.drawRoundedRect(QRectF(6, 5, 12, 14), 2, 2)
        for y in (8, 12, 16):
            painter.drawLine(QPointF(3.5, y), QPointF(6, y))
            painter.drawLine(QPointF(18, y), QPointF(20.5, y))
        painter.drawRoundedRect(QRectF(9, 8, 6, 5), 1, 1)
    elif kind == "logs":
        painter.drawRoundedRect(QRectF(6, 4, 12, 16), 2, 2)
        for y in (9, 12, 15):
            painter.drawLine(QPointF(9, y), QPointF(15, y))
    elif kind == "database":
        painter.drawEllipse(QRectF(5, 4, 14, 5))
        painter.drawLine(QPointF(5, 6.5), QPointF(5, 17))
        painter.drawLine(QPointF(19, 6.5), QPointF(19, 17))
        painter.drawEllipse(QRectF(5, 14.5, 14, 5))
        painter.drawArc(QRectF(5, 9, 14, 5), 180 * 16, 180 * 16)
    elif kind == "health":
        painter.drawEllipse(QPointF(12, 12), 8, 8)
        painter.drawLine(QPointF(8, 12), QPointF(11, 15))
        painter.drawLine(QPointF(11, 15), QPointF(17, 9))
    elif kind == "settings":
        painter.drawEllipse(QPointF(12, 12), 3.3, 3.3)
        for index in range(8):
            angle = math.radians(index * 45)
            start = QPointF(12 + math.cos(angle) * 6.2, 12 + math.sin(angle) * 6.2)
            end = QPointF(12 + math.cos(angle) * 8.2, 12 + math.sin(angle) * 8.2)
            painter.drawLine(start, end)
    elif kind == "exit":
        painter.drawRoundedRect(QRectF(5, 4, 10, 16), 2, 2)
        painter.drawLine(QPointF(15, 12), QPointF(21, 12))
        painter.drawLine(QPointF(18, 9), QPointF(21, 12))
        painter.drawLine(QPointF(18, 15), QPointF(21, 12))
        painter.drawPoint(QPointF(12, 12))
    else:
        painter.drawRoundedRect(QRectF(5, 5, 14, 14), 3, 3)

    painter.end()
    return pixmap

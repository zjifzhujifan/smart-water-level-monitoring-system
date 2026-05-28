from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def export_records_csv(path: str | Path, records: list[dict[str, Any]], keys: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=keys)
        writer.writeheader()
        for record in records:
            writer.writerow({key: record.get(key, "") for key in keys})


def export_records_excel(path: str | Path, records: list[dict[str, Any]], keys: list[str], labels: list[str]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "水位数据"
    sheet.append(labels)
    for record in records:
        sheet.append([record.get(key, "") for key in keys])
    for column in sheet.columns:
        letter = column[0].column_letter
        max_len = max(len(str(cell.value or "")) for cell in column)
        sheet.column_dimensions[letter].width = min(max(max_len + 2, 12), 32)
    workbook.save(path)


def export_text_pdf(path: str | Path, title: str, text: str) -> None:
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=48, leftMargin=48, topMargin=48, bottomMargin=48)
    styles = getSampleStyleSheet()
    styles["Title"].fontName = "STSong-Light"
    styles["Title"].fontSize = 18
    styles["Normal"].fontName = "STSong-Light"
    styles["Normal"].fontSize = 10.5
    styles["Normal"].leading = 16

    story: list[Any] = [Paragraph(title, styles["Title"]), Spacer(1, 12)]
    for line in text.splitlines():
        escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        story.append(Paragraph(escaped if escaped else "&nbsp;", styles["Normal"]))
    doc.build(story)

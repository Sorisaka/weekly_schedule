from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .builder import mark_conflicts
from .models import Event
from .parsers import Config


class ScheduleRenderer:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.page_width, self.page_height = A3
        self.margin_left = 20 * mm
        self.margin_right = 10 * mm
        self.margin_top = 20 * mm
        self.margin_bottom = 15 * mm
        self.time_column_width = 20 * mm
        self.header_height = 12 * mm

    def register_font(self) -> None:
        if not self.config.font_path:
            raise FileNotFoundError(
                "日本語フォントが指定されていません。config.yaml の font.path に TTF/OTF を設定してください。"
            )
        font_path = Path(self.config.font_path)
        if not font_path.exists():
            raise FileNotFoundError(f"フォントファイルが見つかりません: {font_path}")
        pdfmetrics.registerFont(TTFont(self.config.font_name, str(font_path)))

    def render(self, output: Path, week_start: date, events: List[Event], daily: bool) -> None:
        self.register_font()
        c = canvas.Canvas(str(output), pagesize=A3)
        c.setTitle(self.config.page_title)
        self._draw_week_page(c, week_start, events)
        if daily:
            for offset in range(7):
                day = week_start.fromordinal(week_start.toordinal() + offset)
                self._draw_daily_page(c, day, events)
        c.save()

    def _draw_week_page(self, c: canvas.Canvas, week_start: date, events: List[Event]) -> None:
        c.setFont(self.config.font_name, 14)
        week_end = week_start.fromordinal(week_start.toordinal() + 6)
        title = f"{self.config.page_title} {week_start.isoformat()}〜{week_end.isoformat()}"
        c.drawString(self.margin_left, self.page_height - self.margin_top, title)
        self._draw_legend(c)
        grid_top = self.page_height - self.margin_top - self.header_height
        grid_bottom = self.margin_bottom
        grid_left = self.margin_left + self.time_column_width
        grid_right = self.page_width - self.margin_right
        day_width = (grid_right - grid_left) / 7
        self._draw_time_grid(c, grid_left, grid_right, grid_top, grid_bottom)
        self._draw_day_headers(c, grid_left, grid_top, day_width, week_start)
        daily_events = self._group_events(events)
        for idx in range(7):
            day = week_start.fromordinal(week_start.toordinal() + idx)
            day_events = daily_events.get(day, [])
            mark_conflicts(day_events)
            for event in day_events:
                self._draw_event_block(
                    c,
                    event,
                    grid_left + idx * day_width,
                    grid_bottom,
                    day_width,
                    grid_top,
                )
        c.showPage()

    def _draw_daily_page(self, c: canvas.Canvas, day: date, events: List[Event]) -> None:
        c.setFont(self.config.font_name, 14)
        c.drawString(self.margin_left, self.page_height - self.margin_top, f"{day.isoformat()}")
        grid_top = self.page_height - self.margin_top - self.header_height
        grid_bottom = self.margin_bottom
        grid_left = self.margin_left + self.time_column_width
        grid_right = self.page_width - self.margin_right
        self._draw_time_grid(c, grid_left, grid_right, grid_top, grid_bottom)
        self._draw_day_headers(c, grid_left, grid_top, grid_right - grid_left, day)
        daily_events = self._group_events(events)
        day_events = daily_events.get(day, [])
        mark_conflicts(day_events)
        for event in day_events:
            self._draw_event_block(c, event, grid_left, grid_bottom, grid_right - grid_left, grid_top)
        c.showPage()

    def _draw_day_headers(self, c: canvas.Canvas, grid_left: float, grid_top: float, day_width: float, start: date) -> None:
        labels = ["月", "火", "水", "木", "金", "土", "日"]
        c.setFont(self.config.font_name, 11)
        if day_width == (self.page_width - self.margin_right - grid_left):
            c.drawString(grid_left + 4, grid_top + 2, labels[start.weekday()])
            c.drawString(grid_left + 24, grid_top + 2, start.strftime("%m/%d"))
            return
        for idx, label in enumerate(labels):
            day = start.fromordinal(start.toordinal() + idx)
            x = grid_left + idx * day_width
            c.drawString(x + 4, grid_top + 2, f"{label} {day.strftime('%m/%d')}")

    def _draw_time_grid(self, c: canvas.Canvas, left: float, right: float, top: float, bottom: float) -> None:
        start_minutes = 0
        end_minutes = 24 * 60
        total_minutes = end_minutes - start_minutes
        height = top - bottom
        for minute in range(start_minutes, end_minutes + 1, 10):
            y = bottom + (minute - start_minutes) / total_minutes * height
            if minute % 60 == 0:
                c.setStrokeColor(colors.grey)
                c.setLineWidth(0.6)
            elif minute % 30 == 0:
                c.setStrokeColor(colors.lightgrey)
                c.setLineWidth(0.4)
            else:
                c.setStrokeColor(colors.whitesmoke)
                c.setLineWidth(0.2)
            c.line(left, y, right, y)
            if minute % 60 == 0:
                c.setFont(self.config.font_name, 8)
                label = f"{minute // 60:02d}:00"
                c.setFillColor(colors.black)
                c.drawRightString(left - 2, y - 2, label)
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.6)
        c.rect(left, bottom, right - left, top - bottom)

    def _draw_event_block(
        self,
        c: canvas.Canvas,
        event: Event,
        x: float,
        bottom: float,
        width: float,
        top: float,
    ) -> None:
        start_minutes = 0
        end_minutes = 24 * 60
        total_minutes = end_minutes - start_minutes
        schedule_height = top - bottom
        event_start = event.start_min
        event_end = event.end_min
        if event_end < start_minutes:
            return
        if event_start > end_minutes:
            return
        event_start = max(event_start, start_minutes)
        event_end = min(event_end, end_minutes)
        y_start = bottom + (event_start - start_minutes) / total_minutes * schedule_height
        y_end = bottom + (event_end - start_minutes) / total_minutes * schedule_height
        height = max(y_end - y_start, 4)
        fill = _hex_to_color(event.color)
        c.setFillColor(fill)
        c.setStrokeColor(colors.red if event.conflict else colors.black)
        c.setLineWidth(1.0 if event.conflict else 0.4)
        c.rect(x + 1, y_start, width - 2, height, fill=1, stroke=1)
        c.setFillColor(colors.black)
        font_size = 8 if height >= 10 else 6
        c.setFont(self.config.font_name, font_size)
        text_y = y_start + height - (font_size + 2)
        label = event.title
        if event.note:
            label = f"{label} ({event.note})"
        for line in _wrap_text(label, width - 4, c, self.config.font_name, font_size):
            if text_y < y_start + 2:
                break
            c.drawString(x + 3, text_y, line)
            text_y -= font_size + 1

    @staticmethod
    def _group_events(events: List[Event]) -> Dict[date, List[Event]]:
        grouped: Dict[date, List[Event]] = {}
        for event in events:
            grouped.setdefault(event.day, []).append(event)
        return grouped

    def _draw_legend(self, c: canvas.Canvas) -> None:
        legend_items = [
            ("授業", "class"),
            ("バイト", "work"),
            ("予定", "free"),
            ("睡眠", "sleep"),
            ("食事", "meal"),
            ("散歩", "walk"),
        ]
        x = self.margin_left + 260
        y = self.page_height - self.margin_top + 2
        c.setFont(self.config.font_name, 8)
        for label, key in legend_items:
            color = _hex_to_color(self.config.colors.get(key, "#DDDDDD"))
            c.setFillColor(color)
            c.rect(x, y - 6, 10, 6, fill=1, stroke=0)
            c.setFillColor(colors.black)
            c.drawString(x + 12, y - 6, label)
            x += 50


def _wrap_text(text: str, max_width: float, canvas_obj: canvas.Canvas, font_name: str, font_size: int) -> List[str]:
    words = list(text)
    lines: List[str] = []
    current = ""
    for char in words:
        if canvas_obj.stringWidth(current + char, font_name, font_size) > max_width and current:
            lines.append(current)
            current = char
        else:
            current += char
    if current:
        lines.append(current)
    return lines


def _hex_to_color(value: str) -> colors.Color:
    value = value.lstrip("#")
    if len(value) != 6:
        return colors.lightgrey
    r = int(value[0:2], 16) / 255
    g = int(value[2:4], 16) / 255
    b = int(value[4:6], 16) / 255
    return colors.Color(r, g, b)

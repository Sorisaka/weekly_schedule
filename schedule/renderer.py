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
        self.max_event_font_size = config.max_event_font_size
        self.min_event_font_size = 6
        self.event_text_padding_x = 4
        self.event_text_padding_y = 3
        # 10〜15分程度の短い予定ブロックは、縦幅が数ptしか取れず
        # 既定の余白(上下3pt)＋最小フォント(6pt)だと文字が置けない。
        # そのため、短いブロックでは「1行・省略表示・小さめフォント」で必ずタイトルを出す。
        self.min_event_font_size = 4
        # この高さ(pt)以下はコンパクト描画(1行のみ)に切り替える。
        # 10分=約7.3pt, 15分=約11pt (A3/24hスケールのとき)
        self.compact_event_height_pt = 12
        # 20分未満は上下余白/行間を最小化して、タイトル領域を最大化する
        self.short_event_minutes = 20
        self.event_text_padding_y_short = 0  # ほぼゼロ。クリップ回避のため僅かに残す
        self.event_line_gap = 1
        self.event_line_gap_short = 0

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
                    center_text=True,
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
            self._draw_event_block(
                c,
                event,
                grid_left,
                grid_bottom,
                grid_right - grid_left,
                grid_top,
                center_text=False,
            )
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
            y = top - (minute - start_minutes) / total_minutes * height
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
        center_text: bool,
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

        duration_min = max(0, event_end - event_start)
        pad_y = (
            self.event_text_padding_y_short
            if duration_min < self.short_event_minutes
            else self.event_text_padding_y
        )
        line_gap = self.event_line_gap_short if duration_min < self.short_event_minutes else self.event_line_gap

        y_start = top - (event_start - start_minutes) / total_minutes * schedule_height
        y_end = top - (event_end - start_minutes) / total_minutes * schedule_height
        y_top = max(y_start, y_end)
        y_bottom = min(y_start, y_end)
        height = max(y_top - y_bottom, 4)
        fill = _hex_to_color(event.color)
        c.setFillColor(fill)
        c.setStrokeColor(colors.red if event.conflict else colors.black)
        c.setLineWidth(1.0 if event.conflict else 0.4)
        c.rect(x + 1, y_bottom, width - 2, height, fill=1, stroke=1)
        c.setFillColor(colors.black)
        label = event.title
        # 短いブロック(10〜15分程度)でも、最低1行は表示する。
        # ここでは 1) 省略(...)、2) フォント縮小、3) 余白縮小 を組み合わせる。
        if height <= self.compact_event_height_pt:
            pad_x = 2
            content_width = max(1, width - pad_x * 2)
            # 文字のベースラインが上下に食い込みやすいので 1pt だけ安全域を取る
            font_size = max(3, min(self.min_event_font_size, int(height - 1)))
            # 10分(約7pt)でも6ptは現実的に読めるため、上限を6にする
            font_size = min(font_size, 6)
            c.setFont(self.config.font_name, font_size)     

            first_line = (label.splitlines() or [""])[0]
            line = _truncate_text_to_width(first_line, content_width, c, self.config.font_name, font_size)      

            # 縦方向は中央寄せ(ベースライン基準)。
            text_y = y_bottom + (height - font_size) / 2
            if center_text:
                line_width = c.stringWidth(line, self.config.font_name, font_size)
                text_x = x + pad_x + max(0, (content_width - line_width) / 2)
            else:
                text_x = x + pad_x
            c.drawString(text_x, text_y, line)
            return
        if event.note:
            label = f"{label} ({event.note})"
        label = label.replace("\\n", "\n")
        content_width = width - self.event_text_padding_x * 2
        content_height = height - pad_y * 2
        if content_width <= 0 or content_height <= 0:
            return
        font_size, lines = _fit_text_to_box(
            label,
            content_width,
            content_height,
            c,
            self.config.font_name,
            self.max_event_font_size,
            self.min_event_font_size,
            line_gap=line_gap,
        )
        if not lines:
            return
        c.setFont(self.config.font_name, font_size)
        line_height = font_size + line_gap
        text_block_height = len(lines) * line_height - line_gap
        if center_text:
            if text_block_height > height - pad_y * 2:
                text_y = y_top - (font_size + pad_y)
            else:
                text_y = y_bottom + (height + text_block_height) / 2 - font_size
            for line in lines:
                if text_y < y_bottom + pad_y:
                    break
                line_width = c.stringWidth(line, self.config.font_name, font_size)
                text_x = x + self.event_text_padding_x + (content_width - line_width) / 2
                c.drawString(text_x, text_y, line)
                text_y -= line_height
        else:
            text_y = y_top - (font_size + pad_y)
            for line in lines:
                if text_y < y_bottom + pad_y:
                    break
                c.drawString(x + self.event_text_padding_x, text_y, line)
                text_y -= line_height

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
    lines: List[str] = []
    for raw_line in text.splitlines() or [""]:
        current = ""
        for char in list(raw_line):
            if canvas_obj.stringWidth(current + char, font_name, font_size) > max_width and current:
                lines.append(current)
                current = char
            else:
                current += char
        lines.append(current)
    return lines

def _truncate_text_to_width(
    text: str,
    max_width: float,
    canvas_obj: canvas.Canvas,
    font_name: str,
    font_size: int,
    ellipsis: str = "…",
) -> str:
    """max_width に収まるように text を1行で省略する。

    - 日本語(空白なし)を想定し、文字単位で切る
    - 収まらない場合は末尾に … を付ける
    """
    if not text:
        return ""
    if canvas_obj.stringWidth(text, font_name, font_size) <= max_width:
        return text

    # 省略記号を置けないほど狭い場合は、先頭1文字だけでも返す
    if canvas_obj.stringWidth(ellipsis, font_name, font_size) > max_width:
        return text[0]

    # 末尾に ellipsis を付けた状態で max_width に収まる最大の prefix を探す（二分探索）
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi) // 2
        candidate = text[:mid] + ellipsis
        if canvas_obj.stringWidth(candidate, font_name, font_size) <= max_width:
            lo = mid + 1
        else:
            hi = mid
    cut = max(1, lo - 1)
    return text[:cut] + ellipsis

def _fit_text_to_box(
    text: str,
    max_width: float,
    max_height: float,
    canvas_obj: canvas.Canvas,
    font_name: str,
    max_font_size: int,
    min_font_size: int,
    *,
    line_gap: int = 1,
) -> tuple[int, List[str]]:
    for font_size in range(max_font_size, min_font_size - 1, -1):
        lines = _wrap_text(text, max_width, canvas_obj, font_name, font_size)
        if not lines:
            return font_size, lines
        line_height = font_size + line_gap
        total_height = len(lines) * line_height - line_gap
        if total_height <= max_height:
            return font_size, lines
    return min_font_size, _wrap_text(text, max_width, canvas_obj, font_name, min_font_size)


def _hex_to_color(value: str) -> colors.Color:
    value = value.lstrip("#")
    if len(value) != 6:
        return colors.lightgrey
    r = int(value[0:2], 16) / 255
    g = int(value[2:4], 16) / 255
    b = int(value[4:6], 16) / 255
    return colors.Color(r, g, b)

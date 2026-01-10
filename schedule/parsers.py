from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import yaml


_TIME_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?$")


@dataclass
class Config:
    time_table: Dict[int, tuple[int, int]]
    routines: Dict[str, Dict[str, tuple[int, int]]]
    free_override_mode: bool
    work_type_thresholds: Dict[str, int]
    colors: Dict[str, str]
    font_path: Optional[str]
    font_name: str
    page_title: str
    day_start_min: int
    day_end_min: int
    max_event_font_size: int


def parse_time_token(value: str) -> int:
    match = _TIME_RE.match(value.strip())
    if not match:
        raise ValueError(f"Invalid time token: {value}")
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if hour == 24 and minute == 0:
        return 24 * 60
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid time token: {value}")
    return hour * 60 + minute


def parse_time_range(range_str: str) -> tuple[int, int]:
    start_str, end_str = [part.strip() for part in range_str.split("-")]
    start_min = parse_time_token(start_str)
    end_min = parse_time_token(end_str)
    if end_min <= start_min:
        end_min += 24 * 60
    return start_min, end_min


def load_config(path: Path) -> Config:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    time_table = {}
    for key, value in (data.get("time_table", {}) or {}).items():
        period = int(key)
        start_min = parse_time_token(value[0])
        end_min = parse_time_token(value[1])
        if end_min <= start_min:
            end_min += 24 * 60
        time_table[period] = (start_min, end_min)

    routines_cfg = data.get("routines", {}) or {}
    routine_patterns = {}
    for pattern_key in ("pattern_nonwork", "pattern_work_night", "pattern_work_morning"):
        pattern = routines_cfg.get(pattern_key, {}) or {}
        routine_patterns[pattern_key] = {
            name: parse_time_range(f"{times[0]}-{times[1]}") for name, times in pattern.items()
        }

    free_override_mode = bool(routines_cfg.get("free_override_mode", False))
    thresholds_cfg = routines_cfg.get("work_type_thresholds", {}) or {}
    work_type_thresholds = {
        "night_end": parse_time_token(str(thresholds_cfg.get("night_end", "05:00"))),
        "morning_start": parse_time_token(str(thresholds_cfg.get("morning_start", "09:00"))),
    }

    colors = data.get("colors", {}) or {}
    font_path = data.get("font", {}).get("path")
    font_name = data.get("font", {}).get("name", "NotoSansCJK" if font_path else "Helvetica")
    page_title = data.get("page_title", "Weekly Schedule")
    day_start_min = parse_time_token(str(data.get("day_start", "06:00")))
    day_end_min = parse_time_token(str(data.get("day_end", "24:00")))
    max_event_font_size = int(data.get("max_event_font_size", 20))

    return Config(
        time_table=time_table,
        routines=routine_patterns,
        free_override_mode=free_override_mode,
        work_type_thresholds=work_type_thresholds,
        colors=colors,
        font_path=font_path,
        font_name=font_name,
        page_title=page_title,
        day_start_min=day_start_min,
        day_end_min=day_end_min,
        max_event_font_size=max_event_font_size,
    )


def load_classes(path: Path) -> Dict[int, Dict[int, dict]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    weekday_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
    results: Dict[int, Dict[int, dict]] = {i: {} for i in range(7)}
    for key, value in data.items():
        weekday = weekday_map.get(key.lower())
        if weekday is None or value is None:
            continue
        if isinstance(value, dict):
            for period_key, entry in value.items():
                period = int(period_key)
                if isinstance(entry, str):
                    results[weekday][period] = {"title": entry}
                else:
                    results[weekday][period] = entry
        else:
            for entry in value:
                if not entry:
                    continue
                period = int(entry.get("period"))
                results[weekday][period] = entry
    return results


def load_special_days(path: Path) -> Dict[str, List[dict]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    canceled = data.get("canceled", []) or []
    ondemand = data.get("ondemand", []) or []
    return {"canceled": canceled, "ondemand": ondemand}


def load_work_shifts(path: Path) -> List[dict]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    results: List[dict] = []
    current_year = None
    current_month = None
    for line in lines:
        if not line or line.startswith("#"):
            continue
        if line.isdigit() and len(line) == 6:
            current_year = int(line[:4])
            current_month = int(line[4:])
            continue
        if current_year is None or current_month is None:
            continue
        parts = [p.strip() for p in line.split(",") if p.strip()]
        if len(parts) < 2:
            continue
        day = int(parts[0])
        time_range = parts[1]
        results.append(
            {
                "date": date(current_year, current_month, day),
                "time": time_range,
                "title": "バイト",
                "category": "work",
            }
        )
    return results


def load_events(path: Path) -> List[dict]:
    results: List[dict] = []
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    year = None
    for line in lines:
        if not line or line.startswith("#"):
            continue
        if line.isdigit() and len(line) == 4:
            year = int(line)
            continue
        if year is None:
            continue
        for row in csv.reader([line]):
            if not row:
                continue
            date_part = row[0]
            time_part = row[1] if len(row) > 1 else ""
            title = row[2] if len(row) > 2 else "(無題)"
            category = row[3] if len(row) > 3 else "free"
            month, day = map(int, date_part.replace("/", "-").split("-"))
            results.append(
                {
                    "date": date(year, month, day),
                    "time": time_part,
                    "title": title,
                    "category": category,
                }
            )
    return results


def iter_week_dates(week_start: date) -> Iterable[date]:
    for i in range(7):
        yield week_start.fromordinal(week_start.toordinal() + i)

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from schedule.builder import build_week_events
from schedule.parsers import (
    Config,
    load_classes,
    load_config,
    load_events,
    load_special_days,
    load_work_shifts,
)
from schedule.renderer import ScheduleRenderer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="週次予定表PDF生成ツール")
    parser.add_argument("--week-start", required=True, help="週の開始日（月曜） YYYY-MM-DD")
    parser.add_argument("--config", required=True, type=Path, help="config.yaml")
    parser.add_argument("--classes", required=True, type=Path, help="classes.yaml")
    parser.add_argument("--special", required=True, type=Path, help="special_days.yaml")
    parser.add_argument("--work", required=True, type=Path, help="work_shifts.txt")
    parser.add_argument("--events", required=True, type=Path, help="events_YYYY.txt")
    parser.add_argument("--daily", choices=["on", "off"], default="off", help="日別ページの出力")
    parser.add_argument("--out", required=True, type=Path, help="出力PDF")
    return parser.parse_args()


def validate_week_start(week_start: date) -> None:
    if week_start.weekday() != 0:
        raise ValueError("week-start は月曜日を指定してください。")


def main() -> None:
    args = parse_args()
    week_start = date.fromisoformat(args.week_start)
    validate_week_start(week_start)

    config: Config = load_config(args.config)
    classes = load_classes(args.classes)
    special_days = load_special_days(args.special)
    work_shifts = load_work_shifts(args.work)
    events = load_events(args.events)

    week_events = build_week_events(
        week_start=week_start,
        config=config,
        classes=classes,
        special_days=special_days,
        work_shifts=work_shifts,
        events=events,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    renderer = ScheduleRenderer(config)
    renderer.render(args.out, week_start, week_events, daily=args.daily == "on")
    print(f"PDFを生成しました: {args.out}")


if __name__ == "__main__":
    main()

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Dict, Iterable, List

from .models import Event
from .parsers import Config, parse_time_range


_DEFAULT_COLORS = {
    "sleep": "#DDEEFF",
    "meal": "#FFF2CC",
    "walk": "#E6FFDA",
    "class": "#D8E8FF",
    "work": "#FFE0CC",
    "move": "#E8E8E8",
    "free": "#E8D8FF",
    "canceled": "#F8D7DA",
    "ondemand": "#E6FFDA",
}


def build_week_events(
    week_start: date,
    config: Config,
    classes: Dict[int, Dict[int, dict]],
    special_days: Dict[str, List[dict]],
    work_shifts: List[dict],
    events: List[dict],
) -> List[Event]:
    colors = {**_DEFAULT_COLORS, **config.colors}
    canceled_map = _group_special(special_days.get("canceled", []))
    ondemand_map = _group_special(special_days.get("ondemand", []))
    work_map = _group_by_date(work_shifts)
    event_map = _group_by_date(events)

    base_events: List[Event] = []
    for offset in range(7):
        day = week_start.fromordinal(week_start.toordinal() + offset)
        day_classes = classes.get(day.weekday(), {})
        base_events.extend(_build_class_events(day, day_classes, config, colors))
        base_events.extend(_build_work(day, work_map.get(day, []), colors))
        base_events.extend(_build_events(day, event_map.get(day, []), colors))

    normalized: List[Event] = []
    for event in base_events:
        normalized.extend(_split_multi_day_event(event))

    routines = _build_routines_for_week(week_start, config, normalized, colors)
    if config.hide_routine_conflicts:
        routines = _filter_routines_conflicting_with_events(routines, normalized)
    combined = normalized + routines
    with_specials = _apply_special_days(
        week_start,
        config,
        combined,
        classes,
        colors,
        canceled_map,
        ondemand_map,
    )
    return with_specials


def _group_by_date(items: List[dict]) -> Dict[date, List[dict]]:
    grouped: Dict[date, List[dict]] = {}
    for item in items:
        grouped.setdefault(_parse_date(item.get("date")), []).append(item)
    return grouped


def _group_special(items: Iterable[dict]) -> Dict[date, List[dict]]:
    grouped: Dict[date, List[dict]] = {}
    for item in items:
        grouped.setdefault(_parse_date(item.get("date")), []).append(item)
    return grouped


def _parse_date(value: object) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise TypeError(f"Unsupported date value: {value!r}")


def _build_routines_for_week(
    week_start: date,
    config: Config,
    events: List[Event],
    colors: Dict[str, str],
) -> List[Event]:
    results: List[Event] = []
    work_map = _group_work_events(events)
    for offset in range(7):
        day = week_start.fromordinal(week_start.toordinal() + offset)
        pattern_key = _select_routine_pattern(day, work_map)
        routine_ranges = _resolve_routines(day, config, pattern_key)
        for name, (start_min, end_min) in routine_ranges.items():
            category = _routine_category(name)
            results.append(
                Event(
                    title=name,
                    day=day,
                    start_min=start_min,
                    end_min=end_min,
                    category=category,
                    color=colors.get(category, colors["free"]),
                    source="routine",
                    meta={},
                )
            )
    return results


def _resolve_routines(day: date, config: Config, pattern_key: str) -> Dict[str, tuple[int, int]]:
    routines = config.routines.get(pattern_key, {})
    if config.free_override_mode:
        routines = _apply_free_overrides(day, routines)
    return routines


def _apply_free_overrides(day: date, routines: Dict[str, tuple[int, int]]) -> Dict[str, tuple[int, int]]:
    _ = day
    return routines


def _select_routine_pattern(day: date, work_map: Dict[date, List[Event]]) -> str:
    work_segments = work_map.get(day, [])
    if _overlaps_window(work_segments, 0, 10 * 60):
        return "pattern_work_morning"
    if _overlaps_window(work_segments, 18 * 60, 24 * 60):
        return "pattern_work_night"
    if work_segments:
        return "pattern_work_night"
    return "pattern_nonwork"


def _build_class_events(
    day: date,
    day_classes: Dict[int, dict],
    config: Config,
    colors: Dict[str, str],
) -> List[Event]:
    results: List[Event] = []
    for period, entry in day_classes.items():
        time_range = config.time_table.get(int(period))
        if not time_range:
            continue
        title = entry.get("title", "(授業)")
        note = entry.get("location")
        start_min, end_min = time_range
        category = "class"
        color = colors.get(category, colors["class"])
        source = "class"
        meta = {"period": int(period)}
        if note:
            meta["note"] = note
        results.append(
            Event(
                title=title,
                day=day,
                start_min=start_min,
                end_min=end_min,
                category=category,
                color=color,
                source=source,
                note=note,
                meta=meta,
            )
        )
    return results


def _build_canceled_overrides(
    day: date,
    day_classes: Dict[int, dict],
    config: Config,
    colors: Dict[str, str],
    canceled_entries: List[dict],
) -> List[Event]:
    results: List[Event] = []
    canceled_periods = {entry.get("period") for entry in canceled_entries if entry.get("period")}
    cancel_all = any(entry.get("period") is None for entry in canceled_entries)

    if cancel_all:
        canceled_periods = set(day_classes.keys())

    for period in canceled_periods:
        time_range = config.time_table.get(int(period))
        if not time_range:
            continue
        note = _find_note_for_period(canceled_entries, period)
        results.append(
            Event(
                title="休講",
                day=day,
                start_min=time_range[0],
                end_min=time_range[1],
                category="free",
                color=colors.get("canceled", colors["free"]),
                source="special",
                note=note,
                meta={"canceled": True},
            )
        )
    return results


def _find_note_for_period(canceled_entries: List[dict], period: int) -> str | None:
    for entry in canceled_entries:
        if entry.get("period") in (None, period) and entry.get("note"):
            return entry["note"]
    return None


def _build_work(day: date, day_work: List[dict], colors: Dict[str, str]) -> List[Event]:
    results: List[Event] = []
    for shift in day_work:
        start_min, end_min = parse_time_range(shift["time"])
        results.append(
            Event(
                title=shift.get("title", "バイト"),
                day=day,
                start_min=start_min,
                end_min=end_min,
                category="work",
                color=colors.get("work", colors["work"]),
                source="work",
                meta={},
            )
        )
    return results


def _build_events(day: date, day_events: List[dict], colors: Dict[str, str]) -> List[Event]:
    results: List[Event] = []
    for entry in day_events:
        start_min, end_min = parse_time_range(entry["time"])
        category = entry.get("category", "free")
        results.append(
            Event(
                title=entry.get("title", "(予定)"),
                day=day,
                start_min=start_min,
                end_min=end_min,
                category=category,
                color=colors.get(category, colors["free"]),
                source="event",
                meta={},
            )
        )
    return results


def _apply_special_days(
    week_start: date,
    config: Config,
    events: List[Event],
    classes: Dict[int, Dict[int, dict]],
    colors: Dict[str, str],
    canceled_map: Dict[date, List[dict]],
    ondemand_map: Dict[date, List[dict]],
) -> List[Event]:
    results: List[Event] = []
    for event in events:
        if event.source != "class":
            results.append(event)
            continue
        canceled_entries = canceled_map.get(event.day, [])
        cancel_all = any(entry.get("period") is None for entry in canceled_entries)
        canceled_periods = {entry.get("period") for entry in canceled_entries if entry.get("period")}
        if cancel_all or event.meta.get("period") in canceled_periods:
            continue
        ondemand_entries = ondemand_map.get(event.day, [])
        ondemand_periods = {entry.get("period") for entry in ondemand_entries if entry.get("period")}
        if event.meta.get("period") in ondemand_periods:
            event = replace(
                event,
                title=f"[OD]{event.title}",
                color=colors.get("ondemand", event.color),
                meta={**event.meta, "ondemand": True},
            )
        results.append(event)

    for offset in range(7):
        day = week_start.fromordinal(week_start.toordinal() + offset)
        canceled_entries = canceled_map.get(day, [])
        if not canceled_entries:
            continue
        day_classes = classes.get(day.weekday(), {})
        results.extend(_build_canceled_overrides(day, day_classes, config, colors, canceled_entries))
    return results


def _split_multi_day_event(event: Event) -> List[Event]:
    if event.end_min <= 24 * 60:
        return [event]
    results: List[Event] = []
    current = event
    while current.end_min > 24 * 60:
        results.append(replace(current, end_min=24 * 60))
        next_day = current.day.fromordinal(current.day.toordinal() + 1)
        current = replace(current, day=next_day, start_min=0, end_min=current.end_min - 24 * 60)
    results.append(current)
    return results


def _routine_category(name: str) -> str:
    lowered = name.lower()
    if "sleep" in lowered or "睡眠" in name:
        return "sleep"
    if any(key in lowered for key in ("breakfast", "lunch", "dinner")) or any(
        word in name for word in ("朝食", "昼食", "夕食", "夕飯", "昼ごはん", "朝ごはん", "夕ごはん")
    ):
        return "meal"
    if "walk" in lowered or "散歩" in name:
        return "walk"
    return "free"


def _filter_routines_conflicting_with_events(routines: List[Event], events: List[Event]) -> List[Event]:
    event_candidates = [event for event in events if event.source == "event"]
    if not event_candidates:
        return routines
    events_by_day: Dict[date, List[Event]] = {}
    for event in event_candidates:
        events_by_day.setdefault(event.day, []).append(event)
    filtered: List[Event] = []
    for routine in routines:
        day_events = events_by_day.get(routine.day, [])
        if any(_events_overlap(routine, event) for event in day_events):
            continue
        filtered.append(routine)
    return filtered


def _events_overlap(left: Event, right: Event) -> bool:
    return left.start_min < right.end_min and left.end_min > right.start_min


def _group_work_events(events: List[Event]) -> Dict[date, List[Event]]:
    grouped: Dict[date, List[Event]] = {}
    for event in events:
        if event.category != "work":
            continue
        grouped.setdefault(event.day, []).append(event)
    return grouped


def _overlaps_window(events: List[Event], window_start: int, window_end: int) -> bool:
    for event in events:
        if event.start_min < window_end and event.end_min > window_start:
            return True
    return False


def mark_conflicts(events: List[Event]) -> None:
    events.sort(key=lambda item: item.start_min)
    for i, event in enumerate(events):
        for other in events[i + 1 :]:
            if other.start_min >= event.end_min:
                break
            if other.start_min < event.end_min and other.end_min > event.start_min:
                event.conflict = True
                other.conflict = True

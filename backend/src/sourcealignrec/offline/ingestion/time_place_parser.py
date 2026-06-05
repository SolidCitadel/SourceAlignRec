"""course list `time_place` 필드 파싱.

raw 형태: `"화 12:00-13:15 (전220) 목 12:00-13:15 (전220)"`
- N개 meeting이 공백으로 이어붙음. 각 meeting: `<요일> <시작>-<끝> (<강의실>)`
- 강의실 괄호 안. 비어있을 수도 있음(`""` 또는 괄호 자체 생략).

api-contract/_common.md §4 Weekday enum 정합:
- 한글 '월/화/수/목/금/토/일' → 영문 'Mon/Tue/Wed/Thu/Fri/Sat/Sun'.
"""
from __future__ import annotations

import re
from typing import TypedDict

_KOR_TO_EN = {
    "월": "Mon",
    "화": "Tue",
    "수": "Wed",
    "목": "Thu",
    "금": "Fri",
    "토": "Sat",
    "일": "Sun",
}


class MeetingDict(TypedDict):
    day: str
    start_time: str
    end_time: str
    room: str | None


# 한 meeting 토큰: 요일 + 공백 + HH:MM-HH:MM + (선택) 공백 + (강의실)
_MEETING_RE = re.compile(
    r"(?P<day>[월화수목금토일])\s*"
    r"(?P<start>\d{1,2}:\d{2})\s*-\s*(?P<end>\d{1,2}:\d{2})"
    r"(?:\s*\((?P<room>[^)]*)\))?"
)


def _normalize_time(t: str) -> str:
    """`9:00` → `09:00`."""
    h, m = t.split(":")
    return f"{int(h):02d}:{m}"


def parse_time_place(raw: str | None) -> list[MeetingDict]:
    """`time_place` → meetings list. 파싱 실패 토큰은 무시."""
    if not raw or not raw.strip():
        return []
    out: list[MeetingDict] = []
    for m in _MEETING_RE.finditer(raw):
        day_en = _KOR_TO_EN.get(m.group("day"))
        if day_en is None:
            continue
        room = (m.group("room") or "").strip() or None
        out.append(
            MeetingDict(
                day=day_en,
                start_time=_normalize_time(m.group("start")),
                end_time=_normalize_time(m.group("end")),
                room=room,
            )
        )
    return out

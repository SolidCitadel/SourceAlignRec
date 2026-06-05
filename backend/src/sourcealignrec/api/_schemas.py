"""Wire schema base. api-contract/_common.md §1 — JSON 키 camelCase + 내부 snake_case.

각 router의 request/response Pydantic 모델은 WireModel을 상속한다.
"""
import json

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class WireModel(BaseModel):
    """alias로 camelCase emit, snake_case로도 parse 허용."""
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class ClassMeetingOut(WireModel):
    """api-contract/_common.md §4 Weekday. recommend·search·offerings 응답 공통."""
    day: str
    start_time: str
    end_time: str
    room: str | None = None


def parse_meetings_json(raw: str | None) -> list[ClassMeetingOut]:
    """Offering.meetings_json → list[ClassMeetingOut]. 빈/잘못된 JSON은 빈 list."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    out: list[ClassMeetingOut] = []
    for m in data:
        if not isinstance(m, dict):
            continue
        try:
            out.append(
                ClassMeetingOut(
                    day=m.get("day", ""),
                    start_time=m.get("start_time", ""),
                    end_time=m.get("end_time", ""),
                    room=m.get("room"),
                )
            )
        except Exception:
            continue
    return out

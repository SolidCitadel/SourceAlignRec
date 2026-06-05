"""강의계획서 JSON → 구조화된 dict 파싱.

parse_syllabus(data)  : dict → SyllabusFields dict
load_syllabus(path)   : Path → SyllabusFields dict | None
parse_professor(data) : dict → (name: str, affiliation: str | None)
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TypedDict


class PrerequisiteCourse(TypedDict):
    name: str        # 과목명 (코드 포함, 예: "웹/파이선프로그래밍(SWCON104)")
    required: bool   # True=필수 선수, False=추천 선수


class EvaluationItem(TypedDict):
    item: str        # 중간고사, 기말고사, 과제, 출석 등
    ratio: int       # 0~100 정수
    note: str


class RecognizedDept(TypedDict):
    code: str
    name: str
    course_type: str   # 조회학과 기준 이수구분 (field_gb→gradIsuCd 라벨). 빈 문자열 가능.


class SyllabusFields(TypedDict):
    # 기본 정보 (스칼라)
    credits: int | None          # 학점
    course_type: str | None      # 이수구분 (전공필수/전공선택/교양 등)
    dept_name: str | None        # 개설학과
    is_english: bool             # 영어(부분)강좌 여부
    recognized_depts: list[RecognizedDept]  # 이 강의를 학점 인정해주는 학과 list
    # 내용 필드
    course_overview: str | None
    learning_objectives: str | None
    instruction_type_note: str | None
    instruction_type_ratios: list[dict]   # [{type, ratio_pct}]
    evaluation_items: list[EvaluationItem]
    weekly_topics: list[str]
    prerequisite_courses: list[PrerequisiteCourse]
    syllabus_text: str | None             # 레거시 flattened 텍스트
    syllabus_url: str | None              # 학교 강의계획서 원문 permalink (loginYn=N, 공개)


def parse_syllabus(data: dict) -> SyllabusFields:
    bi = data.get("basic_info") or {}
    return SyllabusFields(
        credits=_parse_credits(bi.get("학점")),
        course_type=bi.get("이수구분") or None,
        dept_name=bi.get("개설학과") or None,
        is_english=bool(bi.get("영어강좌여부", "")),
        recognized_depts=_parse_recognized_depts(data.get("recognized_depts") or []),
        course_overview=data.get("course_overview") or None,
        learning_objectives=data.get("learning_objectives_text") or None,
        instruction_type_note=data.get("instruction_type_note") or None,
        instruction_type_ratios=_parse_type_ratios(data.get("instruction_type_ratios") or []),
        evaluation_items=_parse_evaluation(data.get("evaluation_items") or []),
        weekly_topics=_parse_weekly_topics(data.get("weekly_schedule") or []),
        prerequisite_courses=_parse_prerequisites(data.get("prerequisites") or []),
        syllabus_text=_build_syllabus_text(data),
        syllabus_url=_clean_syllabus_url(data.get("syllabus_url")),
    )


def _clean_syllabus_url(raw: str | None) -> str | None:
    """원문 URL에서 크롤 시점 캐시버스터(`&fake=<timestamp>`)만 제거. 나머지 파라미터는 verbatim."""
    if not raw:
        return None
    cleaned = re.sub(r"[?&]fake=\d+", "", raw)
    return cleaned or None


def _parse_recognized_depts(rows: list) -> list[RecognizedDept]:
    result: list[RecognizedDept] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        code = (r.get("code") or "").strip()
        name = (r.get("name") or "").strip()
        if not code and not name:
            continue
        course_type = (r.get("course_type") or "").strip()
        result.append(RecognizedDept(code=code, name=name, course_type=course_type))
    return result


def parse_professor(data: dict) -> tuple[str, str | None]:
    """basic_info.교강사명 → (name, affiliation | None).

    예: '김재홍(소프트웨어융합대학 컴퓨터공학부)' → ('김재홍', '소프트웨어융합대학 컴퓨터공학부')
    """
    raw = (data.get("basic_info") or {}).get("교강사명") or ""
    m = re.match(r"^(.+?)\((.+?)\)", raw.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return raw.strip(), None


def load_syllabus(path: Path) -> SyllabusFields | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return parse_syllabus(data)


# ── 내부 파서 ─────────────────────────────────────────────────────────────────

def _parse_credits(val: str | None) -> int | None:
    try:
        return int(val) if val else None
    except (ValueError, TypeError):
        return None


def _parse_ratio_int(ratio_str: str) -> int:
    """'70%' → 70, '' → 0."""
    m = re.search(r"(\d+)", ratio_str or "")
    return int(m.group(1)) if m else 0


def _parse_type_ratios(items: list) -> list[dict]:
    return [
        {"type": it.get("type", ""), "ratio_pct": _parse_ratio_int(it.get("ratio", ""))}
        for it in items
        if it.get("type")
    ]


def _parse_evaluation(items: list) -> list[EvaluationItem]:
    return [
        EvaluationItem(
            item=it.get("item", ""),
            ratio=_parse_ratio_int(it.get("ratio", "")),
            note=it.get("note", "") or "",
        )
        for it in items
        if it.get("item")
    ]


def _parse_weekly_topics(schedule: list) -> list[str]:
    topics = [w.get("topic", "").strip() for w in schedule]
    return [t for t in topics if t]


def _parse_prerequisites(rows: list) -> list[PrerequisiteCourse]:
    """HTML 테이블 파싱 결과물에서 실제 과목만 추출."""
    result = []
    for row in rows:
        name = (row.get("선수교과목") or "").strip()
        if not name or name in ("선수교과목", "선수\n교과목"):
            continue
        flag = (row.get("필수 선수 과목") or "").replace("\n", "").replace(" ", "")
        required = "필수" in flag
        result.append(PrerequisiteCourse(name=name, required=required))
    return result


def _build_syllabus_text(data: dict) -> str | None:
    """레거시 flattened text (임베딩·검색용)."""
    parts = [
        data.get("course_overview") or "",
        data.get("learning_objectives_text") or "",
    ]
    parts += [w.get("topic", "") for w in (data.get("weekly_schedule") or [])]
    text = "\n".join(p for p in parts if p).strip()
    return text or None

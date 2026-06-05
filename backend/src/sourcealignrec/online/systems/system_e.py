"""System E — OfferingProfile 검색 + Tool Calling (grounding 전용).

e2e-benchmark.md §비교 시스템:
- 검색: OfferingProfile.embedding (D와 동일)
- LLM 컨텍스트: OfferingProfile (D와 동일)
- Tool Calling:
  - 초기 추천 턴: 비활성 (D와 동일 → recommend_initial은 system_d에 위임)
  - 후속 질문 턴: get_reviews, get_syllabus 활성 (grounding case)

후속 질문 grounding 정책:
- 조회 범위 = 추천된 K=3 과목(allowed_offering_ids)만. 컨텍스트 주입 + tool 인자 검증 모두 이 집합 기준.
- tool은 batch(offering_ids 배열) + 1라운드 제한 — 궁금한 과목을 한 번에 모아 조회 후 finalize.
- allowed 밖 id는 거부 메시지를 반환해 환각 grounding을 차단.

선호 변경/재추천은 시스템 책임이 아님 — 사용자가 form/query를 직접 갱신해 새 initial로 호출.
"""
from __future__ import annotations

import json

from sqlmodel import Session, select

from sourcealignrec.core.model_pool import get_pool
from sourcealignrec.db.models import (
    Offering,
    RepresentativeReview,
    Review,
)
from sourcealignrec.online.systems import system_d
from sourcealignrec.online.systems._common import (
    CONVERSE_SYSTEM_PROMPT,
    ConversationOutput,
    RecommendationOutput,
    TOOL_HINT_SUFFIX,
    build_converse_grounding_block,
    build_response_format,
    merge_profiles_into_first_user,
    parse_and_validate,
    strip_think,
    usage_dict,
)

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_reviews",
            "description": (
                "추천된 과목들의 대표 강의평 원문을 반환합니다. raw 강의평이 필요할 때 사용. "
                "궁금한 과목의 offering_id를 배열로 모아 한 번에 전달하세요."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "offering_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "조회할 추천 과목 ID 목록 (예: [\"CSE20100_2026-1\", \"AI300100_2026-1\"]). "
                            "추천된 과목 id만 허용."
                        ),
                    }
                },
                "required": ["offering_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_syllabus",
            "description": (
                "추천된 과목들의 강의계획서 구조화 데이터(주차별 주제, 평가 항목, 선수과목 등)를 반환합니다. "
                "궁금한 과목의 offering_id를 배열로 모아 한 번에 전달하세요."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "offering_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "조회할 추천 과목 ID 목록 (예: [\"CSE20100_2026-1\"]). 추천된 과목 id만 허용."
                        ),
                    }
                },
                "required": ["offering_ids"],
            },
        },
    },
]


def _get_reviews(session: Session, offering_id: str) -> str:
    offering = session.get(Offering, offering_id)
    if not offering:
        return f"{offering_id}: 없음"
    rows = session.exec(
        select(Review.raw_text, RepresentativeReview.rank)
        .join(RepresentativeReview, RepresentativeReview.review_id == Review.id)
        .where(RepresentativeReview.course_id == offering.course_id)
        .where(RepresentativeReview.professor_id == offering.professor_id)
        .order_by(RepresentativeReview.rank)
    ).all()
    if not rows:
        return f"{offering_id}: 리뷰 없음"
    return "\n".join(f"{rank}. {text}" for text, rank in rows)


def _get_syllabus(session: Session, offering_id: str) -> str:
    offering = session.get(Offering, offering_id)
    if not offering:
        return f"{offering_id}: 없음"
    result: dict = {}
    for field in ["course_overview", "learning_objectives", "weekly_topics",
                  "evaluation_items", "prerequisite_courses"]:
        val = getattr(offering, field)
        if not val or val == "[]":
            continue
        try:
            result[field] = json.loads(val)
        except (json.JSONDecodeError, TypeError):
            result[field] = val
    return json.dumps(result, ensure_ascii=False, indent=2)


def _execute_tool(
    session: Session, name: str, args: dict, allowed_set: set[str]
) -> str:
    """batch tool 실행. allowed_set 밖의 id는 거부 메시지로 환각 grounding을 차단한다."""
    ids = args.get("offering_ids") or []
    if isinstance(ids, str):  # 모델이 단건 문자열을 보낸 경우 방어
        ids = [ids]
    if not ids:
        return "offering_ids가 비어 있습니다."
    blocks: list[str] = []
    for oid in ids:
        if oid not in allowed_set:
            blocks.append(
                f"[{oid}] 추천 목록에 없어 조회 불가. 조회 가능한 id: {sorted(allowed_set)}"
            )
        elif name == "get_reviews":
            blocks.append(f"[{oid}]\n{_get_reviews(session, oid)}")
        elif name == "get_syllabus":
            blocks.append(f"[{oid}]\n{_get_syllabus(session, oid)}")
        else:
            return f"알 수 없는 tool: {name}"
    return "\n\n".join(blocks)


def recommend_initial(
    session: Session,
    query: str,
    filters: dict[str, list[str]],
    taken_courses: list[str],
    model: str,
) -> tuple[RecommendationOutput | None, list[dict], dict]:
    """초기 추천 (벤치마크 진입점). e2e-benchmark §실행 범위: D 초기 추천 = C 초기 추천 (tool 비활성)."""
    return system_d.recommend_initial(session, query, filters, taken_courses, model)


def recommend_initial_from_candidates(
    session: Session,
    query: str,
    candidate_ids: list[str],
    model: str,
) -> tuple[RecommendationOutput | None, list[dict], dict]:
    """초기 추천 (API 진입점). api-contract/recommend.md 정합 — candidate id list 받음."""
    return system_d.recommend_initial_from_candidates(session, query, candidate_ids, model)


def converse(
    session: Session,
    messages: list[dict],
    allowed_offering_ids: list[str],
    model: str,
) -> tuple[ConversationOutput | None, list[dict], dict]:
    """대화 turn 응답 (grounding 전용). 표준 tool-calling 결합 패턴.

    `messages`는 완결된 대화: [user(초기 질의), assistant(추천 items), (user 후속, assistant 설명)*,
    user(현재 후속)]. 마지막 user 턴이 답할 질문이다. 추천 과목 OfferingProfile 컨텍스트는 백엔드
    데이터라 첫 user 턴에 merge_profiles_into_first_user로 결합 → 초기 recommend가 본 메시지를 replay.

    grounding 범위·tool 검증의 단일 출처 = allowed_offering_ids (추천된 K=3). tool 인자 id를 이
    집합으로 검증한다.

    호출 구조:
    - Round 1: tools + response_format 동시 호출. tool이 불필요하면 이 응답이 곧 최종 schema 답
      (1회 호출로 종료).
    - tool 호출 시: 결과를 붙여 Round 2 호출(tools 미제공 → 1라운드 제한, batch tool로 모아 조회).

    endpoint 호환(2026-05-27 실측): 운영 모델 gemini-flash-lite·벤치마크 모델
    openrouter/gpt-oss-120b 모두 tools+response_format 결합을 허용하고 tool을 정상 호출한다.
    (참고: groq endpoint는 결합을 400으로 거부 — 모델 swap 시 split 복원 필요.)

    Returns: (parsed | None, transcript, meta).

    meta 추가 필드:
        tool_calls: list[str] — 호출된 tool 이름 시퀀스 (없으면 [])
    """
    allowed = list(dict.fromkeys(allowed_offering_ids))  # dedupe, rank 순서 보존
    allowed_set = set(allowed)
    tool_calls_made: list[str] = []

    pool = get_pool()
    system_msg = {"role": "system", "content": CONVERSE_SYSTEM_PROMPT + TOOL_HINT_SUFFIX}
    response_format = build_response_format(ConversationOutput)

    # 추천 과목 프로필을 첫 user 턴에 결합 (초기 recommend 메시지 replay). 나머지 대화는 messages가 운반.
    profiles_block = build_converse_grounding_block(session, allowed)
    working: list[dict] = merge_profiles_into_first_user(messages, profiles_block)

    # ── Round 1: tools + schema 동시. tool 불필요 시 이 응답이 곧 최종 답 ────
    response = pool.chat(
        model,
        [system_msg, *working],
        tools=TOOLS,
        tool_choice="auto",
        response_format=response_format,
        temperature=0.3,
    )
    msg = response.choices[0].message
    msg_dict: dict = {"role": "assistant", "content": msg.content}
    if msg.tool_calls:
        msg_dict["tool_calls"] = [tc.model_dump() for tc in msg.tool_calls]
    working.append(msg_dict)

    final_response = response  # tool 미사용 시 Round 1 응답이 곧 최종
    if msg.tool_calls:
        for tc in msg.tool_calls:
            tool_calls_made.append(tc.function.name)
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                args = {}
            result = _execute_tool(session, tc.function.name, args, allowed_set)
            working.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })
        # ── Round 2: tool 결과로 최종 schema 답. tools 미제공 → 추가 호출 차단(1라운드) ──
        final_response = pool.chat(
            model,
            [system_msg, *working],
            response_format=response_format,
            temperature=0.3,
        )
        working.append({
            "role": "assistant",
            "content": final_response.choices[0].message.content,
        })

    raw = strip_think(final_response.choices[0].message.content or "")
    parsed, status = parse_and_validate(raw, ConversationOutput, shortlist_ids=None)
    if status != "success":
        # parse_error는 운영에서 가장 흔한 failure mode. raw를 남기지 않으면 원인 추적 불가.
        print(
            f"[system_e.converse] parse failure status={status} "
            f"model={model} raw_len={len(raw)} tool_calls={tool_calls_made}\n"
            f"  raw_head: {raw[:800]!r}",
            flush=True,
        )
    meta = {
        "status": status,
        "schema_honored": status != "parse_error",
        "retry_count": 0,
        "tool_calls": tool_calls_made,
        **usage_dict(final_response),
    }
    return parsed, working, meta

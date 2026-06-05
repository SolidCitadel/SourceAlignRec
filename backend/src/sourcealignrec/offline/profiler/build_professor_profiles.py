"""교수별 대표 리뷰 집계 → LLM 5필드 요약 → ProfessorProfile 저장.

입력: RepresentativeReview(Course+Professor 단위 대표 리뷰, sar-select-reviews 산출)를
교수 단위로 모아 prof-generalizable 타입(grading/assignment/attendance/teaching/professor)만
필터링한 풀. 교수당 9~28개 수준으로, 다과목 교수는 모든 과목이 풀에 포함된다.
ProfessorRepresentativeReview(5개 cap)는 교수 페이지 "대표 리뷰" 표시 전용이라 한 과목으로
쏠릴 수 있어 프로필 입력으로 쓰지 않는다 — 프로필은 과목 커버리지가 더 중요하다.

4필드는 교수 일반화 가능한(과목 주제 무관) 특성이다
(format=강의 운영 경향, evaluation=평가 경향, reviews_summary=학생 평 종합,
caveats=유의사항). 과목 주제(topic)는 의도적으로 제외 — 교수 페이지의 강의 목록
섹션이 담당하며, 교수 프로필은 "어떤 교수인지"(스타일·평가·성향)에 집중한다.
UI 표시 전용(검색·추천 미사용).

Usage:
    uv run sar-build-professor-profiles --model groq/qwen3-32b
    uv run sar-build-professor-profiles --model groq/qwen3-32b --min-reviews 3 --overwrite
"""
from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict
from datetime import datetime

from sqlmodel import Session, select

from sourcealignrec.core.model_pool import get_pool
from sourcealignrec.db.models import (
    Course, ProfessorProfile, RepresentativeReview, Review, ReviewClassification,
)
from sourcealignrec.db.session import engine, init_db
from sourcealignrec.offline.candidates import (  # prof-type 후보 정의 단일 출처
    PROF_SCORE_FIELDS,
    PROF_TYPE_THRESHOLD as THRESHOLD,
)

REQUIRED_FIELDS = ["format", "evaluation", "reviews_summary", "caveats"]

SYSTEM_PROMPT = """\
당신은 한국 대학 강의 정보를 학생에게 제공하는 전문가입니다. 한 교수가 가르친 과목들의 대표 강의평을 보고, 이 교수를 수강 고려하는 학생이 알면 좋을 "어떤 교수인지"(강의 운영·평가 성향·소통·유의사항)를 정리합니다.

입력은 과목명별로 그룹화되어 있습니다. 강의평 본문은 교수의 강의력·평가·과제·출석·성향에 관한 내용입니다. 과목의 학문적 주제·분야는 정리 대상이 아니므로 출력하지 않습니다.

## 출력 형식 (JSON 객체, 다른 텍스트 없이 JSON만)

{
  "format": "강의 운영 방식 경향 (설명 방식, 수업 구성, 강의 자료, 실습·이론 비중 등). 1-3문장.",
  "evaluation": "평가·성적 경향 (성적 분포, 평가 방식, 과제 부담). 1-3문장.",
  "reviews_summary": "교수 강의력·소통·태도 등 정성적 평의 종합. 핵심 주장은 '원문에 가까운 표현'으로 인용(예: '질문에 친절하게 답해준다', '진도가 빠른 편이다'). 1-3문장.",
  "caveats": "수강 전 알아두면 좋은 유의사항 (예: 출석 엄격, 과제 양 많음). 없으면 빈 문자열."
}

## 작성 원칙

- 입력에 여러 과목이 있으면 과목 간 공통되는 경향을 우선 기술한다. 한 과목에서만 두드러지는 점도 그 과목을 명시해 포함할 수 있다.
- 입력이 한 과목이면 그 과목 기준으로 작성한다.
- 근거가 부족한 필드는 빈 문자열("")로 둔다. format은 가능한 채운다.

## 문체·표현 규칙

- 합쇼체 (-습니다/-ㅂ니다 종결): "다룹니다", "운영합니다", "평가합니다"
- 각 필드 1-3 짧은 문장. 줄바꿈 없이.
- 사실 기반. 추측·주관적 평가 표현(매우·정말·아주 등) 금지.

JSON만 출력. 코드블록·설명·마크다운 없음.\
"""


def _build_context(reviews_by_course: dict[str, list[str]]) -> str:
    """대표 리뷰를 과목 단위로 그루핑 — 교수의 과목 간 공통/고유 패턴 변별 신호 강화."""
    parts: list[str] = []
    for course_name, texts in reviews_by_course.items():
        parts.append(f"[{course_name}]")
        for t in texts:
            parts.append(f"- {t}")
        parts.append("")
    return "\n".join(parts).rstrip()


def _check_quality(profile_dict: dict) -> list[str]:
    """JSON schema 품질 체크. 문제 항목 리스트 반환 (빈 리스트면 통과)."""
    issues = []
    for field in REQUIRED_FIELDS:
        if field not in profile_dict:
            issues.append(f"{field} 필드 누락")
            continue
        if not isinstance(profile_dict[field], str):
            issues.append(f"{field} 타입 오류 (str 필요, {type(profile_dict[field]).__name__} 받음)")
    if profile_dict.get("format", "").strip() == "":
        issues.append("format 비어있음")
    return issues


def _call_llm(context: str, model_id: str) -> dict:
    """LLM에 JSON 응답 요청 → dict로 파싱. 실패 시 ValueError."""
    response = get_pool().chat(
        model_id,
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    text = (response.choices[0].message.content or "").strip()
    # thinking 모델의 <think>...</think> 블록 제거
    text = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()
    # 코드 펜스(```json ... ```)가 들어오면 제거
    fence = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```$", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM JSON 파싱 실패: {e}. 원문(앞 200자): {text[:200]}") from e


def run(model_id: str, min_reviews: int = 3, delay: float = 2.0, overwrite: bool = False,
        sample: int | None = None) -> None:
    print(f"모델: {model_id}  |  min_reviews: {min_reviews}")

    with Session(engine) as session:
        if overwrite:
            existing = session.exec(select(ProfessorProfile)).all()
            for p in existing:
                session.delete(p)
            session.commit()
            print("기존 ProfessorProfile 삭제 완료")
            done_ids: set[str] = set()
        else:
            done_ids = set(session.exec(select(ProfessorProfile.professor_id)).all())

        # 입력 풀: RepresentativeReview(Course+Professor 대표) 중 noise 제외 + prof-type 보유.
        rows = session.exec(
            select(
                RepresentativeReview.professor_id,
                Course.name,
                Review.raw_text,
                ReviewClassification,
                RepresentativeReview.rank,
            )
            .join(Review, RepresentativeReview.review_id == Review.id)
            .join(Course, Review.course_id == Course.id)
            .join(ReviewClassification, ReviewClassification.review_id == Review.id)
            .where(ReviewClassification.is_noise == False)  # noqa: E712
            .order_by(RepresentativeReview.professor_id, Course.name,
                      RepresentativeReview.rank)
        ).all()

        if not rows:
            print("RepresentativeReview 데이터 없음. sar-select-reviews 먼저 실행.")
            return

        prof_data: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        for professor_id, course_name, raw_text, rc, _rank in rows:
            if professor_id in done_ids:
                continue
            if not any(getattr(rc, f) >= THRESHOLD for f in PROF_SCORE_FIELDS):
                continue  # prof-generalizable 타입 신호 없는 리뷰는 제외
            prof_data[professor_id][course_name].append(raw_text)

        eligible = {
            pid: courses
            for pid, courses in prof_data.items()
            if sum(len(v) for v in courses.values()) >= min_reviews
        }
        if sample is not None:
            eligible = dict(list(eligible.items())[:sample])
        print(f"프로파일 생성 대상 교수: {len(eligible)}명 (총 {len(prof_data)}명 중)"
              f"{f' (sample={sample})' if sample else ''}")

        saved = 0
        for i, (professor_id, reviews_by_course) in enumerate(eligible.items(), 1):
            review_count = sum(len(v) for v in reviews_by_course.values())
            context = _build_context(reviews_by_course)
            try:
                profile_dict = _call_llm(context, model_id)
            except Exception as e:
                print(f"  [{i}/{len(eligible)}] {professor_id} 오류 (건너뜀): {e}")
                continue

            issues = _check_quality(profile_dict)
            if issues:
                print(f"  [{i}/{len(eligible)}] {professor_id} 품질 경고: {', '.join(issues)}")

            profile_json_str = json.dumps(profile_dict, ensure_ascii=False)
            updated_at = datetime.utcnow()

            existing = session.get(ProfessorProfile, professor_id)
            if existing:
                existing.profile_json = profile_json_str
                existing.source_review_count = review_count
                existing.profile_updated_at = updated_at
                session.add(existing)
            else:
                session.add(ProfessorProfile(
                    professor_id=professor_id,
                    profile_json=profile_json_str,
                    source_review_count=review_count,
                    profile_updated_at=updated_at,
                ))
            saved += 1

            if saved % 10 == 0:
                session.commit()
                print(f"  {i}/{len(eligible)} 완료")

            if delay > 0 and i < len(eligible):
                time.sleep(delay)

        session.commit()
        print(f"\n완료: {saved}개 ProfessorProfile 저장")


def main() -> None:
    parser = argparse.ArgumentParser(description="교수별 ProfessorProfile 생성 (5필드 JSON)")
    parser.add_argument("--model", required=True, help="model-pool model_id (family: llm)")
    parser.add_argument("--min-reviews", type=int, default=3, help="최소 대표 리뷰 수")
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--sample", type=int, default=None, help="처리할 교수 수 제한 (spot-check용)")
    args = parser.parse_args()

    init_db()
    run(args.model, args.min_reviews, args.delay, args.overwrite, args.sample)


if __name__ == "__main__":
    main()

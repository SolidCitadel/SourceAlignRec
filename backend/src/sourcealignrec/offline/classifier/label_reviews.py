"""리뷰 multi-label LLM 라벨링.

고정 seed로 샘플을 결정하므로 중단 후 재실행하면 이어서 진행.

Usage:
    uv run sar-label-reviews --model groq/qwen3-32b
    uv run sar-label-reviews --model groq/qwen3-32b --n 150 --seed 42
"""
from __future__ import annotations

import argparse
import json
import random
import time

import openai
from sqlmodel import Session, select

from sourcealignrec.core.model_pool import get_pool
from sourcealignrec.db.models import Review, ReviewTypeLabel
from sourcealignrec.db.session import engine, init_db


SYSTEM_PROMPT = """\
한국 대학교 강의평을 다음 7가지 타입으로 multi-label 분류한다.

타입 정의:
- grading   : 학점 관대함/깐깐함, 성적 분포에 관한 내용
- exam      : 시험·퀴즈 방식·난이도·범위, 족보 유효성에 관한 내용
- assignment: 과제·팀플·개인 프로젝트의 양과 방식에 관한 내용 (없음·적음도 포함)
- attendance: 출석 정책, 출결 관리 방식에 관한 내용
- teaching  : 강의 품질에 관한 내용 — 설명 방식, 강의력, 수업 진행, 강의 자료
              예) "설명을 잘 못 하신다", "강의력이 좋다", "수업이 알차다"
- topic     : 수업에서 구체적으로 다루는 내용·주제·커리큘럼, 수강 적합 대상, 선수지식에 관한 내용
              예) "알고리즘 위주로 배운다", "비전공자도 들을 만하다" / 제외) "수업이 좋았다" 같은 단순 평가
- professor : 교수의 인성·태도·학생 대하는 방식에 관한 내용 — 수업 품질과 무관한 개인 성격
              예) "교수님이 친절하시다", "학생을 무시하는 태도" / 제외) 강의력·수업 방식

출력 형식 — JSON only, 다른 텍스트 금지:
{"grading": bool, "exam": bool, "assignment": bool, "attendance": bool, "teaching": bool, "topic": bool, "professor": bool}

규칙:
- 여러 타입에 해당하면 모두 true
- 실질적인 수업 정보가 없는 내용(감정 표현, 응원, 의미불명 한줄)은 전부 false
- 확신 없으면 false (과추출보다 과소추출 선호)\
"""


# ── 샘플링 ────────────────────────────────────────────────────────────────────

def _sample_reviews(session: Session, n: int, seed: int) -> list[Review]:
    """과목·길이 다양하게 층화 추출. 같은 seed → 같은 결과 (재실행 시 동일 목록)."""
    reviews = session.exec(select(Review)).all()

    # 과목별 그룹
    by_course: dict[str, list[Review]] = {}
    for r in reviews:
        by_course.setdefault(r.course_id, []).append(r)

    rng = random.Random(seed)
    sampled: list[Review] = []

    for rs in by_course.values():
        rs_sorted = sorted(rs, key=lambda r: len(r.raw_text))
        k = len(rs_sorted)
        # 길이 3분위 버킷에서 하나씩
        for bucket in (rs_sorted[:k//3], rs_sorted[k//3:2*k//3], rs_sorted[2*k//3:]):
            if bucket:
                sampled.append(rng.choice(bucket))

    rng.shuffle(sampled)

    # n 미달이면 남은 풀에서 보충
    if len(sampled) < n:
        sampled_ids = {r.id for r in sampled}
        extra = [r for r in reviews if r.id not in sampled_ids]
        rng.shuffle(extra)
        sampled += extra[:n - len(sampled)]

    return sampled[:n]


def _labeled_ids(session: Session, labeler: str) -> set[str]:
    """이 labeler가 이미 처리한 review_id 집합."""
    rows = session.exec(
        select(ReviewTypeLabel.review_id).where(ReviewTypeLabel.labeler == labeler)
    ).all()
    return set(rows)


# ── LLM 호출 ─────────────────────────────────────────────────────────────────

def _parse(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        content = content.split("```", 2)[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.rsplit("```", 1)[0]
    try:
        data = json.loads(content.strip())
    except json.JSONDecodeError:
        # thinking 토큰 등이 앞에 붙어 있는 경우 fallback
        start, end = content.find("{"), content.rfind("}")
        data = json.loads(content[start:end + 1])

    return {
        "grading":    bool(data.get("grading", False)),
        "exam":       bool(data.get("exam", False)),
        "assignment": bool(data.get("assignment", False)),
        "attendance": bool(data.get("attendance", False)),
        "teaching":   bool(data.get("teaching", False)),
        "topic":      bool(data.get("topic", False)),
        "professor":  bool(data.get("professor", False)),
    }


def _call_llm(text: str, model_id: str) -> dict:
    response = get_pool().chat(
        model_id,
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0.0,
    )
    content = response.choices[0].message.content or ""
    return _parse(content)


# ── 실행 ──────────────────────────────────────────────────────────────────────

def run(model_id: str, n: int = 150, seed: int = 42, delay: float = 8.0) -> None:
    print(f"모델: {model_id}")
    if delay > 0:
        print(f"요청 간격: {delay}초")

    with Session(engine) as session:
        targets = _sample_reviews(session, n, seed)
        done_ids = _labeled_ids(session, model_id)
        pending = [r for r in targets if r.id not in done_ids]

        already = len(targets) - len(pending)
        print(f"목표: {len(targets)}개  |  완료: {already}개  |  남은 것: {len(pending)}개")
        if not pending:
            print("모두 완료됨.")
            return

        labeled = 0
        for i, review in enumerate(pending, 1):
            try:
                result = _call_llm(review.raw_text, model_id)
            except openai.RateLimitError:
                session.commit()
                print(
                    f"\n  [{i}/{len(pending)}] Rate limit 재시도 초과 - {labeled}개 처리 후 중단.\n"
                    f"  다시 실행하면 이어서 진행됩니다."
                )
                return
            except Exception as e:
                print(f"  [{i}/{len(pending)}] {review.id} 오류 (건너뜀): {e}")
                continue

            is_noise = not any(result.values())
            session.add(ReviewTypeLabel(
                review_id=review.id,
                source="llm",
                labeler=model_id,
                is_noise=is_noise,
                **result,
            ))
            labeled += 1

            if labeled % 20 == 0:
                session.commit()
                print(f"  {already + labeled}/{len(targets)} 완료")

            if delay > 0 and i < len(pending):
                time.sleep(delay)

        session.commit()
        print(f"\n완료: {already + labeled}/{len(targets)}개 라벨링됨")


# ── 진입점 ───────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="리뷰 multi-label LLM 라벨링")
    parser.add_argument("--model", default="groq/qwen3-32b")
    parser.add_argument("--n", type=int, default=150, help="목표 샘플 수")
    parser.add_argument("--seed", type=int, default=42, help="샘플링 seed (같은 seed = 같은 목록)")
    parser.add_argument("--delay", type=float, default=8.0, help="요청 간 대기 시간(초). rate limit 방지용")
    args = parser.parse_args()

    init_db()
    run(args.model, args.n, args.seed, args.delay)


if __name__ == "__main__":
    main()

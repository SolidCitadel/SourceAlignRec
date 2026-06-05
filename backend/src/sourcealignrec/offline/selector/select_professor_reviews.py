"""Course 대표 리뷰 풀에서 교수 단위 DynamicScore greedy 선정 → ProfessorRepresentativeReview 저장.

professor-generalizable 타입(professor/teaching/grading/assignment/attendance)만 고려.
DynamicScore(r) = (Σ_{i ∉ S_covered} P_i + λ · Σ_{i ∈ S_covered} P_i) × Density(r)
  P_i       : PROF_LABELS 내 타입 i p-score (classification: BERT float / labels: gold bool→float)
  Density(r): Gaussian KDE — 교수 전체 대표 리뷰 코퍼스 기준 여론 대표성
  λ         : 기커버 타입 감쇄 (default 0.3)

--source labels         : ReviewTypeLabel(gold)을 사용. sar-classify-reviews 불필요.
--source classification : ReviewClassification(BERT 추론)을 사용 (default).

Usage:
    uv run sar-select-professor-reviews --source labels
    uv run sar-select-professor-reviews --top-k 5 --lambda 0.3 --bandwidth 0.5 --overwrite
"""
from __future__ import annotations

import argparse
from collections import defaultdict

import numpy as np
from sqlmodel import Session, select

from sourcealignrec.db.models import (
    ProfessorRepresentativeReview, RepresentativeReview,
    Review, ReviewClassification, ReviewTypeLabel,
)
from sourcealignrec.db.session import engine, init_db
from sourcealignrec.offline.candidates import (  # prof-type 후보 정의 단일 출처
    PROF_LABELS,
    PROF_SCORE_FIELDS,
    PROF_TYPE_THRESHOLD as THRESHOLD,
)


def _compute_kde_density(embeddings: np.ndarray, h: float) -> np.ndarray:
    if len(embeddings) == 1:
        return np.array([1.0])
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1e-9, norms)
    normed = embeddings / norms
    sim = normed @ normed.T
    return np.exp(-(1 - sim) / h).mean(axis=1)


def _greedy_select(
    review_ids: list[str],
    p_scores: np.ndarray,
    density: np.ndarray,
    top_k: int,
    lam: float,
) -> list[tuple[str, int]]:
    selected: list[tuple[str, int]] = []
    covered = np.zeros(len(PROF_LABELS), dtype=float)
    remaining = list(range(len(review_ids)))

    for rank in range(1, top_k + 1):
        if not remaining:
            break
        best_idx, best_score = -1, -1.0
        for i in remaining:
            uncovered = sum(p_scores[i, j] for j in range(len(PROF_LABELS)) if covered[j] < THRESHOLD)
            cover_dup = sum(p_scores[i, j] for j in range(len(PROF_LABELS)) if covered[j] >= THRESHOLD)
            dynamic = (uncovered + lam * cover_dup) * density[i]
            if dynamic > best_score:
                best_score, best_idx = dynamic, i

        selected.append((review_ids[best_idx], rank))
        covered = np.maximum(covered, p_scores[best_idx])
        remaining.remove(best_idx)

    return selected


def run(top_k: int = 5, lam: float = 0.3, bandwidth: float = 0.05, overwrite: bool = False, source: str = "classification") -> None:
    with Session(engine) as session:
        if source == "labels":
            rows = session.exec(
                select(
                    RepresentativeReview.professor_id,
                    RepresentativeReview.review_id,
                    ReviewTypeLabel,
                    Review.embedding,
                )
                .join(Review, RepresentativeReview.review_id == Review.id)
                .join(ReviewTypeLabel, ReviewTypeLabel.review_id == Review.id)
                .where(ReviewTypeLabel.is_noise == False)  # noqa: E712
            ).all()
            if not rows:
                print("RepresentativeReview 또는 ReviewTypeLabel 데이터 없음.")
                print("sar-select-reviews --source labels와 sar-label-reviews를 먼저 실행하세요.")
                return
            def get_p_scores(lbl):
                return [float(getattr(lbl, t)) for t in PROF_LABELS]
            def has_prof_type(lbl):
                return any(getattr(lbl, t) for t in PROF_LABELS)
            classifier_model = "gold_labels"
        else:
            rows = session.exec(
                select(
                    RepresentativeReview.professor_id,
                    RepresentativeReview.review_id,
                    ReviewClassification,
                    Review.embedding,
                )
                .join(Review, RepresentativeReview.review_id == Review.id)
                .join(ReviewClassification, ReviewClassification.review_id == Review.id)
                .where(ReviewClassification.is_noise == False)  # noqa: E712
            ).all()
            if not rows:
                print("RepresentativeReview 또는 ReviewClassification 데이터 없음.")
                print("sar-select-reviews와 sar-classify-reviews를 먼저 실행하세요.")
                return
            def get_p_scores(rc):
                return [getattr(rc, f) for f in PROF_SCORE_FIELDS]
            def has_prof_type(rc):
                return any(getattr(rc, f) >= THRESHOLD for f in PROF_SCORE_FIELDS)
            classifier_model = rows[0][2].model_path if rows else ""

        prof_rows = [
            (professor_id, review_id, score_src, emb)
            for professor_id, review_id, score_src, emb in rows
            if has_prof_type(score_src)
        ]

        print(f"소스: {source} | 대상 리뷰: {len(prof_rows)}개 (course 대표 리뷰 풀, prof-type 보유)")

        groups: dict[str, list] = defaultdict(list)
        for professor_id, review_id, score_src, emb in prof_rows:
            groups[professor_id].append((review_id, score_src, emb))

        if overwrite:
            existing = session.exec(select(ProfessorRepresentativeReview)).all()
            for r in existing:
                session.delete(r)
            session.commit()
            print("기존 ProfessorRepresentativeReview 삭제 완료")
        else:
            done_profs: set[str] = set(
                session.exec(select(ProfessorRepresentativeReview.professor_id)).all()
            )
            groups = {k: v for k, v in groups.items() if k not in done_profs}

        print(f"선정 대상 Professor 그룹: {len(groups)}개")

        total_saved = 0
        for professor_id, items in groups.items():
            review_ids = [review_id for review_id, _, _ in items]
            score_srcs = [src for _, src, _ in items]
            embs = [emb for _, _, emb in items]

            p_scores = np.array([get_p_scores(src) for src in score_srcs])

            if all(e is not None for e in embs):
                density = _compute_kde_density(np.array(embs, dtype=np.float32), bandwidth)
            else:
                density = np.ones(len(score_srcs))

            selected = _greedy_select(review_ids, p_scores, density, top_k, lam)

            for review_id, rank in selected:
                session.add(ProfessorRepresentativeReview(
                    professor_id=professor_id,
                    review_id=review_id,
                    rank=rank,
                    classifier_model_path=classifier_model,
                ))
            total_saved += len(selected)

        session.commit()
        print(f"\n완료: {total_saved}개 ProfessorRepresentativeReview 저장 ({len(groups)}개 교수)")


def main() -> None:
    parser = argparse.ArgumentParser(description="교수 단위 DynamicScore 대표 리뷰 선정")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--lambda", dest="lam", type=float, default=0.3)
    parser.add_argument("--bandwidth", type=float, default=0.5, help="Gaussian KDE bandwidth h")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--source", choices=["labels", "classification"], default="classification",
                        help="p-score 소스: labels=ReviewTypeLabel(gold), classification=ReviewClassification(BERT)")
    args = parser.parse_args()

    init_db()
    run(args.top_k, args.lam, args.bandwidth, args.overwrite, args.source)


if __name__ == "__main__":
    main()

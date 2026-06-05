"""DynamicScore 기반 대표 리뷰 선정 → RepresentativeReview 저장.

DynamicScore(r) = (Σ_{i ∉ S_covered} P_i + λ · Σ_{i ∈ S_covered} P_i) × Density(r)
  P_i         : 타입 i p-score (classification: BERT float / labels: gold bool→float)
  S_covered   : 이미 선정된 리뷰가 커버한 타입 집합 (p_score > threshold)
  λ           : 기커버 타입 감쇄 (default 0.3)
  Density(r)  : Gaussian KDE 기반 여론 대표성
                Density(r)  = (1/N) Σ_j exp(-(1 - CosineSim(Vr,Vj)) / h)
  h           : bandwidth (sar-benchmark-select-reviews로 결정, default 0.05)

임베딩이 없는 리뷰는 Density=1 (uniform) 처리.

--source labels         : ReviewTypeLabel(gold)을 사용. sar-classify-reviews 불필요.
--source classification : ReviewClassification(BERT 추론)을 사용 (default).

Usage:
    uv run sar-select-reviews --source labels
    uv run sar-select-reviews --top-k 5 --lambda 0.3 --bandwidth 0.05 --overwrite
"""
from __future__ import annotations

import argparse
from collections import defaultdict

import numpy as np
from sqlmodel import Session, select

from sourcealignrec.db.models import Review, ReviewClassification, ReviewTypeLabel, RepresentativeReview
from sourcealignrec.db.session import engine, init_db
from sourcealignrec.offline.candidates import COURSE_MIN_REVIEWS  # 후보 최소건수 단일 출처
from sourcealignrec.offline.classifier.train_bert import LABELS

SCORE_FIELDS = [f"{t}_score" for t in LABELS]
THRESHOLD = 0.5


def _compute_kde_density(embeddings: np.ndarray, h: float) -> np.ndarray:
    """Gaussian KDE 여론 대표성.

    높을수록 주변 리뷰들과 의견이 일치하는 리뷰 = 다수 의견을 대표.
    """
    if len(embeddings) == 1:
        return np.array([1.0])
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1e-9, norms)
    normed = embeddings / norms
    sim = normed @ normed.T  # (N, N) cosine similarity
    return np.exp(-(1 - sim) / h).mean(axis=1)


def _greedy_select(
    review_ids: list[str],
    p_scores: np.ndarray,
    density: np.ndarray,
    top_k: int,
    lam: float,
) -> list[tuple[str, int]]:
    selected: list[tuple[str, int]] = []
    covered = np.zeros(len(LABELS), dtype=float)
    remaining = list(range(len(review_ids)))

    for rank in range(1, top_k + 1):
        if not remaining:
            break
        best_idx, best_score = -1, -1.0
        for i in remaining:
            uncovered = sum(p_scores[i, j] for j in range(len(LABELS)) if covered[j] < THRESHOLD)
            cover_dup = sum(p_scores[i, j] for j in range(len(LABELS)) if covered[j] >= THRESHOLD)
            dynamic = (uncovered + lam * cover_dup) * density[i]
            if dynamic > best_score:
                best_score, best_idx = dynamic, i

        selected.append((review_ids[best_idx], rank))
        covered = np.maximum(covered, p_scores[best_idx])
        remaining.remove(best_idx)

    return selected


def _load_from_labels(session: Session) -> tuple[list, str]:
    """ReviewTypeLabel(gold) 기반 로딩. (review_ids, p_scores_row, course_id, professor_id, embedding) 반환."""
    rows = session.exec(
        select(ReviewTypeLabel, Review.course_id, Review.professor_id, Review.embedding)
        .join(Review, ReviewTypeLabel.review_id == Review.id)
        .where(ReviewTypeLabel.is_noise == False)  # noqa: E712
    ).all()
    return rows, "gold_labels"


def _load_from_classification(session: Session) -> tuple[list, str]:
    rows = session.exec(
        select(ReviewClassification, Review.course_id, Review.professor_id, Review.embedding)
        .join(Review, ReviewClassification.review_id == Review.id)
        .where(ReviewClassification.is_noise == False)  # noqa: E712
    ).all()
    model_path = rows[0][0].model_path if rows else ""
    return rows, model_path


def run(top_k: int = 10, lam: float = 0.3, bandwidth: float = 0.05, overwrite: bool = False, source: str = "classification", min_reviews: int = COURSE_MIN_REVIEWS) -> None:
    with Session(engine) as session:
        if source == "labels":
            rows, classifier_model = _load_from_labels(session)
            if not rows:
                print("ReviewTypeLabel 데이터 없음. sar-label-reviews를 먼저 실행하세요.")
                return
            def get_p_scores(item):
                lbl, *_ = item
                return [float(getattr(lbl, t)) for t in LABELS]
            def get_review_id(item):
                lbl, *_ = item
                return lbl.review_id
        else:
            rows, classifier_model = _load_from_classification(session)
            if not rows:
                print("ReviewClassification 데이터 없음. sar-classify-reviews를 먼저 실행하세요.")
                return
            def get_p_scores(item):
                rc, *_ = item
                return [getattr(rc, f) for f in SCORE_FIELDS]
            def get_review_id(item):
                rc, *_ = item
                return rc.review_id

        has_emb = sum(1 for *_, emb in rows if emb is not None)
        print(f"소스: {source} | 대상 리뷰: {len(rows)}개 (noise 제외, 임베딩 보유: {has_emb}개)")

        groups: dict[tuple[str, str], list] = defaultdict(list)
        for row in rows:
            course_id, professor_id, embedding = row[-3], row[-2], row[-1]
            groups[(course_id, professor_id)].append((row, embedding))

        skipped = {k for k, v in groups.items() if len(v) < min_reviews}
        if skipped:
            print(f"min_reviews={min_reviews} 미충족으로 건너뜀: {len(skipped)}개 그룹 → Professor fallback")
        groups = {k: v for k, v in groups.items() if k not in skipped}

        if overwrite:
            existing = session.exec(select(RepresentativeReview)).all()
            for r in existing:
                session.delete(r)
            session.commit()
            print("기존 RepresentativeReview 삭제 완료")
        else:
            done_pairs: set[tuple[str, str]] = set(
                session.exec(
                    select(RepresentativeReview.course_id, RepresentativeReview.professor_id)
                ).all()
            )
            groups = {k: v for k, v in groups.items() if k not in done_pairs}

        print(f"선정 대상 Course+Professor 그룹: {len(groups)}개")

        total_saved = 0
        for (course_id, professor_id), items in groups.items():
            rows_group = [item for item, _ in items]
            embs = [emb for _, emb in items]
            review_ids = [get_review_id(r) for r in rows_group]

            p_scores = np.array([get_p_scores(r) for r in rows_group])

            if all(e is not None for e in embs):
                density = _compute_kde_density(np.array(embs, dtype=np.float32), bandwidth)
            else:
                density = np.ones(len(rows_group))

            selected = _greedy_select(review_ids, p_scores, density, top_k, lam)

            for review_id, rank in selected:
                session.add(RepresentativeReview(
                    course_id=course_id,
                    professor_id=professor_id,
                    review_id=review_id,
                    rank=rank,
                    classifier_model_path=classifier_model,
                ))
            total_saved += len(selected)

        session.commit()
        print(f"\n완료: {total_saved}개 RepresentativeReview 저장 ({len(groups)}개 그룹)")


def main() -> None:
    parser = argparse.ArgumentParser(description="DynamicScore 기반 대표 리뷰 선정")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--lambda", dest="lam", type=float, default=0.3)
    parser.add_argument("--bandwidth", type=float, default=0.05, help="Gaussian KDE bandwidth h")
    parser.add_argument("--min-reviews", type=int, default=COURSE_MIN_REVIEWS, help="그룹 최소 리뷰 수 (미달 시 Professor fallback)")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--source", choices=["labels", "classification"], default="classification",
                        help="p-score 소스: labels=ReviewTypeLabel(gold), classification=ReviewClassification(BERT)")
    args = parser.parse_args()

    init_db()
    run(args.top_k, args.lam, args.bandwidth, args.overwrite, args.source, args.min_reviews)


if __name__ == "__main__":
    main()

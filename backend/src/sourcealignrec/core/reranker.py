"""In-process cross-encoder reranker — dragonkue/bge-reranker-v2-m3-ko (sentence-transformers).

`core/embedder.py`와 동형 — 프로세스당 모델 1벌 lru_cache 로드, (query, doc) 쌍에 relevance
점수 부여. retrieval(bi-encoder)이 좁힌 loose pool을 정밀 재정렬하는 System CE_* 전용.

선정 근거(experiments §9 / plan archive cross-encoder-rerank): 한국어 reranking 벤치 1위
(AutoRAG-ko Top-k1 F1 0.9123) + 임베더(dragonkue arctic-ko)와 동일 계보 + bge-m3 base
컨텍스트 8192(profile·syllabus 모두 안전) + 0.6B in-process.

점수는 raw logit(num_labels=1) — 절대값이 아니라 **순위**만 사용(내림차순 = 관련도 높음).
sigmoid 등 normalize는 ranking에 불변이라 미적용.
"""
from __future__ import annotations

from functools import lru_cache

import torch
from sentence_transformers import CrossEncoder

MODEL_NAME = "dragonkue/bge-reranker-v2-m3-ko"
_IDENTITY = torch.nn.Identity()  # raw logit 반환 — 기본 sigmoid는 음수 logit을 0 근처로 압축(순위는 동일하나 해석·디버깅 불리)


@lru_cache(maxsize=1)
def _model() -> CrossEncoder:
    """프로세스당 1벌 로드(최초 호출 시 ~2.3GB). device는 sentence-transformers 자동 선택."""
    return CrossEncoder(MODEL_NAME)


def rerank(query: str, docs: list[str]) -> list[float]:
    """(query, doc) 쌍별 relevance raw logit list. docs 순서 보존 — 호출자가 zip 후 내림차순 정렬.

    높을수록 관련. sigmoid 미적용(단조라 순위 불변) — 점수 spread 보존해 수동 검증·임계 디버깅 용이.
    """
    if not docs:
        return []
    pairs = [(query, d) for d in docs]
    scores = _model().predict(pairs, activation_fn=_IDENTITY, show_progress_bar=False)
    return [float(s) for s in scores]

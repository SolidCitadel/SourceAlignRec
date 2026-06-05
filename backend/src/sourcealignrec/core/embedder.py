"""In-process 임베딩 — dragonkue/snowflake-arctic-embed-l-v2.0-ko (sentence-transformers).

배포(LM Studio 없는 환경)와 dev 공통 단일 경로. `model_pool`은 chat(갈아끼우는 LLM) 전용 —
임베딩은 DB에 고정돼 갈아끼우기 불가하므로 본 모듈로 분리(deployment-implementation.md 1단계).

전처리 정본 (HF 모델 카드 기준):
- normalize: 모델에 Normalize() 레이어 내장 → encode 결과 자동 L2 정규화.
- pooling: CLS (모델 설정).
- query prefix: 모델 카드는 query에 prompt_name="query"("query: " prefix)를 권장하나,
  기존 파이프라인(LM Studio 경로)이 query·document 모두 prefix 없이 임베딩 →
  그 대칭 동작을 재현하기 위해 **기본 미적용**. 품질용 prefix 도입은 후속(도입 시
  document 재임베딩과 함께 일괄, 벤치마크 비교 가능성 고려).

device는 sentence-transformers 자동 선택: CUDA 가용 시 cuda(dev), 아니면 cpu(배포 ARM).
"""
from __future__ import annotations

from functools import lru_cache

from sentence_transformers import SentenceTransformer

MODEL_NAME = "dragonkue/snowflake-arctic-embed-l-v2.0-ko"


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    """프로세스당 1벌 로드(최초 호출 시 ~2.5GB). API는 startup warm-up 권장."""
    return SentenceTransformer(MODEL_NAME)


def embed(text: str) -> list[float]:
    """단일 텍스트 → 임베딩. 기존 `_common.embed` 시그니처 호환(query·document 공용, prefix 미적용)."""
    vec = _model().encode([text], show_progress_bar=False)[0]
    return vec.tolist()


def embed_many(texts: list[str], *, batch_size: int = 32) -> list[list[float]]:
    """배치 임베딩 — offline 생성·재생성용."""
    vecs = _model().encode(texts, batch_size=batch_size, show_progress_bar=False)
    return [v.tolist() for v in vecs]
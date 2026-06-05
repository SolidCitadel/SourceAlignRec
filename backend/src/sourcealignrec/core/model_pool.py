"""Model Pool — model-pool.yaml → OpenAI client.

외부에서 raw client를 직접 취득하지 말 것 — chat() / embed() 사용.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import openai
import yaml
from dotenv import load_dotenv

_DEFAULT_PATH = Path(__file__).parent.parent.parent.parent / "model-pool.yaml"
_ENV_PATH = Path(__file__).parent.parent.parent.parent / ".env"

load_dotenv(_ENV_PATH)


class ModelPool:
    def __init__(self, path: Path = _DEFAULT_PATH) -> None:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self._endpoints: dict[str, dict] = {
            ep["endpoint_id"]: ep for ep in data.get("endpoints", [])
        }
        self._models: dict[str, dict] = {
            m["model_id"]: m for m in data.get("models", [])
        }
        self._clients: dict[str, openai.OpenAI] = {}

    def _client(self, model_id: str) -> tuple[openai.OpenAI, str]:
        """내부 전용 — 외부에서 직접 호출 금지. chat() / embed() 사용."""
        m = self._models.get(model_id)
        if not m:
            raise KeyError(f"'{model_id}' not found in model pool")
        ep = self._endpoints[m["endpoint_id"]]
        ep_id = ep["endpoint_id"]
        if ep_id not in self._clients:
            self._clients[ep_id] = openai.OpenAI(
                base_url=os.getenv(ep["base_url_env"]),
                api_key=os.getenv(ep["api_key_env"], "none"),
                max_retries=10,
            )
        return self._clients[ep_id], m["model_name"]

    def chat(self, model_id: str, messages: list, **kwargs):
        """RateLimitError 지수 백오프 재시도 포함 chat completion.

        413 (Request too large for TPM)은 retry로 해결 안 됨 — 요청 자체가
        provider TPM 한도를 넘는 케이스. 명시적으로 surface한다.

        chat-khu 같은 프록시는 upstream 429를 400 BadRequest로 wrap해 보냄
        (본문에 "Error code: 429" / "rate limit" 명시). 이런 경우도 RateLimit로
        취급해 backoff retry.
        """
        client, model_name = self._client(model_id)
        for attempt in range(6):
            try:
                return client.chat.completions.create(model=model_name, messages=messages, **kwargs)
            except (openai.RateLimitError, openai.BadRequestError) as e:
                is_rate_limit = isinstance(e, openai.RateLimitError) or (
                    isinstance(e, openai.BadRequestError)
                    and ("429" in str(e) or "rate limit" in str(e).lower())
                )
                if not is_rate_limit:
                    raise
                if attempt == 5:
                    raise
                wait = 30 * (2 ** attempt)
                src = "proxy-wrapped 429" if isinstance(e, openai.BadRequestError) else "429"
                print(f"  RateLimit ({src}, attempt {attempt + 1}/6), {wait}s 대기 후 재시도...")
                time.sleep(wait)
            except openai.APIStatusError as e:
                if e.status_code == 413:
                    raise RuntimeError(
                        f"413 Request too large for {model_id} TPM 한도. "
                        f"rate limit 누적이 아니라 단일 요청 자체가 한도 초과 — retry 무용. "
                        f"shortlist 축소 또는 더 큰 TPM 모델 필요. 원본: {e}"
                    ) from e
                raise

    def min_interval(self, model_id: str) -> float:
        """rpm 제한이 있으면 호출 간 최소 대기 초를 반환. 없으면 0."""
        m = self._models.get(model_id, {})
        rpm = m.get("rpm")
        return (60.0 / rpm) if rpm else 0.0

    def model_ids(self, family: str | None = None) -> list[str]:
        return [
            m["model_id"]
            for m in self._models.values()
            if family is None or m.get("family") == family
        ]


_pool: ModelPool | None = None


def get_pool() -> ModelPool:
    global _pool
    if _pool is None:
        _pool = ModelPool()
    return _pool
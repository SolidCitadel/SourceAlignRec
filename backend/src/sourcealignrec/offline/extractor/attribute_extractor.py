"""AttributeExtractor 인터페이스 + LLM / BERT 구현체."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Protocol, runtime_checkable

import torch
import torch.nn as nn
from transformers import AutoConfig, AutoModel, AutoTokenizer

from sourcealignrec.core.model_pool import get_pool

ATTR_NAMES = ["grading_leniency", "assignment_load", "team_project", "attendance_strictness"]

ATTR_VALUES: dict[str, list[str]] = {
    "grading_leniency":      ["없음", "너그러움", "깐깐함"],
    "assignment_load":       ["없음", "많음", "적음"],
    "team_project":          ["없음", "있음"],
    "attendance_strictness": ["없음", "엄격함", "너그러움"],
}

ALL_ATTR_VALUES: dict[str, set[str]] = {k: set(v) - {"없음"} for k, v in ATTR_VALUES.items()}

MAX_LENGTH = 512
DEFAULT_ENCODER = "klue/roberta-large"
DEFAULT_BERT_MODEL_PATH = "models/attr_extractor/roberta_large"

_COMMON_RULES = """\
규칙:
- 근거가 명확하지 않으면 생략. 애매할 때는 생략이 우선.
- 목록에 없는 값 사용 금지.
- 완화 표현("많지 않음", "부담 적음", "비중 크지 않음" 등)이 있으면 극단값 추출 금지.
- 신호가 상충하거나 방향이 불명확하면 해당 속성 생략.
- 시점 변화가 언급될 경우 현재·최근 기준으로 추출.
- 중립·평균 판단은 추출하지 않음. 명확한 방향성(긍정/부정 극단)이 있을 때만 추출.
- 텍스트에 직접 언급이 없는 속성은 추출하지 않음. 전반적 분위기나 인상으로 유추하지 않음."""

_ATTR_LINES: dict[str, str] = {
    "grading_leniency":      "- grading_leniency      : 너그러움 | 깐깐함  (학점 관대함 — 극단만 추출)",
    "assignment_load":       "- assignment_load        : 많음 | 적음  (수업 외 제출 과제·숙제·레포트 양 — 극단만 추출)",
    "team_project":          "- team_project           : 있음  (팀 프로젝트 명시 언급 시에만)",
    "attendance_strictness": "- attendance_strictness  : 엄격함 | 너그러움  (출석 관리 엄격함 — 극단만 추출)",
}

_ATTR_NOTES: dict[str, str] = {
    "grading_leniency": "grading_leniency: 학점 분포·비율·등급 직접 언급 필수. 시험 난이도·교수 성격·분위기만으로는 추출 금지.",
    "assignment_load":  "assignment_load: 수업 내 퀴즈·발표·실습 제외. 시험 준비·공부 강도·족보 언급은 과제 신호 아님.",
    "team_project":     "team_project: '있음'만 유효. 팀 프로젝트 명시 언급 시에만.",
}


def _build_prompt(attrs: list[str]) -> str:
    """target_attrs 기반 동적 프롬프트 생성. LLM 호출 1회용."""
    attr_defs = "\n".join(_ATTR_LINES[a] for a in attrs if a in _ATTR_LINES)
    notes = [_ATTR_NOTES[a] for a in attrs if a in _ATTR_NOTES]
    example_parts = [
        '"team_project": "있음"' if a == "team_project" else f'"{a}": "..."'
        for a in attrs
    ]
    out_example = "{" + ", ".join(example_parts) + "}"

    parts = [
        "강의평에서 다음 속성을 추출하세요.\n",
        "추출할 속성:",
        attr_defs,
        f"\n출력 형식(JSON only, 해당 없는 속성은 생략):\n{out_example}",
        "근거 없으면: {}",
    ]
    if notes:
        parts.append("\n주의:\n" + "\n".join(f"- {n}" for n in notes))
    parts.append(f"\n{_COMMON_RULES}")
    return "\n".join(parts)


@runtime_checkable
class AttributeExtractor(Protocol):
    """리뷰 텍스트 → attribute 값 추출 인터페이스."""

    def extract(self, text: str, target_attrs: list[str] | None = None) -> dict[str, str]:
        """단건 추출. target_attrs 지정 시 해당 속성만 추출. 반환값: {attr_name: attr_value}."""
        ...

    def extract_batch(self, texts: list[str], target_attrs: list[str] | None = None) -> list[dict[str, str]]:
        """배치 추출."""
        ...


class LLMAttributeExtractor:
    """LLM zero-shot AttributeExtractor. 리뷰당 동적 프롬프트로 LLM 1회 호출."""

    def __init__(self, model_id: str, delay: float = 1.0):
        self._delay = delay
        self.model_id = model_id

    def extract(self, text: str, target_attrs: list[str] | None = None) -> dict[str, str]:
        """target_attrs로 동적 프롬프트 구성 후 LLM 1회 호출."""
        attrs = sorted(target_attrs) if target_attrs else sorted(ATTR_NAMES)
        if not attrs:
            return {}
        return self._call_llm(text, _build_prompt(attrs))

    def _call_llm(self, text: str, system_prompt: str) -> dict[str, str]:
        response = get_pool().chat(
            self.model_id,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            temperature=0.0,
        )
        content = (response.choices[0].message.content or "").strip()
        content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL).strip()
        if content.startswith("```"):
            content = content.split("```", 2)[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.rsplit("```", 1)[0].strip()
        s = content.find("{")
        if s < 0:
            return {}
        try:
            data, _ = json.JSONDecoder().raw_decode(content[s:])
        except json.JSONDecodeError:
            return {}
        return {k: v for k, v in data.items() if k in ALL_ATTR_VALUES and v in ALL_ATTR_VALUES[k]}

    def extract_batch(self, texts: list[str], target_attrs: list[str] | None = None) -> list[dict[str, str]]:
        results = []
        for i, text in enumerate(texts):
            try:
                results.append(self.extract(text, target_attrs))
            except Exception:
                results.append({})
            if self._delay > 0 and i < len(texts) - 1:
                time.sleep(self._delay)
        return results


class BERTMultiHeadAttributeModel(nn.Module):
    """BERT encoder + attribute별 classification head. train_attr_extractor.py에서 학습."""

    def __init__(self, encoder_name: str = DEFAULT_ENCODER):
        super().__init__()
        config = AutoConfig.from_pretrained(encoder_name)
        if hasattr(config, "reference_compile"):
            config.reference_compile = False  # ModernBERT: Triton not available on Windows
        self.encoder = AutoModel.from_pretrained(encoder_name, config=config)
        hidden = self.encoder.config.hidden_size
        self.heads = nn.ModuleList([
            nn.Linear(hidden, len(ATTR_VALUES[attr]))
            for attr in ATTR_NAMES
        ])

    def forward(self, **inputs) -> list[torch.Tensor]:
        # ModernBERT 계열은 token_type_ids 미지원
        accepted = set(self.encoder.forward.__code__.co_varnames)
        inputs = {k: v for k, v in inputs.items() if k in accepted}
        cls = self.encoder(**inputs).last_hidden_state[:, 0, :]
        return [head(cls) for head in self.heads]


class BERTAttributeExtractor:
    """Fine-tuned BERT multi-head AttributeExtractor."""

    def __init__(
        self,
        model_path: str = DEFAULT_BERT_MODEL_PATH,
        encoder_name: str = DEFAULT_ENCODER,
        batch_size: int = 32,
    ):
        path = Path(model_path)
        if not path.exists():
            raise FileNotFoundError(
                f"모델 경로 없음: {path}\n"
                "uv run sar-train-attr 로 먼저 학습하세요."
            )
        self._tokenizer = AutoTokenizer.from_pretrained(encoder_name)
        self._model = BERTMultiHeadAttributeModel(encoder_name)
        self._model.load_state_dict(
            torch.load(path / "model.pt", map_location="cpu", weights_only=True)
        )
        self._model.eval()
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._model.to(self._device)
        self._batch_size = batch_size
        self.model_path = model_path

    def extract(self, text: str, target_attrs: list[str] | None = None) -> dict[str, str]:
        return self.extract_batch([text], target_attrs)[0]

    def extract_batch(self, texts: list[str], target_attrs: list[str] | None = None) -> list[dict[str, str]]:
        active_attrs = target_attrs if target_attrs is not None else ATTR_NAMES
        results: list[dict[str, str]] = [{} for _ in texts]
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i:i + self._batch_size]
            enc = self._tokenizer(
                batch, truncation=True, padding=True,
                max_length=MAX_LENGTH, return_tensors="pt",
            )
            enc = {k: v.to(self._device) for k, v in enc.items()}
            with torch.no_grad():
                logits_list = self._model(**enc)
            for b_idx in range(len(batch)):
                row: dict[str, str] = {}
                for attr_idx, attr_name in enumerate(ATTR_NAMES):
                    if attr_name not in active_attrs:
                        continue
                    pred = logits_list[attr_idx][b_idx].argmax().item()
                    value = ATTR_VALUES[attr_name][pred]
                    if value != "없음":
                        row[attr_name] = value
                results[i + b_idx] = row
        return results

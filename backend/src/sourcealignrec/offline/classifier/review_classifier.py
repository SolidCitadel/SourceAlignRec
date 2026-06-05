"""ReviewClassifier 인터페이스 + LLM / BERT 구현체."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Protocol, runtime_checkable

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from sourcealignrec.core.model_pool import get_pool
from sourcealignrec.offline.classifier.train_bert import LABELS, MAX_LENGTH

_SYSTEM_PROMPT = """\
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
- 확신 없으면 false (과추출보다 과소추출 선호)"""


@runtime_checkable
class ReviewClassifier(Protocol):
    """리뷰 텍스트 → 타입별 p-score 인터페이스."""

    def classify(self, text: str) -> dict[str, float]:
        """단건 추론. 반환값: {type: p-score (0~1)}"""
        ...

    def classify_batch(self, texts: list[str]) -> list[dict[str, float]]:
        """배치 추론."""
        ...


class LLMReviewClassifier:
    """LLM zero-shot ReviewClassifier. p-score는 0.0 또는 1.0."""

    def __init__(self, model_id: str, delay: float = 2.0):
        self._delay = delay
        self.model_id = model_id

    def classify(self, text: str) -> dict[str, float]:
        result = self._call_llm(text)
        return {t: 1.0 if result.get(t, False) else 0.0 for t in LABELS}

    def classify_batch(self, texts: list[str]) -> list[dict[str, float]]:
        results = []
        for i, text in enumerate(texts):
            try:
                results.append(self.classify(text))
            except Exception:
                results.append({t: 0.0 for t in LABELS})
            if self._delay > 0 and i < len(texts) - 1:
                time.sleep(self._delay)
        return results

    def _call_llm(self, text: str) -> dict[str, bool]:
        response = get_pool().chat(
            self.model_id,
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.0,
        )
        import re as _re
        content = (response.choices[0].message.content or "").strip()
        content = _re.sub(r"<think>.*?</think>", "", content, flags=_re.DOTALL).strip()
        if content.startswith("```"):
            content = content.split("```", 2)[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.rsplit("```", 1)[0]
        try:
            data = json.loads(content.strip())
        except json.JSONDecodeError:
            s, e = content.find("{"), content.rfind("}")
            data = json.loads(content[s:e + 1])
        return {t: bool(data.get(t, False)) for t in LABELS}


class BERTReviewClassifier:
    """BERT fine-tuned ReviewClassifier."""

    def __init__(self, model_path: str, batch_size: int = 32):
        path = Path(model_path)
        if not path.exists():
            raise FileNotFoundError(f"모델 경로 없음: {path}")
        self._tokenizer = AutoTokenizer.from_pretrained(str(path))
        self._model = AutoModelForSequenceClassification.from_pretrained(str(path))
        self._model.eval()
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._model.to(self._device)
        self._batch_size = batch_size
        self.model_path = model_path

    def classify(self, text: str) -> dict[str, float]:
        return self.classify_batch([text])[0]

    def classify_batch(self, texts: list[str]) -> list[dict[str, float]]:
        results = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i:i + self._batch_size]
            enc = self._tokenizer(
                batch, truncation=True, padding=True,
                max_length=MAX_LENGTH, return_tensors="pt",
            )
            enc = {k: v.to(self._device) for k, v in enc.items()}
            with torch.no_grad():
                logits = self._model(**enc).logits
            scores = torch.sigmoid(logits).cpu().numpy()
            for row in scores:
                results.append(dict(zip(LABELS, row.tolist())))
        return results

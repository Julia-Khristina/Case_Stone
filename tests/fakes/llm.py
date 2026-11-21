"""Cliente LLM falso com a mesma interface do LLMClient (sem rede). Versão enxuta do fake do Case Suno.

Respostas programadas por schema em fila: cada chamada consome o próximo item; o último se repete.
"""
from __future__ import annotations

import copy
from typing import Any

from src.shared.llm_client import LLMCallResult, LLMConfigError


class FakeLLMClient:
    mode = "simulated"

    def __init__(self, responses: dict[str, list[Any]] | None = None, judge_model: str = "judge-model-x",
                 generation_model: str = "gen-model-y", tokens_per_call: int = 1000) -> None:
        self.responses = {k: list(v) for k, v in (responses or {}).items()}
        self.default_model = generation_model
        self.judge_model = judge_model
        self.tokens_per_call = tokens_per_call
        self.prompts: list[dict[str, Any]] = []

    def model_for(self, role: str, model_id: str | None = None) -> str:
        if model_id:
            return model_id
        return self.judge_model if role == "judge" else self.default_model

    def assert_distinct_models(self) -> None:
        if self.judge_model == self.default_model:
            raise LLMConfigError("juiz igual ao gerador")

    def generate(self, prompt: str, schema_name: str = "text", model_id: str | None = None, temperature=None,
                 cache_parts=None, pydantic_schema=None, system: str | None = None, role: str = "generation"
                 ) -> LLMCallResult:
        queue = self.responses.get(schema_name) or [{}]
        response = queue.pop(0) if len(queue) > 1 else queue[0]
        self.prompts.append({"role": role, "schema": schema_name, "prompt": prompt, "system": system})
        if isinstance(response, Exception):
            raise response
        return LLMCallResult(response=copy.deepcopy(response), usage={"total_tokens": self.tokens_per_call},
                             latency_seconds=0.01, model_id=self.model_for(role, model_id), mode="fake", role=role)

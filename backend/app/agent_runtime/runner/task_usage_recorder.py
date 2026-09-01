"""Task-level LLM usage normalization and persistence."""

from typing import Any

from app.agent_runtime.usage_cost import (
    calculate_llm_call_cost,
    extract_cache_read_tokens,
    extract_cache_write_tokens,
)
from app.storage.database import create_session
from app.storage.services import task_service


class TaskUsageRecorder:
    """Persist task usage and build the corresponding client event payloads."""

    def __init__(
        self,
        *,
        session_id: str,
        task_id: str,
        model_config: dict[str, Any],
    ) -> None:
        self.session_id = session_id
        self.task_id = task_id
        self.model_config = model_config

    def normalize_usage_event(self, event_data: dict) -> dict:
        usage = event_data.get("usage") if isinstance(event_data, dict) else None
        usage_dict = usage if isinstance(usage, dict) else {}
        token_input = int(
            usage_dict.get("input_tokens")
            or usage_dict.get("prompt_tokens")
            or usage_dict.get("token_input")
            or 0
        )
        token_output = int(
            usage_dict.get("output_tokens")
            or usage_dict.get("completion_tokens")
            or usage_dict.get("token_output")
            or 0
        )
        token_cache = extract_cache_read_tokens(usage_dict)
        if token_cache == 0:
            token_cache = max(int(usage_dict.get("token_cache") or 0), 0)
        token_cache_write = extract_cache_write_tokens(usage_dict)
        if token_cache_write == 0:
            token_cache_write = max(int(usage_dict.get("token_cache_write") or 0), 0)
        call_cost = calculate_llm_call_cost(
            token_input=token_input,
            token_output=token_output,
            token_cache=token_cache,
            token_cache_write=token_cache_write,
            input_price=float(self.model_config.get("input_price") or 0),
            output_price=float(self.model_config.get("output_price") or 0),
            cache_read_price=float(self.model_config.get("cache_read_price") or 0),
            cache_write_price=float(self.model_config.get("cache_write_price") or 0),
        )
        return {
            "session_id": self.session_id,
            "token_input": token_input,
            "token_output": token_output,
            "token_cache": token_cache,
            "cost": call_cost,
            "context_input_tokens": token_input,
            "context_length": int(self.model_config.get("max_context_tokens", 0)),
            **(
                {"usage_kind": event_data["usage_kind"]}
                if isinstance(event_data.get("usage_kind"), str) and event_data.get("usage_kind")
                else {}
            ),
        }

    async def persist_task_usage_and_build_payload(
        self,
        event_data: dict,
    ) -> tuple[dict, dict]:
        normalized = self.normalize_usage_event(event_data)
        session = await create_session()
        try:
            task = await task_service.add_task_token_usage(
                session,
                task_id=self.task_id,
                token_input=int(normalized["token_input"]),
                token_output=int(normalized["token_output"]),
                token_cache=int(normalized["token_cache"]),
                cost=float(normalized["cost"]),
            )
            await session.commit()
        finally:
            await session.close()

        usage_payload = {
            "session_id": self.session_id,
            "token_input": int(task.token_input),
            "token_output": int(task.token_output),
            "token_cache": int(task.token_cache),
            "cost": float(task.cost),
            "context_input_tokens": int(task.context_input_tokens),
            "context_length": int(normalized["context_length"]),
        }
        delta_payload = {
            "session_id": self.session_id,
            "task_id": self.task_id,
            "token_input": int(normalized["token_input"]),
            "token_output": int(normalized["token_output"]),
            "token_cache": int(normalized["token_cache"]),
            "cost": float(normalized["cost"]),
        }
        usage_kind = normalized.get("usage_kind")
        if isinstance(usage_kind, str) and usage_kind:
            usage_payload["usage_kind"] = usage_kind
            delta_payload["usage_kind"] = usage_kind
        return usage_payload, delta_payload

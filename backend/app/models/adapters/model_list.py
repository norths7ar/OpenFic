"""Validate real upstream model lists before using absence as evidence."""

from typing import Any


def normalize_model_list(models: Any, *, id_field: str = "id") -> list[dict[str, Any]]:
    if not isinstance(models, list):
        raise ValueError("模型目录响应中的模型列表格式无效")
    normalized = []
    for model in models:
        if not isinstance(model, dict):
            raise ValueError("模型目录响应包含无效模型记录")
        model_id = model.get(id_field)
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("模型目录响应包含无效模型 ID")
        name = model.get("name") if id_field == "id" else model.get("displayName")
        normalized.append(
            {**model, "id": model_id, "name": name if isinstance(name, str) and name else model_id}
        )
    return normalized


def parse_model_list(
    payload: Any, *, field: str = "data", id_field: str = "id"
) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or field not in payload:
        raise ValueError("模型目录响应缺少模型列表")
    if payload.get("error"):
        raise ValueError("模型目录响应包含上游错误")
    # Never treat a partial directory as proof that a configured model disappeared.
    if payload.get("has_more") or payload.get("nextPageToken"):
        raise ValueError("模型目录响应尚有未读取的分页，无法确认完整目录")
    return normalize_model_list(payload[field], id_field=id_field)

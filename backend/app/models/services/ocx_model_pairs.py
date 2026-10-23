"""Retire no user parameters when an OCX directory gains a base/Fast pair."""

from collections import defaultdict
from collections.abc import Collection

from app.models.entities.model import Model


def paired_records(
    models: list[Model],
    raw_directory: Collection[str] | None = None,
) -> dict[str, list[Model]]:
    """Group only exact terminal --fast pairs; optionally require both live IDs."""
    raw_ids = {model.model_id for model in models if model.task_type == "llm"}
    base_ids = {
        raw.removesuffix("--fast")
        for raw in raw_ids
        if raw.endswith("--fast")
        and (raw_directory is not None or raw.removesuffix("--fast") in raw_ids)
    }
    if raw_directory is not None:
        base_ids = {
            base for base in base_ids if base in raw_directory and base + "--fast" in raw_directory
        }
    grouped: dict[str, list[Model]] = defaultdict(list)
    for model in models:
        if model.task_type != "llm":
            continue
        # An exact base ID wins over interpreting its own suffix recursively.
        base = (
            model.model_id if model.model_id in base_ids else model.model_id.removesuffix("--fast")
        )
        if base in base_ids:
            grouped[base].append(model)
    return dict(grouped)


def require_unambiguous_pairs(groups: dict[str, list[Model]]) -> None:
    for base, models in groups.items():
        if len(models) > 1:
            names = "、".join(model.name for model in models)
            raise ValueError(
                f"OCX 模型 {base} 同时保存了多条配置（{names}）。请先手动保留一个配置，再启用 OCX 适配或同步；不会自动合并参数。"
            )

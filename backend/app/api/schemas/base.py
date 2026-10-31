"""API models describe serialized defaults as present in response contracts."""

from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    # Validation schemas still allow omitted defaulted request fields. Serialization
    # schemas describe the actual response, where those fields are always emitted.
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

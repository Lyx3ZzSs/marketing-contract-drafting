import json
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DemoTaskInput(BaseModel):
    document: dict[str, Any]
    simulate_failure: bool = False

    @field_validator("document")
    @classmethod
    def validate_document(cls, value: dict[str, Any]) -> dict[str, Any]:
        if value.get("type") != "doc":
            raise ValueError("document 必须是 Tiptap doc JSON")
        if len(json.dumps(value, ensure_ascii=False).encode()) > 100_000:
            raise ValueError("示例文档不能超过 100 KB")
        return value


class TaskView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class TaskCreated(BaseModel):
    id: uuid.UUID
    status: str = Field(default="queued")

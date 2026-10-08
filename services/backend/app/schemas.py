from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Credentials(Strict):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=128)


class TaskInput(Strict):
    title: str = Field(min_length=1, max_length=512)
    course: str = Field(default="", max_length=512)
    description: str = Field(default="", max_length=10000)
    deadline: AwareDatetime | None = None
    estimated_duration: int = Field(default=60, ge=1, le=20160)
    remaining_duration: int | None = Field(default=None, ge=0, le=20160)
    priority: int = Field(default=5, ge=1, le=10)
    splittable: bool = True
    deadline_locked: bool = False
    duration_locked: bool = False


class EventInput(Strict):
    title: str = Field(min_length=1, max_length=512)
    start_at: AwareDatetime
    end_at: AwareDatetime
    event_type: Literal["course", "meeting", "exam", "personal"] = "course"

    @model_validator(mode="after")
    def interval(self):
        if self.end_at <= self.start_at:
            raise ValueError("结束时间必须晚于开始时间")
        return self


class IngestInput(Strict):
    platform: Literal["manual", "wechat", "canvas"] = "manual"
    source_type: Literal["message", "notification", "assignment", "announcement"] = "message"
    external_id: str | None = Field(default=None, max_length=512)
    channel_name: str = Field(default="", max_length=512)
    title: str = Field(default="", max_length=512)
    content: str = Field(min_length=1, max_length=20000)
    structured_data: dict = Field(default_factory=dict)
    source_updated_at: AwareDatetime | None = None


class TaskData(Strict):
    title: str | None = Field(default=None, min_length=1, max_length=512)
    course: str | None = Field(default=None, max_length=512)
    deadline: AwareDatetime | None = None
    estimated_duration_minutes: int | None = Field(default=None, ge=1, le=20160)
    priority: int | None = Field(default=None, ge=1, le=10)
    splittable: bool | None = None


class AIAction(Strict):
    action: Literal["CREATE_TASK", "UPDATE_TASK", "CANCEL_TASK", "CREATE_EVENT", "UPDATE_EVENT", "CANCEL_EVENT", "IGNORE"]
    confidence: float = Field(ge=0, le=1)
    target_id: str | None = None
    task: TaskData | None = None
    event: EventInput | None = None
    reason: str = Field(default="", max_length=2000)
    requires_confirmation: bool = False


class Review(Strict):
    accept: bool
    decision: AIAction | None = None


class CanvasInput(Strict):
    base_url: str = Field(max_length=2048)
    access_token: str = Field(min_length=1, max_length=4096)

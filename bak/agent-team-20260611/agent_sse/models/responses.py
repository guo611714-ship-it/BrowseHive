from pydantic import BaseModel, Field
from typing import List, Optional, Any

class ChatResponse(BaseModel):
    ok: bool
    response: Optional[str] = None
    error: Optional[str] = None
    mode: Optional[str] = None
    timestamp: Optional[str] = None

class ToolResponse(BaseModel):
    ok: bool
    tool: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[str] = None


class TaskResult(BaseModel):
    task_id: str
    status: str  # "success" | "failed" | "timeout" | "conflict"
    files_changed: List[str] = Field(default_factory=list)
    tests_passed: Optional[bool] = None
    output: str = ""
    error: Optional[str] = None
    duration_ms: int = 0


class ParallelResponse(BaseModel):
    ok: bool
    results: List[TaskResult] = Field(default_factory=list)
    conflicts: List[str] = Field(default_factory=list)
    merged: bool = False
    total_duration_ms: int = 0
    error: Optional[str] = None

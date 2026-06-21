from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
import re

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    mode: Optional[str] = None
    parallel: Optional[bool] = Field(default=None, description="启用并行子代理执行")
    max_concurrent: Optional[int] = Field(default=5, ge=1, le=10, description="最大并发数")

    @field_validator("message")
    @classmethod
    def sanitize_message(cls, v: str) -> str:
        """Strip control characters and normalize whitespace."""
        v = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", v)
        return v.strip()

class ToolRequest(BaseModel):
    tool: str = Field(..., min_length=1, max_length=100)
    args: dict = Field(default_factory=dict)


class ParallelTaskRequest(BaseModel):
    id: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=2000)
    files: List[str] = Field(..., min_length=1)
    constraints: List[str] = Field(default_factory=list)
    agent_type: str = Field(default="coding", pattern="^(coding|testing|research)$")


class ParallelConstraints(BaseModel):
    max_concurrent: int = Field(default=5, ge=1, le=10)
    timeout_per_task: int = Field(default=120, ge=10, le=600)
    test_after_each: bool = True
    merge_strategy: str = Field(default="file-level", pattern="^(file-level|worktree)$")
    dry_run: bool = False
    rollback_on_failure: bool = True
    worktree_pool: bool = True
    cache_dependencies: bool = True
    parallel_test: bool = True


class ParallelRequest(BaseModel):
    tasks: List[ParallelTaskRequest] = Field(..., min_length=1, max_length=10)
    constraints: ParallelConstraints = Field(default_factory=ParallelConstraints)

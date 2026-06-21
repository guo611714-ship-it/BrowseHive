from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    app_name: str = "Agent Team SSE"
    app_version: str = "2.0.0"
    debug: bool = False
    llm_provider: str = "nvidia"
    llm_model: str = "stepfun-ai/step-3.7-flash"
    llm_api_key: Optional[str] = None
    max_concurrent_agents: int = 10
    sse_heartbeat_interval: int = 15
    sse_total_timeout: int = 300
    sse_event_timeout: int = 30

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

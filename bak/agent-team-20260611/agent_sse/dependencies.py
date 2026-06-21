"""FastAPI dependencies for agent_sse -- wraps agent.loop.AgentLoop"""

import logging
from pathlib import Path
from agent.loop import AgentLoop

logger = logging.getLogger(__name__)

_agent_loop: AgentLoop | None = None


async def init_agent_loop():
    global _agent_loop
    try:
        # 使用项目根目录，不依赖进程 CWD
        project_root = Path(__file__).resolve().parent.parent
        _agent_loop = AgentLoop(project_root)
        logger.info(f"AgentLoop initialized, workspace: {project_root}")
    except Exception as e:
        logger.error(f"Failed to initialize AgentLoop: {e}")
        _agent_loop = None
        raise


async def shutdown_agent_loop():
    global _agent_loop
    if _agent_loop:
        logger.info("AgentLoop shutdown: clearing reference")
        if hasattr(_agent_loop, 'close'):
            await _agent_loop.close()
        _agent_loop = None


def get_agent_loop() -> AgentLoop | None:
    return _agent_loop

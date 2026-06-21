"""Hermes 能力 API 路由"""

import time
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
from agent_sse.utils.hermes_metrics import hermes_metrics

router = APIRouter(prefix="/api/hermes", tags=["hermes"])

# Hermes 集成实例（延迟初始化）
_hermes = None


def get_hermes():
    """获取 Hermes 集成实例"""
    global _hermes
    if _hermes is None:
        import sys
        from pathlib import Path
        # 添加 agent 模块路径
        agent_path = Path(__file__).parent.parent.parent / "agent-team-dashboard" / "agent-team-dashboard" / "dist" / "win-unpacked" / "resources"
        agent_path_str = str(agent_path)
        if agent_path_str not in sys.path:
            sys.path.insert(0, agent_path_str)
        # 动态导入
        import importlib
        spec = importlib.util.spec_from_file_location(
            "hermes_integration",
            agent_path / "agent" / "hermes_integration.py"
        )
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _hermes = module.hermes
        else:
            raise ImportError("无法加载 hermes_integration 模块")
    return _hermes


# ── 记忆系统 ──

class MemorySaveRequest(BaseModel):
    key: str
    value: str
    category: str = "general"


@router.get("/memory/status")
async def memory_status():
    """获取记忆系统状态"""
    hermes = get_hermes()
    return hermes.memory.get_status()


@router.get("/memory/search")
async def memory_search(query: str, limit: int = 10):
    """搜索记忆"""
    hermes = get_hermes()
    return hermes.memory.search(query, limit)


@router.post("/memory/save")
async def memory_save(request: MemorySaveRequest):
    """保存记忆"""
    hermes = get_hermes()
    success = hermes.memory.save(request.key, request.value, request.category)
    if success:
        return {"status": "ok", "message": "记忆保存成功"}
    else:
        raise HTTPException(status_code=500, detail="记忆保存失败")


# ── Cron 调度 ──

class CronCreateRequest(BaseModel):
    schedule: str
    prompt: str
    name: Optional[str] = None
    deliver: Optional[List[str]] = None
    skills: Optional[List[str]] = None


@router.get("/cron/status")
async def cron_status():
    """获取 Cron 系统状态"""
    hermes = get_hermes()
    return hermes.cron.get_status()


@router.get("/cron/list")
async def cron_list(include_disabled: bool = False):
    """列出所有定时任务"""
    hermes = get_hermes()
    return hermes.cron.list_jobs(include_disabled)


@router.post("/cron/create")
async def cron_create(request: CronCreateRequest):
    """创建定时任务"""
    hermes = get_hermes()
    try:
        result = hermes.cron.create_job(
            prompt=request.prompt,
            schedule=request.schedule,
            name=request.name,
            deliver=request.deliver,
            skills=request.skills
        )
        return {"status": "ok", "job": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/cron/pause/{job_id}")
async def cron_pause(job_id: str):
    """暂停任务"""
    hermes = get_hermes()
    success = hermes.cron.pause_job(job_id)
    if success:
        return {"status": "ok", "message": f"任务 {job_id} 已暂停"}
    else:
        raise HTTPException(status_code=404, detail="任务不存在")


@router.post("/cron/resume/{job_id}")
async def cron_resume(job_id: str):
    """恢复任务"""
    hermes = get_hermes()
    success = hermes.cron.resume_job(job_id)
    if success:
        return {"status": "ok", "message": f"任务 {job_id} 已恢复"}
    else:
        raise HTTPException(status_code=404, detail="任务不存在")


@router.delete("/cron/{job_id}")
async def cron_delete(job_id: str):
    """删除任务"""
    hermes = get_hermes()
    success = hermes.cron.remove_job(job_id)
    if success:
        return {"status": "ok", "message": f"任务 {job_id} 已删除"}
    else:
        raise HTTPException(status_code=404, detail="任务不存在")


@router.post("/cron/tick")
async def cron_tick():
    """执行一次调度检查"""
    hermes = get_hermes()
    hermes.cron.tick(verbose=False)
    return {"status": "ok", "message": "调度检查完成"}


# ── Skill 系统 ──

class SkillCreateRequest(BaseModel):
    name: str
    content: str


@router.get("/skills/list")
async def skills_list():
    """列出所有技能"""
    hermes = get_hermes()
    return hermes.skill.list_skills()


@router.get("/skills/{name}")
async def skills_get(name: str):
    """获取技能内容"""
    hermes = get_hermes()
    content = hermes.skill.load_skill(name)
    if content:
        return {"name": name, "content": content}
    else:
        raise HTTPException(status_code=404, detail="技能不存在")


@router.post("/skills/create")
async def skills_create(request: SkillCreateRequest):
    """创建技能"""
    hermes = get_hermes()
    success = hermes.skill.create_skill(request.name, request.content)
    if success:
        return {"status": "ok", "message": f"技能 {request.name} 创建成功"}
    else:
        raise HTTPException(status_code=500, detail="技能创建失败")


# ── 统一状态 ──

@router.get("/status")
async def hermes_status():
    """获取 Hermes 集成完整状态"""
    hermes = get_hermes()
    return hermes.get_status()


# ── 监控指标 ──

@router.get("/metrics")
async def hermes_metrics_endpoint():
    """获取 Hermes 监控指标"""
    return hermes_metrics.get_metrics()


@router.get("/metrics/prometheus")
async def hermes_prometheus_metrics():
    """获取 Prometheus 格式监控指标"""
    return PlainTextResponse(
        hermes_metrics.get_prometheus_metrics(),
        media_type="text/plain; version=0.0.4"
    )


@router.get("/health")
async def hermes_health():
    """Hermes 健康检查"""
    hermes = get_hermes()
    status = hermes.get_status()
    return {
        "status": "healthy",
        "memory": status["memory"]["provider"] or "built-in",
        "cron_jobs": status["cron"]["total_jobs"],
        "skills": status["skills"]["count"],
        "timestamp": time.time()
    }

from fastapi import APIRouter, HTTPException, Depends
from agent_sse.models.requests import ToolRequest
from agent_sse.models.responses import ToolResponse
from agent_sse.dependencies import get_agent_loop

router = APIRouter(prefix="/api/tools", tags=["tools"])

@router.get("")
async def list_tools(loop=Depends(get_agent_loop)):
    if not loop:
        return {"tools": []}
    # 返回完整工具定义（包含schema）
    from agent.tools.tool_registry import TOOL_REGISTRY
    tools = []
    for name, func in loop.tools.items():
        tool_info = {"name": name}
        # 从TOOL_REGISTRY获取schema
        if name in TOOL_REGISTRY:
            tool_info.update(TOOL_REGISTRY[name])
        tools.append(tool_info)

    # 合并 hermes 工具
    try:
        from agent_sse.adapters.hermes_adapter import hermes_adapter
        if hermes_adapter._initialized and hermes_adapter._registered_tools:
            for name in hermes_adapter._registered_tools.keys():
                if not any(t["name"] == name for t in tools):
                    tools.append({"name": name, "source": "hermes"})
    except Exception:
        pass

    return {"tools": tools}

@router.post("/execute", response_model=ToolResponse)
async def execute_tool(request: ToolRequest, loop=Depends(get_agent_loop)):
    """Execute a tool via AgentLoop's runner."""
    # 优先尝试 hermes 工具
    try:
        from agent_sse.adapters.hermes_adapter import hermes_adapter
        if hermes_adapter._initialized and hermes_adapter._registered_tools:
            if request.tool in hermes_adapter._registered_tools:
                result = await hermes_adapter._registered_tools[request.tool](**request.args)
                return ToolResponse(ok=True, tool=request.tool, result=result)
    except Exception as e:
        pass

    # 降级到 AgentLoop 工具
    if not loop:
        raise HTTPException(status_code=503, detail="AgentLoop not running")
    if request.tool not in loop.tools:
        raise HTTPException(status_code=404, detail=f"Tool '{request.tool}' not found")
    try:
        result = await loop.runner.execute_tool(request.tool, request.args)
        return ToolResponse(ok=True, tool=request.tool, result=result)
    except Exception as e:
        return ToolResponse(ok=False, tool=request.tool, error=str(e))

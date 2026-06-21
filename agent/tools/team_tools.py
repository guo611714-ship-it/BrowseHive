"""Team 管理工具"""

from typing import Dict, Any, List
from pathlib import Path

from ..team_store import TeamStore, MessageBus, get_team_store, get_message_bus


def spawn_teammate(name: str, role: str, agent_type: str,
                   description: str = "") -> Dict[str, Any]:
    """
    召入新队友

    Args:
        name: 队友名称（唯一）
        role: 角色名称
        agent_type: 子代理类型（决定工具白名单）
        description: 描述

    Returns:
        {"status": "success", "name": "...", "inbox": "..."}
    """
    store = get_team_store()
    success = store.add_teammate(name, role, agent_type, description)
    if not success:
        return {"error": f"Teammate '{name}' already exists"}

    # 创建独立的 thread 文件
    store.save_thread(name, [])

    return {
        "status": "spawned",
        "name": name,
        "role": role,
        "agent_type": agent_type,
        "inbox": f".team/inbox/{name}.jsonl"
    }


def list_teammates() -> List[Dict[str, Any]]:
    """列出所有队友状态"""
    store = get_team_store()
    teammates = store.teammates

    # 补充 Inbox 未读消息数
    for tm in teammates:
        inbox_file = Path(".team/inbox") / f"{tm['name']}.jsonl"
        if inbox_file.exists():
            with open(inbox_file, "r", encoding="utf-8") as f:
                tm["unread_count"] = sum(1 for _ in f)
        else:
            tm["unread_count"] = 0

    return teammates


def send_message(from_actor: str, to: str, message: str,
                 message_type: str = "message",
                 wake: bool = True) -> Dict[str, Any]:
    """
    发送消息给队友

    Args:
        from_actor: 发送者名称
        to: 接收者名称
        message: 消息内容
        message_type: 消息类型（message/broadcast/...）
        wake: 是否唤醒队友

    Returns:
        {"msg_id": "..."}
    """
    bus = get_message_bus()
    msg_id = bus.send(
        to=to,
        message={
            "from": from_actor,
            "type": message_type,
            "content": message
        },
        wake=wake
    )
    return {"msg_id": msg_id, "to": to}


def read_inbox(actor: str, clear: bool = True) -> List[Dict[str, Any]]:
    """
    读取 actor 的 Inbox

    Args:
        actor: 读取者名称
        clear: 读取后是否清空

    Returns:
        消息列表
    """
    bus = get_message_bus()
    messages = bus.read(actor, clear=clear)

    if clear:
        # 更新游标
        store = get_team_store()
        store.set_cursor(actor, store.get_cursor(actor) + len(messages))

    return messages


def broadcast(from_actor: str, to: List[str], message: str,
              wake: bool = True) -> Dict[str, Any]:
    """
    广播消息到多个队友

    Args:
        from_actor: 发送者
        to: 接收者列表
        message: 消息内容
        wake: 是否唤醒

    Returns:
        {"msg_ids": [...]}
    """
    bus = get_message_bus()
    msg_ids = bus.broadcast(
        to=to,
        message={
            "from": from_actor,
            "type": "broadcast",
            "content": message
        },
        wake=wake
    )
    return {"msg_ids": msg_ids, "count": len(msg_ids)}


def shutdown_teammate(name: str, from_actor: str = "lead") -> Dict[str, Any]:
    """
    关闭队友

    Args:
        name: 队友名称
        from_actor: 操作者

    Returns:
        {"status": "shutting_down"}
    """
    bus = get_message_bus()
    bus.send(
        to=name,
        message={
            "from": from_actor,
            "type": "shutdown_request"
        },
        wake=True
    )
    return {"status": "shutdown_requested", "name": name}

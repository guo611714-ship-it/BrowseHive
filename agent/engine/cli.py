"""Engine CLI — 引擎命令行入口

Phase 2: 支持 analyze / submit / status / cancel 命令

用法:
    python -m agent.engine.cli analyze --tasks '[...]'
    python -m agent.engine.cli submit --tasks '[...]'
    python -m agent.engine.cli status --manifest-id m-1-abc
    python -m agent.engine.cli cancel --manifest-id m-1-abc
    python -m agent.engine.cli serve  # 启动常驻服务
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path


def parse_tasks(json_str: str):
    """从 JSON 字符串解析任务列表"""
    from .manifest import FixTask, TaskPriority
    raw = json.loads(json_str)
    return [
        FixTask(
            task_id=t["task_id"],
            description=t["description"],
            files=t.get("files", []),
            agent_type=t.get("agent_type", "neiguan_yingzao"),
            priority=TaskPriority(t.get("priority", "normal")),
            context=t.get("context"),
            depends_on=t.get("depends_on", []),
            line_start=t.get("line_start"),
            line_end=t.get("line_end"),
        )
        for t in raw
    ]


async def cmd_analyze(args):
    """分析任务计划"""
    from .manifest import TaskManifest, SmartSharder
    from .predictor import ConflictPredictor

    tasks = parse_tasks(args.tasks)
    manifest = TaskManifest(tasks=tasks, strategy=args.strategy or "auto")

    predictor = ConflictPredictor()
    sharder = SmartSharder(predictor=predictor)

    analysis = predictor.analyze_manifest(manifest)
    shards = sharder.shard(manifest)

    result = {
        "manifest": manifest.summary(),
        "shards": [
            {"id": s.shard_id, "tasks": s.task_count,
             "files": list(s.files), "reason": s.reason}
            for s in shards
        ],
        "conflicts": analysis,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


async def cmd_submit(args):
    """提交任务"""
    from .manifest import TaskManifest
    from .grpc_service import EngineService

    tasks = parse_tasks(args.tasks)
    manifest = TaskManifest(tasks=tasks, strategy=args.strategy or "auto")

    service = EngineService()
    result = await service.submit_and_wait(manifest, timeout=args.timeout or 600)

    print(json.dumps(result, ensure_ascii=False, indent=2))


async def cmd_status(args):
    """查询状态"""
    from .service import EngineService

    service = EngineService()
    result = service.status(args.manifest_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


async def cmd_cancel(args):
    """取消任务"""
    from .service import EngineService

    service = EngineService()
    result = await service.cancel(args.manifest_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


async def cmd_serve(args):
    """启动常驻服务"""
    from .service import EngineService

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    history_path = Path(args.history or ".engine/history.json")
    service = EngineService(history_path=history_path)
    await service.start()

    print(f"Engine service started on {args.host}:{args.port} (history: {history_path})")
    print("Press Ctrl+C to stop")

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await service.stop()
        print("Engine service stopped")


def main():
    parser = argparse.ArgumentParser(description="Parallel Fix Engine CLI")
    sub = parser.add_subparsers(dest="command")

    # analyze
    p_analyze = sub.add_parser("analyze", help="分析任务计划")
    p_analyze.add_argument("--tasks", required=True, help="JSON 任务列表")
    p_analyze.add_argument("--strategy", choices=["auto", "parallel", "serial", "file"])

    # submit
    p_submit = sub.add_parser("submit", help="提交任务并等待完成")
    p_submit.add_argument("--tasks", required=True, help="JSON 任务列表")
    p_submit.add_argument("--strategy", choices=["auto", "parallel", "serial", "file"])
    p_submit.add_argument("--timeout", type=float, default=600)

    # status
    p_status = sub.add_parser("status", help="查询状态")
    p_status.add_argument("--manifest-id", required=True)

    # cancel
    p_cancel = sub.add_parser("cancel", help="取消任务")
    p_cancel.add_argument("--manifest-id", required=True)

    # serve
    p_serve = sub.add_parser("serve", help="启动常驻服务")
    p_serve.add_argument("--history", help="历史文件路径")
    p_serve.add_argument(
        "--host",
        default=os.environ.get("ENGINE_HOST", "localhost"),
        help="服务监听地址 (default: ENGINE_HOST env or localhost)",
    )
    p_serve.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("ENGINE_PORT", "8001")),
        help="服务监听端口 (default: ENGINE_PORT env or 8001)",
    )
    p_serve.add_argument(
        "--log-level",
        default=os.environ.get("ENGINE_LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="日志级别 (default: ENGINE_LOG_LEVEL env or INFO)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    cmd_map = {
        "analyze": cmd_analyze,
        "submit": cmd_submit,
        "status": cmd_status,
        "cancel": cmd_cancel,
        "serve": cmd_serve,
    }

    asyncio.run(cmd_map[args.command](args))


if __name__ == "__main__":
    main()

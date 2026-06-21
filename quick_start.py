#!/usr/bin/env python3
"""Agent Team 快速启动器（无交互模式）"""

import sys
import subprocess
from pathlib import Path

def quick_start():
    """快速启动 Agent Team"""

    workspace = Path.cwd()

    # 环境检查
    checks = [
        (".team/", "Team 配置目录"),
        ("templates/", "提示词模板"),
        ("memory/", "记忆存储"),
        ("model_config.json", "模型配置"),
        ("agent/", "核心代码"),
    ]

    missing = []
    for path, name in checks:
        if not Path(path).exists():
            missing.append(f"  - {name} ({path})")

    if missing:
        print("=" * 60)
        print("[ERROR] 缺失必要文件/目录:")
        for m in missing:
            print(m)
        print("\n请运行: python setup_team.py")
        print("=" * 60)
        return 1

    # 依赖检查
    try:
        import anthropic  # noqa
    except ImportError:
        print("[WARN] 未检测到 anthropic，正在安装依赖...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        try:
            import anthropic
        except ImportError:
            print("[ERROR] 依赖安装失败，请手动运行: pip install -r requirements.txt")
            return 1

    print("=" * 60)
    print("[OK] Agent Team 启动中...")
    print(f"  工作区: {workspace}")
    print("=" * 60)

    # 启动主程序
    from agent.loop import AgentLoop
    loop = AgentLoop(workspace)

    try:
        loop.run_sync()  # 使用同步运行方法
    except KeyboardInterrupt:
        print("\n[INFO] 再见！")
        return 0
    except Exception as e:
        print(f"[ERROR] 启动失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(quick_start())

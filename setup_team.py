"""Agent Team 快速配置脚本"""

import json
from pathlib import Path

def setup_team():
    """配置 Agent Team 目录结构"""

    base_dir = Path.cwd()

    print("[*] 开始配置 Agent Team...\n")

    # 1. 确保 .team 目录
    team_dir = base_dir / ".team"
    team_dir.mkdir(exist_ok=True)

    inbox_dir = team_dir / "inbox"
    inbox_dir.mkdir(exist_ok=True)

    threads_dir = team_dir / "threads"
    threads_dir.mkdir(exist_ok=True)

    checkpoints_dir = team_dir / "checkpoints"
    checkpoints_dir.mkdir(exist_ok=True)

    cursors_dir = team_dir / "cursors"
    cursors_dir.mkdir(exist_ok=True)

    print("[OK] 目录结构创建完成")

    # 2. 检查并创建 config.json
    config_file = team_dir / "config.json"
    if not config_file.exists():
        config = {
            "version": "1.0",
            "teammates": [
                {
                    "name": "lead",
                    "role": "团队领导",
                    "agent_type": "general",
                    "status": "idle",
                    "description": "大内总管，统筹全局",
                    "max_turns": 50,
                    "model_role": "main"
                },
                {
                    "name": "coder",
                    "role": "工程师",
                    "agent_type": "neiguan_yingzao",
                    "status": "offline",
                    "description": "内官监营造，可读写、执行命令",
                    "max_turns": 100,
                    "model_role": "main"
                },
                {
                    "name": "researcher",
                    "role": "研究员",
                    "agent_type": "dongchang_tanshi",
                    "status": "offline",
                    "description": "东厂探事，只读查访",
                    "max_turns": 30,
                    "model_role": "secondary"
                },
                {
                    "name": "reviewer",
                    "role": "审查员",
                    "agent_type": "shangbao_dianbu",
                    "status": "offline",
                    "description": "尚宝监典簿，只读核验",
                    "max_turns": 20,
                    "model_role": "secondary"
                },
                {
                    "name": "reader",
                    "role": "阅读员",
                    "agent_type": "sili_suitang",
                    "status": "offline",
                    "description": "司礼监随堂，只读文书",
                    "max_turns": 30,
                    "model_role": "secondary"
                }
            ],
            "created_at": "2025-05-25T00:00:00",
            "description": "Agent Team 配置"
        }

        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        print("[OK] 创建 .team/config.json")
    else:
        print("[SKIP] .team/config.json 已存在，跳过")

    # 3. 创建 inbox 文件
    for tm in ["lead", "coder", "researcher", "reviewer", "reader"]:
        inbox_file = inbox_dir / f"{tm}.jsonl"
        if not inbox_file.exists():
            inbox_file.touch()
            print(f"[OK] 创建 {inbox_file}")

    # 4. 检查子代理模板
    templates_dir = base_dir / "templates" / "subagents"
    if templates_dir.exists():
        template_files = list(templates_dir.glob("*.md"))
        print(f"[OK] 子代理模板: {len(template_files)} 个")
    else:
        print("[WARN] templates/subagents/ 不存在，请参考文档创建")

    # 5. 检查 memory 目录
    memory_dir = base_dir / "memory"
    if not memory_dir.exists():
        memory_dir.mkdir()
        print("[OK] 创建 memory/ 目录")

    required_mem_files = ["MEMORY.md", "USER.md", "history.jsonl", "tokens.jsonl"]
    for f in required_mem_files:
        mf = memory_dir / f
        if not mf.exists():
            if f.endswith(".md"):
                mf.write_text(f"# {f}\n\n自动生成的模板。\n", encoding="utf-8")
            else:
                mf.touch()
        print(f"[OK] memory/{f}")

    print("\n" + "="*60)
    print("[SUCCESS] Agent Team 配置完成！")
    print("="*60)
    print("\n下一步：")
    print("1. 编辑 .team/config.json 自定义队友")
    print("2. 编辑 templates/subagents/*.md 完善子代理身份")
    print("3. 创建 model_config.json 并填入 API Key")
    print("4. 运行: python agent.py")
    print("\n查看帮助: python agent.py (启动后输入 /help)")

if __name__ == "__main__":
    setup_team()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Knowledge Base Manager - Windows compatible AI知识库管理器

向后兼容入口 - 导入kb_core中的KnowledgeBaseManager。
CLI argparse和main()保持不变，所有子模块已拆分到:
  kb_utils.py   - 通用工具函数
  kb_storage.py - 存储抽象层
  kb_llm.py     - LLM API调用
  kb_commands.py - CLI命令实现
  kb_core.py    - 核心类（组合以上模块）
"""

import os
import sys
import io
import argparse
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Windows UTF-8 编码支持 — 仅在 main() 中调用
def _setup_windows_encoding():
    """强制Windows控制台使用UTF-8编码"""
    if sys.platform == 'win32':
        os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
        try:
            os.system('chcp.com 65001 >nul 2>&1')
        except Exception as e:
            logger.debug("chcp failed: %s", e)
        try:
            import io
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
        except Exception as e:
            logger.debug("TextIOWrapper failed, using codecs: %s", e)
            import codecs
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'ignore')
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'ignore')

from i18n import t, get_i18n
from agent.kb import KnowledgeBaseManager


# ================================================================== #
#  Interactive Menu (Task 2)
# ================================================================== #

MENU_ITEMS = [
    ("1", "import",        "导入文档"),
    ("2", "query",         "搜索知识库"),
    ("3", "list",          "查看文档列表"),
    ("4", "batch-import",  "批量导入"),
    ("5", "sync",          "同步知识库"),
    ("6", "backup",        "备份知识库"),
    ("7", "status",        "查看状态"),
    ("8", "config",        "系统设置"),
    ("9", None,            "退出"),
]

# Also accept command names directly as input
COMMAND_NAME_MAP = {item[1]: item[1] for item in MENU_ITEMS if item[1]}


def show_interactive_menu() -> str | None:
    """Display interactive command menu. Returns the command string or None to quit."""
    print()
    print("    +--------------------------------------+")
    print("    |       AI知识库管理 v2.0              |")
    print("    +--------------------------------------+")
    for num, cmd, label in MENU_ITEMS:
        cmd_tag = f"[{cmd}]" if cmd else ""
        print(f"    |  {num}. {label:<18s} {cmd_tag:<16s} |")
    print("    +--------------------------------------+")
    print()

    raw = input("请选择操作 (1-9 或命令名): ").strip().lower()
    if not raw:
        return None

    # Direct command name input (e.g. "import" = choice 1)
    if raw in COMMAND_NAME_MAP:
        return COMMAND_NAME_MAP[raw]

    # Number selection
    for num, cmd, _ in MENU_ITEMS:
        if raw == num:
            return cmd  # None for quit

    print("[ERR] 无效选择，请输入 1-9 或命令名")
    return show_interactive_menu()


def show_status(vault_path: str):
    """Show quick knowledge base status summary."""
    km = KnowledgeBaseManager(vault_path)
    index = km._load_index()
    doc_count = len(index.get("documents", []))
    concept_count = len(index.get("concepts", {}))
    entity_count = len(index.get("entities", {}))

    import_dir = km.import_dir
    file_count = len(list(import_dir.glob("*"))) if import_dir.exists() else 0

    cache_dir = km.vault_path / ".cache"
    cache_files = len(list(cache_dir.glob("*"))) if cache_dir.exists() else 0

    print()
    print("[STATUS] AI知识库状态")
    print("=" * 50)
    print(f"  vault:       {km.vault_path}")
    print(f"  documents:   {doc_count}")
    print(f"  concepts:    {concept_count}")
    print(f"  entities:    {entity_count}")
    print(f"  import dir:  {file_count} files")
    print(f"  cache files: {cache_files}")
    print(f"  api_key:     {'[SET]' if km.config.get('api_key') else '[NOT SET]'}")
    print("=" * 50)


def main():
    _setup_windows_encoding()
    parser = argparse.ArgumentParser(description="Knowledge Base Manager for Windows")
    parser.add_argument("--vault", default="./vault", help="Obsidian vault路径")
    parser.add_argument("--lang", default=None, choices=["zh", "en"], help="语言设置 (zh/en)")

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # init命令
    subparsers.add_parser("init", help="初始化知识库")

    # config命令
    config_parser = subparsers.add_parser("config", help="配置设置")
    config_parser.add_argument("--set", nargs=2, metavar=("KEY", "VALUE"), help="设置配置项")

    # import命令
    import_parser = subparsers.add_parser("import", help="导入文档")
    import_parser.add_argument("file", help="要导入的文件路径")
    import_parser.add_argument("--category", help="文档类别")

    # list命令
    subparsers.add_parser("list", help="列出所有文档")

    # query命令
    query_parser = subparsers.add_parser("query", help="查询知识库")
    query_parser.add_argument("question", help="问题")
    query_parser.add_argument("--limit", type=int, default=5, help="返回相关文档数量")

    # graph命令
    subparsers.add_parser("graph", help="生成知识图谱")

    # analyze-text命令（供 /learn 双写调用）
    at_parser = subparsers.add_parser("analyze-text", help="直接分析文本内容")
    at_parser.add_argument("--title", default="untitled", help="知识标题")
    at_parser.add_argument("--category", default="其他", help="分类")
    at_parser.add_argument("--file", help="从文件读取内容（替代stdin）")

    # batch-import命令（批量导入文件夹）
    bi_parser = subparsers.add_parser("batch-import", help="批量导入文件夹中的所有文件")
    bi_parser.add_argument("folder", help="文件夹路径")
    bi_parser.add_argument("--category", default="其他", help="默认分类")
    bi_parser.add_argument("--to-memory", action="store_true", help="同时写入 Memory 知识库")

    # unified-search命令（统一检索）
    us_parser = subparsers.add_parser("unified-search", help="统一检索 Memory + KB")
    us_parser.add_argument("question", help="检索问题")
    us_parser.add_argument("--limit", type=int, default=5, help="返回结果数量")

    # sync-memory-to-kb命令
    sm_parser = subparsers.add_parser("sync-memory-to-kb", help="Memory -> KB 同步")
    sm_parser.add_argument("--memory-dir", required=True, help="Memory 知识库目录")

    # sync-kb-to-memory命令
    sk_parser = subparsers.add_parser("sync-kb-to-memory", help="KB -> Memory 索引同步")
    sk_parser.add_argument("--memory-dir", required=True, help="Memory 知识库目录")

    # rebuild-memory-index命令
    ri_parser = subparsers.add_parser("rebuild-index", help="自动重建 Memory 知识索引")
    ri_parser.add_argument("--memory-dir", required=True, help="Memory 知识库目录")

    # backup命令
    backup_parser = subparsers.add_parser("backup", help="自动备份知识库到 git")
    backup_parser.add_argument("--message", default="", help="提交信息")

    # auto-classify命令（自动分类）
    ac_parser = subparsers.add_parser("auto-classify", help="对指定文件执行自动分类")
    ac_parser.add_argument("file", help="要分类的文件路径")

    # discover-categories命令（分类发现）
    subparsers.add_parser("discover-categories", help="显示分类发现结果")

    # merge-categories命令（合并分类）
    mc_parser = subparsers.add_parser("merge-categories", help="合并两个分类")
    mc_parser.add_argument("source", help="源分类名称")
    mc_parser.add_argument("target", help="目标分类名称")

    # cache-stats命令
    subparsers.add_parser("cache-stats", help="显示缓存统计信息")

    # cache-clear命令
    subparsers.add_parser("cache-clear", help="清除所有缓存")

    # version-list命令
    vl_parser = subparsers.add_parser("version-list", help="查看文档的版本历史")
    vl_parser.add_argument("file", help="文档路径（相对于vault）")
    vl_parser.add_argument("--limit", type=int, default=20, help="显示条数")

    # version-diff命令
    vd_parser = subparsers.add_parser("version-diff", help="对比两个版本的差异")
    vd_parser.add_argument("file", help="文档路径（相对于vault）")
    vd_parser.add_argument("rev1", help="起始版本 (commit hash)")
    vd_parser.add_argument("rev2", nargs="?", default="HEAD", help="目标版本 (默认 HEAD)")

    # version-rollback命令
    vr_parser = subparsers.add_parser("version-rollback", help="回滚到指定版本")
    vr_parser.add_argument("file", help="文档路径（相对于vault）")
    vr_parser.add_argument("rev", help="目标版本 (commit hash)")

    # -- Command aliases (Task 2) --
    COMMAND_ALIASES = {
        "kb": "query",
        "i": "import",
        "l": "list",
        "q": "query",
        "g": "graph",
        "bi": "batch-import",
        "us": "unified-search",
        "sm": "sync-memory-to-kb",
        "sk": "sync-kb-to-memory",
        "ri": "rebuild-index",
        "b": "backup",
        "ac": "auto-classify",
        "dc": "discover-categories",
        "mc": "merge-categories",
        "cs": "cache-stats",
        "cc": "cache-clear",
        "vl": "version-list",
        "vd": "version-diff",
        "vr": "version-rollback",
    }

    args = parser.parse_args()

    # Initialize i18n with --lang or detect from environment
    get_i18n(args.lang)

    if not args.command:
        # First-run wizard (Task 1)
        from agent.kb import SetupWizard
        wizard = SetupWizard()
        if wizard.is_first_run():
            print("[INFO] 检测到首次使用，启动配置向导...")
            print()
            config = wizard.run()
            if config.get("vault_path"):
                args.vault = config["vault_path"]
        else:
            # Interactive menu (Task 2)
            command = show_interactive_menu()
            if command is None:
                print("[BYE]")
                return

            # Map menu-only commands
            if command == "status":
                show_status(args.vault)
                return
            elif command == "sync":
                command = "sync-memory-to-kb"

            args.command = command

    # Resolve alias to canonical command name
    command = COMMAND_ALIASES.get(args.command, args.command)
    args.command = command

    try:
        km = KnowledgeBaseManager(args.vault)

        if command == "init":
            km.init()
        elif command == "config" and args.set:
            km.config_set(args.set[0], args.set[1])
        elif command == "import":
            km.import_document(args.file, args.category)
        elif command == "list":
            km.list_documents()
        elif command == "query":
            km.query(args.question, args.limit)
        elif command == "graph":
            km.generate_graph()
        elif command == "analyze-text":
            if args.file:
                text = Path(args.file).read_text(encoding='utf-8')
            else:
                text = sys.stdin.read()
            km.analyze_text(text, args.title, args.category)
        elif command == "unified-search":
            km.unified_search(args.question, args.limit)
        elif command == "sync-memory-to-kb":
            km.sync_memory_to_kb(args.memory_dir)
        elif command == "sync-kb-to-memory":
            km.sync_kb_to_memory_index(args.memory_dir)
        elif command == "rebuild-index":
            km.rebuild_memory_index(args.memory_dir)
        elif command == "backup":
            km.backup(args.message)
        elif command == "batch-import":
            km.batch_import(args.folder, args.category, args.to_memory)
        elif command == "auto-classify":
            filepath = Path(args.file)
            if not filepath.exists():
                print(f"[ERR] file not found: {filepath}")
                return
            content = filepath.read_text(encoding='utf-8')
            from .kb_utils import _extract_title
            title = _extract_title(content, filepath.stem)
            result = km.auto_classify(content, title)
            print(f"\n[RESULT] suggested category: {result}")
        elif command == "discover-categories":
            km.discover_categories()
        elif command == "merge-categories":
            km.merge_categories(args.source, args.target)
        elif command == "cache-stats":
            km.cache_stats()
        elif command == "cache-clear":
            km.cache_clear()
        elif command == "version-list":
            km.version_list(args.file, args.limit)
        elif command == "version-diff":
            km.version_diff(args.file, args.rev1, args.rev2)
        elif command == "version-rollback":
            km.version_rollback(args.file, args.rev)
        else:
            parser.print_help()

    except KeyboardInterrupt:
        print(f"\n[BYE] {t('bye')}")
    except Exception as e:
        print(f"[ERR] {t('error.generic')}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Agent Team All-Features System Test"""

import asyncio
import inspect
import sys
import time
import json
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

PASS = 0
FAIL = 0
SKIP = 0
RESULTS = []


def check(category, name, status, detail=""):
    global PASS, FAIL, SKIP
    icon = {"PASS": "[OK]", "FAIL": "[XX]", "SKIP": "[--]"}.get(status, "?")
    if status == "PASS": PASS += 1
    elif status == "FAIL": FAIL += 1
    else: SKIP += 1
    RESULTS.append({"category": category, "name": name, "status": status, "detail": detail})
    line = f"  {icon} {name}" + (f" -- {detail}" if detail else "")
    print(line.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def call_fn(fn, *args, **kwargs):
    """Call sync or async function."""
    if inspect.iscoroutinefunction(fn):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(fn(*args, **kwargs))
        finally:
            loop.close()
    else:
        return fn(*args, **kwargs)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. Tool Registry
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_tool_registry():
    section("1. Tool Registry")
    from agent.tools.tool_registry import TOOL_REGISTRY, get_tool_schemas, get_all_tools, cached, clear_cache, cache_stats

    count = len(TOOL_REGISTRY)
    check("Registry", "Registry non-empty", "PASS" if count > 0 else "FAIL", f"{count} tools")

    bad = [k for k, v in TOOL_REGISTRY.items() if "schema" not in v or "implementation" not in v]
    check("Registry", "All tools have schema+impl", "PASS" if not bad else "FAIL", f"bad: {bad}")

    schemas = get_tool_schemas()
    check("Registry", "get_tool_schemas returns list", "PASS" if isinstance(schemas, list) else "FAIL")

    fmt_bad = [s.get("function", {}).get("name", "?") for s in schemas if "type" not in s or "function" not in s]
    check("Registry", "Schema format correct", "PASS" if not fmt_bad else "FAIL", f"bad: {fmt_bad}")

    tools = get_all_tools()
    check("Registry", "get_all_tools returns dict", "PASS" if isinstance(tools, dict) else "FAIL")

    @cached(ttl=60)
    async def test_cached():
        return {"ok": True}
    r = call_fn(test_cached)
    check("Cache", "@cached decorator", "PASS" if r.get("ok") else "FAIL")

    stats = cache_stats()
    check("Cache", "cache_stats", "PASS" if "entries" in stats else "FAIL")

    clear_cache()
    stats2 = cache_stats()
    check("Cache", "clear_cache", "PASS" if stats2["entries"] == 0 else "FAIL")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. File Tools
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_file_tools():
    section("2. File Tools")
    from agent.tools.file_tools import read_file, write_file, glob, grep

    r = call_fn(read_file, "agent/config.py")
    check("File", "read_file", "PASS" if r else "FAIL")

    r = call_fn(read_file, "nonexistent_12345.py")
    check("File", "read_file missing file", "PASS" if r else "FAIL")

    test_path = Path("_test_write_temp.txt")
    r = call_fn(write_file, str(test_path), "hello test")
    check("File", "write_file", "PASS" if r else "FAIL")
    if test_path.exists(): test_path.unlink()

    r = call_fn(glob, "agent/*.py")
    check("File", "glob", "PASS" if r and len(str(r)) > 10 else "FAIL")

    r = call_fn(grep, "TOOL_REGISTRY", "agent/tools/tool_registry.py")
    check("File", "grep", "PASS" if r is not None else "FAIL")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Shell Tools
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_shell_tools():
    section("3. Shell Tools")
    from agent.tools.shell_tools import run_command
    r = call_fn(run_command, "echo hello")
    check("Shell", "run_command(echo)", "PASS" if r else "FAIL")
    r = call_fn(run_command, "python -c 'print(1+1)'")
    check("Shell", "run_command(python)", "PASS" if r else "FAIL")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. Search Tools (removed - was placeholder dead code)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_search_tools():
    section("4. Search Tools")
    check("Search", "removed_placeholder", "SKIP")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. Git Tools
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_git_tools():
    section("5. Git Tools")
    from agent.tools.git_tools import git_log_oneline, git_diff_summary
    r = call_fn(git_log_oneline, 5)
    check("Git", "git_log_oneline", "PASS" if r else "FAIL")
    r = call_fn(git_diff_summary)
    check("Git", "git_diff_summary", "PASS" if r else "FAIL")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. DeepWiki Tools
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_deepwiki_tools():
    section("6. DeepWiki Tools")
    from agent.tools.deepwiki_tools import deepwiki_search, deepwiki_get_stats
    r = call_fn(deepwiki_search, "python")
    check("DeepWiki", "deepwiki_search", "PASS" if r else "FAIL")
    r = call_fn(deepwiki_get_stats)
    check("DeepWiki", "deepwiki_get_stats", "PASS" if r else "FAIL")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. Todo Tools
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_todo_tools():
    section("7. Todo Tools")
    from agent.tools.todo_tools import update_todos, get_todo_manager
    mgr = get_todo_manager()
    check("Todo", "get_todo_manager", "PASS" if mgr else "FAIL")
    r = call_fn(update_todos, [{"task": "test", "done": False}])
    check("Todo", "update_todos", "PASS" if r else "FAIL")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8. Skill Tools
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_skill_tools():
    section("8. Skill Tools")
    from agent.tools.skill_tools import list_skills
    r = call_fn(list_skills)
    check("Skill", "list_skills", "PASS" if r else "FAIL")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 9. Core Systems
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_core_systems():
    section("9. Core Systems")

    from agent.model_orchestrator import ModelOrchestrator
    config_path = Path("model_config.json")
    if config_path.exists():
        orch = ModelOrchestrator(config_path)
        client = orch.get_model_for_complexity(1)
        check("Model", "ModelOrchestrator init", "PASS" if orch else "FAIL")
        check("Model", "get_model_for_complexity(1)", "PASS" if client else "FAIL")
        client2 = orch.get_model_for_complexity(1)
        check("Model", "Routing cache hit", "PASS" if client2 else "FAIL")
        client3 = orch.get_model_for_complexity(10)
        check("Model", "get_model_for_complexity(10)", "PASS" if client3 else "FAIL")
    else:
        check("Model", "ModelOrchestrator", "SKIP", "no config")

    from agent.event_bus import EventBus, Event
    bus = EventBus()
    received = []
    bus.subscribe("test.event", lambda e: received.append(e))
    bus.publish(Event(event_type="test.event", payload={"key": "value"}))
    check("EventBus", "publish/subscribe", "PASS" if received else "FAIL")

    from agent.memory import MemoryStore
    mem = MemoryStore(Path("_test_memory"))
    check("Memory", "MemoryStore init", "PASS" if mem else "FAIL")

    from agent.tools.browser.browser_pool import get_browser_pool
    pool = get_browser_pool()
    check("BrowserPool", "get_browser_pool", "PASS" if pool else "FAIL")

    from agent.state.task_state import TaskStateManager
    from agent.state.task_plan import TaskPlanManager
    tsm = TaskStateManager()
    tpm = TaskPlanManager(tsm)
    check("TaskPlan", "TaskPlanManager init", "PASS" if tpm else "FAIL")

    from agent.team_store import TeamStore
    ts = TeamStore(Path(".team"))
    check("TeamStore", "TeamStore init", "PASS" if ts else "FAIL")

    from agent.dynamic_semaphore import DynamicSemaphore
    sem = DynamicSemaphore(initial=3)
    check("Semaphore", "DynamicSemaphore init", "PASS" if sem else "FAIL")

    from agent.config_watcher import ConfigWatcher
    cw = ConfigWatcher(Path("model_config.json"), lambda: None)
    check("ConfigWatcher", "ConfigWatcher init", "PASS" if cw else "FAIL")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 10. Sub-agent Registry
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_subagent_registry():
    section("10. Sub-agent Registry")
    from agent.subagents.registry import SubagentRegistry

    reg = SubagentRegistry()
    agents = reg.list_available()
    check("Agents", "SubagentRegistry init", "PASS" if reg else "FAIL")
    check("Agents", "list_available non-empty", "PASS" if agents else "FAIL", f"{len(agents)} agents")

    expected = ["xiaohuangmen", "sili_suitang", "dongchang_tanshi", "shangbao_dianbu", "neiguan_yingzao", "liubu_liulanqi"]
    for name in expected:
        spec = reg.get_spec(name)
        if spec:
            check("Agents", f"{name}", "PASS", f"model={spec.preferred_model}, tools={len(spec.allowed_tools)}")
        else:
            check("Agents", f"{name}", "FAIL", "NOT FOUND")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 11. Browser Tools
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_browser_tools():
    section("11. Browser Tools")
    from agent.tools.browser import (
        navigate, click_element, type_text, scroll_page,
        exec_js_tool, multi_tab, wait_for, fill_form,
        manage_cookie, batch_js, browser_status,
        screenshot_and_ask, page_monitor,
        start_browser_session, end_browser_session,
        ask_doubao, ask_deepseek_browser, ask_ouyi,
        ask_kimi, ask_chatglm,
    )

    r = call_fn(browser_status)
    check("Browser", "browser_status", "PASS" if r else "FAIL")

    tools = {
        "navigate": navigate, "click_element": click_element,
        "type_text": type_text, "scroll_page": scroll_page,
        "exec_js_tool": exec_js_tool, "multi_tab": multi_tab,
        "wait_for": wait_for, "fill_form": fill_form,
        "manage_cookie": manage_cookie, "batch_js": batch_js,
        "screenshot_and_ask": screenshot_and_ask, "page_monitor": page_monitor,
        "start_browser_session": start_browser_session,
        "end_browser_session": end_browser_session,
        "ask_doubao": ask_doubao, "ask_deepseek_browser": ask_deepseek_browser,
        "ask_ouyi": ask_ouyi, "ask_kimi": ask_kimi, "ask_chatglm": ask_chatglm,
    }
    for name, fn in tools.items():
        check("Browser", f"{name} callable", "PASS" if callable(fn) else "FAIL")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 12. KB System
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_kb_system():
    section("12. KB System")
    from agent.kb.commands import KBCommandsMixin
    check("KB", "kb_commands mixin", "PASS" if KBCommandsMixin else "FAIL")

    from agent.kb.daemon import KBDaemonCore, StartupMixin, log_info, KBDaemonManager
    check("KB", "daemon (merged)", "PASS")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 13. Dispatch System
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_dispatch_system():
    section("13. Dispatch System")
    from agent.tools.dispatch.parallel_core import SubagentDispatcher
    check("Dispatch", "SubagentDispatcher", "PASS")

    methods = ["dispatch", "dispatch_parallel", "dispatch_with_handoff",
               "dispatch_with_approval", "dispatch_iterative_refine",
               "select_next_agent"]
    for m in methods:
        check("Dispatch", f"{m} method", "PASS" if hasattr(SubagentDispatcher, m) else "FAIL")

    from agent.tools.dispatch.approval import get_pending_approvals
    from agent.tools.dispatch.handoff import dispatch_with_handoff
    from agent.tools.dispatch.refine import dispatch_iterative_refine
    check("Dispatch", "approval functions", "PASS")
    check("Dispatch", "handoff functions", "PASS")
    check("Dispatch", "refine functions", "PASS")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 14. Knowledge Service
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_knowledge_service():
    section("14. Knowledge Service")
    from agent.knowledge_service import KnowledgeService
    ks = KnowledgeService()
    check("KBService", "KnowledgeService init", "PASS" if ks else "FAIL")

    for m in ["read_memory", "write_memory", "search_kb", "get_context_for_task"]:
        check("KBService", f"{m} method", "PASS" if hasattr(ks, m) else "FAIL")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 15. Web Tools
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_web_tools():
    section("15. Web Tools")
    from agent.tools.web_tools import web_fetch
    check("Web", "web_fetch importable", "PASS" if web_fetch else "FAIL")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 16. Config
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_config():
    section("16. Config")
    from agent.config import AI_KNOWLEDGE_BASE, PROJECT_ROOT
    check("Config", "AI_KNOWLEDGE_BASE", "PASS" if AI_KNOWLEDGE_BASE else "FAIL")
    check("Config", "PROJECT_ROOT", "PASS" if PROJECT_ROOT else "FAIL")
    check("Config", "model_config.json exists", "PASS" if Path("model_config.json").exists() else "FAIL")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def main():
    print("\n" + "=" * 60)
    print("  Agent Team All-Features System Test")
    print("=" * 60)

    start = time.time()

    test_tool_registry()
    test_file_tools()
    test_shell_tools()
    test_search_tools()
    test_git_tools()
    test_deepwiki_tools()
    test_todo_tools()
    test_skill_tools()
    test_core_systems()
    test_subagent_registry()
    test_browser_tools()
    test_kb_system()
    test_dispatch_system()
    test_knowledge_service()
    test_web_tools()
    test_config()

    elapsed = time.time() - start

    print(f"\n{'='*60}")
    print(f"  Complete: {elapsed:.1f}s")
    print(f"  [OK] PASS: {PASS}")
    print(f"  [XX] FAIL: {FAIL}")
    print(f"  [--] SKIP: {SKIP}")
    print(f"  Total: {PASS + FAIL + SKIP}")
    print("=" * 60)

    fails = [r for r in RESULTS if r["status"] == "FAIL"]
    if fails:
        print("\nFailed:")
        for f in fails:
            print(f"  [XX] [{f['category']}] {f['name']}: {f['detail']}")

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

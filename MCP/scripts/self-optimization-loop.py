#!/usr/bin/env python3
"""自我优化工作流循环 - AI-chat MCP + Playwright MCP 集成优化."""

import asyncio
import os
import json
import time
from datetime import datetime
from pathlib import Path

# ── 配置 ──────────────────────────────────────────────────────────
WORKSPACE = Path(os.environ.get("DESKTOP", "")) / "claude workspace"
LOG_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright" / "optimization-logs"
CONFIG_FILE = WORKSPACE / ".claude" / "optimization-config.json"
METRICS_FILE = LOG_DIR / "metrics.json"

# 确保目录存在
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── 优化策略 ──────────────────────────────────────────────────────
OPTIMIZATION_STRATEGIES = {
    "browser_performance": {
        "name": "浏览器性能优化",
        "check": "检查浏览器内存使用和页面加载时间",
        "optimize": "清理缓存、调整viewport、禁用不必要的扩展",
    },
    "mcp_stability": {
        "name": "MCP稳定性优化",
        "check": "检查MCP连接状态和错误率",
        "optimize": "调整超时设置、重试逻辑、错误处理",
    },
    "抓取效率": {
        "name": "抓取效率优化",
        "check": "检查页面抓取成功率和响应时间",
        "optimize": "优化选择器、调整等待策略、并行抓取",
    },
    "工作流自动化": {
        "name": "工作流自动化优化",
        "check": "检查任务执行成功率和人工干预次数",
        "optimize": "增加自动化步骤、减少人工干预、优化任务分配",
    },
}

# ── 监控指标 ──────────────────────────────────────────────────────
class Metrics:
    def __init__(self):
        self.data = {
            "browser_memory": [],
            "page_load_times": [],
            "mcp_errors": [],
            "scrape_success_rate": [],
            "task_completion_rate": [],
            "optimization_history": [],
        }
        self.load()

    def load(self):
        if METRICS_FILE.exists():
            with open(METRICS_FILE, "r", encoding="utf-8") as f:
                self.data = json.load(f)

    def save(self):
        with open(METRICS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def record(self, category: str, value):
        if category in self.data:
            self.data[category].append({
                "timestamp": datetime.now().isoformat(),
                "value": value,
            })
            # 保留最近100条记录
            self.data[category] = self.data[category][-100:]
            self.save()

# ── 优化执行器 ──────────────────────────────────────────────────────
class Optimizer:
    def __init__(self):
        self.metrics = Metrics()
        self.optimization_count = 0

    async def check_browser_performance(self) -> dict:
        """检查浏览器性能"""
        # 模拟检查浏览器内存使用
        import psutil
        browser_memory = 0
        for proc in psutil.process_iter(['name', 'memory_info']):
            if proc.info['name'] == 'chrome.exe':
                browser_memory += proc.info['memory_info'].rss

        self.metrics.record("browser_memory", browser_memory)

        return {
            "status": "ok" if browser_memory < 2 * 1024 * 1024 * 1024 else "warning",
            "memory_mb": browser_memory / 1024 / 1024,
            "recommendation": "内存使用正常" if browser_memory < 2 * 1024 * 1024 * 1024 else "建议清理浏览器缓存",
        }

    async def check_mcp_stability(self) -> dict:
        """检查MCP稳定性"""
        # 检查MCP日志文件
        ai_chat_log = Path(os.environ.get("LOCALAPPDATA", "")) / ".claude" / "scripts" / "ai-chat-mcp.log"
        error_count = 0
        if ai_chat_log.exists():
            with open(ai_chat_log, "r", encoding="utf-8") as f:
                content = f.read()
                error_count = content.lower().count("error") + content.lower().count("failed")

        self.metrics.record("mcp_errors", error_count)

        return {
            "status": "ok" if error_count < 10 else "warning",
            "error_count": error_count,
            "recommendation": "MCP运行稳定" if error_count < 10 else "建议检查MCP配置",
        }

    async def optimize_browser(self):
        """优化浏览器配置"""
        print("[优化] 清理浏览器缓存...")
        # 清理Playwright缓存目录
        cache_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright" / "mcp-chrome-persistent" / "Cache"
        if cache_dir.exists():
            import shutil
            shutil.rmtree(cache_dir, ignore_errors=True)
            print(f"[优化] 已清理缓存: {cache_dir}")

        return {"action": "browser_cache_cleaned", "status": "success"}

    async def optimize_mcp(self):
        """优化MCP配置"""
        print("[优化] 检查MCP配置...")
        # 读取当前配置
        config_file = WORKSPACE / ".mcp.json"
        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)

            # 检查是否需要优化
            optimizations = []

            # 检查ai-chat配置
            if "ai-chat" in config.get("mcpServers", {}):
                ai_chat = config["mcpServers"]["ai-chat"]
                if "env" not in ai_chat:
                    ai_chat["env"] = {}
                # 添加性能优化环境变量
                ai_chat["env"]["PYTHONOPTIMIZE"] = "1"
                optimizations.append("ai-chat性能优化")

            if optimizations:
                with open(config_file, "w", encoding="utf-8") as f:
                    json.dump(config, f, ensure_ascii=False, indent=2)
                print(f"[优化] 已应用优化: {', '.join(optimizations)}")
                return {"action": "mcp_config_optimized", "optimizations": optimizations}

        return {"action": "no_optimization_needed", "status": "ok"}

    async def run_optimization_cycle(self):
        """运行一个优化周期"""
        self.optimization_count += 1
        print(f"\n{'='*60}")
        print(f"[优化周期 {self.optimization_count}] 开始 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")

        results = []

        # 1. 检查浏览器性能
        print("\n[检查] 浏览器性能...")
        browser_check = await self.check_browser_performance()
        print(f"  状态: {browser_check['status']}, 内存: {browser_check['memory_mb']:.1f}MB")
        print(f"  建议: {browser_check['recommendation']}")
        results.append(("browser_performance", browser_check))

        # 2. 检查MCP稳定性
        print("\n[检查] MCP稳定性...")
        mcp_check = await self.check_mcp_stability()
        print(f"  状态: {mcp_check['status']}, 错误数: {mcp_check['error_count']}")
        print(f"  建议: {mcp_check['recommendation']}")
        results.append(("mcp_stability", mcp_check))

        # 3. 执行优化
        print("\n[执行] 优化操作...")
        if browser_check["status"] == "warning":
            browser_opt = await self.optimize_browser()
            results.append(("browser_optimization", browser_opt))

        mcp_opt = await self.optimize_mcp()
        results.append(("mcp_optimization", mcp_opt))

        # 4. 记录优化历史
        self.metrics.data["optimization_history"].append({
            "timestamp": datetime.now().isoformat(),
            "cycle": self.optimization_count,
            "results": results,
        })
        self.metrics.save()

        print(f"\n[完成] 优化周期 {self.optimization_count} 结束")
        print(f"{'='*60}\n")

        return results

    async def run_continuous_optimization(self, interval_minutes: int = 30):
        """持续运行优化循环"""
        print(f"[启动] 自我优化工作流循环，间隔: {interval_minutes}分钟")
        print("[提示] 按 Ctrl+C 停止\n")

        while True:
            try:
                await self.run_optimization_cycle()
                print(f"[等待] 下一次优化: {interval_minutes}分钟后...")
                await asyncio.sleep(interval_minutes * 60)
            except KeyboardInterrupt:
                print("\n[停止] 自我优化循环已停止")
                break
            except Exception as e:
                print(f"[错误] 优化周期异常: {e}")
                await asyncio.sleep(60)  # 出错后等待1分钟重试

# ── 主程序 ──────────────────────────────────────────────────────────
async def main():
    optimizer = Optimizer()

    # 运行单次优化
    print("[启动] 自我优化工作流")
    await optimizer.run_optimization_cycle()

    # 如果需要持续优化，取消下面的注释
    # await optimizer.run_continuous_optimization(interval_minutes=30)

if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
Agent Team 生产启动器（Windows 服务模式）
职责：日志管理、异常恢复、优雅退出、服务控制

使用 NSSM 安装为 Windows 服务：
  nssm install AgentTeam "C:\Python311\python.exe" "D:\path\to\run_agent.py"
  nssm set AgentTeam Start SERVICE_AUTO_START
  nssm start AgentTeam
"""

import asyncio
import sys
import os
import signal
import traceback
from pathlib import Path
from datetime import datetime
from agent.loop import AgentLoop

# Windows 服务状态回调
_service_status = None

def set_service_status(status):
    """NSSM 可以指定的服务状态回调（可选）"""
    global _service_status
    _service_status = status


class AgentService:
    """Windows 服务包装器"""

    def __init__(self, workspace: Path = None):
        self.workspace = workspace or Path.cwd()
        self.loop = None
        self.running = False
        self.shutdown_event = asyncio.Event()  # 用于通知 AgentLoop 停止

        # 创建日志目录
        self.log_dir = self.workspace / "logs"
        self.log_dir.mkdir(exist_ok=True)

        # 日志文件（按日期滚动）
        date_str = datetime.now().strftime("%Y-%m-%d")
        self.log_file = self.log_dir / f"agent_{date_str}.log"
        self.error_file = self.log_dir / f"agent_error_{date_str}.log"

        # 信号处理（Ctrl+C）
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame):
        """处理退出信号（应尽可能快，不进行 I/O）"""
        self.running = False
        self.shutdown_event.set()

    def _redirect_output(self):
        """重定向 stdout/stderr 到日志文件"""
        class Logger:
            def __init__(self, log_path):
                self.terminal = sys.__stdout__
                self.log = open(log_path, "a", encoding="utf-8", buffering=1)

            def write(self, message):
                self.terminal.write(message)
                self.log.write(message)

            def flush(self):
                self.terminal.flush()
                self.log.flush()

            def close(self):
                self.log.close()

            # 补充标准文件对象属性
            @property
            def encoding(self):
                return "utf-8"

            def isatty(self):
                return False

            def readable(self):
                return False

            def writable(self):
                return True

            def seekable(self):
                return False

        sys.stdout = Logger(self.log_file)
        sys.stderr = Logger(self.error_file)

    def _restore_output(self):
        """恢复标准输出"""
        if hasattr(sys.stdout, 'close'):
            sys.stdout.close()
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

    async def start(self):
        """启动 Agent 主循环"""
        self._redirect_output()
        print(f"\n{'='*60}")
        print(f"Agent Team 启动")
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"工作区: {self.workspace}")
        print(f"日志: {self.log_file}")
        print(f"{'='*60}\n")

        self.running = True
        restart_count = 0
        max_restarts = 10  # 防止无限重启循环

        while self.running and restart_count < max_restarts:
            try:
                print(f"[INFO] 启动主循环 (尝试 {restart_count + 1})")
                # 创建新的 AgentLoop 实例（放在 try 内以便异常捕获）
                self.loop = AgentLoop(self.workspace, service_mode=True, shutdown_event=self.shutdown_event)
                await self.loop.run()
                # 正常退出（shutdown_event 被设置）
                print("[INFO] 主循环正常退出")
                self.running = False
                break

            except KeyboardInterrupt:
                print("\n[INFO] 用户中断")
                self.running = False
                break

            except Exception as e:
                restart_count += 1
                print(f"[ERROR] Agent 异常: {type(e).__name__}: {e}")
                traceback.print_exc()
                print(f"[WARN] 将在 5 秒后重启 ({restart_count}/{max_restarts})...")
                await asyncio.sleep(5)

        if restart_count >= max_restarts:
            print("[FATAL] 重启次数超限，停止服务")

        self._cleanup()

    def _cleanup(self):
        """清理资源"""
        print("[INFO] 正在清理资源...")
        self._restore_output()
        print("[INFO] 清理完成")

    def run_sync(self):
        """同步入口点"""
        try:
            asyncio.run(self.start())
        except Exception as e:
            print(f"[FATAL] 启动失败: {e}")
            traceback.print_exc()
            sys.exit(1)


def main():
    """入口点：支持工作区参数"""
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    service = AgentService(workspace)
    service.run_sync()


if __name__ == "__main__":
    main()

"""Agent 主循环：组件装配、对话循环、工具调度"""

import asyncio
from typing import List, Dict, Any, Optional
from pathlib import Path

from .runner import AgentRunner
from .memory import MemoryStore
from .context import ContextAssembler
from .team_store import TeamStore, MessageBus
from .llm_client import load_llm_client_from_config


class AgentLoop:
    """主循环，负责所有组件装配和对话管理"""

    def __init__(self, workspace_path: Path = None, service_mode: bool = False, shutdown_event=None):
        self.workspace_path = workspace_path or Path.cwd()
        self.service_mode = service_mode
        self._running = True  # 内部运行标志
        self.shutdown_event = shutdown_event or asyncio.Event()
        self.memory = MemoryStore(self.workspace_path / "memory")
        self.team_store = TeamStore(self.workspace_path / ".team")
        self.message_bus = MessageBus(self.workspace_path / ".team")
        self.context_assembler = ContextAssembler(self.workspace_path / "templates")

        # 加载 LLM 客户端
        config_path = self.workspace_path / "model_config.json"
        try:
            self.llm_client = load_llm_client_from_config(config_path)
        except Exception as e:
            # 加载失败，使用模拟客户端
            self.llm_client = None

        # 工具注册
        self.tools = {}
        self._register_tools()

        # 为文件工具注入工作区（路径沙箱）
        from .tools import file_tools
        file_tools.set_workspace(self.workspace_path)

        # 注入 LLM client 到主 Agent 与子代理派遣器
        try:
            from .model_orchestrator import ModelOrchestrator
            self.model_orchestrator = ModelOrchestrator(self.workspace_path / "model_config.json")

            # 使用 orchestrator 获取 lead teammate 的 LLM client
            lead_config = self.team_store.get_teammate("lead")
            client = self.model_orchestrator.get_client_for_agent("lead", lead_config)
            if client:
                self.llm_client = client
                print(f"[OK] lead teammate 使用模型: {client.provider}/{client.model}")
        except Exception as e:
            print(f"[WARN] ModelOrchestrator 初始化失败，使用原有 llm_client: {e}")
            # 保持之前加载的 self.llm_client 不变

        try:
            from .tools import dispatch_tools
            dispatch_tools.set_global_llm_client(self.llm_client)
            dispatch_tools.set_model_orchestrator(self.model_orchestrator)
            dispatch_tools.set_team_store(self.team_store)
        except ImportError as e:
            print(f"[WARN] dispatch_tools 模块不可用: {e}")
        except AttributeError as e:
            print(f"[WARN] dispatch_tools API 不兼容: {e}")
        except Exception as e:
            print(f"[WARN] dispatch_tools 注入失败: {e}")

        # 创建 Runner（工具完全注册后）
        self.runner = AgentRunner(self.tools)

        # 对话状态
        self.mode = "ask_before_edit"  # "ask_before_edit", "auto", "plan"
        self.plan = {"enabled": False, "drafts": []}

    def shutdown(self):
        """外部调用以停止服务（用于服务模式）"""
        self._running = False
        self.shutdown_event.set()

    def _register_tools(self):
        """注册内置工具"""
        from .tools import (
            shell_tools,
            file_tools,
            web_tools,
            search_tools,
            skill_tools,
            todo_tools,
            dispatch_tools,
            team_tools
        )

        # 合并所有工具到 self.tools
        tool_modules = [shell_tools, file_tools, web_tools, search_tools,
                       skill_tools, todo_tools, dispatch_tools, team_tools]

        for module in tool_modules:
            for name, obj in module.__dict__.items():
                # 只注册函数（排除类、模块等）
                if callable(obj) and not name.startswith("_") and not isinstance(obj, type):
                    self.tools[name] = obj

        # 添加系统状态工具
        self.tools['status'] = self._get_system_status

    async def _get_system_status(self) -> Dict[str, Any]:
        """获取系统状态（/status 命令）"""
        from datetime import datetime

        status = {
            "timestamp": datetime.now().isoformat(timespec='seconds'),
            "llm_client": {
                "provider": self.llm_client.provider if self.llm_client else "none",
                "model": self.llm_client.model if self.llm_client else "none",
                "api_base": self.llm_client.api_base if self.llm_client else "none"
            },
            "team": {},
            "token_stats": {}
        }

        # 遍历所有 teammate
        for tm in self.team_store.teammates:
            name = tm.get("name")
            status["team"][name] = {
                "role": tm.get("role"),
                "agent_type": tm.get("agent_type"),
                "status": tm.get("status"),
                "model": tm.get("model")
            }

        # 获取 token 统计
        try:
            token_stats = self.memory.get_token_stats(days=1)
            status["token_stats"] = token_stats
        except Exception:
            status["token_stats"] = {"error": "无法读取统计信息"}

        return status

    async def process_message(self, user_message: str) -> str:
        """处理用户消息"""
        from datetime import datetime
        from .subagents.registry import SubagentRegistry

        # 1. 检查权限模式
        if self.mode == "plan" and not self.plan.get("enabled", False):
            return "[WARN] Plan 模式未启用，使用 /plan on 开启"

        # 2. 获取历史记录（当前用户消息尚未加入）
        history = self.memory.get_recent_history(limit=50)

        # 3. 构建 System Prompt（不包含当前用户消息）
        try:
            system_prompt = self.context_assembler.build_system_prompt(
                tools=list(self.tools.keys()),
                skills=[],  # 待实现：从 skills 包加载
                subagents=SubagentRegistry.list_available(),
                team=self.team_store.teammates,
                memory={
                    "long_term": self.memory.get_long_term_memory(),
                    "user_prefs": self.memory.get_user_prefs()
                },
                user="",
                history=history,
                workspace_path=str(self.workspace_path)
            )
        except Exception as e:
            system_prompt = f"系统提示生成失败: {e}"

        # 4. 记录用户消息（追加到历史）
        self.memory.append_history({
            "role": "user",
            "content": user_message,
            "timestamp": datetime.now().isoformat()
        })

        # 5. 调用 LLM 或降级到模拟响应
        assistant_reply = ""
        if self.llm_client:
            try:
                response = await self.llm_client.chat(
                    messages=[{"role": "user", "content": user_message}],
                    system=system_prompt
                )
                assistant_reply = response.get("content", "")
                usage = response.get("usage", {})
                if usage:
                    prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
                    completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens") or 0
                    try:
                        self.memory.record_token_usage(
                            provider=self.llm_client.provider,
                            model=self.llm_client.model,
                            input_tokens=prompt_tokens,
                            output_tokens=completion_tokens,
                            cached=False
                        )
                    except Exception:
                        pass
            except Exception as e:
                assistant_reply = f"LLM 调用失败: {e}"
                print(f"[WARN] LLM 调用异常: {e}")

        # 6. 降级到模拟响应
        if not assistant_reply:
            assistant_reply = self._simulate_response(user_message)

        # 7. 记录助手回复
        self.memory.append_history({
            "role": "assistant",
            "content": assistant_reply,
            "timestamp": datetime.now().isoformat()
        })

        return assistant_reply

    def _simulate_response(self, user_message: str) -> str:
        """生成模拟响应（用于测试）"""
        msg = user_message.lower()

        if msg.startswith("/"):
            # 命令已处理，不应该到这里
            return ""

        # 根据用户输入生成有意义的模拟回复
        if "团队" in msg or "队友" in msg:
            return "目前有 5 位固定队友：lead（领导）、coder（工程师）、researcher（研究员）、reviewer（审查员）、reader（阅读员）。使用 /team 查看状态。"

        elif "子代理" in msg or "小太监" in msg:
            return "可用子代理类型：1. 通传小黄门（轻量只读）、2. 司礼监随堂（阅读文档）、3. 东厂探事（查访搜索）、4. 尚宝监典簿（质量检查）、5. 内官监营造（工程执行）。使用 dispatch_subagent 派遣。"

        elif "工具" in msg or "功能" in msg:
            return "内置工具：run_command、read_file、write_file、edit_file、glob、grep、web_fetch、load_skill、update_todos、dispatch_subagent、spawn_teammate、send_message、broadcast 等。"

        elif "模式" in msg or "权限" in msg:
            return f"当前模式: {self.mode}。可用模式：ask_before_edit（编辑前审批）、auto（全自动）、plan（计划模式）。切换命令：/mode <模式>"

        elif "plan" in msg:
            return "Plan 模式用于复杂任务：先进行只读探索和提问，然后提交计划草案等待用户批准。开启命令：/plan on"

        else:
            return f"我收到了您的消息：'{user_message}'\n\n当前为测试模式，未连接真实 LLM API。请配置 model_config.json 中的 API Key 以启用完整功能。\n\n快速命令：\n- /team 查看队友\n- /mode ask_before_edit 切换模式\n- /plan on 开启计划模式\n- /exit 退出"

    async def run(self, service_mode: bool = False):
        """运行对话循环（CLI 模式 或 服务模式

        Args:
            service_mode: 如果为 True，则以服务模式运行（无阻塞输入，周期性睡眠）
        """
        if service_mode:
            print("[*] Agent 已启动（服务模式），等待命令...\n")
            # 服务模式：非阻塞，通过 shutdown_event 等待停止信号
            try:
                await self.shutdown_event.wait()
                print("[INFO] 收到关闭信号，服务模式退出")
            except asyncio.CancelledError:
                print("[INFO] 服务模式被取消")
            finally:
                print("[INFO] 服务模式退出")
        else:
            print("[*] Agent 已启动，输入 /exit 退出\n")
            # CLI 模式：阻塞式输入
            while True:
                try:
                    user_input = input("> ").strip()
                except EOFError:
                    print("\n[INFO] 标准输入已关闭，退出 CLI 模式")
                    break
                except KeyboardInterrupt:
                    print("\n[!] 检测到中断，退出...")
                    break

                if user_input == "/exit":
                    print("👋 再见！")
                    break

                if user_input.startswith("/mode"):
                    parts = user_input.split()
                    if len(parts) > 1:
                        new_mode = parts[1]
                        if new_mode in ["ask_before_edit", "auto", "plan"]:
                            self.mode = new_mode
                            print(f"[OK] 模式切换为: {new_mode}")
                        else:
                            print("[ERROR] 无效模式，可选: ask_before_edit, auto, plan")
                    else:
                        print(f"当前模式: {self.mode}")
                    continue

                if user_input == "/team":
                    self._show_team_status()
                    continue

                if user_input == "/status":
                    self._show_system_status()
                    continue

                if user_input == "/spawn_teammate":
                    print("用法: /spawn_teammate <name> <role> <agent_type>")
                    continue

                # 处理普通消息
                response = await self.process_message(user_input)
                print(f"Agent: {response}\n")

    def _show_team_status(self):
        """显示团队状态"""
        print("\n" + "="*50)
        print("Agent Team 状态")
        print("="*50)

        teammates = self.team_store.teammates
        if not teammates:
            print("未配置任何队友")
        else:
            for tm in teammates:
                status_icon = {
                    "idle": "[IDLE]",
                    "working": "[WORK]",
                    "offline": "[OFF]",
                    "shutdown": "[DOWN]"
                }.get(tm["status"], "????")

                print(f"{status_icon} {tm['name']:10} | {tm['role']:10} | {tm['agent_type']:20} | {tm['status']}")

        # 显示 Inbox 消息数
        print("\nInbox 消息:")
        for tm in teammates:
            inbox_file = self.team_store.inbox_dir / f"{tm['name']}.jsonl"
            if inbox_file.exists():
                count = sum(1 for _ in open(inbox_file, "r", encoding="utf-8"))
                if count > 0:
                    print(f"  {tm['name']}: {count} 条未读")

        print("="*50 + "\n")

    def get_llm_for_teammate(self, teammate_name: str):
        """获取指定队友的 LLM client（用于外部工具/队友调用）"""
        tm = self.team_store.get_teammate(teammate_name)
        if tm:
            return self.model_orchestrator.get_client_for_agent(teammate_name, tm)
        return None

    def _show_system_status(self):
        """显示系统运行状态"""
        print("\n" + "="*60)
        print("Agent Team 系统状态")
        print("="*60)
        print(f"工作区: {self.workspace_path}")
        print(f"模式: {self.mode}")
        print(f"Plan 模式: {'启用' if self.plan.get('enabled') else '关闭'}")

        if self.llm_client:
            print(f"主 Agent LLM: {self.llm_client.provider} / {self.llm_client.model}")
            print(f"   API Base: {self.llm_client.api_base}")
            print(f"   Max Tokens: {self.llm_client.max_tokens}, Temperature: {self.llm_client.temperature}")
        else:
            print("主 Agent LLM: 未配置（模拟模式）")

        try:
            stats = self.memory.get_token_stats(days=1)
            print(f"Token 使用（近24h）: 输入 {stats.get('total_input',0)}, 输出 {stats.get('total_output',0)}")
        except Exception:
            pass

        print(f"已注册工具: {len(self.tools)} 个")
        print("\nTeam 模型分配:")
        print("-" * 60)
        print(f"{'队友名':<12} {'角色':<10} {'agent_type':<22} {'模型'}")
        print("-" * 60)
        for tm in self.team_store.teammates:
            print(f"{tm['name']:<12} {tm['role']:<10} {tm['agent_type']:<22} {tm.get('model', 'N/A')}")
        print("="*60 + "\n")


def main():
    """CLI 入口"""
    import sys
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    loop = AgentLoop(workspace)
    try:
        asyncio.run(loop.run())
    except KeyboardInterrupt:
        print("\n[!] 已退出")


if __name__ == "__main__":
    main()

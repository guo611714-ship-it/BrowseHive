"""配置管理 - 集中所有配置项."""

import json
import os
import threading
import time
from typing import Optional

# 默认配置
DEFAULT_CONFIG = {
    "max_retries": 3,
    "retry_delay": 2,
    "max_pages": 5,
    "page_idle_timeout": 600,
    "chat_timeout": 120,
    "streaming_timeout": 30,
    "no_response_timeout": 15,
    "log_level": "INFO",
    "max_response_length": 2000,
    "schema_version": "1.1.0",
    "tool_mode": "full",
    "headless": False,
    "memory_warn_mb": 1500,
    "memory_critical_mb": 2000,
    "rate_limit_interval": 3,
    "rate_limit_window": 60,
    "rate_limit_max": 10,
    "dedup_window": 300,
    "session_save_path": "",
    "screenshot_dir": "",
    "screenshot_on_error": True,
    "proxy_pool": [],
    "proxy_index": 0,
    "proxy_enabled": False,
    "retry_budget_max": 20,
    "retry_budget_window": 60,
    "browser_use_enabled": True,
    # CDP 端口配置
    "cdp_ports": [9222, 9223, 9224, 9225, 9333],
    "cdp_max_scan_attempts": 3,
    "cdp_default_port": 9222,
    # 发送消息超时（秒）
    "send_timeout": 30,
    # 无响应快速失败阈值
    "max_no_response_attempts": 7,
}

# 平台能力关键词映射
PLATFORM_CAPABILITIES = {
    "doubao": [
        "中文", "润色", "改写", "文案", "创意", "翻译", "总结", "简化", "写作",
        "联网", "file upload", "文件上传", "deepthink", "深度思考", "搜索", "audio", "视频"
    ],
    "volcengine": [
        "代码", "编程", "算法", "技术", "分析", "推理", "调试", "架构", "优化",
        "联网", "文件上传", "视觉", "vision", "AI Agents", "agents", "market insight",
        "数据安全", "安全运营", "智能路由", "smart routing", "音视频", "数据处理"
    ],
    "ouyi": [
        "图片", "图像", "画", "思维导图", "流程图", "可视化", "绘图", "midjourney",
        "写作", "一键写作", "文案", "文章", "MECE", "GROW", "帕累托", "角色扮演",
        "API", "excel", "公式", "创作", "专业框架", "中文本地化", "仙侠", "绘画提示词"
    ],
    "deepseek": [
        "报告", "文档", "专业", "论文", "实验", "数据", "统计", "研究",
        "代码", "编程", "推理", "数学", "算法", "调试", "分析", "深度思考", "R1", "V3",
        "技术方案", "技术架构", "代码审查", "数学计算", "逻辑推理", "开源"
    ],
}

# 任务类型关键词
TASK_KEYWORDS = {
    "browser": ["打开", "浏览", "页面", "标签", "截图", "抓取", "scroll", "navigate", "click"],
    "api": ["统计", "配置", "任务", "协调", "拆分", "基准", "config", "stats", "benchmark"],
}

# 工具集定义
TOOL_SETS = {
    "full": None,  # None表示不过滤，使用全部工具
    "browser-only": [
        "ask_doubao", "ask_deepseek", "ask_volcengine", "ask_ouyi", "smart_ask",
        "open_all_platforms", "login_platform", "check_login", "list_tabs",
    ],
    "api-only": [
        "execute_split", "run_benchmark", "get_fetch_stats",
        "get_config", "set_config", "get_coordination_status",
        "set_task", "get_context", "report_result", "split_task_tool",
    ],
    "smart": None,  # 动态检测任务类型
}

# 缓存配置
CACHE_CONFIG = {
    "response_ttl": 300,        # 响应缓存5分钟
    "response_max": 100,        # 最大缓存条目
    "tool_ttl": 60,             # 工具调用缓存60秒
    "context_ttl": 600,         # 上下文缓存10分钟
    "context_max": 30,          # 上下文缓存最大条目
}

# 限流配置
RATE_LIMIT_CONFIG = {
    "base_interval": 3,         # 同一平台最小请求间隔(秒)
    "window": 60,              # 限流窗口(秒)
    "max_requests": 10,        # 窗口内最大请求数
}

# 重试配置
RETRY_CONFIG = {
    "max_retries": 3,
    "retry_delay": 2,
    "budget_max": 20,
    "budget_window": 60,
}

class ConfigWatcher:
    """配置文件监听器 — 检测文件变化并自动重载."""

    def __init__(self, config: 'Config', file_path: str, poll_interval: float = 2.0):
        self._config = config
        self._file_path = file_path
        self._poll_interval = poll_interval
        self._last_mtime = 0.0
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self):
        """启动监听线程."""
        if self.is_running:
            return
        if not os.path.exists(self._file_path):
            return
        # 初始加载一次文件内容
        self._reload_if_changed()
        self._last_mtime = os.path.getmtime(self._file_path)
        self.is_running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止监听."""
        self.is_running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def check_now(self):
        """立即检查一次文件变化（同步，用于测试）."""
        self._reload_if_changed()

    def _poll_loop(self):
        while not self._stop_event.is_set():
            self._stop_event.wait(self._poll_interval)
            if self._stop_event.is_set():
                break
            self._reload_if_changed()

    def _reload_if_changed(self):
        try:
            if not os.path.exists(self._file_path):
                return
            mtime = os.path.getmtime(self._file_path)
            if mtime <= self._last_mtime:
                return
            self._last_mtime = mtime
            with open(self._file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 只更新 main config 中存在的 key
            for key, value in data.items():
                if key in self._config._config:
                    self._config._config[key] = value
                # 更新子配置
                if key in self._config._cache_config:
                    self._config._cache_config[key] = value
                if key in self._config._rate_limit_config:
                    self._config._rate_limit_config[key] = value
                if key in self._config._retry_config:
                    self._config._retry_config[key] = value
        except Exception:
            pass  # 静默处理，不中断服务


class Config:
    """配置管理器."""

    def __init__(self):
        self._config = DEFAULT_CONFIG.copy()
        self._cache_config = CACHE_CONFIG.copy()
        self._rate_limit_config = RATE_LIMIT_CONFIG.copy()
        self._retry_config = RETRY_CONFIG.copy()
        self._watcher: Optional[ConfigWatcher] = None

    def get(self, key: str, default=None):
        return self._config.get(key, default)

    def __getattr__(self, key: str):
        """支持 config.chat_timeout 形式的属性访问."""
        if key.startswith("_"):
            raise AttributeError(key)
        val = self._config.get(key)
        if val is not None:
            return val
        raise AttributeError(f"Config has no attribute '{key}'")

    def set(self, key: str, value):
        self._config[key] = value

    def update(self, updates: dict):
        self._config.update(updates)

    # 缓存配置访问
    @property
    def cache_ttl(self):
        return self._cache_config["response_ttl"]

    @property
    def cache_max(self):
        return self._cache_config["response_max"]

    @property
    def tool_ttl(self):
        return self._cache_config["tool_ttl"]

    @property
    def context_ttl(self):
        return self._cache_config["context_ttl"]

    @property
    def context_max(self):
        return self._cache_config["context_max"]

    # 限流配置访问
    @property
    def rate_limit_interval(self):
        return self._rate_limit_config["base_interval"]

    @property
    def rate_limit_window(self):
        return self._rate_limit_config["window"]

    @property
    def rate_limit_max(self):
        return self._rate_limit_config["max_requests"]

    # 重试配置访问
    @property
    def max_retries(self):
        return self._retry_config["max_retries"]

    @property
    def retry_delay(self):
        return self._retry_config["retry_delay"]

    @property
    def retry_budget_max(self):
        return self._retry_config["budget_max"]

    @property
    def retry_budget_window(self):
        return self._retry_config["budget_window"]

    def start_watching(self, file_path: str, poll_interval: float = 2.0) -> ConfigWatcher:
        """启动配置文件热重载监听."""
        self._watcher = ConfigWatcher(self, file_path, poll_interval)
        self._watcher.start()
        return self._watcher

    def stop_watching(self):
        """停止配置文件监听."""
        if self._watcher:
            self._watcher.stop()
            self._watcher = None


# 全局配置实例
config = Config()

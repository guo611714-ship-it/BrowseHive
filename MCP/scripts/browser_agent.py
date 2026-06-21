"""browser-harness + browser-use 封装模块.

browser-harness: 通过 CDP 直接连接浏览器，命令行调用
browser-use: AI 驱动的浏览器自动化

策略：browser-harness 优先（更快更直接），browser-use 作为备选
"""

import asyncio
import time
import logging
import os
import json
import subprocess
import tempfile
import ctypes
from typing import TYPE_CHECKING, Optional, Dict, Any

if TYPE_CHECKING:
    pass  # Browser type for static analysis only

logger = logging.getLogger("browser_agent")

# 审计日志
try:
    from browser_audit import get_browser_audit_log
except ImportError:
    get_browser_audit_log = None

# 常量
MAX_CDP_SCAN_ATTEMPTS = 20
DEFAULT_CDP_PORT = 9222

# 加载平台选择器配置（启动时一次）
_SELECTORS_CONFIG = None

def _load_selectors_config():
    """加载平台选择器配置."""
    global _SELECTORS_CONFIG
    if _SELECTORS_CONFIG is None:
        config_path = os.path.join(os.path.dirname(__file__), "config", "platform_selectors.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                _SELECTORS_CONFIG = json.load(f)
        except Exception as e:
            logger.warning(f"加载选择器配置失败: {e}, 使用默认值")
            _SELECTORS_CONFIG = {
                "selectors": {
                    "doubao": {"input": "textarea, [contenteditable='true'], [role='textbox']"},
                    "deepseek": {"input": "textarea, [contenteditable='true']"},
                    "volcengine": {"input": "textarea, [role='textbox']"},
                    "ouyi": {"input": "textarea, [contenteditable='true'], [role='textbox']"}
                }
            }
    return _SELECTORS_CONFIG


def _minimize_chrome_window():
    """最小化 Chrome 窗口（Windows API）。"""
    if os.name != "nt":
        return
    try:
        user32 = ctypes.windll.user32
        SW_MINIMIZE = 6
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def _callback(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            if cls.value != "Chrome_WidgetWin_1":
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            if "Google Chrome" in title:
                user32.ShowWindow(hwnd, SW_MINIMIZE)
                logger.info(f"最小化 Chrome 窗口: {title[:50]}")
                return False
            return True

        user32.EnumWindows(WNDENUMPROC(_callback), 0)
    except Exception as e:
        logger.debug(f"最小化 Chrome 窗口失败(非致命): {e}")

# 性能统计
_stats = {
    "harness_calls": 0,
    "harness_success": 0,
    "harness_fallback": 0,
    "avg_response_time": 0,
    "last_error": None,
}


def get_stats() -> dict:
    """获取性能统计."""
    return _stats.copy()


class BrowserAgent:
    """浏览器操控器 — browser-harness 优先，browser-use 备选."""

    def __init__(self):
        self._harness_available = None
        self._agents = {}  # 保留以备将来扩展
        self._chrome_process = None  # 跟踪Chrome子进程
        self._cdp_port_file = os.path.join(os.path.dirname(__file__), ".cdp_port")

    def _check_harness(self) -> bool:
        """检测 browser-harness 是否可用."""
        if self._harness_available is not None:
            return self._harness_available

        try:
            result = subprocess.run(
                ["browser-harness", "--version"],
                capture_output=True,
                timeout=5
            )
            self._harness_available = result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self._harness_available = False

        if self._harness_available:
            logger.info("browser-harness 可用")
        else:
            logger.info("browser-harness 不可用")

        return self._harness_available

    def _detect_cdp_url(self, prefer_platform: str = None) -> Optional[str]:
        """检测 CDP URL，优先返回有目标平台页面的端口.

        Chrome 147+ 禁用了 /json/version HTTP 端点，改用 socket 连接检测端口可达性。
        """
        import socket

        def _port_alive(port: int, timeout: float = 1.0) -> bool:
            """通过 TCP 连接检测端口是否可达."""
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=timeout):
                    return True
            except (OSError, TimeoutError):
                return False

        def _try_get_tabs(port: int) -> Optional[list]:
            """尝试获取标签页列表（Chrome 147+ 可能返回空/404）."""
            import urllib.request
            proxy_handler = urllib.request.ProxyHandler({})
            opener = urllib.request.build_opener(proxy_handler)
            try:
                req = opener.open(f"http://127.0.0.1:{port}/json", timeout=2)
                data = json.loads(req.read())
                return data if isinstance(data, list) else None
            except Exception:
                return None

        # 1. 优先读取ai-chat MCP保存的端口文件
        if os.path.exists(self._cdp_port_file):
            try:
                with open(self._cdp_port_file, "r") as f:
                    saved_cdp = f.read().strip()
                if saved_cdp:
                    # 从 URL 提取端口号
                    saved_port = int(saved_cdp.rstrip("/").split(":")[-1])
                    if _port_alive(saved_port):
                        _stats["last_error"] = None
                        return saved_cdp
            except Exception:
                pass

        # 2. 扫描所有端口 — 只检测 TCP 可达性，不依赖 /json/version
        from core.config import config
        ports = config.get("cdp_ports", [9222, 9223, 9224, 9225, 9333])
        best_port = None
        for port in ports:
            if not _port_alive(port):
                continue

            # 如果指定了平台，尝试获取标签页匹配
            if prefer_platform:
                tabs = _try_get_tabs(port)
                if tabs:
                    platform_urls = {"doubao": "doubao.com", "deepseek": "deepseek.com", "ouyi": "ai.rcouyi.com", "bing": "bing.com"}
                    target = platform_urls.get(prefer_platform, "")
                    for t in tabs:
                        if target in t.get("url", ""):
                            return f"http://127.0.0.1:{port}"

            if best_port is None:
                best_port = port

        return f"http://127.0.0.1:{best_port}" if best_port else None

    def _check_use(self) -> bool:
        """检测 browser-use 是否可用（已移除，返回False）."""
        # browser-use 已移除以简化架构
        return False

    def _save_cdp_port(self, cdp: str):
        """保存 CDP 端口到文件（原子写入避免竞态）."""
        try:
            # 原子写入：先写临时文件，再重命名（os.replace 在 Windows 上是原子操作）
            temp_file = self._cdp_port_file + ".tmp"
            with open(temp_file, "w") as f:
                f.write(cdp)
            os.replace(temp_file, self._cdp_port_file)
        except Exception:
            pass

    # ── Chrome CDP 管理 ────────────────────────────────────────────

    def _ensure_chrome_cdp(self) -> Optional[str]:
        """确保有 Chrome 实例在 CDP 端口上运行，返回 CDP URL."""
        # 先检查现有端口
        cdp_url = self._detect_cdp_url()
        if cdp_url:
            # 设置进程级环境变量，确保 daemon 子进程能继承
            os.environ['BU_CDP_URL'] = cdp_url
            _minimize_chrome_window()
            return cdp_url

        # 没有可用的 CDP 端口，启动新的 Chrome 实例
        from core.config import config as _cfg
        cdp_port = _cfg.get("cdp_default_port", DEFAULT_CDP_PORT)
        chrome_paths = [
            r"C:\Program Files\Google\Chrome Dev\Application\chrome.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        ]
        chrome_exe = None
        for p in chrome_paths:
            if os.path.exists(p):
                chrome_exe = p
                break
        if not chrome_exe:
            logger.error("未找到 Chrome 浏览器")
            return None

        # 用独立 user-data-dir 启动，避免和现有 Chrome 冲突
        user_data = os.path.join(tempfile.gettempdir(), "bh-chrome-cdp")
        try:
            self._chrome_process = subprocess.Popen([
                chrome_exe,
                f"--remote-debugging-port={cdp_port}",
                f"--user-data-dir={user_data}",
                "--remote-allow-origins=*",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-networking",
                "--disable-sync",
                "--disable-translate",
                "--disable-extensions",
                "about:blank",
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info(f"已启动 Chrome，CDP 端口 {cdp_port}")

            # 等待端口就绪
            import urllib.request
            from core.config import config as browser_config
            max_attempts = browser_config.get("cdp_max_scan_attempts", MAX_CDP_SCAN_ATTEMPTS)
            ready_timeout = browser_config.get("cdp_ready_timeout", 10)
            sleep_interval = ready_timeout / max_attempts if max_attempts > 0 else 0.5
            for attempt in range(max_attempts):
                time.sleep(sleep_interval)
                try:
                    req = urllib.request.urlopen(f"http://127.0.0.1:{cdp_port}/json/version", timeout=2)
                    if "Browser" in req.read().decode():
                        cdp_url = f"http://127.0.0.1:{cdp_port}"
                        # 原子更新 .cdp_port 文件
                        self._save_cdp_port(cdp_url)
                        # 设置进程级环境变量，确保 daemon 子进程能继承
                        os.environ['BU_CDP_URL'] = cdp_url
                        logger.info(f"Chrome CDP 就绪: {cdp_url}")
                        _minimize_chrome_window()
                        return cdp_url
                except Exception:
                    pass
            logger.error(f"Chrome CDP 端口 {cdp_port} 未就绪")
            return None
        except Exception as e:
            logger.error(f"启动 Chrome CDP 失败: {e}")
            return None

    # ── browser-harness 方法 ──────────────────────────────────────

    def _harness_send(self, page, message: str, platform: str) -> dict:
        """使用 browser-harness 发送消息（同步，带3次重试）."""
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                # 构造 Python 代码
                code = self._get_harness_code(message, platform)

                # 确保有 CDP 端口可用
                cdp_url = self._ensure_chrome_cdp()
                env = os.environ.copy()
                if cdp_url:
                    env['BU_CDP_URL'] = cdp_url
                    try:
                        subprocess.run(
                            ['browser-harness', '--reload'],
                            capture_output=True, timeout=5, env=env
                        )
                    except Exception:
                        pass

                # 重启 browser-harness daemon
                try:
                    subprocess.run(
                        ['browser-harness', '--reload'],
                        capture_output=True,  # 二进制模式
                        timeout=5, env=env
                    )
                except Exception:
                    pass

                # 执行 browser-harness (UTF-8 编码输入)
                env['PYTHONIOENCODING'] = 'utf-8'
                env['PYTHONUTF8'] = '1'
                result = subprocess.run(
                    ['browser-harness'],
                    input=code.encode('utf-8'),  # 编码为 UTF-8 bytes
                    capture_output=True,
                    text=False,  # 保持二进制
                    timeout=30,
                    env=env
                )

                # 解码输出（UTF-8 with fallback）
                stdout = result.stdout.decode('utf-8', errors='replace') if result.stdout else ""
                stderr = result.stderr.decode('utf-8', errors='replace') if result.stderr else ""

                # 即使 returncode 非零，只要 stdout 含 "OK" 就视为成功
                if "OK" in stdout:
                    return {"ok": True, "method": "browser-harness", "error": None, "output": stdout}
                if result.returncode == 0:
                    return {"ok": True, "method": "browser-harness", "error": None, "output": stdout}

                last_error = stderr[:200]
                # 非致命错误可重试：timeout、元素未找到
                if attempt < max_retries - 1 and any(kw in last_error for kw in ["timeout", "Timeout", "not found", "no element"]):
                    time.sleep(1 * (attempt + 1))  # 递增等待
                    continue
                return {"ok": False, "method": "browser-harness", "error": last_error}

            except subprocess.TimeoutExpired:
                last_error = "timeout"
                if attempt < max_retries - 1:
                    time.sleep(1 * (attempt + 1))
                    continue
                return {"ok": False, "method": "browser-harness", "error": "timeout"}
            except Exception as e:
                logger.error(f"browser-harness 发送失败: {e}")
                return {"ok": False, "method": "browser-harness", "error": str(e)}

        return {"ok": False, "method": "browser-harness", "error": last_error or "max retries exceeded"}

    def _get_harness_code(self, message: str, platform: str) -> str:
        '''生成 browser-harness Python 代码.

        使用 type_text + press_key 替代 js() 设置值，避免 surrogate 编码错误。
        '''
        # 从配置文件加载选择器
        cfg = _load_selectors_config()
        platform_configs = cfg.get("selectors", {})
        input_selector = platform_configs.get(platform, {}).get("input", "textarea")
        msg_repr = repr(message)

        # 使用普通 triple-quoted string + % 格式化，避免 f-string 花括号冲突
        # 使用 .format() 替代 % 格式化，避免潜在的注入风险
        code_template = (
            '''
import time
_domain = "{domain}"
_tabs = list_tabs()
_switched = False
for _t in _tabs:
    if _domain and _domain in _t.get("url", "").lower():
        switch_tab(_t["targetId"])
        _switched = True
        break
if not _switched:
    page = ensure_real_tab()
wait_for_load()

try:
    input_info = js("""
        const sels = {selectors};
        for (const s of sels) {{
            const el = document.querySelector(s);
            if (el && el.offsetParent !== null) {{
                const rect = el.getBoundingClientRect();
                return {{x: rect.x + rect.width/2, y: rect.y + rect.height/2, found: true}};
            }}
        }}
        return {{found: false}};
    """)
except Exception:
    input_info = {{"found": False}}

if input_info and input_info.get("found"):
    click_at_xy(input_info["x"], input_info["y"])
    time.sleep(0.3)
    type_text({msg})
    time.sleep(0.3)
    press_key("Enter")
    print("OK: message sent")
else:
    click_at_xy(600, 662)
    time.sleep(0.3)
    type_text({msg})
    time.sleep(0.3)
    press_key("Enter")
    print("OK: message sent (fallback)")
'''
        )
        _platform_domains = {
            "doubao": "doubao.com",
            "deepseek": "deepseek.com",
            "ouyi": "ai.rcouyi.com",
            "kimi": "kimi.moonshot.cn",
            "chatglm": "chatglm.cn",
            "volcengine": "volcengine.com",
            "bing": "bing.com",
        }
        domain = _platform_domains.get(platform, platform)
        # 硬编码selectors避免配置文件编码问题
        _default_selectors = ["textarea", "[contenteditable='true']", "[role='textbox']"]
        selectors_js = json.dumps(_default_selectors)
        code = code_template.format(selectors=selectors_js, msg=msg_repr, domain=domain)
        return code
    async def _use_send(self, page, message: str, platform: str) -> dict:
        """browser-use 已移除."""
        return {"ok": False, "method": "removed", "error": "browser-use removed for simplification"}

    # ── 公共接口 ──────────────────────────────────────────────────

    async def send_message(self, page, message: str, platform: str = "doubao") -> dict:
        """发送消息到 AI 平台（仅 browser-harness）."""
        start = time.time()
        audit = get_browser_audit_log() if get_browser_audit_log else None

        if self._check_harness():
            _stats["harness_calls"] += 1
            result = self._harness_send(page, message, platform)
            elapsed = time.time() - start

            # P2: 记录操作审计
            if audit:
                audit.log_step(
                    step_name=f"send_{platform}",
                    action="send_message",
                    params={"platform": platform, "msg_len": len(message)},
                    result={"ok": result.get("ok"), "method": result.get("method"), "elapsed": round(elapsed, 2)},
                )

            if result.get("ok"):
                _stats["harness_success"] += 1
                self._update_avg_time(elapsed)
                return result

            _stats["harness_fallback"] += 1
            _stats["last_error"] = result.get("error", "")[:100]
            return result

        return {"ok": False, "method": "browser-harness", "error": "browser-harness not available"}

    def _get_ws_url_for_platform(self, cdp_url: str, platform: str) -> str:
        """获取指定平台标签页的WebSocket URL."""
        try:
            import urllib.request
            from core.platforms import PLATFORMS
            tabs = json.loads(urllib.request.urlopen(f"{cdp_url}/json", timeout=5).read())

            # 获取平台URL域名用于匹配
            platform_url = PLATFORMS.get(platform, {}).get("url", "")
            platform_domain = ""
            if platform_url:
                from urllib.parse import urlparse
                platform_domain = urlparse(platform_url).netloc.lower()

            # 优先匹配平台域名的标签页
            best_ws = ""
            for t in tabs:
                if t.get("type") != "page" or not t.get("webSocketDebuggerUrl"):
                    continue
                tab_url = t.get("url", "").lower()
                if platform_domain and platform_domain in tab_url:
                    return t["webSocketDebuggerUrl"]
                if not best_ws:
                    best_ws = t["webSocketDebuggerUrl"]

            return best_ws
        except Exception:
            return ""

    async def get_response(self, page, platform: str = "doubao", timeout: int = 120) -> str:
        """获取 AI 响应（通过CDP直接执行JS，智能等待完成）."""
        cdp_url = self._detect_cdp_url(prefer_platform=platform)
        if not cdp_url:
            return ""

        import websocket
        import random

        ws_url = self._get_ws_url_for_platform(cdp_url, platform)
        if not ws_url:
            return ""

        # 多平台响应容器选择器
        _EXTRACT_JS = """(function() {
            var selectors = ['[class*="md-box-root"]', '[class*="ds-markdown"]', '[class*="markdown"]'];
            for (var s of selectors) {
                var els = document.querySelectorAll(s);
                if (els.length > 0) {
                    var last = els[els.length - 1];
                    var text = (last.textContent || '').trim();
                    if (text.length > 5) return text;
                }
            }
            return '';
        })()"""

        _COUNT_JS = """(function() {
            var selectors = ['[class*="md-box-root"]', '[class*="ds-markdown"]', '[class*="markdown"]'];
            for (var s of selectors) {
                var els = document.querySelectorAll(s);
                if (els.length > 0) return els.length;
            }
            return 0;
        })()"""

        try:
            ws = websocket.create_connection(ws_url, timeout=10)
            try:
                # 获取初始消息数
                msg_id = random.randint(1, 999999)
                ws.send(json.dumps({"id": msg_id, "method": "Runtime.evaluate",
                                    "params": {"expression": _COUNT_JS, "returnByValue": True}}))
                resp = json.loads(ws.recv())
                initial_count = (resp.get("result") or {}).get("result", {}).get("value", 0) or 0

                # 等待新消息出现或文本变化
                start = time.time()
                last_text = ""
                stable_count = 0
                seen_new_count = False
                while time.time() - start < timeout:
                    msg_id = random.randint(1, 999999)
                    ws.send(json.dumps({"id": msg_id, "method": "Runtime.evaluate",
                                        "params": {"expression": _EXTRACT_JS, "returnByValue": True}}))
                    resp = json.loads(ws.recv())
                    text = (resp.get("result") or {}).get("result", {}).get("value", "") or ""

                    current_count = 0
                    try:
                        msg_id2 = random.randint(1, 999999)
                        ws.send(json.dumps({"id": msg_id2, "method": "Runtime.evaluate",
                                            "params": {"expression": _COUNT_JS, "returnByValue": True}}))
                        resp2 = json.loads(ws.recv())
                        current_count = (resp2.get("result") or {}).get("result", {}).get("value", 0) or 0
                    except Exception:
                        pass

                    # 检测到新消息
                    if current_count > initial_count:
                        seen_new_count = True

                    # 有文本且稳定2次就返回（兼容新消息和文本变化两种情况）
                    if text and len(text) > 10:
                        if text == last_text:
                            stable_count += 1
                            if stable_count >= 2:
                                return text
                        else:
                            last_text = text
                            stable_count = 0
                    time.sleep(1)

                return last_text or ""
            finally:
                ws.close()
        except ImportError:
            return ""
        except Exception as e:
            logger.error(f"CDP get_response 失败: {e}")
            return ""

    def _get_harness_response_code(self, platform: str, timeout: int = None, initial_count: int = 0) -> str:
        """生成读取AI响应的 browser-harness 代码."""
        cfg = _load_selectors_config()
        browser_cfg = cfg.get("browser", {})
        if timeout is None:
            timeout = browser_cfg.get("harness_timeout", 60)

        # 通用响应读取模板
        platform_urls = {
            "doubao": "https://www.doubao.com/chat/",
            "deepseek": "https://chat.deepseek.com/",
            "ouyi": "https://ai.rcouyi.com/chat/3244281610078725",
            "bing": "https://cn.bing.com/",
        }
        platform_url = platform_urls.get(platform, "https://www.doubao.com/chat/")

        # 从配置文件获取响应选择器，作为fallback
        platform_selectors = cfg.get("selectors", {}).get(platform, {})
        response_selectors = platform_selectors.get("response", [])
        # 将选择器列表转为JS数组字符串，用于fallback匹配
        selectors_js = json.dumps(response_selectors) if response_selectors else "[]"

        _RESP_TEMPLATE = '''
page = ensure_real_tab()
wait_for_load()

url = js("return window.location.href")
if "{platform}" not in str(url) and "doubao" not in str(url) and "deepseek" not in str(url):
    goto_url("{platform_url}")
    wait_for_load()
    import time
    time.sleep(3)

import time
start = time.time()
prev_text = ""
stable_count = 0
network_idle_count = 0

while time.time() - start < {timeout}:
    # 智能等待: 检查网络是否空闲（无进行中的 XHR/fetch）
    try:
        net_status = js("""
            if (typeof _pendingRequests === "undefined") {{
                window._pendingRequests = 0;
            }}
            return {{pending: window._pendingRequests || 0, ready: document.readyState}};
        """)
        if isinstance(net_status, dict):
            pending = net_status.get("pending", 0)
            doc_ready = net_status.get("ready", "complete")
        else:
            pending = 0
            doc_ready = "complete"
        if pending == 0 and doc_ready == "complete":
            network_idle_count += 1
        else:
            network_idle_count = 0
    except Exception:
        network_idle_count = 1  # 无法检测时假设就绪

    try:
        # 将选择器列表注入JS代码
        _selectors_str = json.dumps(response_selectors) if response_selectors else "[]"
        _result = js("""
            var _selectors = """ + _selectors_str + """;
            var _result = {text: ""};

            for (var si = 0; si < _selectors.length; si++) {
                var _els = document.querySelectorAll(_selectors[si]);
                for (var _i = _els.length - 1; _i >= 0; _i--) {
                    var _t = (_els[_i].innerText || _els[_i].textContent || "").trim();
                    if (_t.length > 20 && _t.length < 8000
                        && _t.indexOf("Error") === -1
                        && _t.indexOf("TypeError") === -1
                        && _t.indexOf("重试") === -1) {
                        _result.text = _t;
                        break;
                    }
                }
                if (_result.text) break;
            }

            if (!_result.text) {
                var allDivs = document.querySelectorAll("div");
                var textNodes = [];
                for (var i = 0; i < allDivs.length; i++) {
                    var el = allDivs[i];
                    if (el.children.length === 0) {
                        var t = (el.textContent || "").trim();
                        if (t.length > 15) {
                            var parent = el.parentElement;
                            var gp = parent ? parent.parentElement : null;
                            var gpCls = (gp && gp.className) ? gp.className : "";
                            var pCls = (parent && parent.className) ? parent.className : "";
                            if (t.indexOf("内容由") !== -1 || t.indexOf("AI 生成") !== -1
                                || t.indexOf("下载电脑版") !== -1 || t.indexOf("新对话") !== -1
                                || t.indexOf("历史对话") !== -1 || t.indexOf("超能模式") !== -1
                                || t.indexOf("帮我写作") !== -1 || t.indexOf("PPT 生成") !== -1
                                || t.indexOf("图像生成") !== -1 || t.indexOf("更多") !== -1
                                || t.indexOf("Ctrl K") !== -1 || t.indexOf("AI 创作") !== -1
                                || t.indexOf("云盘") !== -1 || t.indexOf("专家") !== -1
                                || t.indexOf("Beta") !== -1 || t.indexOf("主页") !== -1
                                || t.indexOf("绘画") !== -1 || t.indexOf("画廊") !== -1
                                || t.indexOf("思维导图") !== -1 || t.indexOf("白板") !== -1
                                || t.indexOf("客户端") !== -1 || t.indexOf("画布绘画") !== -1
                                || t.indexOf("内容举报") !== -1 || t.indexOf("高级VIP") !== -1
                                || t.indexOf("Error") !== -1 || t.indexOf("TypeError") !== -1
                                || pCls.indexOf("justify-end") !== -1) {
                                continue;
                            }
                            if (gpCls.indexOf("container-") !== -1
                                || gpCls.indexOf("flow-") !== -1
                                || gpCls.indexOf("markdown") !== -1
                                || gpCls.indexOf("assist") !== -1) {
                                textNodes.push({text: t, priority: 2});
                            } else if (pCls.indexOf("assist") !== -1 || pCls.indexOf("ai") !== -1) {
                                textNodes.push({text: t, priority: 3});
                            } else {
                                textNodes.push({text: t, priority: 1});
                            }
                        }
                    }
                }
                for (var j = textNodes.length - 1; j >= 0; j--) {
                    if (textNodes[j].priority >= 2) {
                        _result.text = textNodes[j].text;
                        break;
                    }
                }
                if (!_result.text && textNodes.length > 0) {
                    _result.text = textNodes[textNodes.length - 1].text;
                }
            }

            if (!_result.text) {
                var fallbackDivs = document.querySelectorAll("div");
                for (var k = fallbackDivs.length - 1; k >= 0; k--) {
                    var ft = (fallbackDivs[k].textContent || "").trim();
                    if (ft.length > 30 && ft.length < 5000
                        && ft.indexOf("Error") === -1
                        && ft.indexOf("TypeError") === -1) {
                        _result.text = ft;
                        break;
                    }
                }
            }

            return _result;
        """)
        text = result.get('text', '') if isinstance(result, dict) else ''
    except Exception:
        text = ""

    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        text = text.encode("utf-8", errors="replace").decode("utf-8")

    if text and len(text) > 10:
        if text == prev_text:
            stable_count += 1
            # 需要: 文本稳定 2 次 + 网络空闲 1 次
            if stable_count >= 2 and network_idle_count >= 1:
                print(text)
                break
        else:
            prev_text = text
            stable_count = 0
    time.sleep(1)
else:
    if prev_text:
        print(prev_text)
    else:
        print("")
'''
        return _RESP_TEMPLATE.format(timeout=timeout, platform=platform, platform_url=platform_url, selectors_js=selectors_js)

    async def switch_mode(self, page, platform: str) -> dict:
        """切换到最佳模式."""
        if not self._check_harness():
            return {"switched": False, "error": "browser-harness not available"}

        try:
            codes = {
                "deepseek": '''
page = ensure_real_tab()
wait_for_load()
js("""
    const radios = document.querySelectorAll('[role="radio"]');
    for (const r of radios) {
        if (r.innerText.includes('专家') && r.getAttribute('aria-checked') !== 'true') {
            r.click();
            return {switched: true};
        }
    }
    return {switched: false};
""")
print("OK: mode check done")
''',
                "doubao": '''
page = ensure_real_tab()
wait_for_load()
print("OK: doubao mode check done")
''',
                "volcengine": '''
page = ensure_real_tab()
wait_for_load()
print("OK: volcengine mode check done")
''',
            }

            code = codes.get(platform)
            if not code:
                return {"switched": False}

            # 检测 CDP URL（优先找有目标平台页面的端口）
            cdp_url = self._detect_cdp_url(prefer_platform=platform)
            env = os.environ.copy()
            if cdp_url:
                env['BU_CDP_URL'] = cdp_url
                # 强制重启 daemon 以确保使用正确的 CDP URL
                try:
                    subprocess.run(
                        ['browser-harness', '--reload'],
                        capture_output=True, timeout=5, env=env
                    )
                except Exception:
                    pass

            result = subprocess.run(
                ['browser-harness'],
                input=code,
                capture_output=True,
                text=True,
                timeout=15,
                env=env
            )
            return {"switched": result.returncode == 0, "mode": "browser-harness"}

        except Exception as e:
            logger.error(f"browser-harness 切换模式失败: {e}")
            return {"switched": False, "error": str(e)}

    async def check_input_ready(self, page) -> dict:
        """检查输入框是否可用（通过 browser-harness）."""
        if not self._check_harness():
            return {"found": False, "error": "browser-harness not available"}
        try:
            code = '''
page = ensure_real_tab()
wait_for_load()
try:
    result = js("""
        const sels = ['textarea', '[contenteditable="true"]', '[role="textbox"]'];
        for (const s of sels) {
            const el = document.querySelector(s);
            if (el && el.offsetParent !== null) return {found: true};
        }
        return {{found: false}};
    """)
except Exception:
    result = {{found: False}}
print(str(result))
'''
            cdp_url = self._detect_cdp_url()
            env = os.environ.copy()
            if cdp_url:
                env['BU_CDP_URL'] = cdp_url
            r = subprocess.run(
                ['browser-harness'], input=code, capture_output=True, text=True, timeout=10, env=env
            )
            if r.returncode == 0:
                import ast
                try:
                    return ast.literal_eval(r.stdout.strip())
                except Exception:
                    return {"found": True}
            return {"found": False, "error": r.stderr[:200]}
        except Exception as e:
            return {"found": False, "error": str(e)}

    def _update_avg_time(self, new_time: float):
        """更新平均响应时间."""
        current = _stats["avg_response_time"]
        total_calls = _stats["harness_success"]
        if total_calls > 0:
            _stats["avg_response_time"] = (current * (total_calls - 1) + new_time) / total_calls
        else:
            _stats["avg_response_time"] = new_time

    def invalidate(self):
        """使缓存失效."""
        self._agents.clear()
        self._harness_available = None
        # 终止Chrome子进程（如果由本实例启动）
        if self._chrome_process:
            try:
                self._chrome_process.terminate()
                self._chrome_process.wait(timeout=5)
            except Exception:
                try:
                    self._chrome_process.kill()
                except Exception:
                    pass
            finally:
                self._chrome_process = None

    def ensure_ready(self) -> bool:
        """确保浏览器 CDP 就绪."""
        return self._ensure_chrome_cdp() is not None

    def open_platform(self, platform_key: str, url: str) -> bool:
        """在浏览器中打开平台页面（通过 browser-harness 执行 goto）."""
        cdp_url = self._detect_cdp_url(platform_key)
        if not cdp_url:
            return False
        env = os.environ.copy()
        env['BU_CDP_URL'] = cdp_url
        # 生成并执行打开页面的代码
        code = f'''
page = ensure_real_tab()
wait_for_load()
page.goto("{url}")
wait_for_load()
print("OK: opened {url}")
'''
        try:
            result = subprocess.run(
                ['browser-harness'],
                input=code.encode('utf-8'),
                capture_output=True,
                text=False,
                timeout=30,
                env=env
            )
            stdout = result.stdout.decode('utf-8', errors='replace') if result.stdout else ""
            return result.returncode == 0 or "OK" in stdout
        except Exception as e:
            logger.error(f"browser-harness 打开平台失败: {e}")
            return False

    def get_current_url(self) -> Optional[str]:
        """获取当前标签页 URL（仅当浏览器已启动）."""
        cdp_url = self._detect_cdp_url()
        if not cdp_url:
            return None
        # 通过执行 JS 获取 URL
        code = '''
page = ensure_real_tab()
wait_for_load()
print(window.location.href)
'''
        env = os.environ.copy()
        env['BU_CDP_URL'] = cdp_url
        try:
            result = subprocess.run(
                ['browser-harness'],
                input=code.encode('utf-8'),
                capture_output=True,
                text=False,
                timeout=10,
                env=env
            )
            stdout = result.stdout.decode('utf-8', errors='replace') if result.stdout else ""
            return stdout.strip()
        except Exception:
            return None


# 全局实例
_browser_agent = None


def get_browser_agent() -> BrowserAgent:
    """获取全局 BrowserAgent 实例."""
    global _browser_agent
    if _browser_agent is None:
        _browser_agent = BrowserAgent()
    return _browser_agent


def reset_browser_agent():
    """重置全局 BrowserAgent."""
    global _browser_agent
    if _browser_agent:
        _browser_agent.invalidate()
    _browser_agent = None

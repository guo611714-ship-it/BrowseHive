"""聊天引擎 - 负责与AI平台交互."""

import time
import asyncio
import hashlib
from collections import deque
from typing import Optional, Dict, Any

from .config import config
from .platforms import PLATFORMS, is_login_page
from .cache_manager import cache_manager

# 常量
SEND_TIMEOUT_DEFAULT = 30  # 发送消息默认超时（秒）
MAX_NO_RESPONSE_ATTEMPTS = 7  # 无响应快速失败阈值
MAX_NO_RESPONSE_ATTEMPTS_KEY = "max_no_response_attempts"

# 熔断器常量
CIRCUIT_BREAKER_THRESHOLD = 3  # 连续失败次数触发熔断
CIRCUIT_BREAKER_COOLDOWN = 60  # 熔断冷却时间（秒）
CIRCUIT_BREAKER_RESET_WINDOW = 300  # 成功后重置计数的窗口（秒）

# 心跳检测常量
HEARTBEAT_INTERVAL = 10  # 心跳检测间隔（秒）
HEARTBEAT_TIMEOUT = 5  # 单次心跳超时（秒）
HEARTBEAT_WINDOW_SIZE = 5  # 滑动窗口大小：最近N次心跳检测


class HeartbeatError(Exception):
    """浏览器心跳连续失败异常，触发熔断器和重试."""
    pass

# 使用 browser_agent (可选)
try:
    from browser_agent import get_browser_agent
    BROWSER_AGENT_AVAILABLE = True
except ImportError:
    BROWSER_AGENT_AVAILABLE = False
    def get_browser_agent():
        return None

class ChatEngine:
    """聊天引擎."""

    def __init__(self):
        self._fetch_stats = {}
        self._error_stats = {}
        self._response_times = {}
        self._response_quality_log = []
        self._active_requests = {}
        self._inflight_requests = {}
        self._retry_budget = []
        self._dedup_enabled = True
        self._message_dedup = {}
        self._message_dedup_content = {}  # 存储消息内容用于近似匹配
        self._rate_limiter = {}
        self._circuit_breakers = {}  # 熔断器状态: {platform: {failures, last_failure, opened_at}}
        # 锁保护共享状态
        self._lock_inflight = asyncio.Lock()
        self._lock_dedup = asyncio.Lock()
        self._lock_rate = asyncio.Lock()
        self._lock_retry = asyncio.Lock()
        self._lock_stats = asyncio.Lock()
        self._lock_quality = asyncio.Lock()  # 保护 _response_quality_log
        self._lock_circuit = asyncio.Lock()  # 保护熔断器状态

    async def _cleanup_request(self, platform_key: str, cache_key: tuple, our_future):
        """清理请求状态 — 统一锁顺序：stats → inflight，不嵌套."""
        async with self._lock_stats:
            if platform_key in self._active_requests:
                self._active_requests[platform_key]["count"] -= 1
        async with self._lock_inflight:
            entry = self._inflight_requests.get(cache_key)
            if entry and entry["future"] is our_future:
                del self._inflight_requests[cache_key]

    async def chat(self, platform_key: str, message: str, timeout: int = 120) -> str:
        """发送消息到指定平台并获取响应（线程安全版本）."""
        # 自动恢复会话（如果从未恢复，延迟导入避免循环依赖）
        if not getattr(self, '_session_restored', False):
            try:
                from .monitor import session_manager as _session_manager
                await _session_manager.restore_snapshot()
            except Exception:
                pass
            self._session_restored = True

        cache_key = (platform_key, hashlib.md5(message.encode()).hexdigest())

        # 1. 检查缓存（先于inflight锁，避免膨胀inflight表）
        cached = await cache_manager.get_response(platform_key, message)
        if cached:
            return cached

        # 2. 获取 inflight 锁，处理请求合并
        loop = asyncio.get_event_loop()
        async with self._lock_inflight:
            if cache_key in self._inflight_requests:
                inflight = self._inflight_requests[cache_key]
                inflight["count"] += 1
                our_future = inflight["future"]
                is_primary = False
            else:
                our_future = loop.create_future()
                self._inflight_requests[cache_key] = {"future": our_future, "count": 1}
                is_primary = True

        if not is_primary:
            try:
                result = await asyncio.wait_for(our_future, timeout=timeout)
            except asyncio.TimeoutError:
                result = f"[超时] {PLATFORMS[platform_key]['name']} 合并请求等待超时"
            except Exception as e:
                result = f"[错误] 合并请求失败: {str(e)[:50]}"
            return result

        # 3. 主请求：衰减统计、更新活跃计数（使用独立锁，不嵌套inflight）
        async with self._lock_stats:
            self._decay_error_stats()
            if platform_key not in self._active_requests:
                self._active_requests[platform_key] = {"count": 0, "start": time.time(), "total": 0}
            self._active_requests[platform_key]["count"] += 1
            self._active_requests[platform_key]["total"] += 1

        # 4. 安全检查（可选）
        try:
            if BROWSER_AGENT_AVAILABLE:
                agent = get_browser_agent()
                current_url = await asyncio.to_thread(agent.get_current_url)
                if current_url and is_login_page(current_url, platform_key):
                    await self._cleanup_request(platform_key, cache_key, our_future)
                    return f"[需要登录] {PLATFORMS[platform_key]['name']} 需要登录"
        except Exception:
            pass

        # 5. 限流和去重检查
        async with self._lock_rate:
            rate_msg = self._check_rate_limit(platform_key)
        if rate_msg:
            await self._cleanup_request(platform_key, cache_key, our_future)
            return rate_msg

        async with self._lock_dedup:
            dedup_msg = self._check_message_dedup(platform_key, message)
        if dedup_msg:
            await self._cleanup_request(platform_key, cache_key, our_future)
            return dedup_msg

        # 6. 主请求执行
        try:
            try:
                effective_timeout = min(timeout, config.chat_timeout)
                result = await self._do_chat_with_retry(platform_key, message, effective_timeout)
            except Exception as e:
                result = f"[错误] {PLATFORMS[platform_key]['name']} 重试后失败: {str(e)[:100]}"
            except asyncio.CancelledError:
                if not our_future.done():
                    our_future.set_exception(asyncio.CancelledError())
                raise
            # 通知等待者
            if not our_future.done():
                our_future.set_result(result)
            return result
        finally:
            # 7. 清理
            await self._cleanup_request(platform_key, cache_key, our_future)

    def assess_complexity(self, message: str) -> dict:
        """评估任务复杂度，返回等级和推荐平台。

        新逻辑：
        - 所有任务都通过能力匹配（移除代码任务的L3特殊处理）
        - 如果best_score>0（有匹配平台）：
          - L1 (<5字符): 短文本，直接发送，不树状
          - L2/L3 (>=5字符): 树状调用，主平台=best_platform，辅助平台=其他平台top 2
        - 如果best_score==0: 按健康评分选择，不树状
        """
        from core.platforms import PLATFORMS, PLATFORM_CAPABILITIES
        char_count = len(message)
        msg_lower = message.lower()

        # 检测平台能力匹配
        platform_scores = {}
        for pk, caps in PLATFORM_CAPABILITIES.items():
            score = sum(1 for cap in caps if cap in msg_lower)
            platform_scores[pk] = score

        best_platform = max(platform_scores, key=platform_scores.get) if platform_scores else ""
        best_score = platform_scores.get(best_platform, 0) if best_platform else 0

        # 有平台能力匹配
        if best_score > 0:
            # L1: 极短文本 (<5字符) → 直接发送
            if char_count < 5:
                return {
                    "level": 1,
                    "platform": best_platform,
                    "reason": "极短文本",
                    "tree": False
                }

            # L2/L3: >=5字符 → 树状调用
            # 辅助平台：按能力匹配分数降序选择其他平台，取top 2
            other_platforms = sorted(
                [(pk, score) for pk, score in platform_scores.items() if pk != best_platform],
                key=lambda x: x[1],
                reverse=True
            )
            secondary = [pk for pk, _ in other_platforms[:2]]

            return {
                "level": 2 if char_count < 100 else 3,
                "platform": best_platform,
                "reason": "能力匹配" if char_count < 100 else "复杂任务",
                "tree": True,
                "tree_config": {
                    "layer1": best_platform,
                    "layer2": secondary,
                }
            }

        # 无能力匹配：按健康评分选择单一平台
        if not message:
            return {"level": 1, "platform": "doubao", "reason": "空消息", "tree": False}

        platform = self.recommend_platform(message)
        if not platform:
            platform = "doubao"

        return {
            "level": 2,
            "platform": platform,
            "reason": "健康评分优选",
            "tree": False
        }

    def recommend_platform(self, message: str) -> str:
        """智能平台推荐：结合任务匹配度+健康评分+历史表现，返回最优平台key。

        使用ChatEngine实例的运行时统计信息。
        """
        if not message:
            return ""

        msg_lower = message.lower()

        # 1. 关键词匹配分 (0-10)
        from core.platforms import PLATFORM_CAPABILITIES
        keyword_scores = {}
        for platform, keywords in PLATFORM_CAPABILITIES.items():
            score = sum(1 for kw in keywords if kw in msg_lower)
            keyword_scores[platform] = min(score * 2, 10)

        # 2. 健康评分 (0-10)，使用self访问运行时统计
        health_scores = {}
        for pk in PLATFORMS.keys():
            health = 10

            # 错误扣分
            stats = self._error_stats.get(pk, {})
            total_err = sum(stats.values())
            if total_err > 5:
                health -= min(total_err * 0.5, 5)

            # 响应时间扣分
            times = self._response_times.get(pk, [])
            if times:
                avg_time = sum(times) / len(times)
                if avg_time > 10:
                    health -= min((avg_time - 10) * 0.3, 3)

            # 成功率加分
            fs = self._fetch_stats.get(pk, {})
            total_fetch = fs.get("success", 0) + fs.get("fail", 0)
            if total_fetch > 0:
                success_rate = fs["success"] / total_fetch
                health += (success_rate - 0.5) * 4

            # 响应质量加分
            if self._response_quality_log:
                quality_scores = [q["score"] for q in self._response_quality_log if q["platform"] == pk]
                if quality_scores:
                    avg_quality = sum(quality_scores[-5:]) / min(len(quality_scores), 5)
                    health += (avg_quality - 5) * 0.5

            health_scores[pk] = max(0, min(health, 10))

        # 3. 综合评分 (关键词60% + 健康40%)
        final_scores = {}
        for pk in PLATFORMS.keys():
            kw = keyword_scores.get(pk, 0)
            hp = health_scores.get(pk, 5)
            if kw == 0:
                final_scores[pk] = hp * 0.3
            else:
                final_scores[pk] = kw * 0.6 + hp * 0.4

        if not final_scores:
            return ""

        best = max(final_scores, key=final_scores.get)
        # 如果最高分太低，返回空
        if final_scores[best] < 1:
            return ""
        return best

    async def _do_chat_with_retry(self, platform_key: str, message: str, timeout: int) -> str:
        """带重试的聊天（集成熔断器）."""
        last_error = None
        max_retries = config.max_retries
        base_delay = config.retry_delay

        start_time = time.time()  # 开始计时

        # 熔断器快速失败检查
        async with self._lock_circuit:
            cb_msg = self._circuit_is_open(platform_key)
            if cb_msg:
                raise Exception(cb_msg)

        for attempt in range(max_retries):
            try:
                effective_timeout = self._get_dynamic_timeout(platform_key, timeout)
                result = await self._send_message(platform_key, message, effective_timeout)
                elapsed = time.time() - start_time  # 计算耗时

                async with self._lock_stats:
                    self._record_response_time(platform_key, elapsed)
                    self._incr_fetch_stats(platform_key, success=True, elapsed=elapsed)
                async with self._lock_circuit:
                    self._circuit_record_success(platform_key)

                result = self._normalize_response(result, platform_key)
                result = self._compress_response(result)
                await cache_manager.set_response(platform_key, message, result)
                await self._record_quality(platform_key, result, message)  # 记录质量（异步加锁）

                return result

            except Exception as e:
                last_error = e
                async with self._lock_circuit:
                    self._circuit_record_failure(platform_key)
                if attempt < max_retries - 1:
                    # 重试预算检查（retry 锁保护）
                    async with self._lock_retry:
                        if not self._check_retry_budget():
                            break
                        self._record_retry()
                    delay = base_delay * (2 ** attempt)
                    await asyncio.sleep(delay)

        # 失败统计
        elapsed = time.time() - start_time  # 计算总耗时
        async with self._lock_stats:
            self._incr_fetch_stats(platform_key, success=False, elapsed=elapsed)
            self._record_error(platform_key, "retry_exhausted")
        raise last_error or Exception("Unknown error")

    async def _send_message(self, platform_key: str, message: str, timeout: int) -> str:
        """发送消息的核心逻辑（基于 browser_agent，替代 Playwright）.

        改进点：
        - send_message 和 get_response 使用独立超时
        - get_response 循环中集成心跳检测，浏览器无响应时提前终止
        - 不同阶段的错误类型区分开
        """
        if not BROWSER_AGENT_AVAILABLE:
            return "[错误] browser_agent 不可用"

        agent = get_browser_agent()
        # 确保浏览器就绪
        if not agent.ensure_ready():
            return f"[错误] 浏览器不可用"

        # 检查登录页（可选，为了安全）
        current_url = agent.get_current_url()
        if current_url and is_login_page(current_url, platform_key):
            return f"[需要登录] {PLATFORMS[platform_key]['name']} 需要登录"

        overall_start = time.time()

        # ── 阶段1: 发送消息（独立超时） ──
        send_timeout = config.get("send_timeout", SEND_TIMEOUT_DEFAULT)
        try:
            send_ok = await asyncio.wait_for(
                agent.send_message(None, message, platform_key),
                timeout=send_timeout
            )
            if not send_ok or not isinstance(send_ok, dict) or not send_ok.get("ok"):
                return f"[错误][发送阶段] 发送失败: {send_ok}"
        except asyncio.TimeoutError:
            return "[错误][发送阶段] send_message超时"
        except Exception as e:
            return f"[错误][发送阶段] 发送异常: {str(e)[:100]}"

        send_elapsed = time.time() - overall_start

        # ── 阶段2: 获取响应（独立超时，含心跳检测） ──
        response_timeout = max(10, timeout - int(send_elapsed))
        heartbeat_results = deque(maxlen=HEARTBEAT_WINDOW_SIZE)

        try:
            # 使用 get_response_with_heartbeat 替代直接调用，集成心跳检测
            response = await self._get_response_with_heartbeat(
                agent, platform_key, response_timeout, heartbeat_results
            )
            if response and not response.startswith("[错误") and not response.startswith("[超时") and len(response.strip()) > 0:
                return response
            return f"[错误][响应阶段] 响应无效: {response}"
        except (asyncio.TimeoutError, HeartbeatError):
            raise  # 向上传播，触发熔断器和重试
        except Exception as e:
            return f"[错误][响应阶段] 获取响应异常: {str(e)[:100]}"

    async def _get_response_with_heartbeat(self, agent, platform_key: str, timeout: int,
                                            heartbeat_results: deque) -> str:
        """带心跳检测的 get_response 封装.

        在等待浏览器响应的过程中定期检查浏览器是否存活，
        如果浏览器心跳连续失败（滑动窗口），提前终止避免挂起。
        """
        start = time.time()
        last_heartbeat = start

        while time.time() - start < timeout:
            # 心跳检测：每 HEARTBEAT_INTERVAL 秒检查一次浏览器状态
            now = time.time()
            if (now - last_heartbeat) >= HEARTBEAT_INTERVAL:
                heartbeat_ok = await self._check_browser_heartbeat(platform_key)
                heartbeat_results.append(heartbeat_ok)
                # 滑动窗口检查：最近N次全部失败才触发
                if len(heartbeat_results) >= HEARTBEAT_WINDOW_SIZE and not any(heartbeat_results):
                    raise HeartbeatError(
                        f"{PLATFORMS[platform_key]['name']} 最近{HEARTBEAT_WINDOW_SIZE}次心跳均无响应"
                    )
                last_heartbeat = now

            # 心跳检查后刷新 now，确保 chunk_timeout 使用最新时间戳
            now = time.time()

            # 尝试获取响应（带短超时，避免阻塞心跳循环）
            chunk_timeout = min(5, timeout - (now - start))
            if chunk_timeout <= 0:
                break
            try:
                response = await asyncio.wait_for(
                    agent.get_response(None, platform_key, timeout=chunk_timeout),
                    timeout=chunk_timeout + 2
                )
                return response
            except asyncio.TimeoutError:
                # 短超时正常，继续循环检查心跳
                continue

        return f"[超时] {timeout}秒内未获取到 {PLATFORMS[platform_key]['name']} 的响应"

    async def _check_input_with_agent(self, page, platform_key: str) -> bool:
        try:
            agent = get_browser_agent()
            result = await agent.check_input_ready(page)
            return result.get("found", False)
        except Exception:
            return False

    async def _send_with_playwright(self, page, platform_key: str, message: str, timeout: int) -> str:
        """使用 Playwright JS 发送并轮询响应."""
        input_check = await page.evaluate("""
            () => {
                const sels = ['textarea', '[contenteditable="true"]', '[role="textbox"]',
                          'textarea[placeholder]', 'input[type="text"]',
                          '.chat-input textarea', 'div[class*="input"] textarea'];
                for (const s of sels) {
                    const el = document.querySelector(s);
                    if (el && el.offsetParent !== null) return {found: true};
                }
                return {found: false};
            }
        """)
        if not input_check.get("found"):
            return f"[错误] {PLATFORMS[platform_key]['name']} 未找到输入框"

        SEND_JS = r"""
        (msg) => {
            const sels = ['textarea','textarea[placeholder]','#chat-input','[contenteditable="true"]','[role="textbox"]','.chat-input textarea','div[class*="input"] textarea'];
            let input = null;
            for (const s of sels) { const el = document.querySelector(s); if (el && el.offsetParent !== null) { input = el; break; } }
            if (!input) return {ok:false, error:'input_not_found'};
            if (input.tagName==='TEXTAREA'||input.tagName==='INPUT') {
                const proto = input.tagName==='TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
                Object.getOwnPropertyDescriptor(proto,'value').set.call(input,msg);
                input.dispatchEvent(new Event('input',{bubbles:true}));
                input.dispatchEvent(new Event('change',{bubbles:true}));
            } else { input.innerText=msg; input.dispatchEvent(new Event('input',{bubbles:true})); }
            const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set
                || Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
            if(nativeSetter && (input.tagName==='TEXTAREA'||input.tagName==='INPUT')) {
                nativeSetter.call(input, msg);
                input.dispatchEvent(new Event('input', {bubbles:true}));
            }
            input.focus();
            for(const btn of document.querySelectorAll('button[type="submit"],button[class*="send"],button[class*="submit"],button[aria-label*="发送"],button[aria-label*="send"]')){
                if(btn&&btn.offsetParent!==null&&!btn.disabled){btn.click();return{ok:true,method:'button_click'};}
            }
            let c=input.parentElement,d=0;
            while(c&&d<10){const svgs=c.querySelectorAll('svg');if(svgs.length>0){const t=svgs[svgs.length-1].parentElement;if(t){t.click();return{ok:true,method:'svg_click'};}}c=c.parentElement;d++;}
            const o={key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true};
            input.dispatchEvent(new KeyboardEvent('keydown',o));input.dispatchEvent(new KeyboardEvent('keyup',o));
            return{ok:true,method:'enter_key'};
        }
        """
        result = await page.evaluate(SEND_JS, message)
        if not result.get("ok"):
            return f"[错误] 发送失败: {result.get('error', 'unknown')}"

        STREAMING_JS = r"""
        () => {
            for(const s of ['button[aria-label*="stop"]','[class*="stop-button"]','[class*="stop_btn"]']){
                try{const el=document.querySelector(s);if(el&&el.offsetParent!==null&&!el.disabled)return{streaming:true,indicator:s};}catch(e){}
            }
            const t=document.body.innerText||'';
            if(t.includes('思考中')&&!t.includes('已完成深度思考'))return{streaming:true,indicator:'volcengine-thinking'};
            return{streaming:false};
        }
        """

        RESPONSE_JS = r"""
        () => {
            const EX=['内容由','AI 生成','请仔细甄别','下载电脑版','历史对话','超能模式','帮我写作','PPT 生成','图像生成','更多','新对话','Ctrl K','AI 创作','云盘','专家','Beta','主页','绘画','画廊','思维导图','白板','客户端','画布绘画','内容举报','高级VIP'];
            const ERR_PATTERNS=['重试.*次后仍失败','Cannot read properties','TypeError:','Page.evaluate','接口重试','请求失败','页面执行脚本触发类型异常'];
            function ex(t){if(!t||t.length<1||t.length>5000)return true;if(t.length<20&&EX.some(k=>t===k||t.includes(k)))return true;if(ERR_PATTERNS.some(p=>new RegExp(p).test(t)))return true;return false;}
            for(let i=document.querySelectorAll('div[class*="flow-markdown-body"]').length-1;i>=0;i--){const t=document.querySelectorAll('div[class*="flow-markdown-body"]')[i].innerText?.trim()||'';if(t.length>0&&t.length<15000&&!ex(t))return{text:t,selector:'doubao-markdown'};}
            for(let i=document.querySelectorAll('div[class*="container"][class*="theme-"]').length-1;i>=0;i--){const t=document.querySelectorAll('div[class*="container"][class*="theme-"]')[i].innerText?.trim()||'';if(t.length>1&&t.length<500&&!ex(t))return{text:t,selector:'doubao-theme-container'};}
            for(let i=document.querySelectorAll('.ds-assistant-message-main-content').length-1;i>=0;i--){const t=document.querySelectorAll('.ds-assistant-message-main-content')[i].innerText?.trim()||'';if(t.length>0&&!ex(t))return{text:t,selector:'deepseek-assistant'};}
            for(let i=document.querySelectorAll('[class*="markdown"]').length-1;i>=0;i--){const el=document.querySelectorAll('[class*="markdown"]')[i];if(el.className?.includes('flow-markdown-body'))continue;const t=el.innerText?.trim()||'';if(t.length>5&&t.length<15000&&!ex(t))return{text:t,selector:'deepseek-markdown-fallback'};}
            for(let i=document.querySelectorAll('div[class*="paragraph_48351"]').length-1;i>=0;i--){const t=document.querySelectorAll('div[class*="paragraph_48351"]')[i].innerText?.trim()||'';if(t.length>0&&t.length<15000&&!t.includes('用户现在')&&!t.includes('让我思考')&&!t.includes('首token')&&!t.includes('总耗时')&&!ex(t))return{text:t,selector:'volcengine-paragraph'};}
            for(let i=document.querySelectorAll('p').length-1;i>=0;i--){const t=document.querySelectorAll('p')[i].innerText?.trim()||'';if(t.length>5&&t.length<3000&&!ex(t)&&!/^\d{4}[-/]/.test(t)&&!/^[\d\s+\-=*/.]+$/.test(t)&&!['2','4','6','8','10'].includes(t))return{text:t,selector:'p-tag'};}
            return{text:'',selector:'none'};
        }
        """

        start = time.time()
        prev_text = ""
        stable_count = 0
        streaming_count = 0
        no_response_count = 0

        while time.time() - start < timeout:
            stream = await page.evaluate(STREAMING_JS)
            if stream.get("streaming"):
                await page.wait_for_timeout(500)
                streaming_count += 1
                resp = await page.evaluate(RESPONSE_JS)
                text = resp.get("text", "")
                if text and len(text) > 10 and text == prev_text:
                    stable_count += 1
                    if stable_count >= 2:
                        return text
                elif text:
                    prev_text = text
                    stable_count = 0
                if streaming_count > 40:
                    break
                continue

            streaming_count = 0
            resp = await page.evaluate(RESPONSE_JS)
            text = resp.get("text", "")

            if text and len(text) > 10:
                no_response_count = 0
                if text == prev_text:
                    stable_count += 1
                    if stable_count >= 2:
                        return text
                else:
                    stable_count = 0
                    prev_text = text
                await page.wait_for_timeout(1000)
            else:
                no_response_count += 1
                max_no_resp = config.get(MAX_NO_RESPONSE_ATTEMPTS_KEY, MAX_NO_RESPONSE_ATTEMPTS)
                if no_response_count > max_no_resp:
                    return f"[快速失败] {PLATFORMS[platform_key]['name']} 发送后未检测到响应"
                await page.wait_for_timeout(2000)

        return f"[超时] {timeout}秒内未获取到 {PLATFORMS[platform_key]['name']} 的响应"

    # ── 熔断器 ───────────────────────────────────────────────────
    def _circuit_is_open(self, platform_key: str) -> Optional[str]:
        """检查熔断器是否打开。返回错误消息或None（允许请求）.

        注意：调用方必须持有 _lock_circuit 锁。本方法会修改 cb['opened_at']（冷却重置），
        若未持锁则存在竞态条件。
        """
        now = time.time()
        cb = self._circuit_breakers.get(platform_key)
        if not cb:
            return None
        if cb.get("opened_at"):
            # 熔断已打开，检查冷却期是否结束
            elapsed = now - cb["opened_at"]
            if elapsed >= CIRCUIT_BREAKER_COOLDOWN:
                # 冷却期结束，允许半开请求（重置opened_at）
                cb["opened_at"] = None
                return None
            remaining = int(CIRCUIT_BREAKER_COOLDOWN - elapsed)
            return f"[熔断] {PLATFORMS[platform_key]['name']} 连续失败{cb['failures']}次，冷却中(剩余{remaining}秒)"
        # 熔断未打开，检查失败计数
        if cb.get("failures", 0) >= CIRCUIT_BREAKER_THRESHOLD:
            cb["opened_at"] = now
            return f"[熔断] {PLATFORMS[platform_key]['name']} 连续失败{cb['failures']}次，跳过"
        return None

    def _circuit_record_success(self, platform_key: str):
        """记录成功：如果在重置窗口内无失败，清零计数器."""
        now = time.time()
        cb = self._circuit_breakers.get(platform_key)
        if cb and cb.get("last_failure"):
            if (now - cb["last_failure"]) >= CIRCUIT_BREAKER_RESET_WINDOW:
                cb["failures"] = 0
                cb["last_failure"] = None
        # 半开状态下成功，完全关闭熔断
        if cb and cb.get("opened_at"):
            cb["failures"] = 0
            cb["opened_at"] = None
            cb["last_failure"] = None

    def _circuit_record_failure(self, platform_key: str):
        """记录失败：增加连续失败计数."""
        if platform_key not in self._circuit_breakers:
            self._circuit_breakers[platform_key] = {"failures": 0, "last_failure": None, "opened_at": None}
        cb = self._circuit_breakers[platform_key]
        now = time.time()
        # 如果距上次失败超过重置窗口，重置计数
        if cb.get("last_failure") and (now - cb["last_failure"]) >= CIRCUIT_BREAKER_RESET_WINDOW:
            cb["failures"] = 0
        cb["failures"] += 1
        cb["last_failure"] = now

    def get_circuit_breaker_status(self) -> dict:
        """获取所有熔断器状态（供外部查询）."""
        status = {}
        for pk, cb in self._circuit_breakers.items():
            status[pk] = {
                "failures": cb.get("failures", 0),
                "is_open": cb.get("opened_at") is not None,
                "cooldown_remaining": max(0, int(CIRCUIT_BREAKER_COOLDOWN - (time.time() - cb["opened_at"]))) if cb.get("opened_at") else 0,
            }
        return status

    # ── 心跳检测 ─────────────────────────────────────────────────
    async def _check_browser_heartbeat(self, platform_key: str) -> bool:
        """检查浏览器是否存活。返回True表示健康."""
        try:
            agent = get_browser_agent()
            if not agent:
                return False
            # 用短超时获取URL，如果页面无响应说明浏览器卡死
            url = await asyncio.wait_for(
                asyncio.to_thread(agent.get_current_url),
                timeout=HEARTBEAT_TIMEOUT
            )
            return url is not None
        except (asyncio.TimeoutError, Exception):
            return False

    # ── 统计和工具方法 ───────────────────────────────────────
    def _incr_fetch_stats(self, platform: str, success: bool, elapsed: float):
        if platform not in self._fetch_stats:
            self._fetch_stats[platform] = {"success": 0, "fail": 0, "total_time": 0.0}
        if success:
            self._fetch_stats[platform]["success"] += 1
            self._fetch_stats[platform]["total_time"] += elapsed
        else:
            self._fetch_stats[platform]["fail"] += 1

    def _score_response(self, text: str, message: str = "") -> dict:
        """轻量响应质量评分：长度+结构+相关度，返回{score, issues}."""
        if not text:
            return {"score": 0, "issues": ["empty"]}
        score = 50  # 基础分
        issues = []

        # 长度评分 (0-25)
        length = len(text)
        if length < 10:
            score += 5
            issues.append("too_short")
        elif length < 50:
            score += 15
        elif length < 500:
            score += 25
        else:
            score += 10
            issues.append("too_long")

        # 结构评分 (0-25)
        if '\n' in text:
            score += 10
        if any(c in text for c in ['1.', '2.', '一、', '二、', '•', '- ']):
            score += 10
        if score >= 20:
            score += 5  # 额外奖励

        # 相关性（简单字符重叠）
        if message:
            msg_chars = set(message.replace(' ', ''))
            resp_chars = set(text.replace(' ', ''))
            overlap = len(msg_chars & resp_chars)
            relevance = min(overlap / max(len(msg_chars), 1) * 10, 10)
            score += int(relevance)

        # 截断检查
        if text.endswith(('...', '…', '→', '：')):
            issues.append("truncated")
            score -= 10

        score = max(0, min(score, 100))
        return {"score": score, "issues": issues}

    async def _record_quality(self, platform: str, text: str, message: str):
        """记录响应质量评分（线程安全）."""
        async with self._lock_quality:
            if not hasattr(self, "_response_quality_log"):
                self._response_quality_log = []
            result = self._score_response(text, message)
            self._response_quality_log.append({
                "platform": platform,
                "score": result["score"],
                "ts": time.time()
            })
            # 保留最近 50 条
            if len(self._response_quality_log) > 50:
                self._response_quality_log.pop(0)

    def _record_response_time(self, platform: str, elapsed: float):
        """记录平台响应时间."""
        if platform not in self._response_times:
            self._response_times[platform] = []
        self._response_times[platform].append(elapsed)
        if len(self._response_times[platform]) > 10:
            self._response_times[platform].pop(0)

    def _get_dynamic_timeout(self, platform: str, base_timeout: int) -> int:
        times = self._response_times.get(platform, [])
        if len(times) < 3:
            return base_timeout
        sorted_times = sorted(times)
        p90_idx = int(len(sorted_times) * 0.9)
        p90 = sorted_times[min(p90_idx, len(sorted_times) - 1)]
        recent = times[-3:] if len(times) >= 3 else times
        recent_avg = sum(recent) / len(recent)
        base = max(p90, recent_avg)
        dynamic = int(base * 1.5 + 15)
        return max(30, min(dynamic, base_timeout))

    def _check_rate_limit(self, platform: str) -> Optional[str]:
        now = time.time()
        window = config.rate_limit_window
        interval = config.rate_limit_interval
        max_requests = config.rate_limit_max

        if not hasattr(self, "_rate_limiter"):
            self._rate_limiter = {}
        if platform not in self._rate_limiter:
            self._rate_limiter[platform] = []

        self._rate_limiter[platform] = [t for t in self._rate_limiter[platform] if (now - t) < window]

        if self._rate_limiter[platform]:
            last = self._rate_limiter[platform][-1]
            if (now - last) < interval:
                wait = interval - (now - last)
                return f"[限流] {platform} 请求过快，请等待{wait:.1f}秒"

        if len(self._rate_limiter[platform]) >= max_requests:
            return f"[限流] {platform} 窗口内请求数已达上限({max_requests})"

        self._rate_limiter[platform].append(now)
        return None

    def _check_message_dedup(self, platform: str, message: str) -> Optional[str]:
        if not self._dedup_enabled:
            return None

        now = time.time()
        msg_hash = hashlib.md5(message.encode()).hexdigest()
        key = (platform, msg_hash)

        # 确保数据结构存在
        if not hasattr(self, "_message_dedup"):
            self._message_dedup = {}
        if not hasattr(self, "_message_dedup_content"):
            self._message_dedup_content = {}

        # 1. 精确匹配
        last_time = self._message_dedup.get(key)
        if last_time and (now - last_time) < config.get("dedup_window", 300):
            remain = config.get("dedup_window", 300) - (now - last_time)
            return f"[去重] {platform} 相同消息已发送，请等待{remain:.0f}秒后再试"

        # 2. 近似匹配：检查同平台的其他消息
        dedup_window = config.get("dedup_window", 300)
        for (pk, stored_hash), ts in list(self._message_dedup.items()):
            if pk != platform:
                continue
            if (now - ts) >= dedup_window:
                continue
            stored_msg = self._message_dedup_content.get((pk, stored_hash))
            if stored_msg and self._message_similarity(message, stored_msg) > 0.8:
                remain = dedup_window - (now - ts)
                return f"[去重] {platform} 疑似重复消息(相似度>80%)，请等待{remain:.0f}秒后再试"

        # 3. 记录本次消息（精确和近似都通过）
        self._message_dedup[key] = now
        self._message_dedup_content[key] = message

        # 4. 清理过期记录
        expired = [k for k, v in self._message_dedup.items() if (now - v) > dedup_window]
        for k in expired:
            del self._message_dedup[k]
            self._message_dedup_content.pop(k, None)

        return None

    def _decay_error_stats(self):
        now = time.time()
        if not hasattr(self, "_last_decay"):
            self._last_decay = now
            return
        if now - self._last_decay < 30:
            return
        self._last_decay = now

        for pk in self._error_stats:
            for err_type in self._error_stats[pk]:
                if self._error_stats[pk][err_type] > 0:
                    self._error_stats[pk][err_type] = max(0, self._error_stats[pk][err_type] - 1)

    async def _save_screenshot(self, page, label: str = "screenshot"):
        """保存页面截图到配置的screenshot_dir."""
        ss_dir = config.get("screenshot_dir", "")
        if not ss_dir or not page:
            return
        try:
            import os
            os.makedirs(ss_dir, exist_ok=True)
            ts = time.strftime('%Y%m%d_%H%M%S')
            filename = f"{label}_{ts}.png"
            path = os.path.join(ss_dir, filename)
            await page.screenshot(path=path, full_page=False)
        except Exception:
            pass

    def _message_similarity(self, a: str, b: str) -> float:
        """计算两个消息的字符级Jaccard相似度."""
        if not a or not b:
            return 0.0
        set_a = set(a.lower().replace(" ", ""))
        set_b = set(b.lower().replace(" ", ""))
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0

    def _check_retry_budget(self) -> bool:
        now = time.time()
        window = config.retry_budget_window
        max_retries = config.retry_budget_max
        self._retry_budget[:] = [t for t in self._retry_budget if (now - t) < window]
        allowed = len(self._retry_budget) < max_retries
        if allowed:
            self._retry_budget.append(now)
        return allowed

    def _record_retry(self):
        pass  # 已在 _check_retry_budget 记录

    def _record_error(self, platform_key: str, err_type: str = "error"):
        """记录错误统计."""
        if platform_key not in self._error_stats:
            self._error_stats[platform_key] = {}
        self._error_stats[platform_key][err_type] = self._error_stats[platform_key].get(err_type, 0) + 1

    def _normalize_response(self, text: str, platform: str = "") -> str:
        if not text:
            return text
        text = text.strip()
        text = self._compress_response(text)
        return text

    def _compress_response(self, text: str) -> str:
        if not text:
            return text
        original_len = len(text)
        import re
        AI_FILLER_PATTERNS = [
            r"当然可以[！!。.]?\s*",
            r"好的[！!。.]?\s*",
            r"没问题[！!。.]?\s*",
            r"以下是[：:]?\s*",
            r"根据你的要求[，,]?\s*",
            r"基于以上分析[，,]?\s*",
            r"总结一下[：:]?\s*",
            r"综上所述[，,]?\s*",
        ]
        AI_FILLER_RE = re.compile("|".join(AI_FILLER_PATTERNS), re.IGNORECASE)
        text = AI_FILLER_RE.sub("", text, count=1)

        lines = text.split("\n")
        compressed = []
        prev = ""
        for line in lines:
            stripped = line.strip()
            if stripped and stripped == prev:
                continue
            compressed.append(line)
            prev = stripped
        text = "\n".join(compressed)
        text = re.sub(r"\n{3,}", "\n\n", text)

        saved = original_len - len(text)
        if saved > 20:
            text += f"\n... [压缩: {original_len}字 → {len(text)}字, 节省{saved}字]"
        return text.strip()

    def get_stats(self) -> dict:
        return {
            "fetch": dict(self._fetch_stats),
            "active_requests": dict(self._active_requests),
        }

# 全局实例
chat_engine = ChatEngine()

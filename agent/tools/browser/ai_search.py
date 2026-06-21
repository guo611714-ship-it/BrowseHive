"""浏览器工具 — AI 搜索与对话"""

import json
import time
import sys
import asyncio
import logging
from typing import Dict

from ..tool_registry import tool, cached
from .browser_client import detect_cdp_url, exec_js as _cdp_exec_js
from .browser_pool import get_monitor, get_browser_pool
from .utils import _ok, _err, _safe_js_str, _operation_log, _log_operation
from .session import _record_to_session

logger = logging.getLogger(__name__)

# ─── MCP路径管理（避免重复插入sys.path）────────────────────────
_mcp_path_added = False


def _ensure_mcp_path():
    """确保MCP_SCRIPTS在sys.path中，只插入一次"""
    global _mcp_path_added
    if _mcp_path_added:
        return
    try:
        from ...config import MCP_SCRIPTS
        mcp_scripts = str(MCP_SCRIPTS)
        if mcp_scripts not in sys.path:
            sys.path.insert(0, mcp_scripts)
        _mcp_path_added = True
    except ImportError:
        pass


def _get_chat_engine():
    try:
        from core.chat_engine import chat_engine
        return chat_engine
    except ImportError:
        pass
    # 降级：尝试从MCP/scripts路径加载
    try:
        import sys
        from ...config import MCP_SCRIPTS
        mcp_scripts = str(MCP_SCRIPTS)
        if mcp_scripts not in sys.path:
            sys.path.insert(0, mcp_scripts)
        from core.chat_engine import chat_engine
        return chat_engine
    except ImportError:
        return None


@tool("ask_doubao", "调用豆包AI对话")
async def ask_doubao(message: str, timeout: int = 120, mode: str = "fast") -> Dict:
    """调用豆包对话

    Args:
        mode: fast(快速)/think(思考)/expert(专家，每日有限)
    """
    engine = _get_chat_engine()
    if not engine:
        return {"error": "Browser AI chat_engine 不可用"}
    try:
        # 模式切换：点击对应按钮
        if mode != "fast":
            _mode_js = {
                "think": """(function(){
                    var btns = document.querySelectorAll('button, [role="button"]');
                    for(var b of btns){if(b.innerText.includes('思考')){b.click();return 'ok';}}
                    return 'not_found';
                })()""",
                "expert": """(function(){
                    var btns = document.querySelectorAll('button, [role="button"]');
                    for(var b of btns){if(b.innerText.includes('专家')){b.click();return 'ok';}}
                    return 'not_found';
                })()""",
            }
            if mode in _mode_js:
                from .browser_client import exec_js
                await exec_js(_mode_js[mode])
                await asyncio.sleep(0.5)

        result = await engine.chat("doubao", message, timeout=timeout)
        return {"platform": "doubao", "mode": mode, "response": result}
    except Exception as e:
        return {"platform": "doubao", "error": str(e)}


@tool("ask_deepseek_browser", "调用DeepSeek浏览器版对话")
async def ask_deepseek_browser(message: str, timeout: int = 120, mode: str = "fast") -> Dict:
    """调用 DeepSeek 浏览器版

    Args:
        mode: fast(快速)/think(深度思考)/search(智能搜索)
    """
    engine = _get_chat_engine()
    if not engine:
        return {"error": "Browser AI chat_engine 不可用"}
    try:
        if mode != "fast":
            _mode_js = {
                "think": """(function(){
                    var btns = document.querySelectorAll('button, [role="button"], span');
                    for(var b of btns){if(b.innerText.includes('深度思考')){b.click();return 'ok';}}
                    return 'not_found';
                })()""",
                "search": """(function(){
                    var btns = document.querySelectorAll('button, [role="button"], span');
                    for(var b of btns){if(b.innerText.includes('智能搜索')){b.click();return 'ok';}}
                    return 'not_found';
                })()""",
            }
            if mode in _mode_js:
                from .browser_client import exec_js
                await exec_js(_mode_js[mode])
                await asyncio.sleep(0.5)

        result = await engine.chat("deepseek", message, timeout=timeout)
        return {"platform": "deepseek", "mode": mode, "response": result}
    except Exception as e:
        return {"platform": "deepseek", "error": str(e)}


@tool("ask_bing", "使用必应搜索引擎搜索答案")
async def ask_bing(message: str, timeout: int = 30) -> Dict:
    """导航到必应搜索并提取搜索结果（含URL，供子agent爬取详情）"""
    from urllib.parse import quote

    # URL编码防止注入
    encoded_q = quote(message, safe="")
    await _cdp_exec_js(f"location.href = 'https://cn.bing.com/search?q={encoded_q}'")
    await asyncio.sleep(4)

    # 提取搜索结果（多选择器容错）
    r = await _cdp_exec_js("""(function() {
        var results = [];
        var selectors = ['#b_results .b_algo', '#b_results li.b_algo', '#b_results .b_ans'];
        var items = [];
        for (var s = 0; s < selectors.length; s++) {
            items = document.querySelectorAll(selectors[s]);
            if (items.length) break;
        }
        for (var i = 0; i < Math.min(items.length, 5); i++) {
            var a = items[i].querySelector('h2 a, h3 a, a');
            var p = items[i].querySelector('.b_caption p, .b_algoSlug, .b_lineclamp2');
            if (a && a.href) results.push({
                title: a.innerText.trim(),
                url: a.href,
                snippet: p ? p.innerText.trim().substring(0, 200) : ''
            });
        }
        return results;
    })()""")

    results = r.get("data", []) or []
    output = []
    for item in results:
        if item.get("title"):
            line = f"【{item['title']}】{item.get('snippet', '')}"
            if item.get("url"):
                line += f"\n  链接: {item['url']}"
            output.append(line)
    text = "\n".join(output) if output else "未找到搜索结果"
    return {"platform": "bing", "response": text}


@tool("ask_ouyi", "调用欧亿AI对话")
async def ask_ouyi(message: str, timeout: int = 120, mode: str = "fast") -> Dict:
    """调用欧亿AI对话"""
    engine = _get_chat_engine()
    if not engine:
        return {"error": "Browser AI chat_engine 不可用"}
    try:
        result = await engine.chat("ouyi", message, timeout=timeout)
        return {"platform": "ouyi", "mode": mode, "response": result}
    except Exception as e:
        return {"platform": "ouyi", "error": str(e)}


@tool("ask_kimi", "调用Kimi（Moonshot AI）对话，擅长长文本分析")
async def ask_kimi(message: str, timeout: int = 120, mode: str = "fast") -> Dict:
    """调用Kimi对话

    Args:
        mode: fast(K2.6快速)/think(K2.6思考，多轮搜索)
    """
    engine = _get_chat_engine()
    if not engine:
        return {"error": "Browser AI chat_engine 不可用"}
    try:
        if mode == "think":
            from .browser_client import exec_js
            await exec_js("""(function(){
                var btns = document.querySelectorAll('button, [role="button"], span');
                for(var b of btns){
                    var t = b.innerText || '';
                    if(t.includes('思考') && !t.includes('快速')){b.click();return 'ok';}
                }
                return 'not_found';
            })()""")
            await asyncio.sleep(0.5)

        result = await engine.chat("kimi", message, timeout=timeout)
        return {"platform": "kimi", "mode": mode, "response": result}
    except Exception as e:
        return {"platform": "kimi", "error": str(e)}


@tool("ask_chatglm", "调用智谱清言（ChatGLM）对话，擅长学术和知识图谱")
async def ask_chatglm(message: str, timeout: int = 120, mode: str = "fast") -> Dict:
    """调用智谱清言对话

    Args:
        mode: fast(默认)/think(思考模式)/search(联网搜索)
    """
    engine = _get_chat_engine()
    if not engine:
        return {"error": "Browser AI chat_engine 不可用"}
    try:
        if mode != "fast":
            _mode_js = {
                "think": """(function(){
                    var btns = document.querySelectorAll('button, [role="button"], span');
                    for(var b of btns){if(b.innerText.trim()==='思考'){b.click();return 'ok';}}
                    return 'not_found';
                })()""",
                "search": """(function(){
                    var btns = document.querySelectorAll('button, [role="button"], span');
                    for(var b of btns){if(b.innerText.trim()==='联网'){b.click();return 'ok';}}
                    return 'not_found';
                })()""",
            }
            if mode in _mode_js:
                from .browser_client import exec_js
                await exec_js(_mode_js[mode])
                await asyncio.sleep(0.5)

        result = await engine.chat("chatglm", message, timeout=timeout)
        return {"platform": "chatglm", "mode": mode, "response": result}
    except Exception as e:
        return {"platform": "chatglm", "error": str(e)}


@tool("smart_ask", "智能路由浏览器AI：自动选择平台+发送+提取回复")
async def smart_ask(message: str, timeout: int = 30) -> Dict:
    """直接用CDP控制台操作浏览器：发送消息并提取AI回复。按URL自动识别平台。"""
    try:
        import websocket, random as _rand
    except ImportError:
        return {"error": "websocket-client 未安装，请运行: pip install websocket-client"}

    def _get_ws(cdp_url):
        try:
            import urllib.request
            tabs = json.loads(urllib.request.urlopen(f"{cdp_url}/json", timeout=3).read())
            for t in tabs:
                if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                    return websocket.create_connection(t["webSocketDebuggerUrl"], timeout=10)
        except Exception as e:
            logger.debug("caught exception: %s", e)
        return None

    def _eval(ws, expr):
        mid = _rand.randint(1, 999999)
        ws.send(json.dumps({"id": mid, "method": "Runtime.evaluate",
                            "params": {"expression": expr, "returnByValue": True, "awaitPromise": True}}))
        return json.loads(ws.recv())

    def _get_val(r):
        return (r.get("result") or {}).get("result", {}).get("value")

    # -- 统一发送JS：自动找输入框+发送按钮（按钮优先aria-label，兜底右下角小按钮，最后Enter）--
    _SEND = """(function(msg) {
        var ta = document.querySelector('textarea, [contenteditable="true"], [role="textbox"]');
        if (!ta) return {ok:false, error:'no_input'};
        if (ta.tagName==='TEXTAREA'||ta.tagName==='INPUT') {
            Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(ta,msg);
            ta.dispatchEvent(new Event('input',{bubbles:true}));
        } else { ta.innerText=msg; ta.dispatchEvent(new Event('input',{bubbles:true})); }
        ta.focus();
        var btns=document.querySelectorAll('button');
        for(var i=0;i<btns.length;i++){
            var a=(btns[i].getAttribute('aria-label')||'').toLowerCase();
            if(btns[i].offsetParent&&!btns[i].disabled&&(a.indexOf('send')>=0||a.indexOf('发送')>=0||btns[i].className.indexOf('send')>=0)){
                btns[i].click(); return{ok:true,method:'aria'};
            }
        }
        for(var j=btns.length-1;j>=0;j--){
            var rc=btns[j].getBoundingClientRect();
            if(rc.bottom>500&&rc.right>600&&rc.width<50&&rc.width>10&&btns[j].offsetParent&&!btns[j].disabled){
                btns[j].click(); return{ok:true,method:'corner'};
            }
        }
        ta.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',keyCode:13,bubbles:true}));
        return{ok:true,method:'enter'};
    })('""" + _safe_js_str(message) + """')"""

    # -- 统一提取JS：按URL自动选选择器 --
    _EXTRACT = """(function(){
        var u=location.href, sels;
        if(u.indexOf('deepseek')>=0) sels=['[class*="ds-message"]','[class*="ds-markdown"]'];
        else if(u.indexOf('rcouyi')>=0) sels=['.message-box:not(.flex-row-reverse)','[class*="text-wrap"]'];
        else sels=['[class*="md-box-root"]','[class*="flow-markdown-body"]'];
        for(var i=0;i<sels.length;i++){
            var els=document.querySelectorAll(sels[i]);
            if(!els.length) continue;
            var t=(els[els.length-1].textContent||'').trim();
            if(t.length>5) return{text:t,count:els.length};
        }
        return{text:'',count:0};
    })()"""

    cdp_url = await detect_cdp_url()
    if not cdp_url:
        return {"error": "CDP未连接"}

    # 将同步websocket操作包装到线程池（避免阻塞事件循环）
    ws = await asyncio.to_thread(_get_ws, cdp_url)
    if not ws:
        return {"error": "无WebSocket连接"}

    try:
        # 记录初始回复数（同步操作在线程池执行）
        r0 = await asyncio.to_thread(_eval, ws, _EXTRACT)
        v0 = _get_val(r0)
        init_count = v0.get("count", 0) if isinstance(v0, dict) else 0

        # 发送
        r_send = await asyncio.to_thread(_eval, ws, _SEND)
        sv = _get_val(r_send)
        if isinstance(sv, dict) and not sv.get("ok"):
            return {"error": sv.get("error", "send_failed")}

        # 等待新回复稳定
        start = time.time()
        last_text = ""
        stable = 0
        while time.time() - start < timeout:
            await asyncio.sleep(1.5)
            r = await asyncio.to_thread(_eval, ws, _EXTRACT)
            v = _get_val(r)
            text = v.get("text", "") if isinstance(v, dict) else ""
            count = v.get("count", 0) if isinstance(v, dict) else 0
            if count > init_count and text and len(text) > 5:
                if text == last_text:
                    stable += 1
                    if stable >= 2:
                        return {"platform": "browser", "response": text}
                else:
                    last_text = text
                    stable = 0
        return {"error": f"超时({timeout}s)，最后文本: {last_text[:100] if last_text else '无'}"}
    finally:
        ws.close()


async def _http_fallback(message: str) -> Dict:
    """HTTP API兜底：直接调用公开接口（绕过CDP）"""
    import os
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        return {"error": "HTTP兜底需要DEEPSEEK_API_KEY环境变量"}

    try:
        import httpx
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://chat.deepseek.com/api/v0/chat/completions",
                json={"model": "deepseek-chat", "messages": [{"role": "user", "content": message}]},
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    return {"platform": "deepseek-http", "response": content}
    except Exception as e:
        logger.warning(f"HTTP兜底失败: {e}")

    return {"error": "所有浏览器AI平台均失败，HTTP兜底也失败"}


@tool("browser_status", "获取浏览器AI系统状态")
@cached(ttl=30)
async def browser_status() -> Dict:
    """获取浏览器 AI 系统状态"""
    cdp_url = await detect_cdp_url()
    engine = _get_chat_engine()
    pool = get_browser_pool()
    monitor = get_monitor()

    return {
        "cdp_available": cdp_url is not None,
        "cdp_url": cdp_url,
        "chat_engine_ready": engine is not None,
        "pool": pool.get_stats(),
        "alerts": monitor.get_alerts(limit=5),
        "operation_count": len(_operation_log),
        "recent_operations": _operation_log[-5:] if _operation_log else []
    }


@tool("batch_ask", "智能路由AI平台提问：自动选择最优平台+模式，整合结果。")
async def batch_ask(message: str, platforms: str = None,
                    mode: str = "auto", synthesize: bool = False) -> Dict:
    """智能路由版本：自动选择最优平台和模式，减少冗余调用。

    Args:
        message: 要问的问题
        platforms: 逗号分隔的平台列表（None=智能路由，指定=直接使用）
        mode: fast/deep/auto（auto=智能路由默认）
        synthesize: 是否用LLM整合多平台回复为统一答案
    """
    from .platform_router import get_router, l1_route, score_answer_quality

    t0 = time.time()
    router = get_router()

    # ── 路由决策 ──
    if platforms:
        # 用户指定平台 → 直接使用（兼容旧接口）
        platform_list = [p.strip().lower() for p in platforms.split(",") if p.strip()]
        route_result = None
    else:
        # 智能路由
        route_result = await router.route_async(message)
        platform_list = route_result.platforms
        mode = route_result.mode
        logger.info(f"路由决策: {route_result.level} | {route_result.category} → "
                    f"{platform_list} + {mode} | {route_result.reason}")

    # ── 模式映射 ──
    if mode == "auto":
        _deep_keywords = ["分析", "推理", "对比", "评估", "设计", "架构", "论证",
                          "为什么", "如何", "优缺点", "方案", "策略", "预测"]
        msg_lower = message.lower()
        mode = "deep" if any(kw in msg_lower for kw in _deep_keywords) else "fast"

    _platform_modes = {
        "doubao": {"fast": "fast", "deep": "think"},
        "deepseek": {"fast": "fast", "deep": "think"},
        "kimi": {"fast": "fast", "deep": "think"},
        "chatglm": {"fast": "fast", "deep": "think"},
        "ouyi": {"fast": "fast", "deep": "fast"},
    }

    platform_map = {
        "doubao": ask_doubao,
        "deepseek": ask_deepseek_browser,
        "kimi": ask_kimi,
        "chatglm": ask_chatglm,
        "ouyi": ask_ouyi,
    }

    # 过滤有效平台
    valid = [(name, fn) for name, fn in platform_map.items() if name in platform_list]
    if not valid:
        return _err(113, f"无有效平台，可选: {list(platform_map.keys())}")

    # 串行执行（browser-harness子进程不能并行，会互相干扰标签状态）
    _ensure_mcp_path()
    results = []
    for name, fn in valid:
        platform_mode = _platform_modes.get(name, {}).get(mode, "fast")
        try:
            from browser_agent import get_browser_agent
            agent = get_browser_agent()

            # 模式切换（发送前点击对应按钮）
            if platform_mode != "fast":
                _switch_js = {
                    "think": """(function(){
                        var btns = document.querySelectorAll('button, [role="button"], span, div');
                        for(var b of btns){
                            var t = (b.innerText || b.textContent || '').trim();
                            if(t==='思考' || t==='深度思考' || t.includes('K2.6 思考')){
                                b.click(); return 'ok';
                            }
                        }
                        return 'not_found';
                    })()""",
                }
                if platform_mode in _switch_js:
                    from .browser_client import exec_js
                    await exec_js(_switch_js[platform_mode])
                    await asyncio.sleep(0.5)

            # 发送
            send_result = await agent.send_message(None, message, name)
            if not send_result.get("ok"):
                results.append({"platform": name, "success": False, "error": send_result.get("error", "send failed")})
                continue
            # 等待响应
            response = await agent.get_response(None, name, timeout=60)
            if response and not response.startswith("["):
                results.append({"platform": name, "success": True, "mode": platform_mode,
                                "answer": {"platform": name, "response": response}})
            else:
                results.append({"platform": name, "success": False, "error": response or "empty response"})
        except Exception as e:
            results.append({"platform": name, "success": False, "error": str(e)[:200]})
    cost = int((time.time() - t0) * 1000)

    success_count = sum(1 for r in results if r["success"])
    fail_count = len(results) - success_count

    # 收集成功答案
    answers = {r["platform"]: r.get("answer", "") for r in results if r["success"]}

    data = {
        "results": list(results),
        "answers": answers,
        "success_count": success_count,
        "fail_count": fail_count,
        "platforms": [r["platform"] for r in results],
        "mode": mode,
        "cost_time": cost,
    }

    # 附加路由信息
    if route_result:
        data["route"] = {
            "level": route_result.level,
            "category": route_result.category,
            "confidence": route_result.confidence,
            "reason": route_result.reason,
        }

    # LLM整合
    if synthesize and answers:
        synthesized = await _synthesize_answers(message, answers)
        data["synthesized"] = synthesized

    _log_operation("batch_ask", {"platforms": platforms, "synthesize": synthesize}, data, cost)
    _record_to_session("batch_ask", {"platforms": platforms}, _ok(data))
    return _ok(data)


async def _synthesize_answers(question: str, answers: Dict[str, str]) -> str:
    """用LLM整合多平台答案为统一回复"""
    # 提取answer文本（可能是dict或string）
    def _extract_text(v):
        if isinstance(v, dict):
            return v.get("response", v.get("error", str(v)))
        return str(v)

    # 构建整合prompt
    answers_text = "\n\n".join(
        f"=== {platform.upper()} ===\n{_extract_text(answer)}"
        for platform, answer in answers.items()
    )
    prompt = f"""你是一个智能整合助手。请根据以下多个AI平台对同一问题的回答，整合出一个最准确、最全面的统一答案。

问题：{question}

各平台回答：
{answers_text}

要求：
1. 综合各平台的优点，取其精华
2. 如有矛盾，选择更可信的答案并说明原因
3. 保持回答简洁清晰
4. 如果某个平台的回答明显错误，忽略它

请给出整合后的统一答案："""

    # 使用ModelOrchestrator获取LLM
    try:
        from agent.model_orchestrator import ModelOrchestrator
        from pathlib import Path
        config_path = Path("model_config.json")
        if config_path.exists():
            orch = ModelOrchestrator(config_path)
            orch._client_cache.clear()
            client = orch.get_model_for_complexity(3)  # 中等复杂度
            if client:
                response = await client.chat([{"role": "user", "content": prompt}])
                if isinstance(response, dict):
                    return response.get("content", "")
                return str(response)
    except Exception as e:
        logger.warning(f"LLM整合失败: {e}")

    # 降级：返回第一个成功答案
    return next(iter(answers.values()), "整合失败")

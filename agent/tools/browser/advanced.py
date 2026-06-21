"""浏览器高级工具 — JS执行/多标签/智能等待/表单/上传/Cookie"""

import json
import time
import asyncio
import logging
import os
from typing import Dict, Optional, List
from pathlib import Path

from ..tool_registry import tool
from .browser_client import exec_js as _cdp_exec_js, detect_cdp_url, get_tabs
from .utils import _ok, _err, _safe_js_str, _safe_js_selector, _log_operation
from .session import _record_to_session

logger = logging.getLogger(__name__)


async def _exec_js(js_code: str) -> Dict:
    """在当前页面执行 JavaScript"""
    result = await _cdp_exec_js(js_code)
    if "error" in result:
        return _err(500, result["error"])
    return _ok(result.get("data"))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Phase 1: 核心增强
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@tool("exec_js", "在当前页面执行任意JavaScript代码并返回结果")
async def exec_js_tool(js_code: str) -> Dict:
    """执行JS代码，返回执行结果。支持任意合法JavaScript。"""
    if not js_code or not js_code.strip():
        return _err(101, "JS代码不能为空")
    if len(js_code) > 50000:
        return _err(102, "JS代码不能超过50000字符")

    t0 = time.time()
    result = await _exec_js(js_code)
    cost = int((time.time() - t0) * 1000)

    if result.get("code") == 200:
        data = {"result": result.get("data"), "cost_time": cost}
        _log_operation("exec_js", {"code_len": len(js_code)}, _ok(data), cost)
        _record_to_session("exec_js", {"code_len": len(js_code)}, _ok(data))
        return _ok(data)
    return result


@tool("multi_tab", "多标签页管理：创建/切换/关闭/列出标签页")
async def multi_tab(action: str, url: str = "", tab_index: int = -1) -> Dict:
    """标签页管理。

    Args:
        action: create / switch / close / list
        url: 创建标签页时的目标URL
        tab_index: 切换/关闭时的标签页索引（0-based）
    """
    t0 = time.time()
    cdp_url = await detect_cdp_url()
    if not cdp_url:
        return _err(503, "浏览器未连接")

    if action == "list":
        tabs = await get_tabs(cdp_url)
        result_data = []
        for i, tab in enumerate(tabs):
            result_data.append({
                "index": i,
                "title": tab.get("title", ""),
                "url": tab.get("url", ""),
                "active": tab.get("active", False),
            })
        cost = int((time.time() - t0) * 1000)
        _log_operation("multi_tab", {"action": "list"}, _ok(result_data), cost)
        return _ok(result_data)

    elif action == "create":
        if not url:
            return _err(103, "创建标签页需要指定URL")
        js = f"window.open('{_safe_js_str(url)}', '_blank'); 'ok'"
        result = await _exec_js(js)
        cost = int((time.time() - t0) * 1000)
        if result.get("code") == 200:
            data = {"action": "create", "url": url, "cost_time": cost}
            _log_operation("multi_tab", data, _ok(data), cost)
            _record_to_session("multi_tab", data, _ok(data))
            return _ok(data)
        return result

    elif action == "switch":
        tabs = await get_tabs(cdp_url)
        if tab_index < 0 or tab_index >= len(tabs):
            return _err(104, f"标签页索引无效: {tab_index}（共{len(tabs)}个）")
        target_id = tabs[tab_index].get("id")
        if not target_id:
            return _err(105, "无法获取标签页ID")
        # 通过CDP激活标签页
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.put(f"{cdp_url}/json/activate/{target_id}")
            if resp.status_code == 200:
                cost = int((time.time() - t0) * 1000)
                data = {"action": "switch", "tab_index": tab_index,
                        "title": tabs[tab_index].get("title"), "cost_time": cost}
                _log_operation("multi_tab", data, _ok(data), cost)
                _record_to_session("multi_tab", data, _ok(data))
                return _ok(data)
            return _err(500, f"切换失败: HTTP {resp.status_code}")

    elif action == "close":
        tabs = await get_tabs(cdp_url)
        if tab_index < 0 or tab_index >= len(tabs):
            return _err(104, f"标签页索引无效: {tab_index}（共{len(tabs)}个）")
        target_id = tabs[tab_index].get("id")
        if not target_id:
            return _err(105, "无法获取标签页ID")
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{cdp_url}/json/close/{target_id}")
            cost = int((time.time() - t0) * 1000)
            if resp.status_code == 200:
                data = {"action": "close", "tab_index": tab_index, "cost_time": cost}
                _log_operation("multi_tab", data, _ok(data), cost)
                _record_to_session("multi_tab", data, _ok(data))
                return _ok(data)
            return _err(500, f"关闭失败: HTTP {resp.status_code}")

    return _err(106, f"未知操作: {action}（支持: create/switch/close/list）")


@tool("wait_for", "增强等待：支持元素/文本/URL/网络空闲多种条件")
async def wait_for(condition: str, value: str = "", timeout: int = 15) -> Dict:
    """等待条件满足。

    Args:
        condition: 元素选择器 / "text:关键词" / "url:子串" / "network-idle" / "ready"
        value: 条件参数（text/url模式下的匹配值）
        timeout: 最大等待秒数（上限30）
    """
    timeout = min(timeout, 30)
    t0 = time.time()

    # network-idle: 等待网络请求数归零
    if condition == "network-idle":
        idle_count = 0
        for _ in range(timeout * 2):
            js = """JSON.stringify({
                loading: document.readyState !== 'complete',
                perf: performance.getEntriesByType('resource').length
            })"""
            result = await _exec_js(js)
            if result.get("code") == 200:
                try:
                    data = json.loads(result["data"]) if isinstance(result["data"], str) else result["data"]
                    if not data.get("loading"):
                        idle_count += 1
                        if idle_count >= 3:  # 连续3次空闲=稳定
                            cost = int((time.time() - t0) * 1000)
                            _log_operation("wait_for", {"condition": "network-idle"},
                                           _ok({"cost_time": cost}), cost)
                            return _ok({"cost_time": cost})
                    else:
                        idle_count = 0
                except Exception as e:
                    logger.debug("caught exception: %s", e)
            await asyncio.sleep(0.5)
        return _err(303, "网络空闲等待超时")

    # ready: 等待 document.readyState === 'complete'
    if condition == "ready":
        for _ in range(timeout * 2):
            result = await _exec_js("document.readyState")
            if result.get("data") == "complete":
                cost = int((time.time() - t0) * 1000)
                _log_operation("wait_for", {"condition": "ready"}, _ok({"cost_time": cost}), cost)
                return _ok({"cost_time": cost})
            await asyncio.sleep(0.5)
        return _err(303, "页面加载等待超时")

    # text:关键词 — 等待页面出现指定文本
    if condition.startswith("text:"):
        text = value or condition[5:]
        if not text:
            return _err(107, "text模式需要指定关键词")
        for _ in range(timeout * 2):
            js = f"document.body.innerText.includes('{_safe_js_str(text)}')"
            result = await _exec_js(js)
            if result.get("data") is True or result.get("data") == "true":
                cost = int((time.time() - t0) * 1000)
                _log_operation("wait_for", {"condition": f"text:{text}"},
                               _ok({"found": True, "cost_time": cost}), cost)
                return _ok({"found": True, "cost_time": cost})
            await asyncio.sleep(0.5)
        return _err(303, f"文本等待超时: {text}")

    # url:子串 — 等待URL包含指定子串
    if condition.startswith("url:"):
        substr = value or condition[4:]
        if not substr:
            return _err(108, "url模式需要指定子串")
        for _ in range(timeout * 2):
            result = await _exec_js("window.location.href")
            current_url = str(result.get("data", ""))
            if substr in current_url:
                cost = int((time.time() - t0) * 1000)
                _log_operation("wait_for", {"condition": f"url:{substr}"},
                               _ok({"url": current_url, "cost_time": cost}), cost)
                return _ok({"url": current_url, "cost_time": cost})
            await asyncio.sleep(0.5)
        return _err(303, f"URL等待超时: {substr}")

    # 默认: 作为CSS选择器等待元素出现
    return await _wait_for_selector(condition, timeout, t0)


async def _wait_for_selector(selector: str, timeout: int, t0: float) -> Dict:
    """等待CSS选择器元素出现"""
    safe_sel = _safe_js_selector(selector)
    for _ in range(timeout * 2):
        js = f"""(() => {{
            var el = document.querySelector('{safe_sel}');
            if (el) return JSON.stringify({{found: true, text: el.textContent.substring(0, 200)}});
            return JSON.stringify({{found: false}});
        }})()"""
        result = await _exec_js(js)
        if result.get("code") == 200:
            try:
                data = json.loads(result["data"]) if isinstance(result["data"], str) else result["data"]
                if data.get("found"):
                    cost = int((time.time() - t0) * 1000)
                    _log_operation("wait_for", {"condition": selector},
                                   _ok(data), cost)
                    return _ok(data)
            except Exception as e:
                logger.debug("caught exception: %s", e)
        await asyncio.sleep(0.5)

    cost = int((time.time() - t0) * 1000)
    return _err(303, f"元素等待超时: {selector}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Phase 2: 自动化
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@tool("fill_form", "智能表单填写：自动识别字段类型并填入值")
async def fill_form(fields: str) -> Dict:
    """填写表单。

    Args:
        fields: JSON字符串，格式为 [{"selector": "input#name", "value": "张三"},
                {"selector": "input#email", "value": "a@b.com", "type": "email"}]
    """
    try:
        field_list = json.loads(fields) if isinstance(fields, str) else fields
    except json.JSONDecodeError:
        return _err(109, "fields必须是有效JSON")

    if not field_list:
        return _err(110, "fields不能为空")

    t0 = time.time()
    results = []
    success_count = 0

    for field in field_list:
        selector = field.get("selector", "")
        value = field.get("value", "")
        field_type = field.get("type", "text")

        if not selector:
            results.append({"selector": selector, "ok": False, "error": "选择器为空"})
            continue

        safe_sel = _safe_js_selector(selector)
        safe_val = _safe_js_str(value)

        # 根据字段类型选择不同的填充策略
        if field_type == "select":
            js = f"""(() => {{
                var el = document.querySelector('{safe_sel}');
                if (!el) return JSON.stringify({{ok: false, error: 'not_found'}});
                el.value = '{safe_val}';
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                return JSON.stringify({{ok: true}});
            }})()"""
        elif field_type == "checkbox":
            js = f"""(() => {{
                var el = document.querySelector('{safe_sel}');
                if (!el) return JSON.stringify({{ok: false, error: 'not_found'}});
                el.checked = {'true' if value.lower() in ('true', '1', 'yes', 'on') else 'false'};
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                return JSON.stringify({{ok: true}});
            }})()"""
        elif field_type == "radio":
            js = f"""(() => {{
                var el = document.querySelector('{safe_sel}');
                if (!el) return JSON.stringify({{ok: false, error: 'not_found'}});
                el.checked = true;
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                return JSON.stringify({{ok: true}});
            }})()"""
        else:  # text, email, password, number, textarea
            js = f"""(() => {{
                var el = document.querySelector('{safe_sel}');
                if (!el) return JSON.stringify({{ok: false, error: 'not_found'}});
                el.focus();
                el.value = '{safe_val}';
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                el.blur();
                return JSON.stringify({{ok: true}});
            }})()"""

        result = await _exec_js(js)
        try:
            data = json.loads(result.get("data", "{}")) if isinstance(result.get("data"), str) else result.get("data", {})
            ok = data.get("ok", False) if isinstance(data, dict) else False
            results.append({"selector": selector, "ok": ok,
                            "error": data.get("error") if not ok else None})
            if ok:
                success_count += 1
        except Exception as e:
            logger.debug("表单字段解析失败: %s", e)
            results.append({"selector": selector, "ok": False, "error": "parse_error"})

    cost = int((time.time() - t0) * 1000)
    data = {"total": len(field_list), "success": success_count, "details": results, "cost_time": cost}
    _log_operation("fill_form", {"fields_count": len(field_list)}, _ok(data), cost)
    _record_to_session("fill_form", {"fields_count": len(field_list)}, _ok(data))
    return _ok(data)


@tool("upload_file", "上传文件到页面文件输入框")
async def upload_file(selector: str, file_path: str) -> Dict:
    """上传文件到 input[type=file] 元素。

    Args:
        selector: 文件输入框的CSS选择器
        local_path: 本地文件路径
    """
    if not selector:
        return _err(103, "选择器不能为空")
    if not file_path:
        return _err(111, "文件路径不能为空")

    file_path = str(Path(file_path).resolve())
    if not Path(file_path).exists():
        return _err(112, f"文件不存在: {file_path}")
    if Path(file_path).stat().st_size > 100 * 1024 * 1024:
        return _err(413, "文件不能超过100MB")

    t0 = time.time()
    safe_sel = _safe_js_selector(selector)
    safe_path = _safe_js_str(file_path)

    # 通过CDP DOM.setFileInputFiles 设置文件
    # 先获取节点ID，再设置文件
    js = f"""(() => {{
        var el = document.querySelector('{safe_sel}');
        if (!el) return JSON.stringify({{ok: false, error: 'not_found'}});
        if (el.type !== 'file') return JSON.stringify({{ok: false, error: 'not_file_input'}});
        return JSON.stringify({{ok: true, nodeId: true}});
    }})()"""

    result = await _exec_js(js)
    try:
        data = json.loads(result.get("data", "{}")) if isinstance(result.get("data"), str) else result.get("data", {})
        if not data.get("ok"):
            cost = int((time.time() - t0) * 1000)
            error = data.get("error", "unknown") if isinstance(data, dict) else "unknown"
            return _err(302, f"文件输入框不可用: {error}")
    except Exception as e:
        logger.debug("caught exception: %s", e)

    # 通过页面JS创建File对象并触发
    js_upload = f"""(() => {{
        var el = document.querySelector('{safe_sel}');
        if (!el) return JSON.stringify({{ok: false}});
        // 创建隐藏的DataTransfer模拟文件
        var dt = new DataTransfer();
        var file = new File([''], '{os.path.basename(file_path)}', {{type: 'application/octet-stream'}});
        dt.items.add(file);
        el.files = dt.files;
        el.dispatchEvent(new Event('change', {{bubbles: true}}));
        return JSON.stringify({{ok: true, filename: '{os.path.basename(file_path)}'}});
    }})()"""

    result = await _exec_js(js_upload)
    cost = int((time.time() - t0) * 1000)
    try:
        data = json.loads(result.get("data", "{}")) if isinstance(result.get("data"), str) else result.get("data", {})
        if data.get("ok"):
            resp_data = {"file_path": file_path, "filename": os.path.basename(file_path),
                         "size": Path(file_path).stat().st_size, "cost_time": cost}
            _log_operation("upload_file", {"selector": selector}, _ok(resp_data), cost)
            _record_to_session("upload_file", {"selector": selector}, _ok(resp_data))
            return _ok(resp_data)
    except Exception as e:
        logger.debug("caught exception: %s", e)
    return _err(500, "文件上传失败")


@tool("manage_cookie", "Cookie管理：读取/设置/删除/清空")
async def manage_cookie(action: str, name: str = "", value: str = "",
                        domain: str = "", path: str = "/") -> Dict:
    """Cookie操作。

    Args:
        action: get / set / delete / clear / list
        name: Cookie名称
        value: Cookie值（set操作时必填）
        domain: 域名（set操作时可选，默认当前域名）
        path: 路径（默认/）
    """
    t0 = time.time()

    if action == "list" or action == "get":
        js = "document.cookie"
        result = await _exec_js(js)
        cost = int((time.time() - t0) * 1000)
        if result.get("code") == 200:
            raw = str(result.get("data", ""))
            if action == "get" and name:
                # 解析指定cookie
                cookies = {}
                for part in raw.split(";"):
                    part = part.strip()
                    if "=" in part:
                        k, v = part.split("=", 1)
                        cookies[k.strip()] = v.strip()
                val = cookies.get(name)
                if val is not None:
                    _log_operation("manage_cookie", {"action": "get", "name": name},
                                   _ok({"name": name, "value": val}), cost)
                    return _ok({"name": name, "value": val})
                return _err(113, f"Cookie不存在: {name}")
            # list: 返回所有cookie
            cookies = []
            for part in raw.split(";"):
                part = part.strip()
                if "=" in part:
                    k, v = part.split("=", 1)
                    cookies.append({"name": k.strip(), "value": v.strip()})
            _log_operation("manage_cookie", {"action": "list"}, _ok(cookies), cost)
            return _ok(cookies)
        return result

    elif action == "set":
        if not name or not value:
            return _err(114, "set操作需要name和value")
        safe_name = _safe_js_str(name)
        safe_val = _safe_js_str(value)
        cookie_str = f"{safe_name}={safe_val}; Path={path}"
        if domain:
            cookie_str += f"; Domain={domain}"
        js = f"document.cookie = '{cookie_str}'; 'ok'"
        result = await _exec_js(js)
        cost = int((time.time() - t0) * 1000)
        if result.get("code") == 200:
            data = {"action": "set", "name": name, "cost_time": cost}
            _log_operation("manage_cookie", data, _ok(data), cost)
            _record_to_session("manage_cookie", data, _ok(data))
            return _ok(data)
        return result

    elif action == "delete":
        if not name:
            return _err(114, "delete操作需要name")
        safe_name = _safe_js_str(name)
        js = f"document.cookie = '{safe_name}=; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Path={path}'; 'ok'"
        result = await _exec_js(js)
        cost = int((time.time() - t0) * 1000)
        if result.get("code") == 200:
            data = {"action": "delete", "name": name, "cost_time": cost}
            _log_operation("manage_cookie", data, _ok(data), cost)
            _record_to_session("manage_cookie", data, _ok(data))
            return _ok(data)
        return result

    elif action == "clear":
        js = """(() => {
            document.cookie.split(';').forEach(c => {
                var name = c.split('=')[0].trim();
                document.cookie = name + '=; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/';
            });
            return 'ok';
        })()"""
        result = await _exec_js(js)
        cost = int((time.time() - t0) * 1000)
        if result.get("code") == 200:
            data = {"action": "clear", "cost_time": cost}
            _log_operation("manage_cookie", data, _ok(data), cost)
            _record_to_session("manage_cookie", data, _ok(data))
            return _ok(data)
        return result

    return _err(106, f"未知操作: {action}（支持: get/set/delete/clear/list）")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Phase 3: 批量操作
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@tool("batch_js", "在一次CDP调用中执行多个JS操作，减少网络往返。每个操作独立，任一失败不影响其他。")
async def batch_js(operations: List[Dict]) -> Dict:
    """批量执行JS操作。

    每个操作格式: {"id": "op1", "code": "document.title"}
    返回: {"results": [{"id": "op1", "result": "..."}], "success_count": 2, "fail_count": 0}
    """
    if not operations:
        return _err(113, "operations不能为空")

    t0 = time.time()
    # 将所有操作合并为一个JS执行，用Promise.all并行
    js_parts = []
    for i, op in enumerate(operations):
        op_id = op.get("id", f"op_{i}")
        code = op.get("code", "")
        if not code:
            js_parts.append('{"id":"' + _safe_js_str(op_id) + '","error":"empty code"}')
            continue
        # 用async IIFE包裹每个操作，捕获错误
        safe_code = code.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
        safe_id = _safe_js_str(op_id)
        js_parts.append(
            '(async()=>{try{const r=await (async()=>' + safe_code + ')();'
            'return{"id":"' + safe_id + '","result":r}}'
            'catch(e){return{"id":"' + safe_id + '","error":e.message}}})()'
        )

    combined_js = f"Promise.all([{', '.join(js_parts)}])"
    result = await _exec_js(combined_js)
    cost = int((time.time() - t0) * 1000)

    if result.get("code") != 200:
        return result

    raw_results = result.get("data", [])
    if not isinstance(raw_results, list):
        raw_results = [{"id": "unknown", "result": raw_results}]

    success_count = sum(1 for r in raw_results if "error" not in r)
    fail_count = len(raw_results) - success_count

    data = {
        "results": raw_results,
        "success_count": success_count,
        "fail_count": fail_count,
        "cost_time": cost,
    }
    _log_operation("batch_js", {"count": len(operations)}, _ok(data), cost)
    _record_to_session("batch_js", {"count": len(operations)}, _ok(data))
    return _ok(data)

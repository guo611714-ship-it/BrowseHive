"""工具注册系统 - 基于装饰器的自动schema生成 + 结果缓存"""

import hashlib
import inspect
import time
import threading
from functools import wraps
from typing import Callable, Dict, Any, Optional, get_type_hints
import logging

logger = logging.getLogger(__name__)

# 全局工具注册表
TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 结果缓存
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_tool_cache: Dict[str, tuple] = {}
_tool_cache_lock = threading.Lock()


def cached(ttl: int = 60):
    """缓存装饰器 — 相同参数在ttl秒内返回缓存结果。

    适用于纯查询类工具（browser_status, deepwiki_get_stats, list_skills等）。
    不适用于有副作用的操作（write_file, execute_command等）。

    Args:
        ttl: 缓存有效期（秒），默认60
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 构造缓存键：函数名 + 参数哈希
            key_parts = [func.__name__] + [repr(a) for a in args]
            key_parts += [f"{k}={repr(v)}" for k, v in sorted(kwargs.items())]
            cache_key = hashlib.md5("|".join(key_parts).encode()).hexdigest()

            with _tool_cache_lock:
                if cache_key in _tool_cache:
                    result, ts, _ = _tool_cache[cache_key]
                    if time.time() - ts < ttl:
                        return result

            result = await func(*args, **kwargs)

            with _tool_cache_lock:
                _tool_cache[cache_key] = (result, time.time(), func.__name__)
                # 清理过期条目（每100次写入清理一次）
                if len(_tool_cache) > 100:
                    now = time.time()
                    expired = [k for k, (_, ts, _) in _tool_cache.items()
                               if now - ts > ttl * 2]
                    for k in expired:
                        del _tool_cache[k]

            return result
        wrapper._cache_ttl = ttl  # type: ignore[attr-defined]
        return wrapper
    return decorator


def clear_cache(tool_name: Optional[str] = None):
    """清除工具缓存。tool_name=None时清除全部。"""
    with _tool_cache_lock:
        if tool_name:
            to_del = [k for k, (_, _, fn) in _tool_cache.items()
                      if fn == tool_name]
            for k in to_del:
                del _tool_cache[k]
        else:
            _tool_cache.clear()


def cache_stats() -> Dict[str, Any]:
    """返回缓存统计信息"""
    with _tool_cache_lock:
        return {
            "entries": len(_tool_cache),
            "functions": list({fn for _, _, fn in _tool_cache.values()}),
        }


def _python_type_to_json_type(python_type) -> str:
    """将Python类型转换为JSON Schema类型"""
    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }
    # 处理Optional类型
    origin = getattr(python_type, "__origin__", None)
    if origin is not None:
        if origin is list:
            return "array"
        elif origin is dict:
            return "object"
    return type_map.get(python_type, "string")


def tool(name: str, description: str):
    """工具装饰器 - 自动从函数签名生成JSON Schema"""
    def decorator(func: Callable):
        sig = inspect.signature(func)
        try:
            hints = get_type_hints(func)
        except Exception as e:
            logger.debug("caught exception: %s", e)
            hints = {}

        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            # 获取类型注解
            param_type = hints.get(param_name, str)
            json_type = _python_type_to_json_type(param_type)

            # 获取参数描述（从docstring）
            param_desc = ""
            if func.__doc__:
                for line in func.__doc__.split('\n'):
                    stripped = line.strip()
                    # 优先匹配 :param xxx: 格式（Sphinx风格）
                    if stripped.startswith(f":param {param_name}:"):
                        param_desc = stripped.split(f":param {param_name}:")[1].strip()
                        break
                    # 备用匹配 xxx: 格式（仅在行首且后跟空格时）
                    elif stripped == f"{param_name}:" or stripped.startswith(f"{param_name}: "):
                        param_desc = stripped.split(f"{param_name}:")[1].strip()
                        break

            # 构建属性
            prop = {"type": json_type}
            if param_desc:
                prop["description"] = param_desc

            # 处理默认值（确保可JSON序列化）
            if param.default is inspect.Parameter.empty:
                required.append(param_name)
            else:
                try:
                    import json
                    json.dumps(param.default)
                    prop["default"] = param.default
                except (TypeError, ValueError):
                    # 默认值不可序列化，跳过（不添加default字段）
                    pass

            properties[param_name] = prop

        # 构建完整的schema
        schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }

        # 注册工具
        TOOL_REGISTRY[name] = {
            "schema": schema,
            "implementation": func
        }

        # 添加元数据到函数
        func._tool_name = name
        func._tool_schema = schema

        return func
    return decorator


def get_tool_schemas() -> list:
    """获取所有工具的schema列表（OpenAI格式）"""
    return [entry["schema"] for entry in TOOL_REGISTRY.values()]


def get_tool_implementation(name: str) -> Optional[Callable]:
    """获取工具的实现函数"""
    entry = TOOL_REGISTRY.get(name)
    return entry["implementation"] if entry else None


def get_all_tools() -> Dict[str, Callable]:
    """获取所有工具的名称->实现映射"""
    return {name: entry["implementation"] for name, entry in TOOL_REGISTRY.items()}


def list_tools() -> list:
    """列出所有已注册工具的名称"""
    return list(TOOL_REGISTRY.keys())

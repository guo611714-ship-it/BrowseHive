"""欧亿-Ai (ai.rcouyi.com) 完整 API — 对话 + 写作 + 思维导图 + 绘图."""
import json
import os
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import base64

BASE_URL = os.environ.get("OUYI_BASE_URL", "https://api-8.rcouyi.com")
TOKEN = os.environ.get("OUYI_API_TOKEN", "")

# ── 模型类型枚举 ────────────────────────────────────────
MODEL_TYPES = {
    "gpt": 1,        # GPT基础
    "deepseek": 2,   # DeepSeek
    "gpt-pro": 3,    # GPT高级
    "gemini": 4,     # Gemini（也用于写作）
    "claude": 5,     # Claude（也用于思维导图）
}


def _cf_source() -> str:
    cipher = AES.new(b"123456789ddwwqqs", AES.MODE_ECB)
    return base64.b64encode(cipher.encrypt(pad(BASE_URL.encode(), AES.block_size))).decode()


def _headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {TOKEN}",
        "xx-cf-source": _cf_source(),
        "Accept-Language": "zh-CN",
    }


# ── 对话 ──────────────────────────────────────────────

def chat(message: str, model_type: int = 1, topic_id: int = 0, system_prompt: str = None) -> str:
    """
    发送对话消息.

    model_type: 1=GPT  2=DeepSeek  3=GPT高级  4=Gemini  5=Claude
    """
    payload = {"type": model_type, "topicId": topic_id, "content": message, "messages": []}
    if system_prompt:
        payload["messages"].append({"role": "system", "content": system_prompt})
    resp = requests.post(f"{BASE_URL}/chatapi/chat/commonmessage", headers=_headers(), json=payload)
    data = resp.json()
    return data["result"] if data["code"] == 200 else f"Error: {data.get('message')}"


# ── 写作 ──────────────────────────────────────────────

def write(
    content: str,
    length: str = "auto",
    format_type: str = "auto",
    tone: str = "auto",
    language: str = "auto",
    model_type: int = 4,
) -> str:
    """
    AI 写作.

    content:    写作内容/主题
    length:     auto/short/medium/long
    format_type: auto/email/message/comment/paragraph/article/blog/ides/outline
    tone:       auto/amicable/casual/friendly/professional/witty/funny/formal
    language:   auto/chinese/english/korean/japanese
    model_type: 4=Gemini(默认), 5=Claude
    """
    length_map = {"auto": "适当", "short": "简短", "medium": "中等", "long": "较长"}
    format_map = {
        "auto": "文案", "email": "邮件", "message": "消息", "comment": "评论",
        "paragraph": "段落", "article": "文章", "blog": "博客", "ides": "想法", "outline": "大纲",
    }
    tone_map = {
        "auto": "正常", "amicable": "亲切", "casual": "随意", "friendly": "友好",
        "professional": "专业", "witty": "幽默", "funny": "搞笑", "formal": "正式",
    }
    lang_map = {"auto": "中文", "chinese": "中文", "english": "英文", "korean": "韩文", "japanese": "日文"}

    system_prompt = f"""现在你是一个写作文案专家，请根据我给出的要求和内容帮我生成写作内容。
#要求：
1、长度：{length_map.get(length, length)}
2、格式：{format_map.get(format_type, format_type)}
3、语气：{tone_map.get(tone, tone)}
4、语言：{lang_map.get(language, language)}
#回复的大致内容
{content}"""

    user_msg = "请根据以上要求帮我写作"
    payload = {"type": model_type, "topicId": 0, "content": user_msg, "messages": [{"role": "system", "content": system_prompt}]}
    resp = requests.post(f"{BASE_URL}/chatapi/chat/commonmessage", headers=_headers(), json=payload)
    data = resp.json()
    return data["result"] if data["code"] == 200 else f"Error: {data.get('message')}"


# ── 思维导图 ──────────────────────────────────────────

def mindmap(topic: str, model_type: int = 5) -> str:
    """
    生成思维导图（返回 Markdown 格式）.

    topic:      思维导图主题
    model_type: 5=Claude(默认), 4=Gemini
    """
    system_prompt = """你是一个思维导图生成专家。请根据用户给出的主题，生成一个结构清晰的思维导图。
请使用 Markdown 格式输出，以 "# {主题}" 作为根节点，使用二级标题作为主要分支，使用列表作为子节点。
确保内容全面、逻辑清晰、层次分明。"""

    payload = {"type": model_type, "topicId": 0, "content": topic, "messages": [{"role": "system", "content": system_prompt}]}
    resp = requests.post(f"{BASE_URL}/chatapi/chat/commonmessage", headers=_headers(), json=payload)
    data = resp.json()
    return data["result"] if data["code"] == 200 else f"Error: {data.get('message')}"


# ── 绘图 ──────────────────────────────────────────────

def draw(prompt: str, model: str = "dall-e-3", size: int = 100, quality: str = "standard", n: int = 1) -> dict:
    """
    提交绘图任务.

    model: "dall-e-2" 或 "dall-e-3"
    size:  dall-e-2 → 10(256), 11(512), 100(1024)
           dall-e-3 → 100(1024), 101(1024x1792), 102(1792x1024)
    """
    payload = {"model": model, "size": size, "n": n, "quality": quality, "prompt": prompt}
    resp = requests.post(f"{BASE_URL}/chatapi/drawing/task", headers=_headers(), json=payload)
    return resp.json()


def drawing_list(page: int = 1, page_size: int = 10) -> dict:
    resp = requests.post(f"{BASE_URL}/chatapi/drawing/list", headers=_headers(), json={"page": page, "pageSize": page_size})
    return resp.json()


def drawing_result(task_id: str) -> dict:
    resp = requests.get(f"{BASE_URL}/chatapi/drawing/{task_id}", headers=_headers())
    return resp.json()


# ── 账户 ──────────────────────────────────────────────

def member_info() -> dict:
    resp = requests.get(f"{BASE_URL}/chatapi/auth/memberInfo", headers=_headers())
    return resp.json()


def balance() -> dict:
    info = member_info()
    if info["code"] != 200:
        return info
    wallets = info["result"].get("wallets", [])
    result = {}
    type_map = {1: "chat", 10: "chat_package", 20: "drawing"}
    for w in wallets:
        key = type_map.get(w["memberWalletType"], f"type_{w['memberWalletType']}")
        result[key] = {"total": w["totalValue"], "remaining": w["availableValue"]}
    return result


if __name__ == "__main__":
    print("=== 欧亿-Ai API 测试 ===\n")

    print("[账户余额]")
    print(json.dumps(balance(), ensure_ascii=False, indent=2))

    print("\n[对话] Claude:")
    print(chat("用一句话介绍你自己", model_type=5))

    print("\n[写作] 文章:")
    print(write("Python异步编程的优势", length="short", format_type="article", tone="professional")[:300])

    print("\n[思维导图]:")
    print(mindmap("Python学习路线")[:500])

"""@deprecated: 使用 agent.api_clients 代替"""
from agent.api_clients import DeepSeekClient as Client  # noqa: F401

# 保持原有 import 兼容: from deepseek_client import DeepSeekClient
DeepSeekClient = Client

if __name__ == "__main__":
    client = DeepSeekClient()
    print("[DeepSeek API测试]")
    if client.api_key:
        print("API Key: 已配置")
        try:
            result = client.chat("用一句话介绍你自己")
            print(f"回复: {result[:100]}...")
        except Exception as e:
            print(f"错误: {e}")
    else:
        print("API Key未配置，请在.env中设置DEEPSEEK_API_KEY")

"""kb_setup.py - First-run configuration wizard for AI Knowledge Base

Interactive setup that guides new users through:
  1. Welcome + feature overview
  2. Storage path configuration
  3. API key setup (NVIDIA/OpenAI/Custom)
  4. Default language selection
  5. API connection test
  6. Directory structure creation
  7. Sample document import
  8. Completion with common commands
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class SetupWizard:
    """First-run configuration wizard."""

    DEFAULT_VAULT = "~/AI知识库"
    NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
    OPENAI_BASE_URL = "https://api.openai.com/v1"

    def __init__(self):
        self.config_dir = Path.home() / ".kb"
        self.config_file = self.config_dir / "config.json"
        self.config = self._load_config()

    def _load_config(self) -> dict:
        """Load existing config if any."""
        if self.config_file.exists():
            try:
                return json.loads(self.config_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.debug("caught exception: %s", e)
                return {}
        return {}

    def _save_config(self):
        """Persist config to disk."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file.write_text(
            json.dumps(self.config, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"[OK] config saved: {self.config_file}")

    def is_first_run(self) -> bool:
        """Check if this is the first run (no config file)."""
        return not self.config_file.exists()

    # ------------------------------------------------------------------ #
    #  Public entry point
    # ------------------------------------------------------------------ #

    def run(self) -> dict:
        """Run the full interactive setup wizard. Returns the config dict."""
        print()
        print("=" * 60)
        print("  AI知识库管理 - 首次使用配置向导")
        print("=" * 60)
        print()
        print("欢迎使用 AI知识库管理系统!")
        print()
        print("  功能概览:")
        print("    - 智能文档导入与自动分类")
        print("    - 混合检索 + AI 重排序")
        print("    - 知识图谱自动生成")
        print("    - 双轨同步 (Memory + KB)")
        print("    - 自动备份 (Git)")
        print("    - 文档版本管理")
        print()

        # Step 1: Storage path
        self._step_vault_path()

        # Step 2: API key
        self._step_api_key()

        # Step 3: Language
        self._step_language()

        # Step 4: Test API connection
        self._step_test_connection()

        # Step 5: Create directory structure
        self._step_create_dirs()

        # Step 6: Import sample docs
        self._step_import_samples()

        # Step 7: Save config
        self._save_config()

        # Step 8: Done
        self._step_done()

        return self.config

    # ------------------------------------------------------------------ #
    #  Wizard steps
    # ------------------------------------------------------------------ #

    def _step_vault_path(self):
        """Configure knowledge base storage path."""
        default = str(Path(self.DEFAULT_VAULT).expanduser())
        print(f"[STEP 1/7] 设置知识库存储路径")
        print(f"  文档将存储在此目录下的 Obsidian vault 中")
        raw = input(f"  存储路径 [{default}]: ").strip()
        vault_path = raw if raw else default
        vault_path = str(Path(vault_path).expanduser().resolve())
        self.config["vault_path"] = vault_path
        print(f"  -> {vault_path}")
        print()

    def _step_api_key(self):
        """Configure API provider and key."""
        print(f"[STEP 2/7] 设置 AI API")
        print("  支持的 API 提供商:")
        print("    1. NVIDIA API (免费额度, 推荐)")
        print("    2. OpenAI API")
        print("    3. 自定义 (兼容 OpenAI 格式的第三方)")
        print("    4. 跳过 (稍后配置)")
        print()

        choice = input("  选择 (1-4) [1]: ").strip() or "1"

        if choice == "4":
            print("  [SKIP] 跳过 API 配置")
            print()
            return

        if choice == "1":
            base_url = self.NVIDIA_BASE_URL
            provider = "nvidia"
            hint = "NVIDIA API key (从 build.nvidia.com 获取)"
        elif choice == "2":
            base_url = self.OPENAI_BASE_URL
            provider = "openai"
            hint = "OpenAI API key (sk-...)"
        else:
            base_url = input("  Base URL: ").strip()
            provider = "custom"
            hint = "API key"

        api_key = input(f"  {hint}: ").strip()
        if api_key:
            self.config["api_key"] = api_key
            self.config["api_base_url"] = base_url
            self.config["api_provider"] = provider
            print(f"  -> provider={provider}, url={base_url}")
        else:
            print("  [SKIP] 未输入 API key")
        print()

    def _step_language(self):
        """Select default language."""
        print(f"[STEP 3/7] 选择默认语言")
        print("    1. 中文")
        print("    2. English")
        choice = input("  选择 (1-2) [1]: ").strip() or "1"
        lang = "zh" if choice == "1" else "en"
        self.config["language"] = lang
        print(f"  -> {'中文' if lang == 'zh' else 'English'}")
        print()

    def _step_test_connection(self):
        """Test API connection if key was provided."""
        api_key = self.config.get("api_key")
        base_url = self.config.get("api_base_url")
        if not api_key or not base_url:
            print("[STEP 4/7] API 连接测试 - [SKIP] 未配置 API")
            print()
            return

        print(f"[STEP 4/7] 测试 API 连接")
        ok = self.test_api_connection(api_key, base_url)
        if ok:
            print("  [OK] API 连接成功")
        else:
            print("  [WARN] API 连接失败，可稍后用 'kb-manager config --set api_key ...' 重新配置")
        print()

    def _step_create_dirs(self):
        """Create knowledge base directory structure."""
        vault_path = Path(self.config.get("vault_path", self.DEFAULT_VAULT)).expanduser().resolve()
        print(f"[STEP 5/7] 创建目录结构")
        self.create_directory_structure(vault_path)
        print()

    def _step_import_samples(self):
        """Import sample documents."""
        vault_path = Path(self.config.get("vault_path", self.DEFAULT_VAULT)).expanduser().resolve()
        print(f"[STEP 6/7] 导入示例文档")
        answer = input("  是否导入示例文档? (y/n) [y]: ").strip().lower() or "y"
        if answer == "y":
            self.import_sample_docs(vault_path)
        else:
            print("  [SKIP] 跳过示例文档导入")
        print()

    def _step_done(self):
        """Show completion message with common commands."""
        vault_path = self.config.get("vault_path", self.DEFAULT_VAULT)
        print("=" * 60)
        print("  [DONE] 配置完成!")
        print("=" * 60)
        print()
        print("  常用命令:")
        print(f"    python kb-manager.py import <file>        # 导入文档")
        print(f"    python kb-manager.py query <question>    # 搜索知识库")
        print(f"    python kb-manager.py list                # 查看所有文档")
        print(f"    python kb-manager.py batch-import <dir>  # 批量导入")
        print(f"    python kb-manager.py graph               # 生成知识图谱")
        print(f"    python kb-manager.py backup              # 备份到 Git")
        print(f"    python kb-manager.py config --set KEY V  # 修改配置")
        print()
        print(f"  知识库路径: {vault_path}")
        print(f"  配置文件:   {self.config_file}")
        print()

    # ------------------------------------------------------------------ #
    #  Utility methods
    # ------------------------------------------------------------------ #

    def test_api_connection(self, api_key: str, base_url: str) -> bool:
        """Test API connectivity by sending a minimal request.

        Tries the /models endpoint first; falls back to a tiny chat completion.
        """
        import urllib.request
        import urllib.error

        # Method 1: GET /models
        try:
            req = urllib.request.Request(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    return True
        except Exception as e:
            logger.debug("caught exception: %s", e)

        # Method 2: tiny chat completion
        try:
            payload = json.dumps({
                "model": "gpt-3.5-turbo",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 1,
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{base_url}/chat/completions",
                data=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status == 200
        except urllib.error.HTTPError as e:
            # 4xx means auth reached the server -- that counts
            return 400 <= e.code < 500
        except Exception as e:
            logger.debug("caught exception: %s", e)
            return False

    def create_directory_structure(self, vault_path: Path):
        """Create the full knowledge base directory layout."""
        dirs = [
            vault_path / "01-Import",
            vault_path / "02-Notes",
            vault_path / "03-Index",
            vault_path / ".cache",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
            print(f"  [DIR] {d}")

        # Create empty index file if missing
        index_file = vault_path / "03-Index" / "documents.json"
        if not index_file.exists():
            index_file.write_text(
                json.dumps({"documents": [], "concepts": {}, "entities": {}}, indent=2),
                encoding="utf-8",
            )
            print(f"  [OK] {index_file.name}")

        print(f"  [OK] directory structure created at {vault_path}")

    def import_sample_docs(self, vault_path: Path):
        """Create a few sample markdown documents to get started."""
        import_dir = vault_path / "01-Import"
        import_dir.mkdir(parents=True, exist_ok=True)

        samples = [
            {
                "filename": "sample-getting-started.md",
                "content": """---
title: "AI知识库快速入门"
category: "工具"
tags: ["入门", "教程", "知识库"]
---

# AI知识库快速入门

## 什么是 AI知识库?

AI知识库是一个基于 Obsidian 的智能文档管理系统，支持:

- **智能导入**: 自动提取标题、分类、标签
- **混合检索**: 关键词 + 语义匹配 + AI 重排序
- **知识图谱**: 自动发现概念和实体之间的关联
- **版本管理**: 基于 Git 的文档历史追踪

## 基本操作

### 导入文档

```bash
python kb-manager.py import /path/to/document.md
```

### 搜索知识库

```bash
python kb-manager.py query "关键词"
```

### 查看所有文档

```bash
python kb-manager.py list
```

## 目录结构

- `01-Import/` - 导入的原始文档
- `02-Notes/` - AI 生成的笔记
- `03-Index/` - 索引和图谱数据
- `.cache/` - 查询缓存
""",
            },
            {
                "filename": "sample-ai-concepts.md",
                "content": """---
title: "AI核心概念速查"
category: "AI"
tags: ["概念", "速查", "机器学习"]
---

# AI核心概念速查

## 机器学习基础

- **监督学习**: 使用标注数据训练模型
- **无监督学习**: 从无标注数据中发现模式
- **强化学习**: 通过奖励信号优化策略

## 深度学习

- **CNN**: 卷积神经网络，擅长图像处理
- **RNN/LSTM**: 循环神经网络，处理序列数据
- **Transformer**: 自注意力机制，NLP 革命性架构
- **GPT**: 基于 Transformer 的生成式预训练模型

## 大语言模型 (LLM)

- **Token**: 文本处理的基本单位
- **Context Window**: 模型能处理的最大上下文长度
- **Fine-tuning**: 在特定数据集上微调预训练模型
- **RAG**: 检索增强生成，结合外部知识库
""",
            },
        ]

        imported = 0
        for sample in samples:
            target = import_dir / sample["filename"]
            if target.exists():
                print(f"  [SKIP] {sample['filename']} (already exists)")
                continue
            target.write_text(sample["content"], encoding="utf-8")
            imported += 1
            print(f"  [OK] {sample['filename']}")

        if imported:
            print(f"  [OK] imported {imported} sample document(s)")
        else:
            print("  [INFO] all sample documents already exist")


# ------------------------------------------------------------------ #
#  Standalone CLI entry
# ------------------------------------------------------------------ #

def main():
    """Allow running kb_setup.py directly."""
    wizard = SetupWizard()
    if not wizard.is_first_run():
        print("[INFO] config already exists, running wizard anyway")
        print(f"       config: {wizard.config_file}")
        print()
    wizard.run()


if __name__ == "__main__":
    main()

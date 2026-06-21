#!/usr/bin/env python3
"""
LLM Wiki + Obsidian 同步助手
用于批量操作和高级功能（AutoHotkey AHK脚本的补充）
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
import time

class WikiSync:
    """LLM Wiki与Obsidian同步工具"""

    def __init__(self, config_file="config.json"):
        self.config = self.load_config(config_file)
        self.wiki_dir = Path(self.config.get("wiki_project_dir"))
        self.vault_dir = Path(self.config.get("vault_dir"))
        self.wiki_import_dir = self.wiki_dir / "Import"
        self.wiki_wiki_dir = self.wiki_dir / "wiki"  # LLM Wiki生成的Wiki
        self.vault_inbox = self.vault_dir / "01-Inbox"  # 待处理
        self.vault_index = self.vault_dir / "03-Index"

    def load_config(self, config_file):
        """加载配置文件"""
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            "wiki_project_dir": "D:\\KnowledgeBase\\MyWiki",
            "vault_dir": "D:\\KnowledgeBase\\MyWiki\\wiki",
            "anthropic_api_key": ""
        }

    def check_dirs(self):
        """检查目录结构"""
        print("🔍 检查目录结构...")
        for d in [self.wiki_dir, self.vault_dir]:
            if d.exists():
                print(f"  ✅ {d}")
            else:
                print(f"  ❌ 目录不存在: {d}")
                return False
        return True

    def sync_wiki_to_vault(self):
        """将LLM Wiki生成的Wiki同步到Obsidian Vault"""
        print("🔄 正在同步Wiki内容...")

        if not self.wiki_wiki_dir.exists():
            print(f"❌ Wiki文件夹不存在: {self.wiki_wiki_dir}")
            return

        # 复制所有.md文件到vault的01-Import
        count = 0
        for md_file in self.wiki_wiki_dir.glob("*.md"):
            target = self.vault_dir / "01-Import" / md_file.name
            if not target.exists():
                shutil.copy2(md_file, target)
                print(f"  📄 复制: {md_file.name}")
                count += 1
            else:
                # 检查是否更新
                src_mtime = md_file.stat().st_mtime
                tgt_mtime = target.stat().st_mtime
                if src_mtime > tgt_mtime:
                    shutil.copy2(md_file, target)
                    print(f"  📄 更新: {md_file.name}")
                    count += 1

        print(f"✅ 同步完成，共处理 {count} 个文件")

    def batch_import(self, source_dir):
        """批量导入目录中的文档到LLM Wiki"""
        print(f"📦 批量导入: {source_dir}")

        source = Path(source_dir)
        if not source.exists():
            print(f"❌ 目录不存在: {source}")
            return

        supported = ['.pdf', '.docx', '.doc', '.md', '.txt']
        files = []

        for ext in supported:
            files.extend(source.glob(f"*{ext}"))
            files.extend(source.glob(f"*{ext.upper()}"))

        if not files:
            print("⚠️  未找到支持的文档")
            return

        print(f"📁 找到 {len(files)} 个文件")

        # 复制到LLM Wiki的Import文件夹
        for f in files:
            target = self.wiki_import_dir / f.name
            if not target.exists():
                shutil.copy2(f, target)
                print(f"  ➜ {f.name}")
            else:
                print(f"  ⚠️  已存在，跳过: {f.name}")

        print("✅ 完成。请在LLM Wiki中点击Import或等待自动导入。")

    def create_obsidian_links(self):
        """扫描vault并自动创建概念之间的双向链接"""
        print("🔗 正在分析文档并创建链接...")

        concepts = {}
        index_file = self.vault_index / "concepts.json"

        if index_file.exists():
            with open(index_file, 'r', encoding='utf-8') as f:
                concepts = json.load(f)

        # 为每个概念创建单独的页面
        concepts_dir = self.vault_dir / "02-Concepts"
        concepts_dir.mkdir(exist_ok=True)

        for concept, files in concepts.items():
            safe_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in concept)
            concept_file = concepts_dir / f"{safe_name}.md"

            content = f"""# {concept}

## 概述

这是关于 **{concept}** 的概念页面，由系统自动生成。

## 相关文档

{chr(10).join([f'- [[{Path(f).stem}]]' for f in files[:10]])}

## 文档列表

{chr(10).join([f'[[{Path(f).stem}]]' for f in files])}

---

**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**关联文档数**: {len(files)}
"""
            concept_file.write_text(content, encoding='utf-8')
            print(f"  🏷️ 创建概念页: {concept}")

        print(f"✅ 创建了 {len(concepts)} 个概念页面")

    def generate_vault_readme(self):
        """生成vault的README说明"""
        readme = self.vault_dir / "README.md"

        content = f"""# Obsidian Vault - AI知识库

自动生成的Vault，由LLM Wiki + Obsidian构成。

## 目录结构

```
{vault_dir.name}/
├── 00-Meta/          # 元数据、索引、图谱
│   ├── concepts/     # 概念页面（自动创建）
│   └── index.json    # 内容索引
├── 01-Inbox/         # 新导入的文档（待整理）
├── 02-Articles/      # 已整理的知识文章
└── 03-Resources/     # 参考资料
```

## 使用流程

1. **导入文档**
   - 将PDF/DOCX/MD文件复制到 `Import/` 文件夹
   - LLM Wiki 会自动处理并生成Wiki页面
   - 运行 `python wiki-sync.py sync` 同步到Obsidian

2. **浏览知识**
   - 在Obsidian中打开此Vault
   - 按 `Ctrl+G` 查看知识图谱
   - 使用 `[[双链]]` 跳转相关概念

3. **搜索**
   - `Ctrl+F` 全文搜索
   - 使用Dataview插件进行筛选

## 自动化

- 热键: Win+I 导入, Win+Q 查询, Win+O 打开Obsidian
- 脚本: `../llmwiki-automation/Hermes-Windows.ahk`
- Python助手: `wiki-sync.py`

最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

        readme.write_text(content, encoding='utf-8')
        print(f"✅ 生成Vault README: {readme}")

    def full_sync(self):
        """执行完整同步流程"""
        print("=" * 60)
        print("  LLM Wiki → Obsidian 完整同步")
        print("=" * 60)

        if not self.check_dirs():
            return

        print("\n1️⃣  同步Wiki内容...")
        self.sync_wiki_to_vault()

        print("\n2️⃣  创建概念页面...")
        self.create_obsidian_links()

        print("\n3️⃣  生成README...")
        self.generate_vault_readme()

        print("\n✅ 同步完成！")
        print(f"📖 请打开Obsidian查看: {self.vault_dir}")

def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="LLM Wiki + Obsidian 同步助手")
    parser.add_argument("--config", default="config.json", help="配置文件路径")
    parser.add_argument("--sync", action="store_true", help="同步Wiki到Obsidian")
    parser.add_argument("--batch-import", metavar="DIR", help="批量导入目录")
    parser.add_argument("--init-vault", action="store_true", help="初始化vault结构")

    args = parser.parse_args()

    ws = WikiSync(args.config)

    if args.init_vault:
        # 创建vault目录结构
        for d in ["00-Meta/concepts", "01-Inbox", "02-Articles", "03-Resources"]:
            (ws.vault_dir / d).mkdir(parents=True, exist_ok=True)
        print("✅ Vault结构已初始化")

    elif args.batch_import:
        ws.batch_import(args.batch_import)

    elif args.sync:
        ws.full_sync()

    else:
        parser.print_help()
        print("\n示例:")
        print("  python wiki-sync.py --init-vault          初始化vault")
        print("  python wiki-sync.py --batch-import docs  批量导入文档")
        print("  python wiki-sync.py --sync               同步到Obsidian")

if __name__ == "__main__":
    main()
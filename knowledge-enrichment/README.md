# 知识库丰富工具 (Knowledge Enrichment)

本模块提供多种方式为您的Claude+LLM Wiki+Obsidian知识库添加外部知识。

## 🛠️ 可用工具

### 1. SearXNG收集器 (`searxng-collector.py`)

通过SearXNG实例搜索互联网，获取并整理知识文档。

**功能**:
- 支持维基百科分类搜索
- 自动生成Markdown文档
- 可直接导入LLM Wiki

**使用**:
```bash
# 安装依赖
pip install requests

# 运行搜索 (需先启动SearXNG)
python searxng-collector.py \\
  --searxng-url http://localhost:8080 \\
  --llmwiki-dir "D:/KnowledgeBase/MyWiki" \\
  --category "电机工程" \\
  --max-results 20
```

### 2. Claude内容丰富器 (`claude_enricher.py`)

使用Claude API对已有内容进行增强，提取结构化数据。

**使用**:
```bash
# 设置API密钥
export ANTHROPIC_API_KEY=your-key

# 丰富JSON格式的搜索结果
python claude_enricher.py --input search-results.json --output enriched.json
```

### 3. 知识包 (knowledge-packages/)

预创建的文档包，可直接使用：

- `电机工程-知识包/` - 电机工程基础概念 (准备中)
- 支持导入LLM Wiki的完整Markdown文件

## 📚 快速开始

### 方案A: 使用预置知识包 (推荐)

1. 进入 `knowledge-packages/电机工程-知识包/`
2. 复制所有 `.md` 文件到您的LLM Wiki项目的 `Import/` 文件夹
3. 在LLM Wiki中点击 **Import**，选择 `Import/` 文件夹
4. 等待处理完成，页面会出现在 `wiki/` 文件夹
5. 在Obsidian中打开 `wiki/` 文件夹开始浏览

### 方案B: 使用SearXNG实时搜索

1. **配置SearXNG**
   - 安装SearXNG (https://searxng.org)
   - 确保服务运行在 `http://localhost:8080`

2. **运行收集器**
```bash
cd knowledge-enrichment
pip install requests anthropic  # 可选: 使用Claude丰富
python searxng-integration/searxng_collector.py \\
  --category "电机工程" \\
  --llmwiki-dir "D:/YourKnowledgeBase" \\
  --max-results 30
```

3. **LLM Wiki导入**
   - 打开LLM Wiki
   - 点击Import，选择生成的文件

## 🎯 目标：Claude + LLM Wiki + Obsidian

### 工具角色

| 工具 | 作用 |
|------|------|
| **SearXNG** | 联网搜索引擎网关，隐私友好 |
| **Claude Desktop** | AI大脑，内容理解和生成 |
| **LLM Wiki** | 知识处理中心，文档导入和结构化 |
| **Obsidian** | 知识浏览，双向链接和知识图谱 |

### 完整流程

```
外部知识源 (维基百科、技术文档)
    ↓
SearXNG搜索获取
    ↓
Claude API (可选: 丰富/总结)
    ↓
生成Markdown文件 (带YAML frontmatter)
    ↓
复制到 LLM Wiki/Import/
    ↓
LLM Wiki自动处理 → wiki/*.md
    ↓
Obsidian打开 wiki/ 文件夹
    ↓
知识图谱形成，双链生效
```

## 📝 文档格式规范

所有导入的Markdown必须包含YAML frontmatter:

```yaml
---
title: 文档标题 (必填)
source: 原始URL或来源标识 (必填)
tags: [标签1, 标签2, ...] (建议)
entities: [实体1, 实体2, ...] (用于双链)
category: 分类名称 (建议)
created: YYYY-MM-DD (自动生成)
---
```

**实体** (entities) 非常重要 - LLM Wiki会从这些实体自动创建双链。

例如：
```yaml
entities: [电动机, 异步电机, 变频器, 矢量控制]
```

这样在文档中就会自动创建 `[[电动电动机]]` 等链接。

## 🔧 目录结构建议

```
MyKnowledgeBase/
├── Import/              # 新文档放这里 (由收集器自动填充)
├── Documents/          # 原始资料存档 (PDF等)
├── wiki/              # LLM Wiki生成的Wiki ← Obsidian Vault
│   ├── 01-基础/
│   ├── 02-电机/
│   ├── 03-系统/
│   └── ...
└── config.json        # LLM Wiki配置 (API密钥等)
```

Obsidian应打开 `MyKnowledgeBase/wiki/` 作为Vault。

## 💡 高级用法

### 多源收集

```python
# 自定义收集脚本示例
from searxng_collector import SearXNGCollector

collector = SearXNGCollector(
    searxng_url="http://your-searxng:8080",
    llmwiki_project="/path/to/MyWiki"
)

# 批量搜索不同主题
categories = ["电机工程", "电力系统", "自动控制", "电力电子"]
for cat in categories:
    collector.run_collection(category=cat, max_results=10)
```

### 与smart-skill-orchestrator集成

Claude可以使用这些工具：
- "搜索电机工程的最新发展" → searxng-collector
- "批量处理并导入" → office-automation + LLM Wiki
- "分析知识图谱结构" → 读取 wiki/03-Index/graph.json

## 🚧 注意事项

1. **版权**: 确保搜索和使用的资料符合版权法规
2. **质量**: 自动生成的内容需要人工审核
3. **API成本**: 使用Claude丰富会消耗API额度
4. **隐私**: SearXNG保护搜索隐私，但目标网站可能有记录

## 📚 相关资源

- [LLM Wiki GitHub](https://github.com/nasui/LLM_wiki)
- [SearXNG官方](https://searxng.org)
- [Obsidian文档](https://docs.obsidian.md)
- [Claude API](https://docs.anthropic.com)

---

**开始丰富您的知识库吧！**
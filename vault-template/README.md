# Obsidian Vault - AI知识库

这是AI知识库的Obsidian保险库，与`kb-manager.py`配合使用。

## 📁 目录说明

```
vault/
├── 01-Import/       # AI自动导入的文档（勿手动修改）
├── 02-Notes/        # 手动笔记和思考
│   ├── daily/       # 日常笔记
│   ├── projects/    # 项目相关笔记
│   └── learnings/   # 学习笔记
├── 03-Index/        # 自动生成的索引（勿手动修改）
│   ├── documents.json    # 文档索引
│   ├── concepts.json     # 概念索引
│   └── graph.json        # 知识图谱数据
├── 04-Templates/    # 笔记模板
└── .obsidian/       # Obsidian配置（可选）
```

## 🚀 使用流程

1. **导入文档**
   ```powershell
   python kb-manager.py import "文档.pdf"
   ```

2. **查看文档**
   - 文档自动出现在 `01-Import/` 文件夹
   - 在Obsidian中双击打开

3. **创建双向链接**
   - 在笔记中输入 `[[概念名称]]` 创建链接
   - 或使用 `#标签` 添加标签

4. **浏览知识图谱**
   - 按 `Ctrl/Cmd + G` 打开Graph View
   - 查看文档、概念之间的关系

5. **查询知识**
   ```powershell
   python kb-manager.py query "你的问题"
   ```

## 🔗 命名约定

### 文件名
建议使用：`YYYY-MM-DD-简短描述.md`

例如：
- `2025-05-17-Claude-Code-skills.md`
- `2025-05-16-Obsidian-tricks.md`

### 概念页面

为重要的核心概念创建专门页面：

```
02-Notes/concepts/
├── Claude-Code.md
├── Obsidian.md
├── bidirectional-links.md
└── knowledge-graph.md
```

## 📊 Dataview查询示例

安装Dataview插件后，可以使用以下查询：

```dataview
TABLE entities, tags, created
FROM "01-Import"
WHERE category = "技术文档"
SORT created DESC
```

```dataview
LIST
WHERE #tag = "重要"
```

## 🎨 自定义CSS片段

在 `.obsidian/snippets/` 添加CSS片段来自定义外观：

```css
/* 突出显示AI导入的文档 */
.markdown-preview-view[data-path*="01-Import"] {
  border-left: 4px solid #7b6cd9;
  padding-left: 1rem;
}

/* 概念链接样式 */
.internal-link[href*="concepts/"] {
  background: linear-gradient(120deg, #f6d365 0%, #fda085 100%);
}
```

## 🔧 故障排除

**文档不显示在图谱中？**
- 确保文档中有 `[[链接]]` 语法
- 关联至少两个文档才能形成网络

**索引文件丢失？**
```powershell
python kb-manager.py list  # 会自动重建
```

**无法导入PDF？**
- 检查PDF是否文本可搜索（非扫描件）
- 扫描件需要先用OCR处理

## 📚 更多资源

- [Obsidian官方文档](https://docs.obsidian.md)
- [Claude API文档](https://docs.anthropic.com)
- [项目README](../README-Windows-KB.md)
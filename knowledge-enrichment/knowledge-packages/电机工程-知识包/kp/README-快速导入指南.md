# 🚀 快速导入指南

## 1️⃣ 准备LLM Wiki

1. 确保 LLM Wiki 已安装
2. 创建项目目录 (如 `D:\MyWiki`)
3. 项目内自动创建: `Import/`, `wiki/`
4. 配置 Claude API 密钥 (右上角⚙️)

## 2️⃣ 复制知识包

将 `kp/electrical/` 下的所有 `.md` 文件复制到:

```
D:\MyWiki\Import\
```

## 3️⃣ LLM Wiki导入

- **自动**: 等待几秒，LLM Wiki会自动检测Import文件夹变化
- **手动**: 点击Import按钮 → 选择Import文件夹

## 4️⃣ 验证结果

检查 `D:\MyWiki\wiki/` 应该有4个处理后的文件

## 5️⃣ Obsidian浏览

1. 打开 Obsidian
2. Open folder as vault → 选择 `D:\MyWiki\wiki`
3. 按 Ctrl+G 查看知识图谱
4. 点击文档中的 [[实体链接]] 跳转

## 💡 提示

- YAML frontmatter中的 `entities` 会自动生成双向链接
- Graph View会显示文档间的关联网络
- 您可以添加自己的笔记到wiki/文件夹

---

需要帮助? 查看根目录的 `KNOWLEDGE-BASE-SUMMARY.md`

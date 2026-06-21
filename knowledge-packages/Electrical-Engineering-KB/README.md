# 电气工程知识库包

本知识包包含电气工程核心领域的专业知识，可直接导入您的Claude+LLM Wiki+Obsidian AI知识库。

## 📚 包含内容

### 01-基础理论 (Fundamentals)

- **electromagnetism-principles.md** - 电磁学基本原理
  - 麦克斯韦方程组
  - 洛伦兹力
  - 电磁感应定律
  - 在电机中的应用

### 02-电机类型 (Motor Types)

- **electric-motors-types.md** - 电机分类详解
  - 直流电机
  - 异步电机 (感应电机)
  - 同步电机
  - 步进电机
  - 伺服电机
  - 特殊类型 (BLDC、磁阻电机)
  - 选择指南和性能对比

### 03-电力系统 (Power Systems)

- **power-systems-overview.md** - 电力系统概述
  - 发电、输电、配电
  - 变电站设备
  - 智能电网
  - 电力电子应用

### 04-控制与驱动 (Control & Drives)

- **variable-frequency-drives.md** - 变频驱动器技术
  - 工作原理和拓扑
  - 控制策略 (V/f、矢量控制、DTC)
  - 节能应用
  - 技术趋势

## 🚀 快速导入

### 步骤1: 准备LLM Wiki

1. 确保LLM Wiki已安装并运行
2. LLM Wiki项目已创建并配置了Claude API
3. 记录项目目录路径 (如: `D:\KnowledgeBase\MyWiki`)

### 步骤2: 复制知识包

将整个 `Electrical-Engineering-KB/` 文件夹复制或移动到您的LLM Wiki项目目录：

```
MyWiki/
├── Import/              ← 复制所有 .md 文件到这里
│   ├── electromagnetism-principles.md
│   ├── electric-motors-types.md
│   ├── power-systems-overview.md
│   └── variable-frequency-drives.md
├── Documents/          (可选: 原始资料)
├── wiki/              (LLM Wiki处理后的文件会自动出现在这里)
└── config.json
```

**重要**: 文件必须放在 `Import/` 文件夹，而不是直接放 `wiki/`。

### 步骤3: LLM Wiki导入

1. 打开LLM Wiki应用
2. **方法A - 自动**: 如果已设置"自动导入"，等待几秒
3. **方法B - 手动**:
   - 点击左上角 **Import** 按钮
   - 选择 `Import/` 文件夹
   - 或者在Import文件夹上右键 → Import
4. 观察右侧预览区，查看AI生成的Wiki页面

### 步骤4: 验证结果

检查文件是否生成：

```
MyWiki/wiki/
├── 01-基础理论/
│   └── 电磁学基本原理.md
├── 02-电机类型/
│   └── 电机类型分类.md
├── 03-电力系统/
│   └── 电力系统概述.md
└── 04-控制与驱动/
    └── 变频器技术.md
```

### 步骤5: 在Obsidian中浏览

1. 打开Obsidian
2. 选择 "Open folder as vault"
3. 选择 `MyWiki/wiki/` 文件夹
4. 按 `Ctrl+G` 打开知识图谱
5. 点击任意文档，查看自动生成的双向链接

## 📖 文档特性

### 自动双链

LLM Wiki会自动提取YAML frontmatter中的`entities`字段，创建双向链接：

```yaml
entities: [电动机, 异步电机, 变频器, 矢量控制]
```

→ 自动生成 `[[电动机]]` `[[异步电机]]` 等链接

### 知识图谱

所有文档通过共享的实体相互连接，在Obsidian中形成有意义的知识网络。

### 可扩展性

您可以添加自己的笔记到 `wiki/` 文件夹：
- 在frontmatter中添加 `entities`
- 在文档中使用 `[[已有页面]]` 创建手动链接
- 图谱会自动更新

## 🔧 故障排除

### 问题: 文件没有出现在wiki/文件夹

**原因**: 未正确导入
**解决**:
1. 确认文件在 `Import/` 文件夹
2. 在LLM Wiki中点击 **Refresh** (刷新)
3. 检查 `Import/` 文件夹是否有写入权限

### 问题: Obsidian中没有双链

**原因**: entities提取不全
**解决**:
1. 打开 `wiki/` 中的文档
2. 检查YAML frontmatter是否有 `entities:` 字段
3. 手动添加需要的实体
4. 重启Obsidian或刷新

### 问题: 乱码

**原因**: 编码问题
**解决**:
1. 确认文件编码为UTF-8
2. LLM Wiki设置 → File Encoding → UTF-8

### 问题: 导入很慢

**正常**: 每个文档需要5-15秒Claude API处理
**加速**:
1. 确保网络连接稳定
2. 检查Claude API配额
3. 少量多次导入，避免阻塞

## 📊 知识图谱预期

导入4个文档后，您应该看到:

- **中心节点**: "电气工程"、"电机"等核心概念
- **主要集群**:
  - 基础理论集群 (电磁学、电机学)
  - 电机类型集群
  - 电力系统集群
  - 控制驱动集群
- **连接**: 文档之间有2-5个共享实体

## 🔄 扩展知识库

### 添加新主题

遵循相同格式创建新Markdown文件:

```markdown
---
title: 你的标题
source: 来源
tags: [标签1, 标签2]
entities: [实体1, 实体2, 实体3]
category: 分类
---

# 标题

内容...
```

### 使用SearXNG联网搜集

我们提供了 `knowledge-enrichment/` 模块，可以:
- 通过SearXNG搜索最新资料
- 使用Claude API自动丰富
- 生成标准格式Markdown

详见: `knowledge-enrichment/README.md`

## 💡 使用技巧

1. **先导入后整理**: 先批量导入，再在Obsidian中整理
2. **善用Graph View**: 发现知识的空白和孤立节点
3. **定期备份**: `wiki/` 文件夹就是您的知识资产
4. **添加个人笔记**: 在 `Insert/` 或其他子文件夹添加您的理解

## 📚 相关文档

- [SETUP-GUIDE.md](../../SETUP-GUIDE.md) - Claude+LLM Wiki+Obsidian完整设置
- [knowledge-enrichment/README.md](../README.md) - 知识搜集工具
- [CONTEXT.md](../../CONTEXT.md) - 领域术语表

---

**开始探索电气工程的海洋吧！** 🚀

生成日期: 2025-05-17
版本: 1.0
EOF
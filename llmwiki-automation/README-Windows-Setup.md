# Windows 下 Claude + LLM Wiki + Obsidian AI知识库搭建指南

本指南说明如何在Windows 11/10上搭建与macOS等效的AI知识库系统。

## 📋 系统要求

| 组件 | 要求 | 获取方式 |
|------|------|----------|
| Windows | 10 或 11 | 已安装 |
| Claude Desktop | 最新版 | https://claude.ai/download |
| LLM Wiki | Windows版 | https://github.com/nasui/LLM_wiki/releases |
| Obsidian | 最新版 | https://obsidian.md/download |
| AutoHotkey | v1.1+ | https://www.autohotkey.com/ |
| Python | 3.9+ (可选) | https://www.python.org/ |

## 🚀 安装步骤

### 1. 安装 Claude Desktop

1. 访问 https://claude.ai/download
2. 下载Windows版本 (Claude Setup.exe)
3. 运行安装程序
4. 登录您的Claude账号

**验证**: 启动Claude Desktop，确认能正常使用

### 2. 安装 LLM Wiki

1. 访问 https://github.com/nasui/LLM_wiki/releases
2. 下载 `LLMwiki-windows.zip` (或 `.tar.gz`)
3. 解压到 `C:\Users\<用户名>\AppData\Local\LLMwiki\`
4. 运行 `LLMwiki.exe`

**首次运行**:
- 点击 **New** 创建新项目
- 选择项目目录 (如 `D:\KnowledgeBase\MyWiki`)
- 点击右上角**设置图标**，配置Claude API密钥
- 选择模型 (推荐 Claude Sonnet 4)

**验证**: LLM Wiki应显示左侧文件区、底部对话区、右侧预览区

### 3. 安装 Obsidian

1. 从 https://obsidian.md/download 下载Windows版
2. 运行安装程序
3. 打开Obsidian，选择 **"Open folder as vault"**
4. 选择您的LLM Wiki项目的 `wiki/` 子文件夹
   - 例如: `D:\KnowledgeBase\MyWiki\wiki`
5. 完成初始设置

**验证**: Obsidian应显示空保险库，左侧文件区为空

### 4. 安装 AutoHotkey

1. 访问 https://www.autohotkey.com/
2. 下载并安装AutoHotkey v1.1
3. 验证安装: 右键菜单应出现 "Run Script" 选项

### 5. 配置 Hermes-Windows 自动化

1. 将 `Hermes-Windows.ahk` 复制到您的知识库目录
2. 编辑 `config.ini`，修改以下路径:

```ini
[Paths]
LLMWiki = C:\Users\YourName\AppData\Local\LLMwiki\LLMwiki.exe
Obsidian = C:\Users\YourName\AppData\Local\Obsidian\Obsidian.exe
WikiProject = D:\KnowledgeBase\MyWiki
Vault = D:\KnowledgeBase\MyWiki\wiki
```

3. 保存配置文件

4. 运行 `Hermes-Windows.ahk` (右键 → Run Script)
   - 系统托盘会出现 H 图标
   - 右键点击图标可访问菜单

## 🔄 工作流程

### 基本流程 (三工具串联)

```
┌─────────────┐
│  文档文件     │ (.pdf, .docx, .md)
└──────┬──────┘
       │
       ▼
┌─────────────────────┐    Win+I
│    Hermes-Windows   ├─────────────►
│   (AutoHotkey)      │              ▼
└─────────────────────┘    ┌──────────────────┐
       │                    │    LLM Wiki      │
       │ 窗口控制             │  - 导入文档       │
       └────────────────────►│  - Claude分析     │
                            │  - 生成Wiki页面   │
                            └────────┬─────────┘
                                     │ 写入 wiki/ 文件夹
                                     ▼
                            ┌──────────────────┐
                            │   Obsidian Vault │
                            │  - 自动显示新页面  │
                            │  - 双向链接跳转   │
                            │  - 知识图谱视图   │
                            └──────────────────┘
```

### 查询知识

```
Win+Q → 激活LLM Wiki → 输入问题 → Claude回答 → 右侧展示
```

## ⌨️ 热键说明

| 热键 | 功能 | 说明 |
|------|------|------|
| **Win+I** | 导入文档 | 激活LLM Wiki并执行导入操作 |
| **Win+Q** | 查询知识库 | 在LLM Wiki对话框中提问 |
| **Win+O** | 打开Obsidian | 激活或启动Obsidian |
| **Win+W** | 聚焦LLM Wiki | 切换到LLM Wiki窗口 |
| **Win+G** | 导入并打开 | 完整流程:导入→等待→打开Obsidian |
| **双击托盘图标** | 配置 | 打开配置窗口 |

## 📂 推荐的项目结构

```
KnowledgeBase/
├── MyWiki/                     # LLM Wiki项目
│   ├── Import/                # 待导入文档
│   ├── Documents/             # 原始文档(可选)
│   ├── wiki/                  # LLM Wiki生成的Markdown ← Obsidian Vault
│   │   ├── Claude-Code.md
│   │   ├── Obsidian.md
│   │   └── ...
│   └── config.json            # LLM Wiki配置
├── Scripts/
│   ├── Hermes-Windows.ahk     # 自动化脚本
│   ├── wiki-sync.py           # Python同步助手(可选)
│   ├── config.ini             # AHK配置文件
│   └── README.md              # 本文件
└── .env                       # Claude API密钥(可选)
```

## 🔧 详细配置

### LLM Wiki Cl属 API设置

1. 打开LLM Wiki
2. 点击右上角⚙️设置图标
3. 填写:
   - **API Key**: 从 https://console.anthropic.com 获取
   - **API Endpoint**: https://api.anthropic.com (默认)
   - **Model**: claude-sonnet-4-20250514 (推荐)
4. 点击"Save"

### Obsidian插件配置

推荐安装以下插件:

1. **Dataview** - 查询和表格
   ```javascript
   // 在笔记中使用
   ```dataview
   LIST FROM "01-Inbox" WHERE #status = "active"
   ```
2. **Excalidraw** - 绘图
3. **Graph Analysis** - 图谱分析
4. **Calendar** - 日历
5. **QuickAdd** - 快速添加笔记

## 📖 使用示例

### 示例1: 导入PDF文档

1. 复制PDF文件路径到剪贴板
2. 按 `Win+I`
3. AHK脚本会自动:
   - 激活LLM Wiki窗口
   - 按下Ctrl+I打开导入
   - 粘贴文件路径
   - 确认导入
4. 等待右侧预览区生成Wiki页面

### 示例2: 查询知识

1. 按 `Win+Q`
2. 输入问题，如: "Claude Code有哪些技能?"
3. LLM Wiki从已导入的文档中查找并回答
4. 回答会包含来源标注

### 示例3: 批量导入

```powershell
# 使用Python辅助脚本
python wiki-sync.py --batch-import "D:\Documents\ToImport"

# 然后手动在LLM Wiki中触发批量导入
# 或使用AHK脚本循环处理
```

## ⚠️ 故障排除

### LLM Wiki无法启动

```
症状: Win+W无反应
解决:
  1. 检查config.ini中的LLMWiki路径是否正确
  2. 手动运行LLMwiki.exe确认能启动
  3. 更新config.ini后重启AHK脚本
```

### 导入失败

```
症状: 文件没有导入
解决:
  1. 确认文件路径已复制到剪贴板
  2. LLM Wiki的Import文件夹有写入权限
  3. 检查文件格式: PDF/DOCX/MD/TXT
```

### Obsidian不显示新文档

```
症状: 导入LLM Wiki后Obsidian是空的
解决:
  1. 确认Vault设置正确指向LLM Wiki的wiki/子文件夹
  2. 在Obsidian中点击文件浏览器刷新
  3. 检查文件是否确实写入了wiki/文件夹
```

### AHK热键冲突

```
症状: Win+I无反应或有其他行为
解决:
  1. 运行AutoHotkey Window Spy查看窗口信息
  2. 修改config.ini中的热键设置
  3. 重新加载脚本(右键托盘图标 → Reload)
```

## 🔄 与macOS方案对比

| 功能 | macOS (Hermes AppleScript) | Windows (Hermes-Windows AHK) |
|------|---------------------------|-----------------------------|
| 自动化语言 | AppleScript | AutoHotkey |
| 启动应用 | `tell application` | `Run, "path\app.exe"` |
| 菜单点击 | `click menu item` | `Send, ^i` (快捷键) |
| 窗口识别 | `window "LLM Wiki"` | `IfWinExist, LLM Wiki` |
| 剪贴板 | `the clipboard` | `Clipboard` 变量 |
| 热键绑定 | System 快捷键 | AHK热键(#i, ^i等) |

**关键差异**:
- macOS方案使用AppleScript直接控制UI元素
- Windows方案主要依赖键盘快捷键，更稳定
- 坐标点击作为后备方案

## 🔮 高级功能

### 定时自动导入

使用Windows任务计划程序:

1. 创建批处理文件 `auto-import.bat`:
```batch
@echo off
cd /d "D:\KnowledgeBase\Scripts"
python wiki-sync.py --batch-import "D:\IncomingDocs"
pause
```

2. 任务计划程序 → 创建基本任务
   - 触发器: 每天/每小时
   - 操作: 启动程序 → 选择bat文件

### Python脚本高级同步

```python
# 创建自定义同步任务
python wiki-sync.py --sync       # 完整同步
python wiki-sync.py --init-vault # 初始化vault结构
```

### 创建Obsidian模板

在vault中创建 `Templates/` 文件夹，添加模板文件:

```markdown
---
title: {{title}}
created: {{date}}
source: {{source}}
---

# {{title}}

## 摘要

## 关键概念
- [[ ]]

## 相关文档
- [[ ]]

## 笔记
```

## 📊 性能建议

| 操作 | 推荐配置 |
|------|----------|
| LLM Wiki导入 | 单次10-20个文档，避免过大 |
| Obsidian插件 | 按需启用，过多影响性能 |
| 图谱渲染 | 文档数<1000时流畅 |
| API调用 | 使用Sonnet而非Opus以节省成本 |

## 🆘 获取帮助

- **LLM Wiki问题**: https://github.com/nasui/LLM_wiki/issues
- **Obsidian问题**: https://obsidian.md/help
- **AutoHotkey问题**: https://www.autohotkey.com/boards/
- **本项目问题**: 在项目GitHub仓库提issue

## 📝 快速检查清单

- [ ] Claude Desktop已安装并登录
- [ ] LLM Wiki已下载，能正常启动
- [ ] LLM Wiki已配置Claude API密钥
- [ ] Obsidian已安装
- [ ] Obsidian已打开LLM Wiki的wiki/文件夹作为Vault
- [ ] AutoHotkey已安装
- [ ] Hermes-Windows.ahk已配置好路径
- [ ] 按Win+I测试导入功能
- [ ] 按Win+O测试打开Obsidian

---

**恭喜!** 完成以上步骤后，您的Windows AI知识库就搭建完成了。

三工具协同工作:
- **Claude** - AI大脑，提供智能分析
- **LLM Wiki** - 知识处理，文档导入和Wiki生成
- **Obsidian** - 知识浏览，双链和图谱

**Hermes-Windows** - 自动化桥梁,让这一切无缝衔接!
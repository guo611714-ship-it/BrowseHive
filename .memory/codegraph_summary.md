# CodeGraph 代码知识图谱索引摘要

> 生成时间: 2025-05-25
> CodeGraph 状态: 已索引 86 文件, 1,570 节点, 2,932 边

---

## 核心架构模块

### 1. AI-Chat MCP 服务器
**路径**: `MCP/scripts/meta-mcp-server.py`
- **43 symbols** | FastMCP("BrowseHive Meta MCP")
- 核心功能: 统一MCP服务器，集成多平台AI接口
- 关键组件:
  - 浏览器自动化 (browser-use + browser-harness)
  - 平台路由 (doubao/deepseek/volcengine/ouyi)
  - 缓存、限流、重试机制
  - 任务拆分与并行执行

### 2. BrowseHive 浏览器AI工作流
**路径**: `.agents/skills/browsehive/`
- ** browsehive_agent.py** (39 symbols)
  - `BrowseHiveAgent` 类: 核心代理
  - `chat()`: 单平台对话 (.agents/skills/browsehive/browsehive_agent.py:255)
  - `chat_multi()`: 多AI平台协作
  - `_ensure_mcp_server()`: MCP服务器管理 (160)
  - `_ensure_cdp()`: Chrome DevTools 连接 (79)
  - 支持platforms: doubao, deepseek, volcengine, ouyi

- **unified_agent_cli.py** (25 symbols)
  - 命令行接口
  - 统一代理入口

### 3. AI 平台客户端

#### 豆包 (Doubao)
- **doubao_client.py**: Doubao API 封装
- 功能: 字节跳动AI，超能模式，中文能力最强，支持联网搜索、文件上传、深度思考

#### DeepSeek
- **deepseek_client.py**: DeepSeek API 封装
- 功能: 专家模式，专注推理，V3和R1模型，开源免费，适合代码/数学/技术分析

#### 火山引擎 (Volcengine)
- **volcengine_client.py**: 火山引擎API封装
- 功能: Doubao-Seed-2.0-pro，企业级，支持AI Agents/智能路由/视觉/音视频/文件上传

#### 欧亿AI (ouyi)
- **ouyi_api.py** (19 symbols)
  - `chat(message, model_type)` (.py:46)
  - `write(theme, length, format_type, tone)`
  - `mindmap(topic)`
  - `draw(prompt, model, size)`
  - `balance()`
  - model_type: 1=GPT, 2=DeepSeek, 3=GPT高级, 4=Gemini, 5=Claude

- **ouyi_chat.py** (17 symbols)
  - `chat()` 函数封装
  - 对话、写作、思维导图、绘图全功能

- **ouyi_draw.py** (21 symbols)
  - DALL-E绘图专用接口
  - 支持 dall-e-2/dall-e-3，多种尺寸

#### Anthropic Claude
- **anthropic_client.py**: Claude API 集成

### 4. 路由与智能调度

**ai_router.py** (4 symbols)
- 智能平台选择
- `_assess_complexity()`: 根据任务类型和关键词自动推荐最优平台
- `split_task()`: 按关键词分配多平台并行

**config_loader.py** (4 symbols)
- 配置文件加载
- 环境变量管理

### 5. 浏览器自动化

#### browser-harness 集成
- CDP (Chrome DevTools Protocol) 直接连接
- 优先使用 browser-harness (更稳定)
- 降级到 browser-use (备用方案)
- CDP 共享连接机制 (`.codegraph/` 内的 `.cdp_port` 文件)

#### Chrome DevTools MCP
- MCP工具集: `mcp__chrome-devtools__*`
- 功能: navigate, click, fill, screenshot, evaluate_script, lighthouse_audit 等

### 6. 办公自动化 Add-ins

#### Excel
- **claude-excel-addin/**: Excel COM 插件
- 通过 Python 操控 Excel

#### Word
- **claude-word-addin/**: Word COM 插件
- 文档处理与格式保持

#### PowerPoint
- **claude-powerpoint-addin/**: PowerPoint COM 插件
- 演示文稿自动化

### 7. Skill 系统

| Skill | 路径 | Symbols | 功能 |
|-------|------|---------|------|
| browsehive | `.agents/skills/browsehive/` | 64 | 浏览器AI工作流 |
| continuous-learning-v2 | `.agents/skills/continuous-learning-v2/` | 156 | 持续学习框架 |
| gpt-image-2 | `.agents/skills/gpt-image-2/` | 14 | 图像提取 |
| office-automation | `.agents/skills/office-automation/` | 43 | 办公自动化 |
| senior-ml-engineer | `.agents/skills/senior-ml-engineer/` | 48 | ML工程 |
| smart-skill-orchestrator | `.agents/skills/smart-skill-orchestrator/` | 38 | 智能Skill路由 |
| word-document-processor | `.agents/skills/word-document-processor/` | 150+ | Word文档处理 |
| ouyi-ai | `.claude/skills/ouyi-ai/` | - | 欧亿AI Skill |

### 8. 文档处理工具

#### PDF 转换
- **pdf_to_text.py**: PDF转文本 (31 symbols)
- **extract_pdf_via_browser.py**: 浏览器渲染PDF提取
- **extract_pdf_fixed.py**: 固定格式PDF解析
- **extract_bytes.py**: 字节流提取

#### Word/Excel 处理
- **scripts/**:
  - `convert_v3.py`: LaTeX转换 (18 symbols)
  - `convert_with_sendkeys.py`: 自动发送 (13 symbols)
  - `read_doc.py`: 读取文档 (7 symbols)
  - `auto_convert_final.py`: 自动转换 (9 symbols)

- **claude-word-addin/**: Word COM 集成
- Word 文档处理器: `skills/word-document-processor/`
  - ooxml 打包/解包/验证
  - 文档结构操作
  - 格式保持与批注处理

#### 图像处理
- **generate_anime.py**: 动漫生成 (12 symbols)

### 9. 知识库管理

- **kb-manager.py** (32 symbols)
  - 知识库CRUD操作
  - 向量化与检索
  - 文档导入导出

### 10. 项目特定代码

#### 继保实验报告 (Electrical Protection Lab)
**路径**: `项目/继保实验报告/`
- **C代码** (STM32):
  - `adc.c/h`: ADC采集 (7+2 symbols)
  - `oled.c/h`: OLED显示 (18+2 symbols)
  - `protection.c/h`: 保护逻辑 (10+2 symbols)
  - `relay.c/h`: 继电器控制 (6+2 symbols)
  - `timer.c/h`: 定时器 (6+2 symbols)
  - `main.c`: 主程序 (13 symbols)
  - `stm32f10x.h`: STM32标准外设库 (54 symbols)
  - `system_stm32f10x.c`: 系统配置 (3 symbols)

- **Python工具**:
  - `convert_formulas.py`: 公式转换 (10 symbols)
  - `extract_docx.py`: 提取docx内容 (7 symbols)
  - `read_docx.py`: 读取docx (7 symbols)
  - `generate_report.js`: 生成报告 (3 symbols)

#### 视频分析
**路径**: `项目/视频总结/`
- `detect_non_teaching.py`: 非教学片段检测 (9 symbols)
- `extract_non_teaching.py`: 非教学内容提取 (15 symbols)
- `process_videos.py`: 视频处理流水线 (18 symbols)
- `skip_guide.py`: 跳过指南生成 (16 symbols)

#### 图像实验报告
**路径**: `项目/图像实验报告/`
- `experiment7.py`: 实验7完整实现 (60 symbols)

#### 作业绘图
**路径**: `项目/作业/`
- `draw_7_1.py`, `draw_7_2.py`, `draw_7_3.py`: 绘制各图 (12-13 symbols)
- `generate_diagrams.py`: 批量生成图表 (32 symbols)
- `generate_all.py`: 总生成器 (33 symbols)
- `fix_*.py`: 修复脚本 (13-14 symbols)
- `insert_*.py`: 插图插入 (13-14 symbols)
- `create_iec61131_diagrams.py`: IEC 61131 图 (9 symbols)

### 11. 知识增强

**knowledge-enrichment/**
- `claude_enricher.py`: Claude知识增强 (16 symbols)
- `searxng-integration/searxng_collector.py`: SearXNG数据收集 (22 symbols)

### 12. LLM Wiki 自动化

**llmwiki-automation/wiki-sync.py** (19 symbols)
- Wiki内容同步与更新

### 13. 脚本集合

**scripts/** - 批量文档转换脚本
- `auto_convert_latex.py`: LaTeX自动转换 (10 symbols)
- `auto_convert_latex_fixed.py`: 修复版 (11 symbols)
- `convert_enhanced.py`: 增强转换 (21 symbols)
- `convert_latex_in_word.py`: Word内转换 (19 symbols)
- `convert_using_word.py`: Word驱动转换 (7 symbols)
- `extract_latex_simple.py`: 简单提取 (8 symbols)
- `test-kb-manager.py`: KB测试 (15 symbols)

### 14. 其他工具

- **generate_anime.py**: 动漫图像生成 (12 symbols)
- **max_compat_fix.py**: 最大兼容性修复 (37 symbols)
- **修复脚本*.py**: 各类修复工具 (10-40 symbols)
- **merge_and_clean.py**: 合并与清理 (批量操作)
- **extract_bytes.py**: 字节提取
- **setup_team.py**: 团队设置 (4 symbols)
- **test_team.py**: 团队测试 (10 symbols)

---

## 关键配置文件

- **mcp_config.json**: MCP服务器配置
- **model_config.example.json**: 模型配置示例
- **requirements.txt**: Python依赖
- **.env.example**: 环境变量模板
- **.claude/settings.local.json**: Claude本地配置
- **.mcp.json**: MCP客户端配置

---

## 技术栈总览

| 类别 | 技术/框架 | 用途 |
|------|-----------|------|
| AI平台 | 豆包/DeepSeek/火山引擎/欧亿AI/Claude | 多模型支持 |
| MCP | FastMCP | 模型上下文协议服务器 |
| 浏览器 | Chrome DevTools Protocol, browser-harness, browser-use | 浏览器自动化 |
| 办公 | COM Interop (Excel/Word/PowerPoint) | Windows办公自动化 |
| 文档 | python-docx, ooxml, LaTeX | 文档处理 |
| PDF | pdfminer, browser-PDF, Umi-OCR | PDF文本提取 |
| 知识库 | ChromaDB/向量存储 (推测) | 知识管理 |
| 代码生成 | 各AI平台API | 自动编程 |
| CLI | argparse, subprocess | 命令行工具 |

---

## CodeGraph 使用提示

### 快速查询

```bash
# 查看所有文件
codegraph files

# 查看符号种类统计
codegraph status

# 搜索符号 (使用 mcp__codegraph__ 工具)
codegraph_context "任务描述"
codegraph_search "符号名"
codegraph_node "符号名"
codegraph_callers "被调用函数"
codegraph_callees "调用函数"
codegraph_trace "from_symbol -> to_symbol"
codegraph_impact "要修改的符号"
codegraph_explore "相关区域"
```

### 关键搜索词
- BrowseHive → `.agents/skills/browsehive/`
- AI-Chat → `MCP/scripts/meta-mcp-server.py`
- ouyi → `ouyi_api.py`, `ouyi_chat.py`, `ouyi_draw.py`
- 办公 → `claude-*-addin/`
- 文档 → `skills/word-document-processor/`
- 继保 → `项目/继保实验报告/`
- 视频 → `项目/视频总结/`
- kb-manager → `kb-manager.py`

---

## 记忆索引位置

本摘要文件: `.memory/codegraph_summary.md`
相关memory:
- `project_browser_workflow.md`: BrowseHive工作流
- `project_codegraph_mcp_setup.md`: CodeGraph MCP配置
- `ai_platforms_capabilities.md`: AI平台能力对比

---

**注**: CodeGraph 实时更新，文件修改后约1秒自动重新索引。查询时优先使用 `codegraph_context` 获取全景，再用 `codegraph_node`/`codegraph_explore` 深入细节。

# Changelog

All notable changes to Agent Team will be documented in this file.

## [2.1.0] - 2026-06-01

### Fixed
- 12个根目录kb_*.py移入agent/kb/包，消除根目录大文件
- browser_pool.py/browser_client.py归入browser/包
- 子代理命名统一: browser_agent -> liubu_liulanqi
- XSS防护: ask_bing URL编码
- websocket import崩溃: try/except保护
- 缓存竞态: _cache_mtime初始化时序修复

### Changed
- kb_commands.py(35K)拆为9个子模块(agent/kb/commands/)
- browser_tools.py(28K)拆为5个子模块(agent/tools/browser/)
- ci.yml更新: agent/覆盖率 + ruff lint + mypy type check
- requirements.txt: 精确版本范围锁定
- README.md: 完整项目文档

### Added
- release.yml: tag触发自动发版CD流水线
- test_e2e_integration.py: 5个E2E测试
- DeepWiki 3层知识架构: 325K索引 + 按需抓取 + 核心缓存
- deepwiki_tools.py: 3个工具(fetch_index/search/get_stats)
- CHANGELOG.md

## [2.0.0] - 2026-05-30

### Added
- 10模型路由系统(复杂度/场景/角色三维)
- 6子代理(朝廷命名体系)
- 4调度模式(并行/Handoff/审批/迭代精炼)
- 3层记忆系统(工作/情景/长期)
- 知识服务统一接口(KnowledgeService)
- 5 MCP Server(HTTP)
- 28个注册工具(@tool装饰器)

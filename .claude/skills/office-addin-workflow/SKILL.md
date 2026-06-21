---
name: office-addin-workflow
description: Office Add-in开发标准化工作流程——设计→实现→测试→修复→部署，一键启动全流程
---

# Office Add-in 开发标准化操作手册

## 触发条件
当用户要求开发、测试、修复、部署Office Add-in时，自动激活此工作流程。

## 设计阶段

### 设计规范（调用frontend-design skill）
- **视觉风格**：与Office原生体验协调的设计风格
- **图标系统**：仅SVG格式，16x16/24x24/32x32三种尺寸
- **命名规范**：CSS类名使用统一前缀
- **代码封装**：JavaScript使用IIFE封装，防止全局污染
- **响应式**：支持160px/320px/640px三种任务窗格宽度
- **无障碍**：WCAG 2.1 AA级（对比度≥4.5:1、键盘导航、屏幕阅读器）

## Agent Team协作模式

### 工作流程
```
/goal 完成 Office Add-in 功能 X
    │
    ├─ 1. 主控拆分任务 → dispatch系统按文件隔离分配
    │
    ├─ 2. 并行执行（每个agent负责不同文件）
    │
    ├─ 3. Code Review 审查产出
    │
    ├─ 4. 修复审查发现
    │
    ├─ 5. 浏览器测试验证（截图各应用）
    │
    ├─ 6. Git 提交 + 保存记忆
    │
    └─ 7. 扫描项目不足 → 输出后续优化清单
```

### Step 7: 扫描项目不足（后续优化清单）

完成修复后，扫描项目现状，输出后续可优化的事项：

| 维度 | 检查内容 |
|------|----------|
| 功能完整性 | 各应用功能是否一致？缺失哪些？ |
| 代码质量 | 有无残留技术债、旧代码？ |
| 架构合规 | 是否符合共享组件库规范？ |
| 测试覆盖 | 关键路径是否有测试？ |
| 浏览器验证 | 各应用UI是否正常？ |

输出待优化清单，保存到记忆中，方便后续 session 继续。

## 实现阶段

### 项目结构（示例，根据实际项目调整）
```
shared/                 # 共享层
├── base.css            # 布局+排版+主题变量
├── components.css      # 组件样式
├── components.js       # IIFE封装，挂载到window
├── toolbar.*           # 右侧功能栏
└── legacy.*            # 旧版兼容组件

{app}-addin/            # 应用层（每个Office应用一个目录）
├── manifest.xml        # Office清单
├── server.js           # Express服务器
├── taskpane.html/js/css
└── office-integration.js
```

### 开发规范
- 共享代码放共享层目录，避免多份重复
- 品牌差异在各自`taskpane.css`
- 多个应用项目同步更新
- 不修改核心DOM ID（#prompt/#send-btn/.messages/.sidebar）
- 新增组件DOM用JS动态插入

## 测试阶段（必须执行）

### 浏览器测试
```bash
# 启动服务器（使用项目配置的端口）
cd <PROJECT_ROOT>
node server.js

# 截图测试各应用
npx playwright screenshot --browser chromium "http://localhost:<PORT>/taskpane.html" app1.png
npx playwright screenshot --browser chromium "http://localhost:<PORT>/<app2>/taskpane.html" app2.png
npx playwright screenshot --browser chromium "http://localhost:<PORT>/<app3>/taskpane.html" app3.png
```

### 验证清单
1. **JS语法**：`node -e "try{new Function(fs.readFileSync('file.js','utf8'));console.log('✅')}catch(e){console.log('❌')}"`
2. **HTML标签平衡**：检查div/button标签数量一致
3. **服务器端点**：curl验证所有HTML/CSS/JS返回200
4. **API代理**：curl POST测试proxy-api端点
5. **残留旧类名**：grep检查已废弃的CSS类名
6. **浏览器UI**：截图验证侧边栏、工具栏、按钮、输入框

### 浏览器测试要点
- 右侧工具栏是否可见
- 侧边栏收起/展开是否正常
- 按钮是否可点击
- 历史对话是否可切换
- 输入框是否可输入
- 发送按钮是否工作
- 下拉菜单是否展开

## 修复阶段

### Bug优先级
- **CRITICAL**：崩溃/安全漏洞 → 立即修复
- **HIGH**：功能严重受损 → 优先修复
- **MEDIUM**：功能异常 → 计划修复
- **LOW**：体验问题 → 后续优化

### 修复流程
1. 读取相关文件
2. 定位问题根因
3. 修复代码
4. 验证JS语法
5. **浏览器测试验证**
6. 同步到各应用项目
7. Git提交

### 常见问题模式
- 引用已删除元素 → 移除所有引用
- `pointer-events:none`阻止点击 → 检查禁用状态
- z-index冲突 → 检查元素层级
- 函数未导出 → 添加window.xxx
- DOM元素不存在 → 添加null检查

## 部署阶段

### Manifest配置
```xml
<SourceLocation DefaultValue="http://localhost:<PORT>/taskpane.html"/>
<IconUrl DefaultValue="http://localhost:<PORT>/assets/icon.png"/>
```

### 注册表注册（Windows）
```powershell
New-ItemProperty -Path 'HKCU:\Software\Microsoft\Office\16.0\Wef\Developer' `
    -Name '<YourAddInName>' `
    -Value '<path-to-manifest.xml>' `
    -PropertyType String -Force
```

### 使用方式
1. 关闭并重新打开Office应用
2. 插入 → 我的加载项 → 开发人员
3. 选择加载项添加

## 版本管理

### Git工作流
```bash
cd <PROJECT_ROOT>
git add -A
git commit -m "feat/fix: 描述"
```

### 提交规范
- `feat:` 新功能
- `fix:` Bug修复
- `refactor:` 重构
- `docs:` 文档

## Agent Team 协作原则

1. **修复后必测**：每次修改后必须浏览器测试验证UI
2. **多应用同步**：各Office应用必须保持一致
3. **Agent并行**：大任务拆分为独立agent并行执行，每个agent负责不同文件
4. **frontend-design指导**：UI设计必须调用frontend-design skill
5. **dispatch超时保护**：LLM 60s / dispatch 300s 防止无限卡住
6. **模型自动fallback**：502时自动切换备用模型
7. **质量门禁**：pre-commit检查（pytest/mypy/ruff等），任一失败阻止提交


## Parallel Fix (并行修复)

当任务涉及多个独立修改时，**不要逐个串行执行**。
调用 `submit_fix_manifest` 工具，由 ParallelFixEngine 并行执行：

```json
{
  "name": "submit_fix_manifest",
  "arguments": {
    "source": "stocktake",
    "data": {
      "skills": {
        "<skill_name>": {"verdict": "Improve", "reason": "<描述>", "path": "<文件路径>"}
      }
    },
    "strategy": "auto",
    "filter_actionable": true
  }
}
```

- 引擎自动处理分片、冲突预测、并行调度
- 等待返回结果后，检查 conflicts 列表

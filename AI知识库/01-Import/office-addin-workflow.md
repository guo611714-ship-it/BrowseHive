---
name: office-addin-workflow
description: Office Add-in优化测试修复标准工作流程，涵盖设计、实现、测试、修复全流程
metadata: 
  node_type: memory
  type: reference
  originSessionId: 7e79cb7f-102c-4563-8ea4-d4acc47bb00b
---

# Office Add-in 工作流程

## 1. 设计阶段

### 设计美学
- 使用frontend-design skill进行UI设计
- 风格：Warm Editorial × Office Precision
- 字体：DM Sans (body) + Playfair Display (headings)
- 配色：Excel绿#217346 / Word蓝#2B579A / PPT红#D24726
- 组件前缀：pro-office-（新版）/ plus-office-（旧版兼容）
- 动效：var(--semi-transition) / var(--semi-transition-spring)
- 图标：全部自定义SVG（禁止emoji）

### 设计规范
- IIFE封装避免全局污染
- 所有可交互元素含aria-label + tabindex
- :focus-visible焦点环
- 最小320px响应式
- localStorage持久化状态

## 2. 实现阶段

### 架构
```
claude-shared/           # 共享层
  base.css               # 布局+排版+主题变量
  pro-office.css         # pro-office-组件样式
  pro-office.js          # IIFE封装，window.ProOffice
  function-toolbar.css   # 右侧功能栏
  function-toolbar.js    # 功能栏toggle+drag
  
claude-{app}-addin/      # 应用层
  manifest.xml           # Office清单（端口3103）
  server.js              # Express服务器
  taskpane.html/js/css   # UI+逻辑+品牌样式
  office-integration.js  # Office.js API
```

### 实现原则
- 共享代码放claude-shared/，避免三份重复
- 品牌差异在各自taskpane.css
- 三个项目同步更新
- 新增组件DOM用JS动态插入
- 不修改核心DOM ID（#prompt/#send-btn/.messages/.sidebar等）

### Agent Team协作
- 大任务拆分为独立agent并行执行
- 每个agent负责不同文件，避免冲突
- 使用frontend-design skill指导UI设计
- Agent完成后再做最终验证

## 3. 测试阶段

### 浏览器测试（必须）
```bash
# 启动服务器
cd D:/.pogget/user_storage/u_fd754f/b5edd/claude-excel-addin
node server.js  # 端口3103

# 截图测试
npx playwright screenshot --browser chromium "http://localhost:3103/taskpane.html" test.png
npx playwright screenshot --browser chromium "http://localhost:3103/word/taskpane.html" test.png
npx playwright screenshot --browser chromium "http://localhost:3103/ppt/taskpane.html" test.png
```

### 验证清单
1. **JS语法**：`node -e "try{new Function(fs.readFileSync('file.js','utf8'));console.log('✅')}catch(e){console.log('❌')}" `
2. **HTML标签平衡**：检查div/button标签数量一致
3. **服务器端点**：curl验证所有HTML/CSS/JS返回200
4. **API代理**：curl POST测试proxy-api端点
5. **CSS类名匹配**：检查HTML中的class在CSS中有定义
6. **残留旧类名**：grep检查semi-toggle/semi-dropdown等旧类名

### 浏览器测试要点
- 右侧工具栏是否可见
- 侧边栏收起/展开是否正常
- 按钮是否可点击
- 历史对话是否可切换
- 输入框是否可输入
- 发送按钮是否工作
- 下拉菜单是否展开

## 4. 修复阶段

### Bug分类
- **CRITICAL**：会导致崩溃或安全漏洞 → 立即修复
- **HIGH**：功能严重受损 → 优先修复
- **MEDIUM**：功能异常 → 计划修复
- **LOW**：体验问题 → 后续优化

### 修复流程
1. 读取相关文件
2. 定位问题根因
3. 修复代码
4. 验证JS语法
5. 浏览器测试
6. 同步到三个项目
7. Git提交

### 常见问题模式
- **semi-quick引用**：删除quick action卡片后，JS中仍有引用
- **pointer-events:none**：CSS禁用状态阻止点击
- **z-index冲突**：元素层级导致点击被遮挡
- **函数未导出**：function定义了但未window.xxx
- **DOM元素不存在**：getElementById返回null

## 5. 部署阶段

### Manifest更新
```xml
<SourceLocation DefaultValue="http://localhost:3103/taskpane.html"/>
<IconUrl DefaultValue="http://localhost:3103/assets/icon.png"/>
```

### 注册表注册（Windows）
```powershell
New-ItemProperty -Path 'HKCU:\Software\Microsoft\Office\16.0\Wef\Developer' `
    -Name 'ClaudeExcelAssistant' `
    -Value 'D:\path\to\manifest.xml' `
    -PropertyType String -Force
```

### WEF目录注册
```powershell
$WefPath = "$env:LOCALAPPDATA\Microsoft\Office\16.0\Wef"
$AddinDir = "$WefPath\ClaudeExcelAssistant"
New-Item -ItemType Directory -Path $AddinDir -Force
Copy-Item manifest.xml "$AddinDir\manifest.xml"
```

### 使用方式
1. 关闭并重新打开Office应用
2. 插入 → 我的加载项 → 开发人员
3. 选择ClaudeExcelAssistant添加

## 6. 版本管理

### Git工作流
```bash
cd D:/.pogget/user_storage/u_fd754f/b5edd
git add -A
git commit -m "feat/fix: 描述"
npx gitnexus analyze  # 更新知识图谱
```

### 提交信息规范
- `feat:` 新功能
- `fix:` Bug修复
- `refactor:` 重构
- `docs:` 文档更新

## 7. 记忆管理

### 项目记忆
- 保存到 `~/.claude/projects/.../memory/project_office_addin.md`
- 包含：架构、文件结构、已实现功能、服务器配置、设计规范
- 更新MEMORY.md索引

### 从对话中学习
- 用户偏好（不要手动操作、用命令行、调用agent team）
- 技术决策（为什么用这个方案）
- 问题模式（什么容易出错）

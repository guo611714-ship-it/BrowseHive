---
name: office-testing-feedback
description: "Testing lessons - Office 2021 Web Add-in limitations, browser-harness for automation, Chrome Dev debugging setup"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 746c168e-f9fa-4697-a929-fdae2e4c1a89
---

# Office 测试经验教训

## Office 2021 限制

Office 2021桌面版不支持Web Add-in加载。开发工具选项卡中只有COM加载项，没有Web Add-in浏览功能。

**Why:** Office 2021没有"获取加载项"按钮，"共享文件夹"功能也无法连接本地目录

**How to apply:** 开发Office Add-in时确认目标Office版本，Office 2021只能使用COM Add-in

## Browser-Harness 使用

- CLI工具，路径: `C:\Users\lenovo\AppData\Local\Programs\Python\Python311\Scripts\browser-harness`
- 需要Chrome以调试模式启动: `chrome.exe --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir="E:/llq" --no-first-run`
- Chrome路径: `C:\Program Files\Google\Chrome Dev\Application\chrome.exe`（注意是Chrome Dev，不是Chrome）
- 关键函数: `ensure_real_tab()`, `navigate()`, `capture_screenshot()`, `click_at_xy()`, `js()`, `page_info()`
- js()返回值可能有编码问题，用`print()`输出而不是直接return

## Chrome DevTools MCP

- 需要Chrome以`--remote-debugging-port=9222`启动才能连接
- MCP服务器可能断开，用`/mcp`命令重连

## API调用经验

- Node.js的https模块在Windows上有TLS/连接问题，curl更可靠
- Windows Git Bash中curl的`@file`语法不工作，改用Node.js原生https
- NVIDIA API的中文输入可能有编码问题（curl输出乱码），浏览器端正常

**Why:** 多次尝试不同方法后总结的经验

**How to apply:** 遇到类似问题时直接使用验证过的方法

## Windows环境

- 桌面路径: `D:\Users\lenovo\Desktop\` (不是C盘)
- 公共桌面: `C:\Users\Public\Desktop\`

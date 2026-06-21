; Hermes for Windows - LLM Wiki Automation Script
; 替代macOS的AppleScript，在Windows上自动控制LLM Wiki
; 需要: AutoHotkey v1.1+ (https://www.autohotkey.com/)

#NoEnv
#SingleInstance Force
SendMode Input
SetWorkingDir %A_ScriptDir%

; =====================================================
; 配置文件
; =====================================================
llmwiki_path := "C:\Path\To\LLMWiki.exe"  ; 请修改为您的LLM Wiki实际路径
obsidian_path := "C:\Path\To\Obsidian.exe" ; 请修改为您的Obsidian实际路径
wiki_project_dir := "D:\KnowledgeBase\MyWiki"  ; LLM Wiki项目目录
vault_dir := "D:\KnowledgeBase\ObsidianVault"   ; Obsidian Vault目录

; =====================================================
; 热键定义
; =====================================================
; Win+I: 导入文档到知识库
#i::ImportDocument()

; Win+Q: 查询知识库
#q::QueryKnowledge()

; Win+O: 打开Obsidian Vault
#o::OpenObsidianVault()

; Win+W: 激活LLM Wiki窗口
#w::ActivateLLMWiki()

; Win+G: 生成Wiki后打开Obsidian
#g::ImportAndOpen()

; =====================================================
; 主功能: 导入文档
; =====================================================
ImportDocument() {
    global llmwiki_path, wiki_project_dir

    ; 1. 启动或激活LLM Wiki
    IfWinExist, LLM Wiki
    {
        WinActivate
    }
    else
    {
        Run, "%llmwiki_path%" "%wiki_project_dir%"
        WinWaitActive, LLM Wiki,, 10
        if (ErrorLevel) {
            MsgBox, 48, 错误, 无法启动LLM Wiki，请检查路径配置
            return
        }
    }

    Sleep, 1000

    ; 2. 点击Import按钮 (通常位置: 左上角或菜单)
    ; 方案A: 使用菜单 - Ctrl+I 或 Alt+F, I
    Send, ^i
    Sleep, 500

    ; 3. 等待文件选择对话框
    WinWaitActive, 打开,, 5
    if (ErrorLevel) {
        ; 可能是不同的对话框标题
        WinActivate, 打开
    }

    ; 4. 粘贴文件路径 (从剪贴板获取或提示输入)
    ; 这里假设已复制文件路径到剪贴板
    Clipboard := ""
    Send, ^v
    Sleep, 300
    Send, {Enter}

    ; 等待导入完成 (LLM Wiki会在右侧显示处理进度)
    Sleep, 5000  ; 根据文档大小调整

    MsgBox, 64, 完成, 文档导入完成！`n`n请查看LLM Wiki右侧预览区。
}

; =====================================================
; 主功能: 查询知识库
; =====================================================
QueryKnowledge() {
    global llmwiki_path, wiki_project_dir

    ; 激活LLM Wiki
    IfWinExist, LLM Wiki
    {
        WinActivate
    }
    else
    {
        Run, "%llmwiki_path%" "%wiki_project_dir%"
        WinWaitActive, LLM Wiki,, 10
    }

    Sleep, 500

    ; 聚焦底部对话框
    Click, 100, 700  ; 根据实际窗口位置调整坐标
    Sleep, 200

    ; 输入查询内容 (从剪贴板或输入框)
    query := InputBox("请输入问题:", "知识库查询")
    if (query = "")
        return

    SendRaw, %query%
    Send, {Enter}

    ; 等待回答生成
    ToolTip, 正在生成回答...
    Sleep, 8000  ; 根据问题复杂度调整
    ToolTip

    MsgBox, 64, 回答完成, 回答已生成在LLM Wiki右侧，`n您也可以复制后使用Ctrl+Q快速打开Obsidian查看相关文档。
}

; =====================================================
; 主功能: 打开Obsidian Vault
; =====================================================
OpenObsidian() {
    global obsidian_path, vault_dir

    ; 检查Obsidian是否已打开该vault
    IfWinExist, Obsidian
    {
        WinActivate
        ; 如果是新会话，需要打开指定vault
        ; 这里可以扩展逻辑
    }
    else
    {
        Run, "%obsidian_path%" "%vault_dir%"
        WinWaitActive, Obsidian,, 10
    }

    ; 可选: 打开Graph View
    Sleep, 1000
    Send, ^g
}

OpenObsidianVault() {
    OpenObsidian()
}

; =====================================================
; 辅助功能: 激活LLM Wiki窗口
; =====================================================
ActivateLLMWiki() {
    IfWinExist, LLM Wiki
    {
        WinActivate
        WinMaximize  ; 可选: 最大化窗口
    }
    else
    {
        MsgBox, 48, 未找到, LLM Wiki窗口未打开
    }
}

; =====================================================
; 流程: 导入并打开
; =====================================================
ImportAndOpen() {
    ; 1. 导入文档 (需要先复制文件路径到剪贴板)
    MsgBox, 68, 导入文档, 请先复制要导入的PDF/文档文件路径到剪贴板，`n然后点击确定。
    IfMsgBox, Cancel
        return

    ImportDocument()

    ; 2. 等待几秒让Wiki生成
    Sleep, 3000

    ; 3. 打开Obsidian查看
    OpenObsidian()

    MsgBox, 64, 完成, 文档已导入并可在Obsidian中查看知识图谱。
}

; =====================================================
; 配置对话框
; =====================================================
ShowConfig() {
    global llmwiki_path, obsidian_path, wiki_project_dir, vault_dir

    Gui, New, , Hermes-Windows 配置
    Gui, Add, Text, , LLM Wiki 可执行文件路径:
    Gui, Add, Edit, vllmwiki_path w400, %llmwiki_path%
    Gui, Add, Button, default gBrowseLLM, 浏览...

    Gui, Add, Text, , Obsidian 可执行文件路径:
    Gui, Add, Edit, vobsidian_path w400, %obsidian_path%
    Gui, Add, Button, gBrowseObsidian, 浏览...

    Gui, Add, Text, , LLM Wiki 项目目录:
    Gui, Add, Edit, vwiki_project_dir w400, %wiki_project_dir%
    Gui, Add, Button, gBrowseWiki, 浏览...

    Gui, Add, Text, , Obsidian Vault 目录:
    Gui, Add, Edit, vvault_dir w400, %vault_dir%
    Gui, Add, Button, gBrowseVault, 浏览...

    Gui, Add, Button, gSaveConfig, 保存配置
    Gui, Add, Button, gCancelConfig, 取消

    Gui, Show
    return

    BrowseLLM:
        FileSelectFile, selected, , , 选择LLM Wiki可执行文件, LLMWiki.exe
        if (selected != "") {
            GuiControl,, llmwiki_path, %selected%
        }
        return

    BrowseObsidian:
        FileSelectFile, selected, , , 选择Obsidian可执行文件, Obsidian.exe
        if (selected != "") {
            GuiControl,, obsidian_path, %selected%
        }
        return

    BrowseWiki:
        FileSelectFolder, selected, , 3, 选择LLM Wiki项目目录
        if (selected != "") {
            GuiControl,, wiki_project_dir, %selected%
        }
        return

    BrowseVault:
        FileSelectFolder, selected, , 3, 选择Obsidian Vault目录
        if (selected != "") {
            GuiControl,, vault_dir, %selected%
        }
        return

    SaveConfig:
        Gui, Submit
        ; 保存到配置文件
        IniWrite, %llmwiki_path%, config.ini, Paths, LLMWiki
        IniWrite, %obsidian_path%, config.ini, Paths, Obsidian
        IniWrite, %wiki_project_dir%, config.ini, Paths, WikiProject
        IniWrite, %vault_dir%, config.ini, Paths, Vault
        MsgBox, 64, 配置已保存, 配置已保存到config.ini
        Gui, Destroy
        return

    CancelConfig:
        Gui, Destroy
        return
}

; 加载配置
LoadConfig() {
    global llmwiki_path, obsidian_path, wiki_project_dir, vault_dir

    if FileExist("config.ini") {
        IniRead, llmwiki_path, config.ini, Paths, LLMWiki, %llmwiki_path%
        IniRead, obsidian_path, config.ini, Paths, Obsidian, %obsidian_path%
        IniRead, wiki_project_dir, config.ini, Paths, WikiProject, %wiki_project_dir%
        IniRead, vault_dir, config.ini, Paths, Vault, %vault_dir%
    }
}

; =====================================================
; 系统托盘菜单
; =====================================================
Menu, Tray, Tip, Hermes for Windows (LLM Wiki Automation)
Menu, Tray, Add, 配置..., ShowConfig
Menu, Tray, Add, 导入文档, ImportDocument
Menu, Tray, Add, 查询知识库, QueryKnowledge
Menu, Tray, Add, 打开Obsidian, OpenObsidianVault
Menu, Tray, Add
Menu, Tray, Add, 退出, ExitApp
Menu, Tray, Default, 导入文档

; =====================================================
; 初始化
; =====================================================
LoadConfig()
return

; =====================================================
; 退出
; =====================================================
ExitApp:
    ExitApp
return
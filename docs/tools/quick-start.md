# Windows AI知识库 - 快速开始

5分钟快速搭建您的第一个AI知识库。

## 📦 第一步：安装依赖

```powershell
# 1. 确保已安装Python 3.9+
python --version

# 2. 安装所需库
pip install anthropic pypdf2 python-docx markdown
```

## 🔑 第二步：获取API密钥

1. 访问 https://console.anthropic.com
2. 注册/登录账号
3. 点击 **"Create API Key"**
4. 复制密钥（sk-ant-...）

## 🏗️ 第三步：初始化知识库

```powershell
# 创建并初始化vault目录
mkdir my-kb
cd my-kb
python ../kb-manager.py init

# 配置API密钥
python kb-manager.py config --set api-key YOUR_API_KEY_HERE
```

或者双击运行 `win-start.bat` 菜单驱动的版本。

## 📥 第四步：导入你的第一个文档

```powershell
# 导入PDF
python kb-manager.py import "C:\path\to\your\document.pdf"

# 导入Word文档
python kb-manager.py import "C:\path\to\notes.docx"

# 导入Markdown
python kb-manager.py import "C:\path\to\notes.md"
```

## 📖 第五步：在Obsidian中打开

1. 启动Obsidian
2. 选择 **"Open folder as vault"**
3. 选择您的 `my-kb/` 文件夹
4. 按下 `Ctrl+G` 查看知识图谱

## 🔍 查询知识库

```powershell
python kb-manager.py query "你的问题"
```

示例：
```powershell
python kb-manager.py query "文档中提到的核心概念有哪些?"
```

## ✅ 完成！

您现在拥有一个功能齐全的AI知识库系统。

## 📚 进一步阅读

- [完整使用指南](./README-Windows-KB.md)
- [架构说明](./windows-knowledge-base-workflow.md)
- [文件总览](./FILES-OVERVIEW.md)
- [Vault使用说明](../vault-template/README.md)

## 🆘 遇到问题？

1. **API密钥错误**
   ```powershell
   python kb-manager.py config --set api-key NEW_KEY
   ```

2. **无法导入PDF**
   - 确认PDF是文本可搜索的（不是扫描件）
   - 运行: `pip install pypdf2`

3. **Obsidian不显示文档**
   - 确保文档在 `01-Import/` 文件夹
   - 重启Obsidian或刷新

4. **中文乱码**
   - 这是Windows控制台编码问题，不影响功能
   - 在Obsidian中查看文档会正常显示

---

**提示**: 导入多个文档后，知识图谱会更有价值！
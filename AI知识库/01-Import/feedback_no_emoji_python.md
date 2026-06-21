---
name: no-emoji-in-python
description: 不要在Python文件中写emoji字符，用户讨厌emoji
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 7194df5c-9a78-4cbb-a2a2-939de8925a0e
---

永远不要在 Python 文件（.py）中使用 emoji 字符。用户明确表示讨厌 emoji。

**Why:** 用户不喜欢 emoji，认为它们不专业且影响代码可读性。

**How to apply:**
- 所有 Python 文件中的 print 输出、注释、字符串都不使用 emoji
- 替代方案：用纯文本符号如 [OK]、[FAIL]、[WARN]、[INFO]、[SKIP] 等
- 不影响 markdown 文件（skill 文件、文档等可以用 emoji）

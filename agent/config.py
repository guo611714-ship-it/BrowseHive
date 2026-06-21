"""项目配置 - 路径常量定义"""

from pathlib import Path

# 项目根目录（基于agent目录的位置）
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# 核心目录
AGENT_DIR = PROJECT_ROOT / "agent"
TEMPLATES_DIR = AGENT_DIR / "templates"
TOOLS_DIR = AGENT_DIR / "tools"
DISPATCH_DIR = TOOLS_DIR / "dispatch"

# 数据目录
DATA_DIR = PROJECT_ROOT / ".team"
MEMORY_DIR = DATA_DIR / "memory"
TEAM_DIR = DATA_DIR
CHECKPOINTS_DIR = DATA_DIR / "checkpoints"
BROWSER_SESSIONS_DIR = DATA_DIR / "browser_sessions"
AGENT_MEMORY_DIR = DATA_DIR / "agent_memory"

# 外部资源目录
AI_KNOWLEDGE_BASE = PROJECT_ROOT / "AI知识库"
AI_KB_INDEX = AI_KNOWLEDGE_BASE / "03-Index" / "documents.json"
AI_KB_IMPORT = AI_KNOWLEDGE_BASE / "01-Import"
MCP_SCRIPTS = PROJECT_ROOT / "MCP" / "scripts"
CDP_PORT_FILE = MCP_SCRIPTS / ".cdp_port"

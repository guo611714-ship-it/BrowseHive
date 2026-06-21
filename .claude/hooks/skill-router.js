#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');

// ─── Config ─────────────────────────────────────────────
const SKILLS_DIR = path.join(os.homedir(), '.claude', 'skills');
const LEARNING_FILE = path.join(os.homedir(), '.claude', 'skill-router-learning.json');
const MOMENTUM_FILE = path.join(os.homedir(), '.claude', 'skill-router-momentum.json');
const REGISTRY_FILE = path.join(os.homedir(), '.claude', 'skill-router-registry.json');
const MIN_KEYWORDS = 2;
const HIGH_CONFIDENCE = 4;
const SEMANTIC_THRESHOLD = 0.35;
const MAX_SKILLS_IN_PROMPT = 10;

// ─── v1.5: Usage Learning ───────────────────────────────
function loadJSON(file, fallback) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); }
  catch { return fallback; }
}

function saveJSON(file, data) {
  try { fs.writeFileSync(file, JSON.stringify(data, null, 2)); } catch {}
}

function loadLearning() { return loadJSON(LEARNING_FILE, { weights: {}, history: [] }); }

function recordUsage(learning, skillName, accepted) {
  learning.history.push({ skill: skillName, accepted, ts: Date.now() });
  if (learning.history.length > 200) learning.history = learning.history.slice(-200);
  if (!learning.weights[skillName]) learning.weights[skillName] = 1.0;
  learning.weights[skillName] += accepted ? 0.1 : -0.1;
  learning.weights[skillName] = Math.max(0.5, Math.min(2.0, learning.weights[skillName]));
  saveJSON(LEARNING_FILE, learning);
}

// ─── v1.3: Context Awareness ────────────────────────────
function detectProjectType(cwd) {
  try {
    const claudeMd = path.join(cwd, 'CLAUDE.md');
    if (fs.existsSync(claudeMd)) {
      const c = fs.readFileSync(claudeMd, 'utf8').toLowerCase();
      if (/\b(python|django|flask|fastapi)\b/.test(c)) return 'python';
      if (/\b(react|nextjs|vue|angular|svelte)\b/.test(c)) return 'web';
      if (/\b(embedded|keil|stm32|firmware)\b/.test(c)) return 'embedded';
      if (/\b(excel|word|office|powerpoint)\b/.test(c)) return 'office';
    }
    const files = fs.readdirSync(cwd).slice(0, 50);
    if (files.some(f => f.endsWith('.py') || f === 'requirements.txt' || f === 'pyproject.toml')) return 'python';
    if (files.some(f => f === 'package.json')) return 'web';
    if (files.some(f => f.endsWith('.uvprojx') || f.endsWith('.uvproj'))) return 'embedded';
    if (files.some(f => /\.(xlsx|docx|pptx)$/.test(f))) return 'office';
  } catch {}
  return 'general';
}

const PROJECT_SKILL_BOOST = {
  python: ['python-performance-optimization', 'python-design-patterns', 'senior-ml-engineer'],
  web: ['react', 'react-three-fiber', 'vercel-react-best-practices', 'deploy-to-vercel'],
  embedded: ['keil', 'build-keil'],
  office: ['excel-automation', 'word-document-processor', 'office-automation', 'ppt-visual'],
};

// ─── Momentum: Cross-session learning ───────────────────
function loadMomentum() { return loadJSON(MOMENTUM_FILE, { sessions: 0, skillCounts: {} }); }

function updateMomentum(skillName) {
  const m = loadMomentum();
  m.sessions++;
  m.skillCounts[skillName] = (m.skillCounts[skillName] || 0) + 1;
  m.lastUpdated = Date.now();
  saveJSON(MOMENTUM_FILE, m);
}

function getMomentumBoost(skillName) {
  const m = loadMomentum();
  const count = m.skillCounts[skillName] || 0;
  return count > 5 ? 0.5 : count > 2 ? 0.3 : 0;
}

// ─── Skill Discovery ────────────────────────────────────
const STOP_WORDS = new Set([
  'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had',
  'her', 'was', 'one', 'our', 'out', 'has', 'his', 'how', 'its', 'may',
  'new', 'now', 'old', 'see', 'way', 'who', 'why', 'did', 'get', 'got',
  'let', 'say', 'she', 'too', 'use', 'with', 'that', 'this', 'will',
  'each', 'make', 'like', 'long', 'look', 'many', 'most', 'over',
  'such', 'take', 'than', 'them', 'then', 'what', 'when', 'your',
  'from', 'they', 'been', 'have', 'into', 'just', 'know', 'also',
  'back', 'only', 'very', 'some', 'them', 'time', 'about', 'would',
  'make', 'like', 'his', 'these', 'two', 'write', 'go', 'see',
  'number', 'add', 'still', 'should', 'after', 'being', 'does',
  'first', 'any', 'where', 'much', 'use', 'using', 'used',
]);

function extractKeywords(skillPath) {
  try {
    const content = fs.readFileSync(path.join(skillPath, 'SKILL.md'), 'utf8');
    const keywords = new Set();
    const fmMatch = content.match(/^---\s*\n([\s\S]*?)\n---/);
    if (fmMatch) {
      const tags = fmMatch[1].match(/tags:\s*\[([^\]]+)\]/);
      if (tags) tags[1].split(',').forEach(t => keywords.add(t.trim().toLowerCase()));
      let descText = '';
      const normalized = fmMatch[1].replace(/\r\n/g, '\n');
      const descMulti = normalized.match(/description:\s*>-?\n([\s\S]*?)(?=\n\w|\n---)/);
      const descSingle = normalized.match(/description:\s*(?!>-)(.+)/);
      if (descMulti) descText = descMulti[1].replace(/\n\s*/g, ' ').toLowerCase();
      else if (descSingle) descText = descSingle[1].toLowerCase();
      if (descText) {
        descText.split(/\s+/).forEach(w => { const c = w.replace(/[^a-z0-9-]/g, ''); if (c.length > 2 && !STOP_WORDS.has(c)) keywords.add(c); });
        const zhMatches = descText.match(/[一-鿿]{2,4}/g);
        if (zhMatches) zhMatches.forEach(m => keywords.add(m));
      }
    }
    const dirName = path.basename(skillPath).toLowerCase().replace(/[_]/g, '-');
    if (dirName.length > 2) keywords.add(dirName);
    const lines = content.split('\n').slice(0, 80);
    for (const line of lines) {
      const m = line.match(/(?:trigger|关键词|keyword|tag|triggers?):\s*(.+)/i);
      if (m) m[1].toLowerCase().split(/[,;|]/).forEach(w => { const c = w.trim().replace(/[^a-z0-9一-鿿-]/g, ''); if (c.length > 1) keywords.add(c); });
    }
    return [...keywords].slice(0, 30);
  } catch { return []; }
}

// ─── v2.1: Auto-detect new skills via mtime cache ───────
function getSkills() {
  const registry = loadJSON(REGISTRY_FILE, { skills: {}, lastScan: 0 });
  const currentSkills = {};
  let changed = false;

  try {
    for (const dir of fs.readdirSync(SKILLS_DIR)) {
      const skillMd = path.join(SKILLS_DIR, dir, 'SKILL.md');
      if (!fs.existsSync(skillMd)) continue;
      try {
        const stat = fs.statSync(skillMd);
        const cached = registry.skills[dir];
        if (cached && cached.mtime === stat.mtimeMs) {
          currentSkills[dir] = cached.keywords;
        } else {
          const keywords = extractKeywords(path.join(SKILLS_DIR, dir));
          currentSkills[dir] = keywords;
          registry.skills[dir] = { keywords, mtime: stat.mtimeMs };
          changed = true;
        }
      } catch {}
    }
  } catch {}

  if (changed) {
    registry.lastScan = Date.now();
    saveJSON(REGISTRY_FILE, registry);
  }

  return Object.entries(currentSkills).map(([name, keywords]) => ({ name, keywords }));
}

// ─── ZH_EN_MAP: Cross-language matching ─────────────────
const ZH_EN_MAP = {
  // ── 图像/生成 ──
  '图片': ['image', 'generate', 'images', 'text-to-image'],
  '图像': ['image', 'generate', 'images'],
  '生成图片': ['generate', 'image', 'text-to-image'],
  '生成图': ['generate', 'image', 'text-to-image'],
  'AI画': ['image', 'generate', 'gpt'],
  'AI绘图': ['image', 'generate', 'gpt'],
  '画图': ['image', 'generate', 'draw'],
  '绘图': ['image', 'generate', 'draw'],
  '文生图': ['text-to-image', 'generate', 'image'],
  '图生图': ['image-to-image', 'image', 'edit'],
  '编辑图片': ['edit', 'image-edit', 'editing'],
  '修图': ['edit', 'image-edit'],
  '换脸': ['identity-preserving', 'face', 'swap'],
  '换背景': ['background', 'swap', 'edit'],
  '风格迁移': ['style', 'transfer', 'style-transfer'],
  '批量处理图片': ['batch', 'multi-image', 'images'],
  // ── React/前端 ──
  'react': ['react', 'component', 'nextjs'],
  '组件': ['component', 'react', 'components'],
  '前端': ['react', 'nextjs', 'frontend', 'web'],
  '界面': ['react', 'component', 'ui'],
  'UI': ['react', 'component', 'ui'],
  'nextjs': ['nextjs', 'next', 'react'],
  'next': ['nextjs', 'next', 'react'],
  '3D': ['three', 'fiber', 'threejs', 'meshes'],
  '三维': ['three', 'fiber', 'threejs'],
  '3d场景': ['three', 'fiber', 'scene', 'meshes'],
  'json渲染': ['json', 'render', 'json-render'],
  // ── Python ──
  'python': ['python', 'django', 'flask'],
  'Python测试': ['python', 'pytest', 'testing', 'test'],
  '单元测试': ['test', 'testing', 'pytest', 'unit'],
  'pytest': ['python', 'pytest', 'testing'],
  'genkit': ['genkit', 'python', 'flows'],
  'AI应用': ['ai', 'genkit', 'flows', 'agents'],
  // ── GitNexus 系列 ──
  '代码分析': ['analyze', 'analysis', 'gitnexus'],
  '代码探索': ['explore', 'architecture', 'flow'],
  '代码重构': ['refactor', 'refactoring', 'rename', 'extract'],
  '代码调试': ['debug', 'debugging', 'trace', 'error'],
  '影响分析': ['impact', 'analysis', 'safety', 'break'],
  'PR审查': ['review', 'pull-request', 'merge'],
  'PR review': ['review', 'pull-request', 'merge'],
  '审查代码': ['review', 'code-review'],
  '代码审查': ['review', 'code-review'],
  '代码图谱': ['gitnexus', 'index', 'knowledge-graph'],
  // ── 文档/办公 ──
  '文档': ['document', 'word', 'documentation'],
  'word': ['word', 'document', 'word-document'],
  'Word': ['word', 'document', 'word-document'],
  '写文档': ['document', 'word', 'create'],
  '处理文档': ['document', 'word', 'processing'],
  // ── 表格/Excel ──
  '表格': ['excel', 'spreadsheet', 'table', 'excel-automation'],
  'excel': ['excel', 'spreadsheet', 'excel-automation'],
  'Excel': ['excel', 'spreadsheet', 'excel-automation'],
  '电子表格': ['excel', 'spreadsheet', 'excel-automation'],
  '数据表': ['excel', 'spreadsheet', 'table'],
  '格式': ['format', 'formatting', 'preservation'],
  '修订': ['tracked', 'changes', 'revision'],
  '英语单词': ['word', 'master', 'semantics', 'epiphany'],
  '背单词': ['word', 'master', 'semantics'],
  '单词': ['word', 'master', 'deep-dive'],
  // ── PPT ──
  'ppt': ['ppt', 'powerpoint', 'presentation', 'pptx'],
  'PPT': ['ppt', 'powerpoint', 'presentation', 'pptx'],
  '演示文稿': ['ppt', 'powerpoint', 'presentation'],
  '幻灯片': ['ppt', 'powerpoint', 'slides'],
  // ── 嵌入式 ──
  'keil': ['keil', 'mdk', 'uvprojx'],
  'Keil': ['keil', 'mdk', 'uvprojx'],
  '嵌入式': ['embedded', 'keil', 'stm32', 'firmware'],
  'STM32': ['stm32', 'keil', 'mdk', 'embedded'],
  '单片机': ['embedded', 'keil', 'stm32', 'mdk', 'firmware'],
  '烧录': ['flash', 'jlink', 'openocd'],
  '编译': ['build', 'rebuild', 'compile'],
  // ── 部署 ──
  '部署': ['deploy', 'deployment'],
  'azure': ['azure', 'deployment', 'azd'],
  'Azure': ['azure', 'deployment', 'azd'],
  '云部署': ['azure', 'deploy', 'cloud'],
  'vercel': ['vercel', 'deploy', 'deployment'],
  'Vercel': ['vercel', 'deploy', 'deployment'],
  // ── AI/ML ──
  '大模型': ['llm', 'model', 'ai-models'],
  'LLM': ['llm', 'model', 'ai-models'],
  '模型': ['model', 'ai-models'],
  '机器学习': ['ml', 'model', 'deployment', 'mlops'],
  'MLOps': ['mlops', 'pipeline', 'deployment', 'monitoring'],
  'RAG': ['rag', 'retrieval', 'knowledge'],
  '向量': ['embedding', 'vector', 'rag'],
  '微调': ['fine-tune', 'finetune', 'training'],
  '推理': ['inference', 'model', 'deploy'],
  '模型部署': ['model', 'deployment', 'production'],
  '漂移检测': ['drift', 'monitoring', 'data'],
  '特征存储': ['feature', 'store', 'feature-store'],
  'prompt': ['prompt', 'caching', 'claude'],
  'Claude API': ['claude', 'anthropic', 'sdk', 'api'],
  'Anthropic': ['claude', 'anthropic', 'sdk'],
  'AI模型': ['ai', 'model', 'claude', 'openai'],
  '应用模式': ['pattern', 'llm', 'application'],
  // ── Agent ──
  '代理': ['agent', 'agents', 'sdk'],
  'agent': ['agent', 'agents', 'sdk'],
  'Agent': ['agent', 'agents', 'sdk'],
  '智能体': ['agent', 'agents', 'durable', 'stateful'],
  '工作流': ['workflow', 'flow', 'durable'],
  'WebSocket': ['websocket', 'real-time', 'apps'],
  '定时任务': ['scheduled', 'tasks', 'cron'],
  // ── 搜索 ──
  '搜索': ['search-searxng', 'searxng', 'baidu'],
  '联网搜索': ['search-searxng', 'searxng', 'baidu', 'bing'],
  '百度': ['search-searxng', 'searxng', 'baidu'],
  '谷歌': ['search-searxng', 'google'],
  // ── Git/GitHub ──
  'github': ['github', 'git'],
  'GitHub': ['github', 'git'],
  'git加速': ['git', 'mirror', 'accelerator', 'cdn'],
  'clone加速': ['clone', 'mirror', 'accelerator', 'speed'],
  '镜像': ['mirror', 'cdn', 'proxy', 'china'],
  // ── 认证 ──
  '认证': ['auth', 'authentication', 'betterauth'],
  '登录': ['auth', 'login', 'session'],
  'OAuth': ['oauth', 'auth', 'betterauth'],
  'session': ['session', 'auth', 'betterauth'],
  // ── 视频 ──
  '视频': ['video', 'animation', 'remotion'],
  '动画': ['video', 'animation', 'remotion'],
  'Remotion': ['remotion', 'video', 'react'],
  // ── PDF/OCR ──
  'PDF': ['pdf', 'extraction', 'pdfplumber'],
  'pdf': ['pdf', 'extraction', 'pdfplumber'],
  '提取PDF': ['pdf', 'extraction', 'text'],
  'OCR': ['ocr', 'smart-ocr', 'recognition'],
  '文字识别': ['ocr', 'recognition', 'smart-ocr'],
  // ── 股票/金融 ──
  '股票': ['stock', 'finance', 'trading'],
  '炒股': ['stock', 'trading', 'finance'],
  'K线': ['stock', 'chart', 'candlestick'],
  // ── AI视频/头像 ──
  'AI视频': ['ai', 'video', 'generation'],
  '数字人': ['avatar', 'ai', 'video'],
  'AI头像': ['avatar', 'ai', 'image'],
  // ── 测试 ──
  '测试': ['test', 'testing'],
  '自动化测试': ['test', 'playwright', 'browser', 'automation'],
  '截图': ['screenshot', 'capture', 'playwright'],
  '浏览器测试': ['browser', 'playwright', 'testing'],
  // ── Skill 管理 ──
  '创建技能': ['skill-creator', 'skill', 'create'],
  '新建skill': ['skill-creator', 'skill', 'create'],
  '技能': ['skill-creator', 'skill', 'smart-skill-orchestrator'],
  '找技能': ['find-skills', 'skill', 'find', 'discover'],
  '发现技能': ['find-skills', 'skill', 'find', 'discover'],
  '安装技能': ['find-skills', 'skill', 'install', 'discover'],
  // ── 持续学习 ──
  '学习': ['learning', 'instinct', 'continuous'],
  '记忆': ['learning', 'instinct', 'memory'],
  // ── 权限 ──
  '鉴权': ['auth', 'authentication'],
  '权限': ['permission', 'auth', 'role'],
  // ── 创意/设计 (brainstorming) ──
  '头脑风暴': ['brainstorming', 'creative', 'design'],
  'brainstorm': ['brainstorming', 'creative', 'design'],
  '创意设计': ['brainstorming', 'creative', 'design'],
  '构思方案': ['brainstorming', 'design', 'features'],
  '帮我构思': ['brainstorming', 'design', 'creative'],
  '需求分析': ['brainstorming', 'requirements', 'design'],
  '功能设计': ['brainstorming', 'features', 'functionality'],
  // ── 欧亿-Ai (ouyi-ai) ──
  '对话': ['对话', 'chat', 'ouyi-ai', 'api'],
  '写作': ['写作', 'write', 'ouyi-ai'],
  '思维导图': ['思维导图', 'mindmap', 'ouyi-ai'],
  '绘图': ['绘图', 'draw', 'dall-e', 'ouyi-ai'],
  '画图': ['绘图', 'draw', 'image', 'dall-e', 'ouyi-ai'],
  '欧亿': ['欧亿', 'ouyi-ai', 'api'],
  'ouyi': ['ouyi-ai', 'api'],
  // ── 学术论文审稿 (academic-paper-reviewer) ──
  '论文审稿': ['academic-paper-reviewer', 'peer', 'review'],
  '论文评审': ['academic-paper-reviewer', 'peer', 'review'],
  '审稿': ['academic-paper-reviewer', 'peer', 'review', 'referee'],
  'peer review': ['academic-paper-reviewer', 'peer', 'review'],
  '论文': ['academic-paper-reviewer', 'paper', 'manuscript'],
  // ── Karpathy 编码规范 (karpathy-guidelines) ──
  '编码规范': ['karpathy-guidelines', 'code', 'guidelines'],
  '代码规范': ['karpathy-guidelines', 'code', 'guidelines'],
  '重构代码': ['karpathy-guidelines', 'refactor', 'code'],
  'karpathy': ['karpathy-guidelines', 'guidelines', 'code'],
  '避免过度设计': ['karpathy-guidelines', 'overcomplication', 'surgical'],
  // ── 密码/认证 (1password) ──
  '密码': ['1password', 'password', 'secret', 'vault'],
  '密码管理': ['1password', 'password', 'secret', 'vault'],
  '密钥': ['1password', 'secret', 'credential', 'vault'],
  // ── 代码审查 (autoreview) ──
  '自动审查': ['autoreview', 'review', 'auto'],
  '自动代码审查': ['autoreview', 'review', 'codex'],
  // ── 浏览器工作流 (browsehive) ──
  '浏览': ['browsehive', 'browser', 'harness', 'chrome'],
  '浏览器': ['browsehive', 'browser', 'harness', 'chrome'],
  'bh': ['browsehive', 'browser', 'harness'],
  'hive': ['browsehive', 'browser', 'harness'],
  '打开AI平台': ['browsehive', 'doubao', 'deepseek', 'browser'],
  // ── 摄像头 (camsnap) ──
  '摄像头': ['camsnap', 'camera', 'rtsp', 'onvif'],
  '监控': ['camsnap', 'camera', 'rtsp', 'surveillance'],
  'RTSP': ['camsnap', 'rtsp', 'camera'],
  // ── GIF (gifgrep) ──
  'GIF': ['gifgrep', 'gif', 'sticker', 'meme'],
  '动图': ['gifgrep', 'gif', 'sticker', 'animation'],
  '表情包': ['gifgrep', 'meme', 'sticker', 'template'],
  // ── Meme (meme-maker) ──
  'meme': ['meme-maker', 'meme', 'template'],
  '梗图': ['meme-maker', 'meme', 'template'],
  // ── GitHub Issues (gh-issues) ──
  'issue': ['gh-issues', 'github', 'issue', 'bug'],
  'issues': ['gh-issues', 'github', 'issue'],
  '提issue': ['gh-issues', 'github', 'issue', 'report'],
  // ── GitHub 归档 (gitcrawl) ──
  'github归档': ['gitcrawl', 'github', 'archive', 'search'],
  'PR搜索': ['gitcrawl', 'github', 'pull-request', 'search'],
  // ── Google Workspace (gog) ──
  'gmail': ['gog', 'gmail', 'email', 'google'],
  'Gmail': ['gog', 'gmail', 'email', 'google'],
  'google': ['gog', 'google', 'workspace'],
  '日历': ['gog', 'calendar', 'google'],
  'Google Drive': ['gog', 'google', 'drive', 'workspace'],
  // ── 邮件 (himalaya) ──
  '邮件': ['himalaya', 'imap', 'smtp'],
  '收邮件': ['himalaya', 'imap', 'inbox'],
  '发邮件': ['himalaya', 'smtp', 'compose'],
  '邮箱': ['himalaya', 'imap', 'mail'],
  // ── 图像编辑 (image-edit) ──
  '图像编辑': ['image-edit', 'runcomfy', 'edit', 'flux'],
  '图像修复': ['image-edit', 'inpaint', 'edit', 'restore'],
  'Flux': ['image-edit', 'flux', 'kontext', 'edit'],
  // ── LLM 模式 (llm-patterns) ──
  'LLM模式': ['llm-patterns', 'llm', 'pattern', 'prompt'],
  '应用模式': ['llm-patterns', 'pattern', 'llm', 'prompt'],
  'prompt管理': ['llm-patterns', 'prompt', 'management', 'llm'],
  // ── MCP 管理 (mcporter) ──
  'MCP': ['mcporter', 'mcp', 'server', 'tool'],
  'MCP服务器': ['mcporter', 'mcp', 'server', 'tool'],
  // ── 模型路由 (model-router) ──
  '模型路由': ['model-router', 'router', 'model', 'select'],
  '模型选择': ['model-router', 'router', 'model', 'select'],
  '选择模型': ['model-router', 'router', 'model', 'select'],
  '模型成本': ['model-router', 'model', 'cost', 'token'],
  '节省token': ['model-router', 'token', 'cost', 'save'],
  // ── 模型用量 (model-usage) ──
  '模型用量': ['model-usage', 'usage', 'cost', 'model'],
  '用量统计': ['model-usage', 'usage', 'cost', 'statistics'],
  'token用量': ['model-usage', 'token', 'usage', 'cost'],
  // ── Node.js 调试 (node-inspect-debugger) ──
  'Node调试': ['node-inspect-debugger', 'node', 'inspect', 'debug'],
  'Node.js调试': ['node-inspect-debugger', 'node', 'inspect', 'debug'],
  'Node连接': ['node-connect', 'node', 'connect', 'pair'],
  // ── Notion (notion) ──
  'notion': ['notion', 'pages', 'markdown', 'content'],
  'Notion': ['notion', 'pages', 'markdown', 'content'],
  '笔记管理': ['notion', 'obsidian', 'notes'],
  // ── Obsidian (obsidian) ──
  'obsidian': ['obsidian', 'vaults', 'notes', 'markdown'],
  'Obsidian': ['obsidian', 'vaults', 'notes', 'markdown'],
  '知识库': ['obsidian', 'notion', 'vaults'],
  '双链笔记': ['obsidian', 'links', 'notes'],
  // ── 语音识别 (openai-whisper) ──
  '语音识别': ['openai-whisper', 'whisper', 'speech', 'transcribe'],
  '语音转文字': ['openai-whisper', 'whisper', 'speech', 'transcribe'],
  '转录': ['openai-whisper', 'whisper', 'transcribe', 'audio'],
  'Whisper': ['openai-whisper', 'whisper', 'speech', 'transcribe'],
  // ── TTS (sag/sherpa-onnx-tts) ──
  '语音合成': ['sag', 'sherpa-onnx-tts', 'tts', 'speech'],
  'TTS': ['sag', 'sherpa-onnx-tts', 'tts', 'speech'],
  '文字转语音': ['sag', 'sherpa-onnx-tts', 'tts', 'speech'],
  // ── Python 调试 (python-debugpy) ──
  'Python调试': ['python-debugpy', 'python', 'debug', 'pdb'],
  'Python断点': ['python-debugpy', 'python', 'breakpoint', 'debug'],
  // ── 代码审查流程 (receiving/requesting-code-review) ──
  '接收审查': ['receiving-code-review', 'review', 'feedback'],
  '请求审查': ['requesting-code-review', 'review', 'pull-request'],
  '提交审查': ['requesting-code-review', 'review', 'merge'],
  // ── 原型验证 (spike) ──
  '原型': ['spike', 'prototype', 'spike', 'feasibility'],
  '验证可行性': ['spike', 'spike', 'feasibility', 'validate'],
  '技术调研': ['spike', 'spike', 'research', 'feasibility'],
  // ── 摘要 (summarize) ──
  '摘要': ['summarize', 'transcribe', 'youtubevideos'],
  '总结': ['summarize', 'transcribe', 'podcasts'],
  '总结视频': ['summarize', 'youtubevideos', 'transcribe'],
  '总结文章': ['summarize', 'articles', 'transcripts'],
  // ── 任务协调 (taskflow) ──
  '任务协调': ['taskflow', 'task', 'flow', 'coordinate'],
  '多步任务': ['taskflow', 'task', 'flow', 'multi-step'],
  // ── 视频帧 (video-frames) ──
  '视频帧': ['video-frames', 'frame', 'video', 'ffmpeg'],
  '截取视频': ['video-frames', 'frame', 'clip', 'ffmpeg'],
  // ── 健康检查 (healthcheck) ──
  '健康检查': ['healthcheck', 'health', 'audit', 'security'],
  '安全审计': ['healthcheck', 'security', 'audit', 'firewall'],
  // ── Discord 归档 (discrawl) ──
  'Discord归档': ['discrawl', 'discord', 'archive', 'search'],
  'Discord搜索': ['discrawl', 'discord', 'search', 'dm'],
  // ── 幻灯片/演示 (canvas) ──
  'HTML渲染': ['canvas', 'html', 'canvas', 'render'],
  // ── 优化测试 (optimizetests) ──
  '优化测试': ['optimizetests', 'test', 'optimize', 'ci'],
  // ── Oracle (oracle) ──
  'oracle': ['oracle', 'review', 'debug', 'second-model'],
  '第二模型审查': ['oracle', 'oracle', 'review', 'second-model'],
  // ── 会话日志 (session-logs) ──
  '会话日志': ['session-logs', 'session', 'log', 'jq'],
  '查看历史': ['session-logs', 'session', 'log', 'history'],
  // ── Nano Banana Edit (nano-banana-edit) ──
  'NanoBanana': ['nano-banana-edit', 'nano-banana', 'edit', 'identity'],
  // ── 视频/动画 (video-frames 已覆盖) ──
  '提取帧': ['video-frames', 'frame', 'extract', 'ffmpeg'],
  // ── 语音通话 (voice-call) ──
  '语音通话': ['voice-call', 'voice', 'call', 'openclaw'],
  '打电话': ['voice-call', 'voice', 'call'],
  // ── tmux (tmux) ──
  'tmux': ['tmux', 'session', 'pane', 'terminal'],
  '终端复用': ['tmux', 'tmux', 'terminal', 'multiplexer'],
  // ── 图表/绘图 (diagram-maker) ──
  '图表': ['diagram-maker', 'diagram', 'chart', 'draw'],
  '流程图': ['diagram-maker', 'diagram', 'flowchart', 'mermaid'],
  '架构图': ['diagram-maker', 'diagram', 'architecture', 'draw'],
  // ── 连续学习 (continuous-learning-v2) ──
  '持续学习': ['continuous-learning-v2', 'learning', 'continuous', 'instinct'],
  // ── 成本感知 (cost-aware-llm-pipeline) ──
  '成本感知': ['cost-aware-llm-pipeline', 'cost', 'pipeline', 'llm'],
  '成本优化': ['cost-aware-llm-pipeline', 'cost', 'optimize', 'token'],
  // ── 管理器 (smart-skill-orchestrator) ──
  '技能路由': ['smart-skill-orchestrator', 'skill', 'router', 'orchestrator'],
  '技能编排': ['smart-skill-orchestrator', 'skill', 'orchestrator', 'chain'],
  // ── 标签重复PR (tag-duplicate-prs-issues) ──
  '重复PR': ['tag-duplicate-prs-issues', 'duplicate', 'tag', 'pr'],
  // ── 通道消息流 (channel-message-flows) ──
  '消息流': ['channel-message-flows', 'channel', 'message', 'flow'],
};

// ─── v2.2: Auto-build ZH_EN_MAP from skill descriptions ──
// Scans all SKILL.md files for Chinese text near English keywords,
// auto-generates cross-language mappings. No manual maintenance needed.
function autoBuildZhMap(skills) {
  const autoMap = {};

  for (const skill of skills) {
    try {
      const content = fs.readFileSync(path.join(SKILLS_DIR, skill.name, 'SKILL.md'), 'utf8');
      const fmMatch = content.match(/^---\s*\n([\s\S]*?)\n---/);
      if (!fmMatch) continue;

      const normalized = fmMatch[1].replace(/\r\n/g, '\n');
      // Get description text (both single-line and >- multi-line)
      let descText = '';
      const descMulti = normalized.match(/description:\s*>-?\n([\s\S]*?)(?=\n\w|\n---)/);
      const descSingle = normalized.match(/description:\s*(?!>-)(.+)/);
      if (descMulti) descText = descMulti[1].replace(/\n\s*/g, ' ');
      else if (descSingle) descText = descSingle[1];
      if (!descText) continue;

      // Extract Chinese segments (2-4 chars only — meaningful words, not sentence fragments)
      const zhSegments = descText.match(/[一-鿿]{2,4}/g) || [];
      // Extract English keywords from same description (non-stopwords, >2 chars)
      const enKeywords = [];
      descText.toLowerCase().split(/\s+/).forEach(w => {
        const c = w.replace(/[^a-z0-9-]/g, '');
        if (c.length > 2 && !STOP_WORDS.has(c)) enKeywords.push(c);
      });
      // Also include skill's own directory name as keyword
      const dirName = skill.name.toLowerCase().replace(/[_]/g, '-');
      if (dirName.length > 2) enKeywords.push(dirName);

      if (zhSegments.length === 0 || enKeywords.length === 0) continue;

      // Map each Chinese segment to the English keywords from the same skill
      for (const zh of zhSegments) {
        if (!autoMap[zh]) autoMap[zh] = new Set();
        enKeywords.forEach(ek => autoMap[zh].add(ek));
      }
    } catch {}
  }

  // Convert Sets to Arrays and merge with manual ZH_EN_MAP
  const merged = { ...ZH_EN_MAP };
  for (const [zh, enSet] of Object.entries(autoMap)) {
    const enArr = [...enSet].slice(0, 8); // Cap at 8 keywords per entry
    if (merged[zh]) {
      // Merge: add new keywords to existing entry
      const existing = new Set(merged[zh]);
      enArr.forEach(ek => existing.add(ek));
      merged[zh] = [...existing].slice(0, 10);
    } else {
      merged[zh] = enArr;
    }
  }

  return merged;
}

// ─── v2.0: Semantic Matching (zero-token word overlap) ──
// Expand prompt into English keyword space using ZH_EN_MAP, then compute
// Jaccard similarity against each skill's keyword set. No LLM calls needed.
function expandPromptKeywords(prompt, zhMap) {
  const lower = prompt.toLowerCase();
  const expanded = new Set();

  // Direct word extraction
  lower.split(/[\s,.;!?，。；！？、]+/).forEach(w => {
    const clean = w.replace(/[^a-z0-9]/g, '');
    if (clean.length > 1) expanded.add(clean);
  });

  // Chinese n-gram extraction (2-6 chars)
  const zhChars = lower.match(/[一-鿿]{2,6}/g) || [];
  zhChars.forEach(z => expanded.add(z));

  // Cross-language expansion via zhMap (auto-built + manual)
  for (const [zh, enKeywords] of Object.entries(zhMap)) {
    if (lower.includes(zh.toLowerCase())) {
      enKeywords.forEach(ek => expanded.add(ek));
    }
  }

  return [...expanded];
}

function semanticMatch(prompt, skills, zhMap) {
  const promptKws = expandPromptKeywords(prompt, zhMap);
  if (promptKws.length === 0) return [];

  const promptSet = new Set(promptKws);
  const matches = [];

  for (const skill of skills) {
    if (skill.keywords.length === 0) continue;
    const skillSet = new Set(skill.keywords);
    // Jaccard similarity
    let intersection = 0;
    for (const kw of promptSet) { if (skillSet.has(kw)) intersection++; }
    const union = promptSet.size + skillSet.size - intersection;
    const similarity = union > 0 ? intersection / union : 0;
    if (similarity >= SEMANTIC_THRESHOLD) {
      matches.push({ name: skill.name, score: similarity * 10, method: 'semantic' });
    }
  }

  return matches.sort((a, b) => b.score - a.score).slice(0, 3);
}

// ─── v1.7: Multi-skill Chaining ────────────────────────
// Detect multiple distinct actions in a single prompt
const CONNECTORS = ['然后', '接着', '之后', '再', '做完', '并且', '同时',
  'then', 'next', 'after', 'and then', 'finally'];
const PUNCTUATION = ['。', '！', '？', '.', '!', '?', '\n', '；', ';', '，', ','];

function detectMultipleActions(prompt) {
  // Split by punctuation and connectors
  let segments = [prompt];
  for (const conn of CONNECTORS) {
    const newSegments = [];
    for (const seg of segments) {
      newSegments.push(...seg.split(conn));
    }
    segments = newSegments;
  }
  // Also split by Chinese punctuation
  for (const p of PUNCTUATION) {
    const newSegments = [];
    for (const seg of segments) {
      newSegments.push(...seg.split(p));
    }
    segments = newSegments;
  }

  const cleaned = segments.map(s => s.trim()).filter(s => s.replace(/[\s\p{P}]/gu, '').length >= 2);
  return cleaned.length >= 2 ? cleaned : null;
}

function matchSegment(segment, skills, learning, projectType, zhMap) {
  const lower = segment.toLowerCase();
  const boosted = PROJECT_SKILL_BOOST[projectType] || [];
  const matches = [];

  for (const skill of skills) {
    let directHits = 0;
    let zhHits = 0;
    for (const kw of skill.keywords) { if (lower.includes(kw)) directHits++; }
    for (const [zh, enKeywords] of Object.entries(zhMap)) {
      if (lower.includes(zh.toLowerCase())) {
        for (const ek of enKeywords) {
          if (skill.keywords.includes(ek)) zhHits++;
        }
      }
    }
    const score = (directHits + zhHits) * (learning.weights[skill.name] || 1.0) + getMomentumBoost(skill.name)
      + (boosted.includes(skill.name) ? 1 : 0);
    // Require meaningful match: 2+ direct hits, 1+ zh-map hits, or 1+ each
    if (score >= MIN_KEYWORDS && (directHits >= 2 || zhHits >= 1 || (directHits >= 1 && zhHits >= 1))) {
      matches.push({ name: skill.name, score });
    }
  }

  return matches.sort((a, b) => b.score - a.score).slice(0, 1);
}

// ─── Quick Match (keyword + cross-language) ──────────────
function quickMatch(prompt, skills, learning, projectType, zhMap) {
  const lower = prompt.toLowerCase();
  const boosted = PROJECT_SKILL_BOOST[projectType] || [];
  const matches = [];

  for (const skill of skills) {
    let directHits = 0;
    let zhHits = 0;
    for (const kw of skill.keywords) { if (lower.includes(kw)) directHits++; }
    for (const [zh, enKeywords] of Object.entries(zhMap)) {
      if (lower.includes(zh.toLowerCase())) {
        for (const ek of enKeywords) {
          if (skill.keywords.includes(ek)) zhHits++;
        }
      }
    }
    let score = directHits + zhHits;
    if (boosted.includes(skill.name)) score += 1;
    score *= learning.weights[skill.name] || 1.0;
    score += getMomentumBoost(skill.name);
    // Accept: 2+ direct hits, 1+ zh-map hits, or 1+ each
    if (score >= 1 && (directHits >= 2 || zhHits >= 1 || (directHits >= 1 && zhHits >= 1))) {
      matches.push({ name: skill.name, score });
    }
  }

  return matches.sort((a, b) => b.score - a.score).slice(0, 3);
}

// ─── Main ───────────────────────────────────────────────
async function readStdin() {
  let raw = '';
  process.stdin.setEncoding('utf8');
  for await (const chunk of process.stdin) raw += chunk;
  return raw;
}

async function main() {
  try {
    const raw = await readStdin();
    if (!raw.trim()) process.exit(0);

    const data = JSON.parse(raw);
    const prompt = data.prompt || data.tool_input?.prompt || '';
    if (!prompt) process.exit(0);

    const cwd = data.cwd || process.cwd();

    // Skip if user explicitly invoked a skill or slash command
    if (/^\/\w/.test(prompt.trim())) process.exit(0);

    const skills = getSkills();
    const learning = loadLearning();
    const projectType = detectProjectType(cwd);
    const zhMap = autoBuildZhMap(skills);

    // ── v1.7: Multi-skill chaining (checked FIRST) ──
    const segments = detectMultipleActions(prompt);
    if (segments && segments.length >= 2) {
      const chainResults = [];
      const usedSkills = new Set();
      for (const seg of segments) {
        const segMatches = matchSegment(seg, skills, learning, projectType, zhMap);
        for (const m of segMatches) {
          if (!usedSkills.has(m.name)) {
            chainResults.push({ segment: seg, skill: m.name, score: m.score });
            usedSkills.add(m.name);
          }
        }
      }

      if (chainResults.length >= 2) {
        const steps = chainResults.map((r, i) => `${i + 1}. ${r.segment} → ${r.skill}`).join('; ');
        const response = {
          hookSpecificOutput: {
            hookEventName: 'UserPromptSubmit',
            updatedPrompt: prompt + `\n\n[chain:${chainResults.map(r => r.skill).join('→')}]`,
          },
        };
        process.stdout.write(JSON.stringify(response));
        process.exit(0);
      }
    }

    // ── Phase 1: Quick keyword match ──
    const quickMatches = quickMatch(prompt, skills, learning, projectType, zhMap);

    // High confidence → auto-invoke
    if (quickMatches.length > 0 && quickMatches[0].score >= HIGH_CONFIDENCE) {
      const skillName = quickMatches[0].name;
      recordUsage(learning, skillName, true);
      updateMomentum(skillName);
      const response = {
        hookSpecificOutput: {
          hookEventName: 'UserPromptSubmit',
          updatedPrompt: prompt + `\n\n[skill:${skillName}]`,
        },
      };
      process.stdout.write(JSON.stringify(response));
      process.exit(0);
    }

    // Medium confidence → inject candidate list
    if (quickMatches.length > 0) {
      const matches = quickMatches.map(m => m.name).join(', ');
      const response = {
        hookSpecificOutput: {
          hookEventName: 'UserPromptSubmit',
          updatedPrompt: prompt + `\n\n[skills:${matches}]`,
        },
      };
      process.stdout.write(JSON.stringify(response));
      process.exit(0);
    }

    // ── v2.0: Semantic fallback (borderline = 0-1 keywords) ──
    const semanticMatches = semanticMatch(prompt, skills, zhMap);
    if (semanticMatches.length > 0 && semanticMatches[0].score >= SEMANTIC_THRESHOLD * 10) {
      const sm = semanticMatches[0];
      const allNames = semanticMatches.map(m => m.name).join(', ');
      const response = {
        hookSpecificOutput: {
          hookEventName: 'UserPromptSubmit',
          updatedPrompt: prompt + `\n\n[skills:${allNames}]`,
        },
      };
      process.stdout.write(JSON.stringify(response));
      process.exit(0);
    }

    // ── Phase 3: Project context fallback ──
    if (projectType !== 'general') {
      const relevant = (PROJECT_SKILL_BOOST[projectType] || []).slice(0, 3).join(', ');
      const response = {
        hookSpecificOutput: {
          hookEventName: 'UserPromptSubmit',
          updatedPrompt: prompt + `\n\n[project:${projectType}:${relevant}]`,
        },
      };
      process.stdout.write(JSON.stringify(response));
    }

    process.exit(0);
  } catch {
    process.exit(0);
  }
}

main();

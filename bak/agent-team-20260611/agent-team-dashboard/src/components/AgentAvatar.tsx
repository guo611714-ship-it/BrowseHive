// 明朝官职 Agent SVG 形象
// 风格：简约线条画 + 圆形构图 + 单一主色调

interface AgentAvatarProps {
  agentId: string;
  size?: number;
  status: 'idle' | 'running' | 'completed' | 'failed' | 'waiting';
}

// 状态颜色叠加
const STATUS_OVERLAY: Record<string, string> = {
  idle: 'opacity-30',
  running: 'opacity-100',
  completed: 'opacity-100',
  failed: 'opacity-100',
  waiting: 'opacity-60',
};

export function AgentAvatar({ agentId, size = 80, status }: AgentAvatarProps) {
  const opacity = STATUS_OVERLAY[status];

  return (
    <div className={opacity} style={{ width: size, height: size }}>
      {getAvatar(agentId)}
    </div>
  );
}

function getAvatar(id: string) {
  switch (id) {
    case 'xiaohuangmen':
      return <Xiaohuangmen />;
    case 'sili_suitang':
      return <SiliSuitang />;
    case 'dongchang_tanshi':
      return <DongchangTanshi />;
    case 'shangbao_dianbu':
      return <ShangbaoDianbu />;
    case 'neiguan_yingzao':
      return <NeiguanYingzao />;
    case 'liubu_liulanqi':
      return <LiubuLiulanqi />;
    case 'hanlin':
      return <Hanlin />;
    case 'zhukao':
      return <Zhukao />;
    case 'planner':
      return <Planner />;
    case 'multimodal':
      return <Multimodal />;
    default:
      return <Unknown />;
  }
}

// 1. 黄门通传使 - 橙色 - 手持圣旨
function Xiaohuangmen() {
  return (
    <svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="50" cy="50" r="48" stroke="#F97316" strokeWidth="2" fill="#FFF7ED" />
      {/* 乌纱帽 */}
      <path d="M35 35 L50 25 L65 35 L60 38 L50 30 L40 38 Z" fill="#1E293B" />
      <rect x="38" y="35" width="24" height="8" rx="2" fill="#1E293B" />
      {/* 脸 */}
      <circle cx="50" cy="48" r="8" fill="#FEF3C7" stroke="#1E293B" strokeWidth="1.5" />
      <circle cx="47" cy="47" r="1" fill="#1E293B" />
      <circle cx="53" cy="47" r="1" fill="#1E293B" />
      <path d="M48 52 Q50 54 52 52" stroke="#1E293B" strokeWidth="1" fill="none" />
      {/* 官服 */}
      <path d="M38 56 L50 52 L62 56 L65 75 L35 75 Z" fill="#F97316" stroke="#1E293B" strokeWidth="1.5" />
      {/* 圣旨 */}
      <rect x="58" y="58" width="12" height="18" rx="2" fill="#FCD34D" stroke="#1E293B" strokeWidth="1" />
      <line x1="60" y1="62" x2="68" y2="62" stroke="#1E293B" strokeWidth="0.8" />
      <line x1="60" y1="65" x2="68" y2="65" stroke="#1E293B" strokeWidth="0.8" />
      <line x1="60" y1="68" x2="68" y2="68" stroke="#1E293B" strokeWidth="0.8" />
    </svg>
  );
}

// 2. 司礼文书官 - 蓝色 - 手持毛笔和书本
function SiliSuitang() {
  return (
    <svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="50" cy="50" r="48" stroke="#3B82F6" strokeWidth="2" fill="#EFF6FF" />
      {/* 乌纱帽 */}
      <path d="M30 38 L50 28 L70 38 L65 42 L50 33 L35 42 Z" fill="#1E293B" />
      <rect x="35" y="38" width="30" height="6" rx="2" fill="#1E293B" />
      {/* 脸 */}
      <circle cx="50" cy="50" r="9" fill="#FEF3C7" stroke="#1E293B" strokeWidth="1.5" />
      <circle cx="47" cy="49" r="1" fill="#1E293B" />
      <circle cx="53" cy="49" r="1" fill="#1E293B" />
      <path d="M47 54 Q50 56 53 54" stroke="#1E293B" strokeWidth="1" fill="none" />
      {/* 胡须 */}
      <path d="M48 55 L46 60" stroke="#1E293B" strokeWidth="1" />
      <path d="M52 55 L54 60" stroke="#1E293B" strokeWidth="1" />
      {/* 官服 */}
      <path d="M36 58 L50 54 L64 58 L68 78 L32 78 Z" fill="#3B82F6" stroke="#1E293B" strokeWidth="1.5" />
      {/* 书本 */}
      <rect x="28" y="60" width="10" height="14" rx="1" fill="#FEF3C7" stroke="#1E293B" strokeWidth="1" />
      <line x1="30" y1="63" x2="36" y2="63" stroke="#1E293B" strokeWidth="0.5" />
      <line x1="30" y1="66" x2="36" y2="66" stroke="#1E293B" strokeWidth="0.5" />
      {/* 毛笔 */}
      <line x1="65" y1="55" x2="72" y2="75" stroke="#1E293B" strokeWidth="2" />
      <circle cx="72" cy="76" r="2" fill="#1E293B" />
    </svg>
  );
}

// 3. 东厂探子 - 深蓝 - 蒙面+放大镜
function DongchangTanshi() {
  return (
    <svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="50" cy="50" r="48" stroke="#6366F1" strokeWidth="2" fill="#EEF2FF" />
      {/* 连帽 */}
      <path d="M30 40 Q50 20 70 40 L68 65 Q50 70 32 65 Z" fill="#312E81" stroke="#1E293B" strokeWidth="1.5" />
      {/* 面罩 */}
      <path d="M35 45 Q50 42 65 45 L63 55 Q50 58 37 55 Z" fill="#1E293B" />
      {/* 眼睛 */}
      <ellipse cx="43" cy="50" rx="4" ry="3" fill="white" />
      <ellipse cx="57" cy="50" rx="4" ry="3" fill="white" />
      <circle cx="43" cy="50" r="1.5" fill="#6366F1" />
      <circle cx="57" cy="50" r="1.5" fill="#6366F1" />
      {/* 放大镜 */}
      <circle cx="50" cy="72" r="10" stroke="#6366F1" strokeWidth="2" fill="none" />
      <line x1="57" y1="79" x2="65" y2="88" stroke="#6366F1" strokeWidth="3" strokeLinecap="round" />
      <circle cx="50" cy="72" r="6" fill="#EEF2FF" opacity="0.5" />
    </svg>
  );
}

// 4. 尚宝校验官 - 绿色 - 手持玉玺+对勾
function ShangbaoDianbu() {
  return (
    <svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="50" cy="50" r="48" stroke="#10B981" strokeWidth="2" fill="#ECFDF5" />
      {/* 官帽 */}
      <path d="M35 35 L50 25 L65 35 L60 38 L50 30 L40 38 Z" fill="#1E293B" />
      <rect x="38" y="35" width="24" height="8" rx="2" fill="#1E293B" />
      {/* 脸 */}
      <circle cx="50" cy="48" r="8" fill="#FEF3C7" stroke="#1E293B" strokeWidth="1.5" />
      <circle cx="47" cy="47" r="1" fill="#1E293B" />
      <circle cx="53" cy="47" r="1" fill="#1E293B" />
      {/* 胡须 */}
      <path d="M46 52 L44 58" stroke="#1E293B" strokeWidth="1" />
      <path d="M50 53 L50 59" stroke="#1E293B" strokeWidth="1" />
      <path d="M54 52 L56 58" stroke="#1E293B" strokeWidth="1" />
      {/* 官服 */}
      <path d="M38 56 L50 52 L62 56 L65 75 L35 75 Z" fill="#10B981" stroke="#1E293B" strokeWidth="1.5" />
      {/* 玉玺 */}
      <rect x="58" y="55" width="14" height="12" rx="2" fill="#10B981" stroke="#1E293B" strokeWidth="1.5" />
      <path d="M62 61 L65 64 L70 58" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// 5. 内官营造官 - 黄色 - 手持罗盘
function NeiguanYingzao() {
  return (
    <svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="50" cy="50" r="48" stroke="#F59E0B" strokeWidth="2" fill="#FFFBEB" />
      {/* 工帽 */}
      <path d="M38 32 Q50 25 62 32 L60 38 L40 38 Z" fill="#1E293B" />
      <rect x="40" y="36" width="20" height="6" rx="1" fill="#1E293B" />
      {/* 脸 */}
      <circle cx="50" cy="48" r="8" fill="#FEF3C7" stroke="#1E293B" strokeWidth="1.5" />
      <circle cx="47" cy="47" r="1" fill="#1E293B" />
      <circle cx="53" cy="47" r="1" fill="#1E293B" />
      <path d="M48 52 Q50 54 52 52" stroke="#1E293B" strokeWidth="1" fill="none" />
      {/* 工服 */}
      <path d="M36 56 L50 52 L64 56 L68 78 L32 78 Z" fill="#F59E0B" stroke="#1E293B" strokeWidth="1.5" />
      {/* 罗盘 */}
      <circle cx="50" cy="72" r="10" stroke="#1E293B" strokeWidth="1.5" fill="#FFFBEB" />
      <circle cx="50" cy="72" r="7" stroke="#1E293B" strokeWidth="1" fill="none" />
      <line x1="50" y1="65" x2="50" y2="79" stroke="#1E293B" strokeWidth="0.8" />
      <line x1="43" y1="72" x2="57" y2="72" stroke="#1E293B" strokeWidth="0.8" />
      <circle cx="50" cy="72" r="2" fill="#F59E0B" />
    </svg>
  );
}

// 6. 御前御者 - 粉色 - 眼睛图案
function LiubuLiulanqi() {
  return (
    <svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="50" cy="50" r="48" stroke="#EC4899" strokeWidth="2" fill="#FDF2F8" />
      {/* 官帽 */}
      <path d="M35 35 L50 25 L65 35 L60 38 L50 30 L40 38 Z" fill="#1E293B" />
      <rect x="38" y="35" width="24" height="8" rx="2" fill="#1E293B" />
      {/* 脸（无脸风格） */}
      <circle cx="50" cy="48" r="8" fill="#FDF2F8" stroke="#1E293B" strokeWidth="1.5" />
      {/* 大眼睛 - 核心特征 */}
      <ellipse cx="50" cy="48" rx="5" ry="4" fill="white" stroke="#1E293B" strokeWidth="1" />
      <circle cx="50" cy="48" r="2.5" fill="#EC4899" />
      <circle cx="50" cy="48" r="1" fill="#1E293B" />
      <circle cx="51" cy="47" r="0.5" fill="white" />
      {/* 官服 */}
      <path d="M38 56 L50 52 L62 56 L65 75 L35 75 Z" fill="#EC4899" stroke="#1E293B" strokeWidth="1.5" />
      {/* 胸前眼睛装饰 */}
      <ellipse cx="50" cy="65" rx="6" ry="4" fill="white" stroke="#1E293B" strokeWidth="1" />
      <circle cx="50" cy="65" r="2" fill="#EC4899" />
    </svg>
  );
}

// 7. 翰林 - 紫色 - 手持毛笔和书卷
function Hanlin() {
  return (
    <svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="50" cy="50" r="48" stroke="#8B5CF6" strokeWidth="2" fill="#F5F3FF" />
      {/* 学士帽 */}
      <rect x="38" y="28" width="24" height="10" rx="2" fill="#1E293B" />
      <path d="M35 35 L65 35" stroke="#1E293B" strokeWidth="2" />
      <circle cx="50" cy="28" r="2" fill="#8B5CF6" />
      {/* 脸 */}
      <circle cx="50" cy="48" r="8" fill="#FEF3C7" stroke="#1E293B" strokeWidth="1.5" />
      <circle cx="47" cy="47" r="1" fill="#1E293B" />
      <circle cx="53" cy="47" r="1" fill="#1E293B" />
      <path d="M48 52 Q50 54 52 52" stroke="#1E293B" strokeWidth="1" fill="none" />
      {/* 胡须 */}
      <path d="M47 53 L45 58" stroke="#1E293B" strokeWidth="0.8" />
      <path d="M53 53 L55 58" stroke="#1E293B" strokeWidth="0.8" />
      {/* 官服 */}
      <path d="M38 56 L50 52 L62 56 L65 75 L35 75 Z" fill="#8B5CF6" stroke="#1E293B" strokeWidth="1.5" />
      {/* 书卷 */}
      <rect x="28" y="60" width="8" height="15" rx="1" fill="#FEF3C7" stroke="#1E293B" strokeWidth="1" />
      <line x1="30" y1="63" x2="34" y2="63" stroke="#1E293B" strokeWidth="0.5" />
      <line x1="30" y1="66" x2="34" y2="66" stroke="#1E293B" strokeWidth="0.5" />
      {/* 毛笔 */}
      <line x1="65" y1="55" x2="72" y2="72" stroke="#1E293B" strokeWidth="1.5" />
      <path d="M72 72 L74 76 L70 76 Z" fill="#1E293B" />
    </svg>
  );
}

// 8. 主考 - 红色 - 手持天平
function Zhukao() {
  return (
    <svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="50" cy="50" r="48" stroke="#EF4444" strokeWidth="2" fill="#FEF2F2" />
      {/* 官帽 */}
      <path d="M35 35 L50 25 L65 35 L60 38 L50 30 L40 38 Z" fill="#1E293B" />
      <rect x="38" y="35" width="24" height="8" rx="2" fill="#1E293B" />
      {/* 脸 */}
      <circle cx="50" cy="48" r="8" fill="#FEF3C7" stroke="#1E293B" strokeWidth="1.5" />
      <circle cx="47" cy="47" r="1" fill="#1E293B" />
      <circle cx="53" cy="47" r="1" fill="#1E293B" />
      <path d="M47 52 L53 52" stroke="#1E293B" strokeWidth="1" />
      {/* 胡须 */}
      <path d="M46 53 L44 58" stroke="#1E293B" strokeWidth="1" />
      <path d="M54 53 L56 58" stroke="#1E293B" strokeWidth="1" />
      {/* 官服 */}
      <path d="M38 56 L50 52 L62 56 L65 75 L35 75 Z" fill="#EF4444" stroke="#1E293B" strokeWidth="1.5" />
      {/* 天平 */}
      <line x1="30" y1="60" x2="30" y2="75" stroke="#1E293B" strokeWidth="1.5" />
      <line x1="22" y1="60" x2="38" y2="60" stroke="#1E293B" strokeWidth="1.5" />
      <path d="M22 60 L18 70 L26 70 Z" fill="#EF4444" stroke="#1E293B" strokeWidth="1" />
      <path d="M38 60 L34 70 L42 70 Z" fill="#EF4444" stroke="#1E293B" strokeWidth="1" />
    </svg>
  );
}

// 9. 军师 - 青色 - 手持算盘和卷轴
function Planner() {
  return (
    <svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="50" cy="50" r="48" stroke="#06B6D4" strokeWidth="2" fill="#ECFEFF" />
      {/* 布帽 */}
      <path d="M35 35 Q50 25 65 35 L62 40 L38 40 Z" fill="#1E293B" />
      <rect x="38" y="38" width="24" height="5" rx="1" fill="#06B6D4" />
      {/* 脸 */}
      <circle cx="50" cy="48" r="8" fill="#FEF3C7" stroke="#1E293B" strokeWidth="1.5" />
      <circle cx="47" cy="47" r="1" fill="#1E293B" />
      <circle cx="53" cy="47" r="1" fill="#1E293B" />
      <path d="M48 52 Q50 54 52 52" stroke="#1E293B" strokeWidth="1" fill="none" />
      {/* 胡须 */}
      <path d="M48 53 L46 58" stroke="#1E293B" strokeWidth="0.8" />
      <path d="M52 53 L54 58" stroke="#1E293B" strokeWidth="0.8" />
      {/* 道袍 */}
      <path d="M36 56 L50 52 L64 56 L68 78 L32 78 Z" fill="#06B6D4" stroke="#1E293B" strokeWidth="1.5" />
      {/* 算盘 */}
      <rect x="28" y="62" width="14" height="10" rx="1" fill="#FEF3C7" stroke="#1E293B" strokeWidth="1" />
      <line x1="28" y1="67" x2="42" y2="67" stroke="#1E293B" strokeWidth="0.8" />
      <circle cx="31" cy="65" r="1" fill="#06B6D4" />
      <circle cx="35" cy="65" r="1" fill="#06B6D4" />
      <circle cx="39" cy="65" r="1" fill="#06B6D4" />
      {/* 卷轴 */}
      <rect x="60" y="58" width="6" height="16" rx="2" fill="#FEF3C7" stroke="#1E293B" strokeWidth="1" />
    </svg>
  );
}

// 10. 丹青 - 绿色 - 手持画笔和颜料
function Multimodal() {
  return (
    <svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="50" cy="50" r="48" stroke="#84CC16" strokeWidth="2" fill="#F7FEE7" />
      {/* 文人巾 */}
      <path d="M38 32 Q50 22 62 32 L60 38 L40 38 Z" fill="#1E293B" />
      <path d="M42 38 L58 38 L56 42 L44 42 Z" fill="#84CC16" />
      {/* 脸 */}
      <circle cx="50" cy="48" r="8" fill="#FEF3C7" stroke="#1E293B" strokeWidth="1.5" />
      <circle cx="47" cy="47" r="1" fill="#1E293B" />
      <circle cx="53" cy="47" r="1" fill="#1E293B" />
      <path d="M48 52 Q50 54 52 52" stroke="#1E293B" strokeWidth="1" fill="none" />
      {/* 长衫 */}
      <path d="M36 56 L50 52 L64 56 L68 78 L32 78 Z" fill="#84CC16" stroke="#1E293B" strokeWidth="1.5" />
      {/* 颜料碗 */}
      <ellipse cx="32" cy="70" rx="6" ry="4" fill="#FEF3C7" stroke="#1E293B" strokeWidth="1" />
      <ellipse cx="32" cy="70" rx="4" ry="2.5" fill="#84CC16" />
      {/* 画笔 */}
      <line x1="62" y1="58" x2="70" y2="75" stroke="#1E293B" strokeWidth="1.5" />
      <path d="M70 75 L72 80 L68 80 Z" fill="#EF4444" />
    </svg>
  );
}

// 未知
function Unknown() {
  return (
    <svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="50" cy="50" r="48" stroke="#94A3B8" strokeWidth="2" fill="#F1F5F9" />
      <text x="50" y="58" textAnchor="middle" fontSize="24" fill="#94A3B8">?</text>
    </svg>
  );
}

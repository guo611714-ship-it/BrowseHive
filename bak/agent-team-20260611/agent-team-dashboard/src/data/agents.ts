// 明朝官职 Agent 形象设计
// 每个 Agent 有独特的 emoji、配色、描述

export interface AgentProfile {
  id: string;
  name: string;           // 官职名
  emoji: string;          // 角色形象
  accent: string;         // 主题色
  description: string;    // 职责描述
  personality: string;    // 性格特点
}

export const AGENT_PROFILES: AgentProfile[] = [
  {
    id: 'xiaohuangmen',
    name: '黄门通传使',
    emoji: '🦊',
    accent: '#F97316',
    description: '信息传递，连接内外',
    personality: '机敏灵活，耳聪目明',
  },
  {
    id: 'sili_suitang',
    name: '司礼文书官',
    emoji: '🐼',
    accent: '#3B82F6',
    description: '文书处理，批阅奏章',
    personality: '严谨细致，一丝不苟',
  },
  {
    id: 'dongchang_tanshi',
    name: '东厂探子',
    emoji: '🦉',
    accent: '#6366F1',
    description: '探查搜索，搜集情报',
    personality: '神出鬼没，洞察秋毫',
  },
  {
    id: 'shangbao_dianbu',
    name: '尚宝校验官',
    emoji: '🐉',
    accent: '#10B981',
    description: '校验验证，把关质量',
    personality: '明察秋毫，不容瑕疵',
  },
  {
    id: 'neiguan_yingzao',
    name: '内官营造官',
    emoji: '🏗️',
    accent: '#F59E0B',
    description: '构建部署，营造万物',
    personality: '心灵手巧，化虚为实',
  },
  {
    id: 'liubu_liulanqi',
    name: '御前御者',
    emoji: '🐒',
    accent: '#EC4899',
    description: '浏览器操作，如臂使指',
    personality: '身手敏捷，眼观六路',
  },
  {
    id: 'hanlin',
    name: '翰林',
    emoji: '📜',
    accent: '#8B5CF6',
    description: '代码审查，字斟句酌',
    personality: '学富五车，明辨是非',
  },
  {
    id: 'zhukao',
    name: '主考',
    emoji: '🎯',
    accent: '#EF4444',
    description: '测试执行，公正严明',
    personality: '铁面无私，一视同仁',
  },
  {
    id: 'planner',
    name: '军师',
    emoji: '🧠',
    accent: '#06B6D4',
    description: '任务规划，运筹帷幄',
    personality: '深谋远虑，算无遗策',
  },
  {
    id: 'multimodal',
    name: '丹青',
    emoji: '🎨',
    accent: '#84CC16',
    description: '多模态处理，挥毫泼墨',
    personality: '才华横溢，妙笔生花',
  },
];

// 根据 agent id 获取 profile
export function getAgentProfile(agentId: string): AgentProfile {
  return AGENT_PROFILES.find((p) => p.id === agentId) || {
    id: agentId,
    name: agentId.slice(0, 8),
    emoji: '❓',
    accent: '#94A3B8',
    description: '未知身份',
    personality: '神秘莫测',
  };
}

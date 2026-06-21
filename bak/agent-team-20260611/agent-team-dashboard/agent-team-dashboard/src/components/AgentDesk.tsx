import type { AgentState } from '../types';
import { useDashboardStore } from '../stores/dashboard';
import { getAgentProfile } from '../data/agents';
import { AgentAvatar } from './AgentAvatar';

const STATUS_CONFIG = {
  idle: {
    label: '空闲',
    animation: '',
    icon: '💤',
  },
  running: {
    label: '运行中',
    animation: 'animate-breathe',
    icon: '🔄',
  },
  completed: {
    label: '完成',
    animation: 'animate-bounce-in',
    icon: '✅',
  },
  failed: {
    label: '失败',
    animation: 'animate-shake',
    icon: '❌',
  },
  waiting: {
    label: '等待',
    animation: 'animate-pulse-soft',
    icon: '⏸️',
  },
};

interface AgentDeskProps {
  agent: AgentState;
  isSelected: boolean;
  delay: number;
}

export function AgentDesk({ agent, isSelected, delay }: AgentDeskProps) {
  const selectAgent = useDashboardStore((s) => s.selectAgent);
  const config = STATUS_CONFIG[agent.status];
  const profile = getAgentProfile(agent.id);

  // 根据状态和 profile 配色生成样式
  const statusColor = {
    idle: 'bg-gray-100 border-gray-200 text-gray-500',
    running: 'bg-blue-50 border-blue-200 text-blue-600',
    completed: 'bg-green-50 border-green-200 text-green-600',
    failed: 'bg-red-50 border-red-200 text-red-600',
    waiting: 'bg-yellow-50 border-yellow-200 text-yellow-600',
  }[agent.status];

  return (
    <div
      className={`
        relative p-3 rounded-xl border-2 transition-all duration-300 cursor-pointer
        bg-white desk-shadow hover:scale-[1.02] hover:shadow-lg
        animate-slide-up stagger-${delay + 1}
        ${isSelected ? 'border-blue-500 ring-2 ring-blue-500/20' : `border-${profile.accent}/30`}
      `}
      style={{ borderColor: isSelected ? undefined : `${profile.accent}30` }}
      onClick={() => selectAgent(agent.id)}
    >
      {/* Status indicator */}
      <div
        className="absolute -top-2 -right-2 w-6 h-6 rounded-full flex items-center justify-center text-xs status-glow"
        style={{ backgroundColor: `${profile.accent}20`, color: profile.accent }}
      >
        {config.icon}
      </div>

      {/* Agent Avatar */}
      <div className={`flex justify-center mb-2 ${config.animation}`}>
        <AgentAvatar agentId={agent.id} size={80} status={agent.status} />
      </div>

      {/* Monitor */}
      <div className="flex justify-center mb-2">
        <div className="w-20 h-8 bg-gray-800 rounded-md flex items-center justify-center">
          <div className="w-18 h-6 bg-gray-700 rounded-sm flex items-center justify-center">
            {agent.currentTool ? (
              <span className="text-[7px] text-green-400 font-mono truncate px-1">{agent.currentTool}</span>
            ) : (
              <div className="w-8 h-1 bg-gray-600 rounded" />
            )}
          </div>
        </div>
      </div>

      {/* Info */}
      <div className="text-center">
        <div className="font-display text-xs font-semibold text-office-text truncate">
          {profile.name}
        </div>
        <div className="text-[10px] mt-0.5" style={{ color: profile.accent }}>
          {config.label}
        </div>
      </div>

      {/* Progress bar for running agents */}
      {agent.status === 'running' && agent.taskProgress !== undefined && (
        <div className="absolute bottom-0 left-0 right-0 h-1 bg-gray-100 rounded-b-xl overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{ width: `${agent.taskProgress}%`, backgroundColor: profile.accent }}
          />
        </div>
      )}
    </div>
  );
}

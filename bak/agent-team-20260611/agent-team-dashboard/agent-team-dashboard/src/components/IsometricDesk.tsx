// Marvis 风格等距办公桌 - 分层设计版
// 统一办公桌背景 + 角色动画视频叠加

import { useRef, useEffect } from 'react';
import type { AgentState } from '../types';
import { useDashboardStore } from '../stores/dashboard';
import { getAgentProfile } from '../data/agents';

interface IsometricDeskProps {
  agent: AgentState;
  isSelected: boolean;
}

// agent ID 到角色视频的映射
const CHARACTER_VIDEOS: Record<string, { idle: string; working: string }> = {
  xiaohuangmen: { idle: '/animations/char-xiaohuangmen-idle.mp4', working: '/animations/char-xiaohuangmen-working.mp4' },
  sili_suitang: { idle: '/animations/char-sili_suitang-idle.mp4', working: '/animations/char-xiaohuangmen-working.mp4' },
  dongchang_tanshi: { idle: '/animations/char-dongchang_tanshi-idle.mp4', working: '/animations/char-xiaohuangmen-working.mp4' },
  shangbao_dianbu: { idle: '/animations/char-shangbao_dianbu-idle.mp4', working: '/animations/char-xiaohuangmen-working.mp4' },
  neiguan_yingzao: { idle: '/animations/char-neiguan_yingzao-idle.mp4', working: '/animations/char-xiaohuangmen-working.mp4' },
  liubu_liulanqi: { idle: '/animations/char-liubu_liulanqi-idle.mp4', working: '/animations/char-xiaohuangmen-working.mp4' },
  hanlin: { idle: '/animations/char-hanlin-idle.mp4', working: '/animations/char-xiaohuangmen-working.mp4' },
  zhukao: { idle: '/animations/char-zhukao-idle.mp4', working: '/animations/char-xiaohuangmen-working.mp4' },
  planner: { idle: '/animations/char-planner-idle.mp4', working: '/animations/char-xiaohuangmen-working.mp4' },
  multimodal: { idle: '/animations/char-multimodal-idle.mp4', working: '/animations/char-xiaohuangmen-working.mp4' },
};

// 统一办公桌背景
const DESK_BACKGROUND = '/backgrounds/desk.png';

// 状态对应的视频
function getVideoForStatus(agentId: string, status: string): string {
  const videos = CHARACTER_VIDEOS[agentId];
  if (!videos) return '/animations/char-xiaohuangmen-working.mp4';

  switch (status) {
    case 'running':
      return videos.working;
    case 'completed':
      return '/animations/char-completed.mp4';
    case 'failed':
      return '/animations/char-failed.mp4';
    default:
      return videos.idle;
  }
}

export function IsometricDesk({ agent, isSelected }: IsometricDeskProps) {
  const selectAgent = useDashboardStore((s) => s.selectAgent);
  const profile = getAgentProfile(agent.id);
  const videoRef = useRef<HTMLVideoElement>(null);

  const videoSrc = getVideoForStatus(agent.id, agent.status);

  // 状态变化时切换视频
  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.load();
      videoRef.current.play().catch(() => {});
    }
  }, [videoSrc]);

  return (
    <div
      className={`
        relative cursor-pointer transition-all duration-300 group
        hover:scale-105 hover:-translate-y-1
        ${isSelected ? 'ring-2 ring-blue-500 ring-offset-4 rounded-2xl' : ''}
      `}
      onClick={() => selectAgent(agent.id)}
    >
      {/* 阴影 */}
      <div className="absolute bottom-2 left-1/2 -translate-x-1/2 w-3/4 h-4 bg-black/10 rounded-full blur-sm" />

      {/* 分层容器 */}
      <div className="relative w-full aspect-square overflow-hidden rounded-xl">
        {/* 底层：统一办公桌背景 */}
        <img
          src={DESK_BACKGROUND}
          alt=""
          className="absolute inset-0 w-full h-full object-cover"
        />

        {/* 中层：角色动画视频 */}
        <video
          ref={videoRef}
          src={videoSrc}
          className="absolute inset-0 w-full h-full object-cover mix-blend-multiply"
          loop
          muted
          playsInline
          autoPlay
          preload="auto"
        />

        {/* 顶层：状态指示灯 */}
        <div className="absolute top-2 right-2">
          {agent.status === 'running' && (
            <div className="w-3 h-3 bg-blue-500 rounded-full animate-pulse" />
          )}
          {agent.status === 'completed' && (
            <div className="w-3 h-3 bg-green-500 rounded-full" />
          )}
          {agent.status === 'failed' && (
            <div className="w-3 h-3 bg-red-500 rounded-full animate-pulse" />
          )}
        </div>

        {/* 顶层：工具名称标签 */}
        {agent.status === 'running' && agent.currentTool && (
          <div className="absolute bottom-2 left-1/2 -translate-x-1/2 bg-black/80 text-white text-[8px] px-2 py-0.5 rounded font-mono whitespace-nowrap">
            {agent.currentTool}
          </div>
        )}
      </div>

      {/* 信息标签 */}
      <div className="text-center mt-1">
        <div className="font-display text-xs font-semibold text-office-text truncate">
          {profile.name}
        </div>
        <div className="text-[10px] font-medium" style={{ color: profile.accent }}>
          {getStatusLabel(agent.status)}
        </div>
      </div>
    </div>
  );
}

function getStatusLabel(status: string): string {
  switch (status) {
    case 'running': return '运行中';
    case 'completed': return '完成';
    case 'failed': return '失败';
    case 'waiting': return '等待';
    default: return '空闲';
  }
}

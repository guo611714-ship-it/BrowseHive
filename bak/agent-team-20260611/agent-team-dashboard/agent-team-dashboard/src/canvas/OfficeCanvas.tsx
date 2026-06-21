// 办公室 Canvas - 整合所有渲染器，实现实时动画

import { useRef, useEffect, useCallback } from 'react';
import type { AgentState } from '../types';
import { useDashboardStore } from '../stores/dashboard';
import { getAgentProfile } from '../data/agents';
import { drawDesk } from './DeskRenderer';
import { drawCharacter } from './CharacterRenderer';
import { drawMonitor } from './MonitorRenderer';

interface OfficeCanvasProps {
  agents: AgentState[];
  selectedAgentId: string | null;
}

// 每个 agent 的布局位置（5x2 网格）
const GRID_POSITIONS = [
  { x: 100, y: 80 },   // 第1行第1列
  { x: 300, y: 80 },   // 第1行第2列
  { x: 500, y: 80 },   // 第1行第3列
  { x: 700, y: 80 },   // 第1行第4列
  { x: 900, y: 80 },   // 第1行第5列
  { x: 100, y: 280 },  // 第2行第1列
  { x: 300, y: 280 },  // 第2行第2列
  { x: 500, y: 280 },  // 第2行第3列
  { x: 700, y: 280 },  // 第2行第4列
  { x: 900, y: 280 },  // 第2行第5列
];

export function OfficeCanvas({ agents, selectedAgentId }: OfficeCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef(0);
  const selectAgent = useDashboardStore((s) => s.selectAgent);

  // 动画循环
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationId: number;

    const animate = () => {
      frameRef.current++;

      // 清空画布
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // 绘制背景
      ctx.fillStyle = '#F8F9FA';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // 绘制每个 agent
      agents.forEach((agent, index) => {
        if (index >= GRID_POSITIONS.length) return;

        const pos = GRID_POSITIONS[index];
        const profile = getAgentProfile(agent.id);
        const isSelected = agent.id === selectedAgentId;

        // 绘制办公桌
        drawDesk(ctx, pos.x, pos.y, 0.8);

        // 绘制显示器
        drawMonitor(ctx, {
          x: pos.x,
          y: pos.y,
          status: agent.status,
          tool: agent.currentTool,
          frame: frameRef.current,
        });

        // 绘制角色
        drawCharacter(ctx, {
          x: pos.x + 75,
          y: pos.y + 50,
          color: profile.accent,
          status: agent.status,
          frame: frameRef.current,
        });

        // 绘制选中高亮
        if (isSelected) {
          ctx.strokeStyle = '#3B82F6';
          ctx.lineWidth = 3;
          ctx.beginPath();
          ctx.roundRect(pos.x - 10, pos.y - 10, 180, 200, 10);
          ctx.stroke();
        }

        // 绘制状态指示灯
        drawStatusLight(ctx, pos.x + 160, pos.y + 60, agent.status);

        // 绘制进度条
        if (agent.status === 'running' && agent.taskProgress !== undefined) {
          drawProgressBar(ctx, pos.x + 20, pos.y + 180, 130, agent.taskProgress, profile.accent);
        }
      });

      animationId = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      cancelAnimationFrame(animationId);
    };
  }, [agents, selectedAgentId]);

  // 点击处理
  const handleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    // 检查点击了哪个 agent
    agents.forEach((agent, index) => {
      if (index >= GRID_POSITIONS.length) return;

      const pos = GRID_POSITIONS[index];
      if (x >= pos.x - 10 && x <= pos.x + 170 && y >= pos.y - 10 && y <= pos.y + 190) {
        selectAgent(agent.id);
      }
    });
  }, [agents, selectAgent]);

  return (
    <canvas
      ref={canvasRef}
      width={1000}
      height={500}
      className="w-full h-full cursor-pointer"
      onClick={handleClick}
    />
  );
}

// 绘制状态指示灯
function drawStatusLight(ctx: CanvasRenderingContext2D, x: number, y: number, status: string) {
  const color = {
    running: '#3B82F6',
    completed: '#10B981',
    failed: '#EF4444',
    waiting: '#F59E0B',
  }[status] || '#9CA3AF';

  // 外圈
  ctx.fillStyle = color;
  ctx.globalAlpha = 0.3;
  ctx.beginPath();
  ctx.arc(x, y, 8, 0, Math.PI * 2);
  ctx.fill();

  // 内圈
  ctx.globalAlpha = 1;
  ctx.beginPath();
  ctx.arc(x, y, 5, 0, Math.PI * 2);
  ctx.fill();
}

// 绘制进度条
function drawProgressBar(ctx: CanvasRenderingContext2D, x: number, y: number, width: number, progress: number, color: string) {
  // 背景
  ctx.fillStyle = '#E5E7EB';
  ctx.beginPath();
  ctx.roundRect(x, y, width, 4, 2);
  ctx.fill();

  // 进度
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.roundRect(x, y, width * (progress / 100), 4, 2);
  ctx.fill();
}

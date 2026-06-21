// Marvis 风格 Canvas - 完全重写，更精致的等距办公室

import { useRef, useEffect, useCallback } from 'react';
import type { AgentState } from '../types';
import { useDashboardStore } from '../stores/dashboard';
import { getAgentProfile } from '../data/agents';

interface MarvisCanvasProps {
  agents: AgentState[];
  selectedAgentId: string | null;
}

// 5x2 网格布局
const GRID = {
  cols: 5,
  rows: 2,
  deskWidth: 160,
  deskHeight: 180,
  gapX: 40,
  gapY: 60,
  offsetX: 60,
  offsetY: 40,
};

export function MarvisCanvas({ agents, selectedAgentId }: MarvisCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef(0);
  const selectAgent = useDashboardStore((s) => s.selectAgent);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationId: number;

    const animate = () => {
      frameRef.current++;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // 背景
      ctx.fillStyle = '#FAFBFC';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // 绘制每个 agent
      agents.forEach((agent, index) => {
        if (index >= 10) return;

        const col = index % GRID.cols;
        const row = Math.floor(index / GRID.cols);
        const x = GRID.offsetX + col * (GRID.deskWidth + GRID.gapX);
        const y = GRID.offsetY + row * (GRID.deskHeight + GRID.gapY);

        const profile = getAgentProfile(agent.id);
        const isSelected = agent.id === selectedAgentId;

        drawFullDesk(ctx, x, y, agent, profile.accent, isSelected, frameRef.current);
      });

      animationId = requestAnimationFrame(animate);
    };

    animate();
    return () => cancelAnimationFrame(animationId);
  }, [agents, selectedAgentId]);

  const handleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const x = (e.clientX - rect.left) * scaleX;
    const y = (e.clientY - rect.top) * scaleY;

    agents.forEach((agent, index) => {
      if (index >= 10) return;
      const col = index % GRID.cols;
      const row = Math.floor(index / GRID.cols);
      const dx = GRID.offsetX + col * (GRID.deskWidth + GRID.gapX);
      const dy = GRID.offsetY + row * (GRID.deskHeight + GRID.gapY);

      if (x >= dx && x <= dx + GRID.deskWidth && y >= dy && y <= dy + GRID.deskHeight) {
        selectAgent(agent.id);
      }
    });
  }, [agents, selectAgent]);

  return (
    <canvas
      ref={canvasRef}
      width={960}
      height={500}
      className="w-full h-full cursor-pointer"
      onClick={handleClick}
    />
  );
}

// 绘制完整的办公桌场景
function drawFullDesk(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  agent: AgentState,
  color: string,
  isSelected: boolean,
  frame: number
) {
  ctx.save();
  ctx.translate(x, y);

  // 选中高亮
  if (isSelected) {
    ctx.shadowColor = '#3B82F6';
    ctx.shadowBlur = 20;
    ctx.fillStyle = 'rgba(59, 130, 246, 0.1)';
    ctx.beginPath();
    ctx.roundRect(-5, -5, GRID.deskWidth + 10, GRID.deskHeight + 10, 12);
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  // 阴影
  ctx.fillStyle = 'rgba(0, 0, 0, 0.05)';
  ctx.beginPath();
  ctx.ellipse(80, 170, 60, 10, 0, 0, Math.PI * 2);
  ctx.fill();

  // 桌腿
  ctx.fillStyle = '#D1D5DB';
  ctx.fillRect(20, 130, 5, 35);
  ctx.fillRect(135, 130, 5, 35);

  // 桌面
  const deskGrad = ctx.createLinearGradient(10, 120, 10, 132);
  deskGrad.addColorStop(0, '#FFFFFF');
  deskGrad.addColorStop(1, '#F3F4F6');
  ctx.fillStyle = deskGrad;
  ctx.beginPath();
  ctx.roundRect(10, 120, 140, 12, 3);
  ctx.fill();
  ctx.strokeStyle = '#E5E7EB';
  ctx.lineWidth = 0.5;
  ctx.stroke();

  // 显示器支架
  ctx.fillStyle = '#9CA3AF';
  ctx.fillRect(72, 90, 16, 30);

  // 显示器
  ctx.fillStyle = '#111827';
  ctx.beginPath();
  ctx.roundRect(40, 55, 80, 38, 4);
  ctx.fill();

  // 屏幕
  drawScreen(ctx, agent.status, agent.currentTool, frame);

  // 椅子
  ctx.fillStyle = '#6B7280';
  ctx.beginPath();
  ctx.roundRect(55, 140, 50, 10, 3);
  ctx.fill();
  ctx.fillStyle = '#9CA3AF';
  ctx.beginPath();
  ctx.ellipse(80, 155, 30, 6, 0, 0, Math.PI * 2);
  ctx.fill();

  // 角色
  drawCharacter(ctx, 80, 100, color, agent.status, frame);

  // 状态灯
  drawStatusDot(ctx, 145, 60, agent.status, frame);

  // 进度条
  if (agent.status === 'running' && agent.taskProgress !== undefined) {
    drawProgress(ctx, 20, 165, 120, agent.taskProgress, color);
  }

  ctx.restore();
}

// 绘制屏幕内容
function drawScreen(ctx: CanvasRenderingContext2D, status: string, tool: string | undefined, frame: number) {
  ctx.save();
  ctx.beginPath();
  ctx.roundRect(44, 59, 72, 30, 2);
  ctx.clip();

  // 屏幕背景
  const bgColor = {
    running: '#1E3A5F',
    completed: '#1E3A2E',
    failed: '#3A1E1E',
    waiting: '#3A351E',
  }[status] || '#0F172A';
  ctx.fillStyle = bgColor;
  ctx.fillRect(44, 59, 72, 30);

  switch (status) {
    case 'running':
      drawRunningScreen(ctx, tool, frame);
      break;
    case 'completed':
      drawCompletedScreen(ctx, frame);
      break;
    case 'failed':
      drawFailedScreen(ctx, frame);
      break;
    default:
      drawIdleScreen(ctx, frame);
      break;
  }

  ctx.restore();
}

function drawRunningScreen(ctx: CanvasRenderingContext2D, tool: string | undefined, frame: number) {
  // 代码行
  ctx.fillStyle = '#60A5FA';
  ctx.font = '5px monospace';
  const lines = ['fn main() {', '  let x = 1;', '  println!(x);', '}'];
  lines.forEach((line, i) => {
    const alpha = 0.5 + Math.sin(frame * 0.1 + i) * 0.3;
    ctx.globalAlpha = alpha;
    ctx.fillText(line, 48, 68 + i * 6);
  });
  ctx.globalAlpha = 1;

  // 光标
  if (frame % 20 < 10) {
    ctx.fillStyle = '#60A5FA';
    ctx.fillRect(48 + (frame % 60), 64, 1, 6);
  }
}

function drawCompletedScreen(ctx: CanvasRenderingContext2D, frame: number) {
  ctx.fillStyle = '#34D399';
  ctx.font = 'bold 14px sans-serif';
  ctx.fillText('✓', 74, 80);
}

function drawFailedScreen(ctx: CanvasRenderingContext2D, frame: number) {
  const shake = Math.sin(frame * 0.8) * 1;
  ctx.fillStyle = '#F87171';
  ctx.font = 'bold 12px sans-serif';
  ctx.fillText('✗', 74 + shake, 80);
}

function drawIdleScreen(ctx: CanvasRenderingContext2D, frame: number) {
  // 像素游戏 - 贪吃蛇
  ctx.fillStyle = '#4ADE80';
  const snakeX = 50 + (frame % 50);
  ctx.fillRect(snakeX, 70, 4, 4);
  ctx.fillRect(snakeX - 4, 70, 4, 4);
  ctx.fillRect(snakeX - 8, 70, 4, 4);

  // 食物
  ctx.fillStyle = '#F87171';
  ctx.fillRect(90, 70, 3, 3);
}

// 绘制角色
function drawCharacter(ctx: CanvasRenderingContext2D, x: number, y: number, color: string, status: string, frame: number) {
  ctx.save();
  ctx.translate(x, y);

  const breathe = Math.sin(frame * 0.05) * 1;
  const typing = status === 'running' ? Math.sin(frame * 0.3) * 2 : 0;

  // 身体
  ctx.fillStyle = '#111827';
  ctx.beginPath();
  ctx.ellipse(0, 15 + breathe, 14, 18, 0, 0, Math.PI * 2);
  ctx.fill();

  // 手臂
  if (status === 'running') {
    ctx.fillStyle = '#111827';
    ctx.beginPath();
    ctx.ellipse(-16, 12 + typing, 6, 4, -0.3, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.ellipse(16, 12 - typing, 6, 4, 0.3, 0, Math.PI * 2);
    ctx.fill();
  }

  // 头
  ctx.fillStyle = '#111827';
  ctx.beginPath();
  ctx.arc(0, -8, 12, 0, Math.PI * 2);
  ctx.fill();

  // 眼睛
  const blink = frame % 80 > 75;
  if (blink) {
    ctx.strokeStyle = '#FFFFFF';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(-5, -10);
    ctx.lineTo(-2, -10);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(2, -10);
    ctx.lineTo(5, -10);
    ctx.stroke();
  } else {
    ctx.fillStyle = '#FFFFFF';
    ctx.beginPath();
    ctx.arc(-3, -10, 1.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(3, -10, 1.5, 0, Math.PI * 2);
    ctx.fill();
  }

  // 官帽
  ctx.fillStyle = '#111827';
  ctx.beginPath();
  ctx.moveTo(-10, -18);
  ctx.lineTo(0, -25);
  ctx.lineTo(10, -18);
  ctx.closePath();
  ctx.fill();
  ctx.fillRect(-14, -20, 8, 3);
  ctx.fillRect(6, -20, 8, 3);

  // 帽顶装饰
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(0, -22, 2.5, 0, Math.PI * 2);
  ctx.fill();

  // 领巾
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(-5, 5);
  ctx.lineTo(0, 12);
  ctx.lineTo(5, 5);
  ctx.closePath();
  ctx.fill();

  ctx.restore();
}

// 状态灯
function drawStatusDot(ctx: CanvasRenderingContext2D, x: number, y: number, status: string, frame: number) {
  const colors: Record<string, string> = {
    running: '#3B82F6',
    completed: '#10B981',
    failed: '#EF4444',
    waiting: '#F59E0B',
  };
  const color = colors[status] || '#9CA3AF';

  ctx.fillStyle = color;
  ctx.globalAlpha = 0.3;
  ctx.beginPath();
  ctx.arc(x, y, 6, 0, Math.PI * 2);
  ctx.fill();

  ctx.globalAlpha = status === 'running' ? 0.7 + Math.sin(frame * 0.1) * 0.3 : 1;
  ctx.beginPath();
  ctx.arc(x, y, 3.5, 0, Math.PI * 2);
  ctx.fill();
  ctx.globalAlpha = 1;
}

// 进度条
function drawProgress(ctx: CanvasRenderingContext2D, x: number, y: number, width: number, progress: number, color: string) {
  ctx.fillStyle = '#E5E7EB';
  ctx.beginPath();
  ctx.roundRect(x, y, width, 3, 1.5);
  ctx.fill();

  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.roundRect(x, y, width * (progress / 100), 3, 1.5);
  ctx.fill();
}

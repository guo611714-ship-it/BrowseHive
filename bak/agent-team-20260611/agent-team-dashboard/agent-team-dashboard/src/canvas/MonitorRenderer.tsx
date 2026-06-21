// 显示器绘制器 - 绘制显示器内容

interface MonitorProps {
  x: number;
  y: number;
  status: 'idle' | 'running' | 'completed' | 'failed' | 'waiting';
  tool?: string;
  frame: number;
}

export function drawMonitor(ctx: CanvasRenderingContext2D, props: MonitorProps) {
  const { x, y, status, tool, frame } = props;

  ctx.save();
  ctx.translate(x, y);

  // 显示器屏幕背景
  const screenColor = getScreenColor(status);
  ctx.fillStyle = screenColor;
  ctx.beginPath();
  ctx.roundRect(59, 74, 82, 32, 3);
  ctx.fill();

  // 屏幕内容
  drawScreenContent(ctx, status, tool, frame);

  ctx.restore();
}

function getScreenColor(status: string): string {
  switch (status) {
    case 'running': return '#DBEAFE';
    case 'completed': return '#D1FAE5';
    case 'failed': return '#FEE2E2';
    case 'waiting': return '#FEF3C7';
    default: return '#1E293B';
  }
}

function drawScreenContent(ctx: CanvasRenderingContext2D, status: string, tool: string | undefined, frame: number) {
  ctx.save();

  switch (status) {
    case 'running':
      // 打字动画 - 代码滚动
      drawCodeAnimation(ctx, tool, frame);
      break;
    case 'completed':
      // 完成 - 绿色对勾
      drawCheckmark(ctx, frame);
      break;
    case 'failed':
      // 失败 - 红色错误
      drawError(ctx, frame);
      break;
    case 'waiting':
      // 等待 - 加载动画
      drawLoading(ctx, frame);
      break;
    default:
      // 空闲 - 像素游戏
      drawPixelGame(ctx, frame);
      break;
  }

  ctx.restore();
}

function drawCodeAnimation(ctx: CanvasRenderingContext2D, tool: string | undefined, frame: number) {
  ctx.fillStyle = '#3B82F6';
  ctx.font = '8px monospace';

  // 工具名
  if (tool) {
    ctx.fillText(tool.slice(0, 10), 65, 88);
  }

  // 代码行
  const lines = ['const x = 1;', 'function() {}', 'return obj;', 'import React;'];
  lines.forEach((line, i) => {
    const y = 92 + i * 4;
    const offset = (frame * 0.5 + i * 10) % 100;
    ctx.fillStyle = `rgba(59, 130, 246, ${0.3 + Math.sin(offset * 0.1) * 0.2})`;
    ctx.fillText(line.slice(0, 12), 65, y);
  });

  // 光标闪烁
  if (frame % 20 < 10) {
    ctx.fillStyle = '#3B82F6';
    ctx.fillRect(65 + (frame % 80), 82, 1, 8);
  }
}

function drawCheckmark(ctx: CanvasRenderingContext2D, frame: number) {
  const scale = Math.min(1, frame * 0.1);
  ctx.save();
  ctx.translate(100, 90);
  ctx.scale(scale, scale);

  ctx.strokeStyle = '#10B981';
  ctx.lineWidth = 3;
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(-8, 0);
  ctx.lineTo(-2, 6);
  ctx.lineTo(8, -6);
  ctx.stroke();

  ctx.restore();
}

function drawError(ctx: CanvasRenderingContext2D, frame: number) {
  const shake = Math.sin(frame * 0.5) * 2;
  ctx.save();
  ctx.translate(shake, 0);

  ctx.strokeStyle = '#EF4444';
  ctx.lineWidth = 3;
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(-6, -6);
  ctx.lineTo(6, 6);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(6, -6);
  ctx.lineTo(-6, 6);
  ctx.stroke();

  ctx.restore();
}

function drawLoading(ctx: CanvasRenderingContext2D, frame: number) {
  ctx.fillStyle = '#F59E0B';
  for (let i = 0; i < 3; i++) {
    const alpha = ((frame + i * 10) % 30) / 30;
    ctx.globalAlpha = 0.3 + alpha * 0.7;
    ctx.beginPath();
    ctx.arc(85 + i * 10, 90, 3, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

function drawPixelGame(ctx: CanvasRenderingContext2D, frame: number) {
  // 简单的像素游戏动画
  ctx.fillStyle = '#374151';
  ctx.font = '6px monospace';
  ctx.fillText('TETRIS', 80, 85);

  // 方块下落
  const blockY = (frame * 2) % 30;
  ctx.fillStyle = '#3B82F6';
  ctx.fillRect(90, 80 + blockY, 6, 6);
  ctx.fillStyle = '#10B981';
  ctx.fillRect(82, 80 + blockY, 6, 6);
  ctx.fillStyle = '#F59E0B';
  ctx.fillRect(98, 80 + blockY, 6, 6);
}

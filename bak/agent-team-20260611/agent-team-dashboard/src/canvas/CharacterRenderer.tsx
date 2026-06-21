// 角色绘制器 - 绘制黑色剪影角色

interface CharacterProps {
  x: number;
  y: number;
  color: string;
  status: 'idle' | 'running' | 'completed' | 'failed' | 'waiting';
  frame: number;
}

export function drawCharacter(ctx: CanvasRenderingContext2D, props: CharacterProps) {
  const { x, y, color, status, frame } = props;

  ctx.save();
  ctx.translate(x, y);

  // 根据状态调整动画
  const bodyOffset = status === 'running' ? Math.sin(frame * 0.3) * 2 : 0;
  const headTilt = status === 'running' ? Math.sin(frame * 0.2) * 0.05 : 0;

  // 椅子
  ctx.fillStyle = '#6B7280';
  ctx.beginPath();
  ctx.roundRect(-15, 48, 30, 12, 4);
  ctx.fill();

  // 身体
  ctx.fillStyle = '#1F2937';
  ctx.beginPath();
  ctx.ellipse(0, 28 + bodyOffset, 20, 25, 0, 0, Math.PI * 2);
  ctx.fill();

  // 手臂（打字动画）
  if (status === 'running') {
    const armY = Math.sin(frame * 0.5) * 3;
    ctx.fillStyle = '#1F2937';
    ctx.beginPath();
    ctx.ellipse(-25, 25 + armY, 8, 5, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.ellipse(25, 25 - armY, 8, 5, 0, 0, Math.PI * 2);
    ctx.fill();
  }

  // 头
  ctx.save();
  ctx.rotate(headTilt);
  ctx.fillStyle = '#1F2937';
  ctx.beginPath();
  ctx.arc(0, -5, 16, 0, Math.PI * 2);
  ctx.fill();

  // 眼睛
  const blinkFrame = frame % 60;
  const isBlinking = blinkFrame > 55;

  if (isBlinking) {
    // 眨眼
    ctx.strokeStyle = '#FFFFFF';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(-6, -8);
    ctx.lineTo(-2, -8);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(2, -8);
    ctx.lineTo(6, -8);
    ctx.stroke();
  } else {
    // 正常眼睛
    ctx.fillStyle = '#FFFFFF';
    ctx.beginPath();
    ctx.arc(-4, -8, 2, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(4, -8, 2, 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.restore();

  // 官帽/装饰
  drawAccessory(ctx, color, status, frame);

  // 领巾
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(-8, 15);
  ctx.lineTo(0, 25);
  ctx.lineTo(8, 15);
  ctx.closePath();
  ctx.fill();

  ctx.restore();
}

function drawAccessory(ctx: CanvasRenderingContext2D, color: string, status: string, frame: number) {
  // 官帽
  ctx.fillStyle = '#1F2937';
  ctx.beginPath();
  ctx.moveTo(-12, -20);
  ctx.lineTo(0, -28);
  ctx.lineTo(12, -20);
  ctx.closePath();
  ctx.fill();

  // 帽翅
  ctx.fillRect(-18, -22, 8, 4);
  ctx.fillRect(10, -22, 8, 4);

  // 帽顶装饰
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(0, -25, 3, 0, Math.PI * 2);
  ctx.fill();
}

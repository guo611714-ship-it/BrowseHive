// 办公桌绘制器 - 绘制统一的等距办公桌

export function drawDesk(ctx: CanvasRenderingContext2D, x: number, y: number, scale: number = 1) {
  ctx.save();
  ctx.translate(x, y);
  ctx.scale(scale, scale);

  // 桌腿
  ctx.fillStyle = '#D1D5DB';
  ctx.fillRect(35, 145, 6, 35);
  ctx.fillRect(159, 145, 6, 35);

  // 桌腿横梁
  ctx.fillStyle = '#E5E7EB';
  ctx.fillRect(35, 145, 130, 4);

  // 桌面
  const deskGradient = ctx.createLinearGradient(25, 135, 25, 147);
  deskGradient.addColorStop(0, '#F9FAFB');
  deskGradient.addColorStop(1, '#F3F4F6');
  ctx.fillStyle = deskGradient;
  ctx.beginPath();
  ctx.roundRect(25, 135, 150, 12, 3);
  ctx.fill();

  // 桌面边框
  ctx.strokeStyle = '#E5E7EB';
  ctx.lineWidth = 1;
  ctx.stroke();

  // 显示器支架
  ctx.fillStyle = '#9CA3AF';
  ctx.fillRect(92, 105, 16, 30);

  // 显示器外框
  ctx.fillStyle = '#1F2937';
  ctx.beginPath();
  ctx.roundRect(55, 70, 90, 40, 5);
  ctx.fill();

  // 椅子
  ctx.fillStyle = '#9CA3AF';
  ctx.beginPath();
  ctx.ellipse(100, 160, 28, 8, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = '#6B7280';
  ctx.beginPath();
  ctx.roundRect(85, 148, 30, 12, 4);
  ctx.fill();

  ctx.restore();
}

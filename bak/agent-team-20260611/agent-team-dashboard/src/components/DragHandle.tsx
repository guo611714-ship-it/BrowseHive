interface DragHandleProps {
  onDrag: (delta: number) => void;
  direction?: 'left' | 'right';
}

export function DragHandle({ onDrag, direction = 'right' }: DragHandleProps) {
  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;

    const handleMouseMove = (e: MouseEvent) => {
      const delta = direction === 'right' ? e.clientX - startX : startX - e.clientX;
      onDrag(delta);
    };

    const handleMouseUp = () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  return (
    <div
      className="w-1 hover:w-1.5 bg-gray-200 hover:bg-blue-400 cursor-col-resize transition-all flex-shrink-0"
      onMouseDown={handleMouseDown}
    />
  );
}

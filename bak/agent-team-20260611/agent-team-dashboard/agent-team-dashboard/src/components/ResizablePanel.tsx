import { ReactNode } from 'react';
import { DragHandle } from './DragHandle';

interface ResizablePanelProps {
  children: ReactNode;
  width: number;
  collapsed: boolean;
  onWidthChange?: (width: number) => void;
  onToggleCollapse: () => void;
  dragDirection?: 'left' | 'right';
  minWidth?: number;
  maxWidth?: number;
  collapseIcon?: string;
  expandIcon?: string;
}

export function ResizablePanel({
  children,
  width,
  collapsed,
  onWidthChange,
  onToggleCollapse,
  dragDirection = 'right',
  minWidth = 200,
  maxWidth = 400,
  collapseIcon = '◀',
  expandIcon = '▶',
}: ResizablePanelProps) {
  if (collapsed) {
    return (
      <div className="flex flex-col items-center w-12 bg-white border-r border-office-border">
        <button
          onClick={onToggleCollapse}
          className="w-full h-12 flex items-center justify-center text-office-muted hover:bg-office-bg transition-colors"
          title="展开面板"
        >
          {expandIcon}
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-full bg-white">
      <div style={{ width }} className="flex flex-col border-r border-office-border overflow-hidden">
        {/* 折叠按钮 */}
        <div className="h-8 flex items-center justify-end px-2 border-b border-office-border">
          <button
            onClick={onToggleCollapse}
            className="w-6 h-6 flex items-center justify-center text-office-muted hover:bg-office-bg rounded transition-colors text-xs"
            title="收起面板"
          >
            {collapseIcon}
          </button>
        </div>
        {/* 内容 */}
        <div className="flex-1 overflow-auto">
          {children}
        </div>
      </div>
      {/* 拖拽手柄 */}
      {onWidthChange && (
        <DragHandle
          direction={dragDirection}
          onDrag={(delta) => {
            const newWidth = width + delta;
            onWidthChange(Math.max(minWidth, Math.min(maxWidth, newWidth)));
          }}
        />
      )}
    </div>
  );
}

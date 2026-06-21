import { ReactNode } from 'react';

interface CollapsibleHeaderProps {
  children: ReactNode;
  collapsed: boolean;
  onToggle: () => void;
}

export function CollapsibleHeader({ children, collapsed, onToggle }: CollapsibleHeaderProps) {
  if (collapsed) {
    return (
      <div
        className="h-1 bg-transparent hover:h-2 hover:bg-gray-200 cursor-pointer transition-all"
        onMouseEnter={(e) => {
          e.currentTarget.style.height = '48px';
          e.currentTarget.style.opacity = '1';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.height = '4px';
          e.currentTarget.style.opacity = '0.5';
        }}
        onClick={onToggle}
        title="显示 Header"
      />
    );
  }

  return (
    <header
      className="h-12 px-4 md:px-6 flex items-center justify-between border-b border-office-border bg-white/80 backdrop-blur-sm cursor-pointer select-none"
      onDoubleClick={onToggle}
    >
      {children}
    </header>
  );
}

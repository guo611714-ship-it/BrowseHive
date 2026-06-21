import { useDashboardStore } from '../stores/dashboard';
import { useMemo } from 'react';

interface StatsOverviewProps {
  compact?: boolean;
}

export function StatsOverview({ compact = false }: StatsOverviewProps) {
  const tasks = useDashboardStore((s) => s.tasks);

  const stats = useMemo(() => ({
    total: tasks.length,
    running: tasks.filter((t) => t.status === 'running').length,
    completed: tasks.filter((t) => t.status === 'completed').length,
    failed: tasks.filter((t) => t.status === 'failed').length,
  }), [tasks]);

  const items = [
    { label: '总任务', value: stats.total, color: 'text-office-text' },
    { label: '运行中', value: stats.running, color: 'text-agent-running' },
    { label: '已完成', value: stats.completed, color: 'text-agent-complete' },
    { label: '失败', value: stats.failed, color: 'text-agent-failed' },
  ];

  if (compact) {
    return (
      <div className="flex items-center gap-4 px-2">
        {items.map((item) => (
          <div key={item.label} className="flex items-center gap-1.5">
            <span className={`font-display text-sm font-bold ${item.color}`}>{item.value}</span>
            <span className="text-[10px] text-office-muted">{item.label}</span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="p-4 border-b border-office-border">
      <h2 className="font-display text-sm font-semibold text-office-muted mb-3 uppercase tracking-wider">
        任务概览
      </h2>
      <div className="grid grid-cols-2 gap-3">
        {items.map((item) => (
          <div
            key={item.label}
            className="bg-office-bg rounded-lg p-3 text-center"
          >
            <div className={`font-display text-2xl font-bold ${item.color}`}>
              {item.value}
            </div>
            <div className="text-xs text-office-muted mt-1">{item.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

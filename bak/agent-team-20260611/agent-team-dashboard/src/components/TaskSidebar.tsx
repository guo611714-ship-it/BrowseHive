import { useState } from 'react';
import { useDashboardStore } from '../stores/dashboard';
import type { Task } from '../types';

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-agent-waiting',
  running: 'bg-agent-running',
  completed: 'bg-agent-complete',
  failed: 'bg-agent-failed',
};

const STATUS_LABELS: Record<string, string> = {
  pending: '等待中',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
};

export function TaskSidebar() {
  const { tasks, selectAgent } = useDashboardStore();
  const [filter, setFilter] = useState<string>('all');
  const [search, setSearch] = useState('');

  const filtered = tasks.filter((t) => {
    if (filter !== 'all' && t.status !== filter) return false;
    if (search && !t.description.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-office-border">
        <h2 className="font-display text-sm font-semibold text-office-muted mb-3 uppercase tracking-wider">
          任务列表
        </h2>

        {/* Search */}
        <input
          type="text"
          placeholder="搜索任务..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full px-3 py-2 text-sm border border-office-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 bg-office-bg"
        />

        {/* Filter tabs */}
        <div className="flex gap-1 mt-3">
          {['all', 'running', 'completed', 'failed'].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-2 py-1 text-xs rounded-md transition-colors ${
                filter === f
                  ? 'bg-office-text text-white'
                  : 'bg-office-bg text-office-muted hover:bg-gray-200'
              }`}
            >
              {f === 'all' ? '全部' : STATUS_LABELS[f]}
            </button>
          ))}
        </div>
      </div>

      {/* Task list */}
      <div className="flex-1 overflow-auto p-2">
        {filtered.length === 0 ? (
          <div className="text-center text-office-muted text-sm py-8">
            暂无任务
          </div>
        ) : (
          <div className="space-y-2">
            {filtered.map((task) => (
              <TaskItem key={task.id} task={task} onSelect={selectAgent} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function TaskItem({ task, onSelect }: { task: Task; onSelect: (agentId: string) => void }) {
  return (
    <div
      className="p-3 rounded-lg border border-office-border bg-white hover:border-gray-300 transition-colors cursor-pointer"
      onClick={() => task.agentId && onSelect(task.agentId)}
    >
      <div className="flex items-start gap-2">
        <div className={`w-2 h-2 rounded-full mt-1.5 ${STATUS_COLORS[task.status]}`} />
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-office-text truncate">
            {task.description}
          </div>
          <div className="text-xs text-office-muted mt-1">
            {STATUS_LABELS[task.status]}
            {task.agentId && ` · ${task.agentId.slice(0, 8)}`}
          </div>
        </div>
      </div>

      {/* Progress bar */}
      {task.progress !== undefined && task.status === 'running' && (
        <div className="mt-2 h-1 bg-office-bg rounded-full overflow-hidden">
          <div
            className="h-full bg-agent-running rounded-full transition-all duration-500"
            style={{ width: `${task.progress}%` }}
          />
        </div>
      )}
    </div>
  );
}

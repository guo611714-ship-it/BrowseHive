import { useEffect, useRef } from 'react';
import { useDashboardStore } from '../stores/dashboard';

const LEVEL_COLORS: Record<string, string> = {
  info: 'text-office-muted',
  warn: 'text-agent-waiting',
  error: 'text-agent-failed',
};

const LEVEL_LABELS: Record<string, string> = {
  info: 'INFO',
  warn: 'WARN',
  error: 'ERRO',
};

export function LogStream() {
  const { logs } = useDashboardStore();
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs.length]);

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-office-border">
        <h2 className="font-display text-sm font-semibold text-office-muted uppercase tracking-wider">
          实时日志
        </h2>
      </div>

      {/* Log entries */}
      <div ref={scrollRef} className="flex-1 overflow-auto p-3 font-mono text-xs">
        {logs.length === 0 ? (
          <div className="text-center text-office-muted py-8">暂无日志</div>
        ) : (
          <div className="space-y-1">
            {logs.map((entry) => (
              <LogEntry key={entry.id} entry={entry} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function LogEntry({ entry }: { entry: { timestamp: number; level: string; agentId?: string; message: string } }) {
  const time = new Date(entry.timestamp).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });

  return (
    <div className="flex items-start gap-2 py-0.5 hover:bg-office-bg rounded">
      <span className="text-office-muted shrink-0">{time}</span>
      <span className={`shrink-0 font-semibold ${LEVEL_COLORS[entry.level]}`}>
        [{LEVEL_LABELS[entry.level]}]
      </span>
      {entry.agentId && (
        <span className="text-blue-500 shrink-0">{entry.agentId.slice(0, 6)}</span>
      )}
      <span className="text-office-text break-all">{entry.message}</span>
    </div>
  );
}

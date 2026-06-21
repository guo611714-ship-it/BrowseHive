import type { AgentState } from '../types';
import { useDashboardStore } from '../stores/dashboard';

export function ToolPanel({ agent }: { agent: AgentState }) {
  const { selectAgent } = useDashboardStore();

  return (
    <div className="h-48 border-t border-office-border bg-white flex flex-col animate-slide-up">
      {/* Header */}
      <div className="px-4 py-2 border-b border-office-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg">{agent.avatar}</span>
          <span className="font-display text-sm font-semibold">{agent.name}</span>
          <span className="text-xs text-office-muted">
            · {agent.taskDescription || '无任务'}
          </span>
        </div>
        <button
          onClick={() => selectAgent(null)}
          className="text-office-muted hover:text-office-text text-sm"
        >
          ✕
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Tool calls */}
        <div className="flex-1 overflow-auto p-4">
          <div className="text-xs font-semibold text-office-muted mb-2 uppercase tracking-wider">
            工具调用链
          </div>
          {agent.toolCalls.length === 0 ? (
            <div className="text-sm text-office-muted py-4 text-center">
              暂无工具调用
            </div>
          ) : (
            <div className="space-y-2">
              {agent.toolCalls.map((call) => (
                <div
                  key={call.id}
                  className="flex items-center gap-3 p-2 rounded-lg bg-office-bg"
                >
                  <div
                    className={`w-2 h-2 rounded-full ${
                      call.status === 'running'
                        ? 'bg-agent-running animate-pulse-soft'
                        : call.status === 'done'
                        ? 'bg-agent-complete'
                        : call.status === 'error'
                        ? 'bg-agent-failed'
                        : 'bg-agent-idle'
                    }`}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate">{call.name}</div>
                    {call.result && (
                      <div className="text-xs text-office-muted truncate mt-0.5">
                        {call.result.slice(0, 100)}
                      </div>
                    )}
                  </div>
                  {call.durationMs !== undefined && (
                    <div className="text-xs text-office-muted">{call.durationMs}ms</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Current tool info */}
        <div className="w-64 border-l border-office-border p-4">
          <div className="text-xs font-semibold text-office-muted mb-2 uppercase tracking-wider">
            当前工具
          </div>
          {agent.currentTool ? (
            <div className="space-y-2">
              <div className="p-3 rounded-lg bg-agent-running/10 border border-agent-running/20">
                <div className="text-sm font-mono font-medium text-agent-running">
                  {agent.currentTool}
                </div>
                <div className="text-xs text-office-muted mt-1">执行中...</div>
              </div>
            </div>
          ) : (
            <div className="text-sm text-office-muted py-4 text-center">
              无活跃工具
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

import { useEffect, useState } from 'react';
import { useDashboardStore, initMockData } from './stores/dashboard';
import { useLayoutStore } from './stores/layout';
import { StatsOverview } from './components/StatsOverview';
import { TaskSidebar } from './components/TaskSidebar';
import { MarvisCanvas } from './canvas/MarvisCanvas';
import { ToolPanel } from './components/ToolPanel';
import { LogStream } from './components/LogStream';
import { ResizablePanel } from './components/ResizablePanel';
import { CollapsibleHeader } from './components/CollapsibleHeader';
import { fetchAgentStatus, connectSSE, fetchAgents, fetchTasks } from './utils/api';

export default function App() {
  const { agents, selectedAgentId, connected, setConnected, addLog, updateAgent } = useDashboardStore();
  const {
    sidebarWidth, logWidth, sidebarCollapsed, mainCollapsed, logCollapsed, headerCollapsed,
    setSidebarWidth, setLogWidth, toggleSidebar, toggleMain, toggleLog, toggleHeader, resetLayout,
  } = useLayoutStore();
  const [useMock, setUseMock] = useState(true);

  useEffect(() => {
    fetchAgentStatus()
      .then((data) => {
        if (data.ok) {
          setUseMock(false);
          setConnected(true);
          addLog({
            id: `log-${Date.now()}`,
            timestamp: Date.now(),
            level: 'info',
            message: `已连接 Agent Team (工具数: ${data.tools})`,
          });
          const teammateCount = data.teammates || 10;
          for (let i = 0; i < teammateCount; i++) {
            const agentId = ['xiaohuangmen', 'sili_suitang', 'dongchang_tanshi', 'shangbao_dianbu', 'neiguan_yingzao', 'liubu_liulanqi', 'hanlin', 'zhukao', 'planner', 'multimodal'][i] || `agent-${i}`;
            updateAgent(agentId, { status: 'idle' });
          }
        } else {
          throw new Error('Agent Team not running');
        }
      })
      .catch(() => {
        setUseMock(true);
        initMockData();
        addLog({
          id: `log-${Date.now()}`,
          timestamp: Date.now(),
          level: 'warn',
          message: 'Agent Team 未运行，使用演示数据',
        });
      });
  }, []);

  useEffect(() => {
    if (useMock) return;

    const disconnect = connectSSE(
      'dashboard-status',
      (event, data) => {
        if (event === 'tool_progress') {
          const d = data as { status: string; tool: string; agent_id?: string };
          if (d.agent_id) {
            updateAgent(d.agent_id, {
              status: d.status === 'running' ? 'running' : 'idle',
              currentTool: d.status === 'running' ? d.tool : undefined,
            });
          }
        }
      },
      (err) => {
        console.error('SSE error:', err);
        setConnected(false);
      }
    );

    return () => disconnect();
  }, [useMock]);

  // Poll agents and tasks
  useEffect(() => {
    if (useMock) return;
    
    const abortController = new AbortController();
    
    const pollInterval = setInterval(async () => {
      try {
        const [agentData, taskData] = await Promise.all([
          fetchAgents(abortController.signal),
          fetchTasks(abortController.signal),
        ]);
        
        if (agentData.ok && agentData.agents) {
          agentData.agents.forEach((agent: any) => {
            updateAgent(agent.id, {
              status: agent.status || 'idle',
              name: agent.name,
            });
          });
        }
        
        if (taskData.ok && taskData.tasks) {
        if (taskData.ok && taskData.tasks) {
          const store = useDashboardStore.getState();
          const serverTaskIds = new Set(taskData.tasks.map((t: any) => t.id));
          // Remove tasks that no longer exist on server
          store.tasks.forEach((t: any) => {
            if (!serverTaskIds.has(t.id)) {
              store.removeTask(t.id);
            }
          });
          taskData.tasks.forEach((task: any) => {
            const existing = store.tasks.find((t: any) => t.id === task.id);
            if (!existing) {
              store.addTask({
                id: task.id,
                description: task.description,
                status: task.status,
                progress: task.progress ?? 0,
                agentId: task.agentId,
                createdAt: task.createdAt || Date.now(),
              });
            } else {
              store.updateTask(task.id, {
                status: task.status,
                progress: task.progress ?? existing.progress,
              });
            }
          });
        }
      } catch (err) {
        console.error('Poll failed:', err);
      }
    }, 2000);
    
    return () => {
      abortController.abort();
      clearInterval(pollInterval);
    };
  }, [useMock]);


  const agentList = Array.from(agents.values());
  const selectedAgent = selectedAgentId ? agents.get(selectedAgentId) : null;

  return (
    <div className="h-screen flex flex-col bg-office-bg">
      {/* Header */}
      <CollapsibleHeader collapsed={headerCollapsed} onToggle={toggleHeader}>
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 md:w-8 md:h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white font-bold text-xs md:text-sm">
            AT
          </div>
          <h1 className="font-display text-base md:text-xl font-bold text-office-text">Agent Team Dashboard</h1>
        </div>
        <div className="flex items-center gap-2 md:gap-4">
          <div className="flex items-center gap-1.5 md:gap-2 text-xs md:text-sm text-office-muted">
            <div className={`w-1.5 h-1.5 md:w-2 md:h-2 rounded-full ${connected ? 'bg-agent-complete' : 'bg-agent-failed'}`} />
            <span className="hidden sm:inline">{connected ? '已连接' : '未连接'}</span>
          </div>
          {useMock && (
            <span className="text-[10px] md:text-xs text-agent-waiting bg-agent-waiting/10 px-1.5 md:px-2 py-0.5 md:py-1 rounded">
              演示
            </span>
          )}
          <button
            onClick={resetLayout}
            className="text-xs text-office-muted hover:text-office-text px-2 py-1 rounded hover:bg-office-bg"
            title="重置布局"
          >
            ↺
          </button>
        </div>
      </CollapsibleHeader>

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
        <ResizablePanel
          width={sidebarWidth}
          collapsed={sidebarCollapsed}
          onWidthChange={setSidebarWidth}
          onToggleCollapse={toggleSidebar}
          dragDirection="right"
          collapseIcon="◀"
          expandIcon="▶"
        >
          <StatsOverview />
          <TaskSidebar />
        </ResizablePanel>

        {/* Main Area */}
        {mainCollapsed ? (
          <div className="flex flex-col items-center w-12 bg-white border-r border-office-border">
            <button
              onClick={toggleMain}
              className="w-full h-12 flex items-center justify-center text-office-muted hover:bg-office-bg transition-colors"
              title="展开主区域"
            >
              ▶
            </button>
          </div>
        ) : (
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="flex-1 p-3 md:p-6 overflow-auto">
              <div className="flex-1">
                <MarvisCanvas agents={agentList} selectedAgentId={selectedAgentId} />
              </div>
            </div>
            {selectedAgent && <ToolPanel agent={selectedAgent} />}
            {/* Main 折叠按钮 */}
            <div className="h-8 flex items-center justify-center border-t border-office-border">
              <button
                onClick={toggleMain}
                className="text-office-muted hover:text-office-text text-xs px-2 py-1 rounded hover:bg-office-bg"
                title="收起主区域"
              >
                ▼
              </button>
            </div>
          </div>
        )}

        {/* Log Panel */}
        <ResizablePanel
          width={logWidth}
          collapsed={logCollapsed}
          onWidthChange={setLogWidth}
          onToggleCollapse={toggleLog}
          dragDirection="left"
          collapseIcon="▶"
          expandIcon="◀"
        >
          <LogStream />
        </ResizablePanel>
      </div>
    </div>
  );
}

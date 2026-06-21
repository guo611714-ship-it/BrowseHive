import { create } from 'zustand';
import type { AgentState, Task, LogEntry, DashboardStats } from '../types';
import { AGENT_PROFILES } from '../data/agents';

interface DashboardState {
  agents: Map<string, AgentState>;
  tasks: Task[];
  logs: LogEntry[];
  selectedAgentId: string | null;
  connected: boolean;

  // Actions
  selectAgent: (agentId: string | null) => void;
  updateAgent: (agentId: string, update: Partial<AgentState>) => void;
  addTask: (task: Task) => void;
  updateTask: (taskId: string, update: Partial<Task>) => void;
  removeTask: (taskId: string) => void;
  addLog: (entry: LogEntry) => void;
  setConnected: (connected: boolean) => void;
  getStats: () => DashboardStats;
}

// Agent avatars - 使用明朝官职 profile
// Agent color accents - 使用 profile 中的 accent

export const useDashboardStore = create<DashboardState>((set, get) => ({
  agents: new Map(),
  tasks: [],
  logs: [],
  selectedAgentId: null,
  connected: false,

  selectAgent: (agentId) => set({ selectedAgentId: agentId }),

  updateAgent: (agentId, update) =>
    set((state) => {
      const agents = new Map(state.agents);
      const existing = agents.get(agentId);
      if (existing) {
        agents.set(agentId, { ...existing, ...update });
      } else {
        // Create new agent with profile
        const profile = AGENT_PROFILES.find((p) => p.id === agentId);
        agents.set(agentId, {
          id: agentId,
          name: profile?.name || agentId.slice(0, 8),
          avatar: profile?.emoji || '❓',
          status: 'idle',
          toolCalls: [],
          ...update,
        });
      }
      return { agents };
    }),

  addTask: (task) =>
    set((state) => ({ tasks: [task, ...state.tasks].slice(0, 100) })),

  removeTask: (taskId) =>
    set((state) => ({
      tasks: state.tasks.filter((t) => t.id !== taskId),
    })),

  updateTask: (taskId, update) =>
    set((state) => ({
      tasks: state.tasks.map((t) => (t.id === taskId ? { ...t, ...update } : t)),
    })),

  addLog: (entry) =>
    set((state) => ({
      logs: [...state.logs, entry].slice(-200),
    })),

  setConnected: (connected) => set({ connected }),

  getStats: () => {
    const tasks = get().tasks;
    return {
      total: tasks.length,
      running: tasks.filter((t) => t.status === 'running').length,
      completed: tasks.filter((t) => t.status === 'completed').length,
      failed: tasks.filter((t) => t.status === 'failed').length,
    };
  },
}));

// Initialize with mock data for demo
export function initMockData() {
  const store = useDashboardStore.getState();

  // 使用明朝官职 profile
  const mockAgents: AgentState[] = [
    { id: 'xiaohuangmen', name: '黄门通传使', avatar: '🦊', status: 'running', currentTool: 'read_file', taskDescription: '读取配置文件', toolCalls: [] },
    { id: 'sili_suitang', name: '司礼文书官', avatar: '🐼', status: 'running', currentTool: 'edit', taskDescription: '修改样式代码', toolCalls: [] },
    { id: 'dongchang_tanshi', name: '东厂探子', avatar: '🦉', status: 'completed', taskDescription: '搜索相关文件', toolCalls: [] },
    { id: 'shangbao_dianbu', name: '尚宝校验官', avatar: '🐉', status: 'idle', toolCalls: [] },
    { id: 'neiguan_yingzao', name: '内官营造官', avatar: '🏗️', status: 'waiting', taskDescription: '等待依赖任务完成', toolCalls: [] },
    { id: 'liubu_liulanqi', name: '御前御者', avatar: '🐒', status: 'failed', taskDescription: '浏览器自动化失败', toolCalls: [] },
    { id: 'hanlin', name: '翰林', avatar: '📜', status: 'idle', toolCalls: [] },
    { id: 'zhukao', name: '主考', avatar: '🎯', status: 'idle', toolCalls: [] },
    { id: 'planner', name: '军师', avatar: '🧠', status: 'idle', toolCalls: [] },
    { id: 'multimodal', name: '丹青', avatar: '🎨', status: 'idle', toolCalls: [] },
  ];

  const mockTasks: Task[] = [
    { id: 'task-1', description: '修复登录页面 bug', status: 'running', agentId: 'xiaohuangmen', progress: 60, createdAt: Date.now() - 30000 },
    { id: 'task-2', description: '更新仪表盘样式', status: 'running', agentId: 'sili_suitang', progress: 30, createdAt: Date.now() - 20000 },
    { id: 'task-3', description: '搜索文档资料', status: 'completed', agentId: 'dongchang_tanshi', progress: 100, createdAt: Date.now() - 60000, completedAt: Date.now() - 10000 },
    { id: 'task-4', description: '等待部署依赖', status: 'pending', agentId: 'neiguan_yingzao', progress: 0, createdAt: Date.now() - 5000 },
    { id: 'task-5', description: '浏览器测试', status: 'failed', agentId: 'liubu_liulanqi', progress: 45, createdAt: Date.now() - 40000 },
  ];

  mockAgents.forEach((agent) => store.updateAgent(agent.id, agent));
  mockTasks.forEach((task) => store.addTask(task));

  store.addLog({ id: 'l1', timestamp: Date.now() - 5000, level: 'info', agentId: 'xiaohuangmen', message: '开始读取配置文件...' });
  store.addLog({ id: 'l2', timestamp: Date.now() - 3000, level: 'info', agentId: 'sili_suitang', message: '正在编辑 style.css' });
  store.addLog({ id: 'l3', timestamp: Date.now() - 1000, level: 'warn', agentId: 'liubu_liulanqi', message: '浏览器连接超时，重试中...' });
  store.addLog({ id: 'l4', timestamp: Date.now(), level: 'error', agentId: 'liubu_liulanqi', message: '浏览器测试失败: element not found' });
}

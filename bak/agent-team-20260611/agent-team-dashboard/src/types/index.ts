export type AgentStatus = 'idle' | 'running' | 'completed' | 'failed' | 'waiting';

export interface AgentState {
  id: string;
  name: string;
  avatar: string;
  status: AgentStatus;
  currentTool?: string;
  taskDescription?: string;
  taskProgress?: number;
  startedAt?: number;
  toolCalls: ToolCall[];
}

export interface ToolCall {
  id: string;
  name: string;
  params: Record<string, unknown>;
  result?: string;
  status: 'pending' | 'running' | 'done' | 'error';
  durationMs?: number;
}

export interface Task {
  id: string;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  agentId?: string;
  progress?: number;
  createdAt: number;
  completedAt?: number;
}

export interface LogEntry {
  id: string;
  timestamp: number;
  level: 'info' | 'warn' | 'error';
  agentId?: string;
  message: string;
}

export interface DashboardStats {
  total: number;
  running: number;
  completed: number;
  failed: number;
}

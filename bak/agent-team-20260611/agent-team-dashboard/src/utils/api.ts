const BASE_URL = 'http://127.0.0.1:8772';

export async function fetchAgentStatus() {
  const res = await fetch(`${BASE_URL}/api/agent/status`);
  if (!res.ok) throw new Error('Failed to fetch agent status');
  return res.json();
}

export async function fetchTools() {
  const res = await fetch(`${BASE_URL}/api/tools`);
  if (!res.ok) throw new Error('Failed to fetch tools');
  return res.json();
}



export async function fetchAgents(signal?: AbortSignal) {
  const res = await fetch(`${BASE_URL}/api/agent/agents`, { signal });
  if (!res.ok) throw new Error('Failed to fetch agents');
  return res.json();
}

export async function fetchTasks(signal?: AbortSignal) {
  const res = await fetch(`${BASE_URL}/api/agent/tasks`, { signal });
  if (!res.ok) throw new Error('Failed to fetch tasks');
  return res.json();
}
export async function fetchMetrics() {
  const res = await fetch(`${BASE_URL}/api/agent/metrics`);
  if (!res.ok) throw new Error('Failed to fetch metrics');
  return res.json();
}

// 发送任务到 Agent Team
export async function sendTask(message: string) {
  const res = await fetch(`${BASE_URL}/api/agent/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error('Failed to send task');
  return res.json();
}

// SSE 流式连接
export function connectSSE(
  message: string,
  onEvent: (event: string, data: unknown) => void,
  onError?: (error: Error) => void
) {
  const controller = new AbortController();

  fetch(`${BASE_URL}/api/agent/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok) throw new Error(`SSE request failed: ${res.status}`);
      const reader = res.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        let currentEvent = 'message';
        for (const line of lines) {
          if (line.startsWith('event:')) {
            currentEvent = line.slice(6).trim();
          } else if (line.startsWith('data:')) {
            const rawData = line.slice(5).trim();
            try {
              const data = JSON.parse(rawData);
              onEvent(currentEvent, data);
            } catch {
              onEvent(currentEvent, rawData);
            }
          } else if (line === '') {
            currentEvent = 'message';
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onError?.(err);
      }
    });

  return () => controller.abort();
}

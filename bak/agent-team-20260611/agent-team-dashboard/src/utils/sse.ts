export interface SSEOptions {
  url: string;
  body?: unknown;
  onEvent?: (event: string, data: unknown) => void;
  onError?: (error: Error) => void;
  onOpen?: () => void;
  onClose?: () => void;
}

export function createSSEClient(options: SSEOptions) {
  let controller: AbortController | null = null;
  let retryTimeout: ReturnType<typeof setTimeout> | null = null;
  let retryDelay = 1000;
  const maxRetryDelay = 30000;

  async function connect() {
    controller = new AbortController();

    try {
      const res = await fetch(options.url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: options.body ? JSON.stringify(options.body) : undefined,
        signal: controller.signal,
      });

      if (!res.ok) {
        throw new Error(`SSE request failed: ${res.status}`);
      }

      options.onOpen?.();
      retryDelay = 1000; // Reset on successful connection

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
              options.onEvent?.(currentEvent, data);
            } catch {
              // Plain text data
              options.onEvent?.(currentEvent, rawData);
            }
          } else if (line === '') {
            currentEvent = 'message';
          }
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        // Intentional close
        return;
      }
      options.onError?.(err as Error);
      scheduleRetry();
    } finally {
      options.onClose?.();
    }
  }

  function scheduleRetry() {
    if (retryTimeout) return;
    retryTimeout = setTimeout(() => {
      retryTimeout = null;
      connect();
    }, retryDelay);
    retryDelay = Math.min(retryDelay * 2, maxRetryDelay);
  }

  function disconnect() {
    if (retryTimeout) {
      clearTimeout(retryTimeout);
      retryTimeout = null;
    }
    controller?.abort();
    controller = null;
  }

  return { connect, disconnect };
}

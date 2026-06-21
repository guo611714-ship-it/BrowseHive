/**
 * HTTP Adapter — bridges StreamableHTTPServerTransport to JsonRpcTransport.
 */

import {
  JsonRpcResponse,
  JsonRpcTransport,
  MessageHandler,
} from './transport';

export function createHttpAdapter(mcpTransport: any): JsonRpcTransport {
  return new HttpAdapter(mcpTransport);
}

class HttpAdapter implements JsonRpcTransport {
  private mcpTransport: any;
  private messageHandler: MessageHandler | null = null;
  private stopped = false;
  private nextRequestId = 1;
  private pendingRequests = new Map<string, { resolve: (v: any) => void; reject: (e: Error) => void }>();

  constructor(mcpTransport: any) {
    this.mcpTransport = mcpTransport;

    this.mcpTransport.onmessage = (msg: any) => {
      // Resolve pending request if msg is a response with matching id
      if (msg && msg.id != null) {
        const key = String(msg.id);
        const pending = this.pendingRequests.get(key);
        if (pending) {
          this.pendingRequests.delete(key);
          if (msg.error) {
            pending.reject(new Error(msg.error.message || 'Request failed'));
          } else {
            pending.resolve(msg.result);
          }
          return;
        }
      }
      if (this.messageHandler && !this.stopped) {
        this.messageHandler(msg).catch(() => {});
      }
    };

    this.mcpTransport.onclose = () => {
      this.stopped = true;
      for (const [, pending] of this.pendingRequests) {
        pending.reject(new Error('Transport closed'));
      }
      this.pendingRequests.clear();
    };
  }

  start(handler: MessageHandler): void {
    this.messageHandler = handler;
  }

  stop(): void {
    if (this.stopped) return;
    this.stopped = true;
    for (const [, pending] of this.pendingRequests) {
      pending.reject(new Error('Transport stopped'));
    }
    this.pendingRequests.clear();
  }

  send(response: JsonRpcResponse): void {
    if (this.stopped) return;
    this.mcpTransport.send(response).catch(() => {});
  }

  notify(method: string, params?: unknown): void {
    this.send({ jsonrpc: '2.0', method, params } as any);
  }

  request(method: string, params?: unknown, timeoutMs = 5000): Promise<unknown> {
    const id = `http-${this.nextRequestId++}`;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pendingRequests.delete(id);
        reject(new Error(`Request ${method} timed out after ${timeoutMs}ms`));
      }, timeoutMs);
      this.pendingRequests.set(id, {
        resolve: (v) => { clearTimeout(timer); resolve(v); },
        reject: (e) => { clearTimeout(timer); reject(e); },
      });
      this.send({ jsonrpc: '2.0', id, method, params } as any);
    });
  }

  sendResult(id: string | number, result: unknown): void {
    this.send({ jsonrpc: '2.0', id, result });
  }

  sendError(id: string | number | null, code: number, message: string, data?: unknown): void {
    this.send({ jsonrpc: '2.0', id, error: { code, message, data } });
  }
}

#!/usr/bin/env node
'use strict';

/**
 * NVIDIA (OpenAI format) → Anthropic format 转换代理
 *
 * 架构：Claude Code → 本代理(:8081) → Model Router(:8080) → NVIDIA API
 *
 * 功能：将 NVIDIA OpenAI 格式的响应转换为 Anthropic 格式，
 *       使 Claude Code 能正确解析第三方模型的输出。
 */

const http = require('http');
const https = require('https');

const PORT = parseInt(process.env.PROXY_PORT || '8081', 10);
const ROUTER_URL = process.env.ROUTER_URL || 'http://127.0.0.1:8080';

// ─── 格式转换 ───────────────────────────────────────────────

function stopReasonMap(finishReason) {
  const map = {
    stop: 'end_turn',
    length: 'max_tokens',
    'tool_calls': 'tool_use',
    content_filter: 'end_turn',
  };
  return map[finishReason] || 'end_turn';
}

function convertNonStreaming(oai) {
  const text = (oai.choices || []).map(c => c.message?.content || '').join('');
  const finish = oai.choices?.[0]?.finish_reason || 'stop';
  return {
    id: oai.id || `msg_${Date.now()}`,
    type: 'message',
    role: 'assistant',
    content: [{ type: 'text', text }],
    model: oai.model || 'unknown',
    stop_reason: stopReasonMap(finish),
    stop_sequence: null,
    usage: {
      input_tokens: oai.usage?.prompt_tokens || 0,
      output_tokens: oai.usage?.completion_tokens || 0,
      cache_creation_input_tokens: 0,
      cache_read_input_tokens: 0,
    },
  };
}

function wrapStreaming(oaiSseChunk) {
  try {
    const oai = JSON.parse(oaiSseChunk);
    const delta = oai.choices?.[0]?.delta;
    const finish = oai.choices?.[0]?.finish_reason;

    if (delta?.content) {
      return [
        `event: content_block_delta`,
        `data: ${JSON.stringify({
          type: 'content_block_delta',
          index: 0,
          delta: { type: 'text_delta', text: delta.content },
        })}`,
        '',
      ].join('\n');
    }

    if (finish) {
      return [
        `event: content_block_stop`,
        `data: ${JSON.stringify({ type: 'content_block_stop', index: 0 })}`,
        '',
        `event: message_delta`,
        `data: ${JSON.stringify({
          type: 'message_delta',
          delta: { stop_reason: stopReasonMap(finish), stop_sequence: null },
          usage: {
            output_tokens: oai.usage?.completion_tokens || 0,
          },
        })}`,
        '',
        `event: message_stop`,
        `data: ${JSON.stringify({ type: 'message_stop' })}`,
        '',
      ].join('\n');
    }
  } catch {
    // 非 JSON 行，原样透传
  }
  return null;
}

// ─── HTTP 代理 ──────────────────────────────────────────────

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', c => chunks.push(c));
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf-8')));
    req.on('error', reject);
  });
}

function forwardToRouter(path, headers, body) {
  const url = new URL(path, ROUTER_URL);
  const isHttps = url.protocol === 'https:';
  const client = isHttps ? https : http;

  return new Promise((resolve, reject) => {
    const opts = {
      hostname: url.hostname,
      port: url.port || (isHttps ? 443 : 80),
      path: url.pathname,
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-api-key': headers['x-api-key'] || '',
        'anthropic-version': headers['anthropic-version'] || '2023-06-01',
        'anthropic-beta': headers['anthropic-beta'] || '',
      },
    };

    const proxyReq = client.request(opts, resolve);
    proxyReq.on('error', reject);
    proxyReq.write(body);
    proxyReq.end();
  });
}

async function handleMessages(req, res) {
  const rawBody = await readBody(req);
  let parsed;
  try {
    parsed = JSON.parse(rawBody);
  } catch {
    res.writeHead(400, { 'content-type': 'application/json' });
    res.end(JSON.stringify({
      type: 'error',
      error: { type: 'invalid_request_error', message: 'Invalid JSON body' },
    }));
    return;
  }

  const wantStream = parsed.stream === true;

  try {
    const upstream = await forwardToRouter('/v1/messages', req.headers, rawBody);

    if (upstream.statusCode !== 200) {
      const errBody = await readBody(upstream);
      res.writeHead(upstream.statusCode, { 'content-type': 'application/json' });
      res.end(errBody);
      return;
    }

    if (!wantStream) {
      const oaiResp = JSON.parse(await readBody(upstream));
      const anthropicResp = convertNonStreaming(oaiResp);
      res.writeHead(200, {
        'content-type': 'application/json',
        'x-request-id': `req_${Date.now()}`,
      });
      res.end(JSON.stringify(anthropicResp));
      return;
    }

    // ── Streaming ──
    res.writeHead(200, {
      'content-type': 'text/event-stream',
      'cache-control': 'no-cache',
      'x-request-id': `req_${Date.now()}`,
    });

    // 发送 message_start（使用上游返回的 model 信息）
    let modelInfo = 'unknown';
    let inputTokens = 0;
    let started = false;

    let buffer = '';
    upstream.on('data', chunk => {
      buffer += chunk.toString('utf-8');

      // 尝试从第一个 chunk 提取 model 信息
      if (!started) {
        try {
          const preview = JSON.parse(buffer.replace(/^data: /, '').trim());
          if (preview.model) modelInfo = preview.model;
          if (preview.usage?.prompt_tokens) inputTokens = preview.usage.prompt_tokens;
        } catch {
          // 还没完整 JSON，继续收
        }
        if (buffer.includes('\n\n') || buffer.length > 200) {
          started = true;
          const msgStart = {
            type: 'message_start',
            message: {
              id: `msg_${Date.now()}`,
              type: 'message',
              role: 'assistant',
              content: [],
              model: modelInfo,
              stop_reason: null,
              stop_sequence: null,
              usage: { input_tokens: inputTokens, output_tokens: 0 },
            },
          };
          res.write(`event: message_start\ndata: ${JSON.stringify(msgStart)}\n\n`);

          // 发送 content_block_start
          const blockStart = {
            type: 'content_block_start',
            index: 0,
            content_block: { type: 'text', text: '' },
          };
          res.write(`event: content_block_start\ndata: ${JSON.stringify(blockStart)}\n\n`);
        }
        return;
      }

      // 正常 SSE 事件处理
      while (buffer.includes('\n\n')) {
        const idx = buffer.indexOf('\n\n');
        const raw = buffer.slice(0, idx).trim();
        buffer = buffer.slice(idx + 2);

        if (!raw) continue;

        // 提取 data 行
        const lines = raw.split('\n');
        let dataLine = '';
        for (const l of lines) {
          if (l.startsWith('data: ')) {
            dataLine = l.slice(6);
            break;
          }
        }
        if (!dataLine || dataLine === '[DONE]') continue;

        const anthropicEvent = wrapStreaming(dataLine);
        if (anthropicEvent) {
          res.write(anthropicEvent);
        }
      }
    });

    upstream.on('end', () => {
      // 发送 message_stop（如果没有已经发过）
      res.write(`event: message_stop\ndata: ${JSON.stringify({ type: 'message_stop' })}\n\n`);
      res.end();
    });

    upstream.on('error', err => {
      console.error('[proxy] stream error:', err.message);
      res.write(`event: error\ndata: ${JSON.stringify({
        type: 'error',
        error: { type: 'api_error', message: err.message },
      })}\n\n`);
      res.end();
    });
  } catch (err) {
    console.error('[proxy] error:', err.message);
    res.writeHead(502, { 'content-type': 'application/json' });
    res.end(JSON.stringify({
      type: 'error',
      error: { type: 'api_error', message: `Proxy error: ${err.message}` },
    }));
  }
}

// ─── 服务器 ─────────────────────────────────────────────────

const server = http.createServer(async (req, res) => {
  // CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, GET, OPTIONS');
  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  // 健康检查
  if (req.method === 'GET' && req.url === '/health') {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', proxy: 'nvidia-anthropic', port: PORT }));
    return;
  }

  // 主消息端点
  if (req.method === 'POST' && req.url === '/v1/messages') {
    await handleMessages(req, res);
    return;
  }

  // Token counting（兼容）
  if (req.method === 'POST' && req.url === '/v1/messages/count_tokens') {
    const body = await readBody(req);
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ input_tokens: 0 }));
    return;
  }

  res.writeHead(404);
  res.end('Not found');
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`[nvidia-anthropic-proxy] listening on http://127.0.0.1:${PORT}`);
  console.log(`[nvidia-anthropic-proxy] upstream: ${ROUTER_URL}`);
  console.log(`[nvidia-anthropic-proxy] conversion: OpenAI → Anthropic format`);
});

process.on('uncaughtException', err => {
  console.error('[proxy] uncaught:', err);
});

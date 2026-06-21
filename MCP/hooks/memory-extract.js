#!/usr/bin/env node
/**
 * Memory Extract Hook v2 - Stop
 * 1. 从会话中提取事实存储到ChromaDB
 * 2. 生成会话摘要
 * 3. 执行记忆衰减
 */

const { execSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');
const crypto = require('crypto');

const PYTHON = path.join(os.homedir(), '.claude', 'memory', 'venv', 'Scripts', 'python.exe');
const MEMORY_STORE = path.join(os.homedir(), '.claude', 'memory', 'scripts', 'memory_store.py');
const EXTRACT_SCRIPT = path.join(os.homedir(), '.claude', 'memory', 'scripts', 'memory_extract.py');
const SESSION_DIR = path.join(os.homedir(), '.claude', 'session-env');

function readStdin() {
  return new Promise((resolve) => {
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', chunk => data += chunk);
    process.stdin.on('end', () => resolve(data));
  });
}

function getRecentTranscript() {
  try {
    if (!fs.existsSync(SESSION_DIR)) return '';

    const dirs = fs.readdirSync(SESSION_DIR)
      .filter(d => fs.statSync(path.join(SESSION_DIR, d)).isDirectory())
      .sort()
      .reverse();

    if (dirs.length === 0) return '';

    const sessionDir = path.join(SESSION_DIR, dirs[0]);
    const jsonlFiles = fs.readdirSync(sessionDir)
      .filter(f => f.endsWith('.jsonl'))
      .sort()
      .reverse();

    if (jsonlFiles.length === 0) return '';

    const transcriptPath = path.join(sessionDir, jsonlFiles[0]);
    const content = fs.readFileSync(transcriptPath, 'utf8');
    const lines = content.split('\n').filter(l => l.trim());
    const recent = lines.slice(-80).join('\n');

    return { text: recent, sessionId: dirs[0] };
  } catch (e) {
    return null;
  }
}

function generateSummary(transcript) {
  // 从会话记录中提取关键信息生成摘要
  const lines = transcript.split('\n').filter(l => l.trim());
  const userMessages = [];
  const topics = new Set();
  const decisions = [];

  for (const line of lines) {
    try {
      const data = JSON.parse(line);
      // 提取用户消息
      if (data.type === 'human' || data.role === 'user') {
        const msg = data.content || data.message || '';
        if (msg.length > 10) {
          userMessages.push(msg.substring(0, 200));
          // 提取关键词作为主题
          const words = msg.split(/[\s,，。、]+/).filter(w => w.length > 2);
          words.slice(0, 5).forEach(w => topics.add(w));
        }
      }
      // 提取工具调用决策
      if (data.type === 'assistant' && data.content) {
        const content = typeof data.content === 'string' ? data.content : '';
        if (content.includes('Edit') || content.includes('Write') || content.includes('Bash')) {
          decisions.push(content.substring(0, 100));
        }
      }
    } catch (e) {
      // skip non-JSON lines
    }
  }

  const topicList = Array.from(topics).slice(0, 5);
  const summary = userMessages.length > 0
    ? `会话涉及${userMessages.length}个用户请求，主题包括：${topicList.join('、')}`
    : '简短会话';

  return { summary, topics: topicList, decisions: decisions.slice(0, 3) };
}

function runDecay() {
  try {
    const result = execSync(`"${PYTHON}" "${MEMORY_STORE}" decay`, {
      encoding: 'utf8',
      timeout: 10000,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
    }).trim();
    return JSON.parse(result);
  } catch (e) {
    return null;
  }
}

async function main() {
  try {
    const input = await readStdin();
    const hookData = JSON.parse(input);

    // 获取会话记录
    const transcriptData = getRecentTranscript();
    if (!transcriptData || !transcriptData.text || transcriptData.text.length < 50) {
      process.exit(0);
    }

    // 1. 提取事实
    try {
      execSync(`"${PYTHON}" "${EXTRACT_SCRIPT}" -`, {
        input: transcriptData.text,
        encoding: 'utf8',
        timeout: 60000,
        env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
      });
    } catch (e) {
      // best-effort
    }

    // 2. 生成并保存会话摘要
    try {
      const { summary, topics, decisions } = generateSummary(transcriptData.text);
      const topicsJson = JSON.stringify(topics);
      execSync(`"${PYTHON}" "${MEMORY_STORE}" save-summary "${transcriptData.sessionId}" "${summary}" '${topicsJson}'`, {
        encoding: 'utf8',
        timeout: 10000,
        env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
      });
    } catch (e) {
      // best-effort
    }

    // 3. 执行记忆衰减（每天只执行一次）
    const decayMarker = path.join(os.homedir(), '.claude', 'memory', 'data', '.last-decay');
    const now = new Date();
    const lastDecay = fs.existsSync(decayMarker)
      ? new Date(fs.readFileSync(decayMarker, 'utf8').trim())
      : new Date(0);

    if (now.toDateString() !== lastDecay.toDateString()) {
      runDecay();
      fs.writeFileSync(decayMarker, now.toISOString());
    }

    process.exit(0);
  } catch (e) {
    process.exit(0);
  }
}

main();

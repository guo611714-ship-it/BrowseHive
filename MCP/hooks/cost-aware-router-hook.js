#!/usr/bin/env node
'use strict';

/**
 * Cost-Aware MCP Router Hook
 * 基于 cost-aware-llm-pipeline 的复杂度评估逻辑
 * 在 UserPromptSubmit 时自动路由到最优模型
 */

const fs = require('fs');
const path = require('path');

// ─── 配置加载 ─────────────────────────────────────────────
const CONFIG_PATH = path.join(
  process.env.USERPROFILE || process.env.HOME,
  '.claude',
  'cost-aware-mcp-router.yaml'
);

// ─── 复杂度评估器（基于 cost-aware-llm-pipeline）─────────
const THRESHOLDS = {
  char_thresholds: {
    nvidia: 50,
    doubao: 200,
    deepseek: 1000,
    claude: 5000
  },
  keywords: {
    L1_simple: ['你好', 'hi', 'hello', '谢谢', '测试', '1+1', '翻译这句话'],
    L2_medium: ['润色', '总结', '解释', '写', '生成', '分析', '推理', '画', '整理'],
    L3_complex: ['代码', '函数', 'class', 'function', 'bug', '调试', '优化', '架构', '设计', '重构']
  }
};

function assessComplexity(prompt) {
  const p = prompt.toLowerCase();
  const charCount = prompt.length;

  // L1 简单：<20字符
  if (charCount < 20) {
    return { level: 1, model: 'nvidia', reason: '短文本', charCount };
  }

  // L3 复杂：仅代码任务（检测代码关键词）
  const codeKeywords = ['代码', '函数', 'class', 'function', 'bug', '调试', 'def ', 'import ', 'const ', 'let ', 'var '];
  const hasCode = codeKeywords.some(k => p.includes(k)) || /[{}\[\]();]/.test(prompt);
  if (hasCode) {
    return { level: 3, model: 'claude', reason: '代码任务', charCount };
  }

  // L2 中等：>50字符的非代码任务（链式处理）
  return {
    level: 2,
    model: 'chain',
    chain: ['doubao', 'deepseek', 'volcengine'],
    reason: '中等任务',
    charCount,
    pipeline: true
  };
}

// ─── 树状调用执行器 ───────────────────────────────────────
function executeTree(prompt) {
  return {
    tree: {
      layer1: { model: 'doubao', tool: 'mcp__ai-chat__ask_doubao' },
      layer2: [
        { model: 'deepseek', tool: 'mcp__ai-chat__ask_deepseek' },
        { model: 'volcengine', tool: 'mcp__ai-chat__ask_volcengine' }
      ],
      layer3: { model: 'nvidia', endpoint: 'http://127.0.0.1:8080' }
    },
    prompt: prompt,
    description: '豆包→(DeepSeek+火山引擎)→NVIDIA整合'
  };
}

// ─── 路由决策 ─────────────────────────────────────────────
function getRoute(complexity) {
  const routes = {
    1: {
      name: 'NVIDIA API',
      tool: null,
      endpoint: 'http://127.0.0.1:8080',
      savings: '100%'
    },
    2: {
      name: '树状调用（豆包→DeepSeek+火山引擎→NVIDIA整合）',
      tree: {
        layer1: { model: 'doubao', tool: 'mcp__ai-chat__ask_doubao' },
        layer2: [
          { model: 'deepseek', tool: 'mcp__ai-chat__ask_deepseek' },
          { model: 'volcengine', tool: 'mcp__ai-chat__ask_volcengine' }
        ],
        layer3: { model: 'nvidia', endpoint: 'http://127.0.0.1:8080' }
      },
      savings: '100%'
    },
    3: {
      name: 'Claude',
      tool: null,
      native: true,
      savings: '0%'
    }
  };
  return routes[complexity.level];
}

// ─── 主函数 ────────────────────────────────────────────────
function main() {
  const prompt = process.argv[2] || '';

  if (!prompt) {
    process.stderr.write('[cost-aware-router] No prompt provided\n');
    process.exit(1);
  }

  const complexity = assessComplexity(prompt);
  const route = getRoute(complexity);

  // 输出路由决策
  const result = {
    complexity: complexity.level,
    model: complexity.model,
    route: route,
    reason: complexity.reason,
    prompt_length: prompt.length
  };

  process.stdout.write(JSON.stringify(result));
}

// ─── 执行 ──────────────────────────────────────────────────
main();

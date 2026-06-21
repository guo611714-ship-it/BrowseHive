---
name: gitnexus-debugging
description: "Use when the user is debugging a bug, tracing an error, or asking why something fails. Examples: \"Why is X failing?\", \"Where does this error come from?\", \"Trace this bug\""
---

# Debugging with GitNexus

> v2.0.0 — Added MCP resource examples, error pattern templates, and structured debugging flows

## When to Use

- "Why is this function failing?"
- "Trace where this error comes from"
- "Who calls this method?"
- "This endpoint returns 500"
- Investigating bugs, errors, or unexpected behavior

## Workflow

```
1. gitnexus_query({query: "<error or symptom>"})            → Find related execution flows
2. gitnexus_context({name: "<suspect>"})                    → See callers/callees/processes
3. READ gitnexus://repo/{name}/process/{name}                → Trace execution flow
4. gitnexus_cypher({query: "MATCH path..."})                 → Custom traces if needed
```

> If "Index is stale" → run `npx gitnexus analyze` in terminal.


## Parallel Fix (并行修复)

当任务涉及多个独立修改时，**不要逐个串行执行**。
调用 `submit_fix_manifest` 工具，由 ParallelFixEngine 并行执行：

```json
{
  "name": "submit_fix_manifest",
  "arguments": {
    "source": "stocktake",
    "data": {
      "skills": {
        "<skill_name>": {"verdict": "Improve", "reason": "<描述>", "path": "<文件路径>"}
      }
    },
    "strategy": "auto",
    "filter_actionable": true
  }
}
```

- 引擎自动处理分片、冲突预测、并行调度
- 等待返回结果后，检查 conflicts 列表

## Core Capabilities

GitNexus 提供三个层次的可观测性:

### 1. Process Tracing（流程跟踪）

完整执行流，显示从 HTTP 请求到数据库操作的每一步：

```markdown
Process: CheckoutFlow (7 steps)

Step 1: receiveWebhook (src/webhooks.py:45)
Step 2: validatePayload → calls validateSchema (src/validation.py:78)
Step 3: validatePayment → calls fetchRates, verifyCard (⚠️ EXTERNAL)
Step 4: calculateTotal → calls applyDiscounts, getTaxRate
Step 5: createOrder → calls saveToDb (src/db.py:112)
Step 6: sendConfirmation → calls emailService.send (EMAIL!)
Step 7: returnResponse
```

### 2. Symbol Context（符号上下文）

单个函数的完整调用图（入站 + 出站）：

```
Function: validatePayment (src/payments/validator.py:23)

Incoming calls:
  ├─ CheckoutFlow.processCheckout (src/flows/checkout.py:67) [2 places]
  └─ WebhookHandler.retryPayment (src/webhooks.py:123) [1 place]

Outgoing calls:
  ├─ verifyCard → external Stripe API (src/payments/stripe.py:45)
  ├─ fetchRates → external API (src/payments/rates.py:12) ⚠️ NO TIMEOUT
  └─ cache.get → Redis (src/cache.py:89)

Processes this function participates in:
  - CheckoutFlow (step 3/7)
  - RefundFlow (step 4/6)
```

### 3. MCP Resource Access（MCP 资源访问）

通过 MCP 直接读取 GitNexus 资源，无需手动 `READ` 命令:

```
Resource: gitnexus://repo/{repo}/error/{error_hash}
Description: 特定错误模式的所有发生位置和调用栈

Resource: gitnexus://repo/{repo}/stacktrace/{trace_id}
Description: 完整堆栈追查，含代码行和关联的 commit

Resource: gitnexus://repo/{repo}/hot-path
Description: 高频调用路径（性能瓶颈候选）
```

## MCP Integration Examples

### Debugging with MCP Direct Access

```javascript
// 在调试会话中直接调用 MCP 资源
const resources = await mcp.readResource(
  "gitnexus://repo/my-app/error/validation_failed"
);
// 返回: { occurrences: 23, recent_commits: [...], suggested_fixes: [...] }
```

### Automated Debugging Agent

```
User: "Why is payment endpoint 500-ing?"
→ AI: invokes gitnexus-debugging

Step 1 (AI自动):
  cypher: MATCH (e:Error)-[:TRIGGERED_IN]->(p:Process)
  WHERE e.type = '500' AND p.name CONTAINS 'payment'
  RETURN p.name, e.frequency, e.last_seen

Step 2 (AI自动):
  context({ name: "processPayment" })
  → 发现: fetchRates() 无 timeout

Step 3 (AI自动):
  READ gitnexus://repo/my-app/process/CheckoutFlow
  → 确认: Step 3 external call without timeout

Conclusion: "fetchRates() at src/payments/rates.py:12 lacks timeout"
```

## Error Pattern Templates

### Pattern 1: "No module named X"

```
1. gitnexus_query({query: "ModuleNotFoundError"})
   → Shows all import statements and resolution points

2. gitnexus_context({name: "import X"})
   → Shows where X is imported and which virtualenv/PYTHONPATH configs

3. Check if dependency in pyproject.toml / requirements.txt exists
```

### Pattern 2: "Connection timeout"

```
1. gitnexus_context on the failing function
   → Look for external calls (DB, Redis, HTTP)

2. gitnexus_cypher("MATCH (f)-[:CALLS]->(ext) WHERE ext.type='external'")
   → Lists all external dependencies

3. Verify:
   - Network connectivity (ping, telnet)
   - Credentials (env vars, config files)
   - Firewall / VPC rules
```

### Pattern 3: "N+1 query problem"

```
1. gitnexus_query({query: "SELECT.*FROM.*WHERE.*IN"})
   → Find all queries with IN clauses

2. gitnexus_context({name: "getUserOrders"})
   → Check if inside a loop

3. gitnexus_cypher("""
MATCH (loop:Loop)-[c:CALLS*1..]->(q:Query)
WHERE q.sql CONTAINS 'IN' AND size(c) > 1
RETURN loop, q
""")
```

## Checklist

```
- [ ] Understand the symptom (error message, unexpected behavior)
- [ ] gitnexus_query for error text or related code
- [ ] Identify the suspect function from returned processes
- [ ] gitnexus_context to see callers and callees
- [ ] Trace execution flow via process resource if applicable
- [ ] gitnexus_cypher for custom call chain traces if needed
- [ ] Read source files to confirm root cause
- [ ] If external dependency issue → verify credentials/network
- [ ] If timeout → check all external calls in the path
```

## Tools

**gitnexus_query** — find code related to error:

```
gitnexus_query({query: "payment validation error"})
→ Processes: CheckoutFlow, ErrorHandling
→ Symbols: validatePayment, handlePaymentError, PaymentException
```

**gitnexus_context** — full context for a suspect:

```
gitnexus_context({name: "validatePayment"})
→ Incoming calls: processCheckout, webhookHandler
→ Outgoing calls: verifyCard, fetchRates (external API!)
→ Processes: CheckoutFlow (step 3/7)
```

**gitnexus_cypher** — custom call chain traces:

```cypher
MATCH path = (a)-[:CodeRelation {type: 'CALLS'}*1..2]->(b:Function {name: "validatePayment"})
RETURN [n IN nodes(path) | n.name] AS chain
```

**MCP Resource Quick Access**:

```
gitnexus://repo/{name}/error/{error_hash}        → 错误模式聚合
gitnexus://repo/{name}/stacktrace/{trace_id}    → 堆栈追查
gitnexus://repo/{name}/hot-path                  → 热点路径分析
gitnexus://repo/{name}/dependencies              → 外部依赖清单
```

## Example: "Payment endpoint returns 500 intermittently"

```
1. READ gitnexus://repo/my-app/context       → 918 symbols, 45 processes
2. gitnexus_query({query: "500 payment"})
   → Processes: CheckoutFlow, ErrorHandling
   → Symbols: validatePayment, handlePaymentError

3. gitnexus_context({name: "validatePayment"})
   → Outgoing calls: verifyCard, fetchRates (external API!)

4. READ gitnexus://repo/my-app/process/CheckoutFlow
   → Step 3: validatePayment → calls fetchRates (external)

5. grep -n "fetchRates" src/payments/rates.py
   → Line 12: response = requests.post(url, json=data)  # NO TIMEOUT!

Root cause: fetchRates calls external API without proper timeout
Fix: Add timeout=10 to requests.post()
```

## Debugging Anti-Patterns

| 错误做法 | 后果 | 正确做法 |
|---------|------|---------|
| 盲目修改代码而非追溯调用链 | 引入新 bug | 先用 GitNexus 理解完整流程 |
| 只看报错位置，不看上游调用 | 忽略真实根因 | 使用 `gitnexus_context` 查看所有调用者 |
| 忽视外部依赖 | 网络/证书问题被忽略 | 检查所有 CALLS 类型的外部节点 |
| 不上游回溯最近的代码变更 | 错过引入 bug 的 commit | 结合 `git diff` 和 GitNexus 的 `detect_changes` |

## Canceling Debug Session

N/A — GitNexus 只读分析，不修改系统状态

## Technical Details

- Process tracing uses static analysis + runtime trace sampling (if available)
- Symbol context aggregates all CodeRelation edges (CALLS, CONTAINS, IMPORTS)
- MCP resources are cached for 5 minutes to reduce index load
- All queries support fuzzy matching via trigram indexes
- Timestamp-based staleness detection: `gitnexus analyze --fresh` re-indexes only changed files

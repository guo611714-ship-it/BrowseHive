---
name: gitnexus-exploring
description: "Use when the user asks how code works, wants to understand architecture, trace execution flows, or explore unfamiliar parts of the codebase. Examples: \"How does X work?\", \"What calls this function?\", \"Show me the auth flow\""
---

# Exploring Codebases with GitNexus

> v2.0.0 — Added scenario-based templates, concrete workflow examples, and architectural exploration patterns

## When to Use

- "How does authentication work?"
- "What's the project structure?"
- "Show me the main components"
- "Where is the database logic?"
- Understanding code you haven't seen before

## Workflow

```
1. READ gitnexus://repos                          → Discover indexed repos
2. READ gitnexus://repo/{name}/context             → Codebase overview, check staleness
3. gitnexus_query({query: "<what you want to understand>"})  → Find related execution flows
4. gitnexus_context({name: "<symbol>"})            → Deep dive on specific symbol
5. READ gitnexus://repo/{name}/process/{name}      → Trace full execution flow
```

> If step 2 says "Index is stale" → run `npx gitnexus analyze` in terminal.


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

## Scenario-Based Templates

### Template A: "How does [feature] work?"

适用于理解某个功能的完整调用链。

```
User: "How does user authentication work?"

AI Response Workflow:
1. gitnexus_query({query: "auth authentication login"})
   → Processes: LoginFlow, TokenRefresh, LogoutFlow
   → Symbols: authenticateUser, verifyToken, refreshSession

2. gitnexus_context({name: "authenticateUser"})
   → Incoming: LoginHandler, APIMiddleware
   → Outgoing: verifyCredentials, createSession, emitAuditLog

3. READ gitnexus://repo/my-app/process/LoginFlow
   → Step-by-step: POST /login → middleware.authenticate → authenticateUser →
      verifyCredentials → hash.compare → createSession → set-cookie

4. Highlight key files:
   - src/auth/middleware.py (middleware)
   - src/auth/credentials.py (verifyCredentials)
   - src/auth/session.py (createSession)
```

期望输出: 清晰的 3-7 步骤说明 + 关键文件路径

---

### Template B: "Show me the [concept] architecture"

适用于理解领域设计的广度（有哪些模块及其关系）。

```
User: "Show me the payment architecture"

AI Response Workflow:
1. READ gitnexus://repo/my-app/clusters
   → Clusters: Payments, Orders, Users, Notifications
   → 显示每个 cluster 的 cohesion score（>0.7 表示高度内聚）

2. gitnexus_context({name: "payments"})
   → Cluster 成员: processor.py, validator.py, rates.py, refunds.py, stripe.py

3. 绘制模块关系图（基于 CodeRelation INTERACTS_WITH）:
   Payments ↔ Orders (高频调用)
   Payments → StripeAdapter (外部依赖)
   Payments → Notifications (事件订阅)

4. 列出所有 Cluster 并说明职责:
   - Payments: 核心支付逻辑、验证、退款
   - Orders: 订单生命周期管理
   - Users: 用户资料和权限
   - Notifications: 邮件/Slack/短信通知
```

期望输出: Cluster 图 + 关键文件 + 模块间关系

---

### Template C: "Where is the [domain] logic?"

适用于在大型代码库中定位特定领域的代码。

```
User: "Where is the database logic?"

AI Response Workflow:
1. gitnexus_query({query: "database db connection pool query"})
   → Files: src/db/connection.py, src/db/models.py, src/db/migrations/

2. 按文件类型分组:
   - Connection management: src/db/connection.py (pool size, health checks)
   - ORM models: src/db/models.py (User, Order, Product)
   - Migrations: src/db/migrations/001_*.sql
   - Query builders: src/db/queries.py (select, insert helpers)

3. Highlight entry points:
   - `get_connection()` is the public API (used 47 次)
   - `db.query()` is the low-level executor
   - All models inherit from BaseModel

4. 生成目录树:
   db/
   ├── connection.py    # Pool management, health checks
   ├── models.py        # SQLAlchemy models (12 models)
   ├── queries.py       # Query builder helpers
   ├── transactions.py  # @transaction decorator
   └── migrations/      # Alembic migrations (47 files)
```

期望输出: 文件位置 + 职责说明 + 代码组织模式

---

### Template D: "What are the main entry points?"

适用于理解程序的启动和 API 边界。

```
User: "What are the main entry points?"

AI Response Workflow:
1. gitnexus_cypher("MATCH (f:Function) WHERE f.is_entrypoint = true RETURN f")

2. 按类型分组:
   - HTTP Handlers: POST /api/v1/orders (src/api/handlers.py:45)
   - CLI Commands: cli.py:main() → 5 subcommands
   - Background Jobs: app.py:worker_main() → 3 job types
   - Webhooks: webhooks.py:handle_* (3 providers)

3. 显示调用关系:
   main() → create_app() → register_blueprints() → handler functions

4. 外部依赖标注:
   - /api/* → 需要 authentication middleware
   - worker_main() → connects to Redis & PostgreSQL
   - webhooks → signature verification (security!)
```

期望输出: 入口点列表 + 调用链 + 外部依赖

---

## Predefined Workflows

### Explore: API Layer

```
1. gitnexus_query({query: "router api endpoint"})
   → Finds FastAPI/Express/Flask route definitions

2. gitnexus_context({name: "create_app" or "setup_routes"})
   → Shows all route registrations and middleware stack

3. For each major endpoint:
   READ gitnexus://repo/{name}/process/{handler_name}
   → Trace full request lifecycle
```

### Explore: Data Pipeline

```
1. gitnexus_query({query: "pipeline etl transform load"})
   → Identifies data sources, transformers, destinations

2. Find the orchestrator:
   gitnexus_context({name: "run_pipeline" or "main_pipeline"})

3. Map data flow:
   Source (CSV/API/DB) → Validation → Transformation → Load (DW/S3/DB)
```

### Explore: Error Handling Strategy

```
1. gitnexus_query({query: "exception try except catch"})
   → Shows all error handling locations

2. Categorize by:
   - Recovery (retry, fallback)
   - Logging + re-raise
   - Silent swallow (⚠️ suspect)

3. Cross-reference with:
   - Custom exception classes (Defining custom error types)
   - Global error handlers (Last-resort catch-all)
```


## Checklist

```
- [ ] READ gitnexus://repo/{name}/context
- [ ] gitnexus_query for the concept you want to understand
- [ ] Review returned processes (execution flows)
- [ ] gitnexus_context on key symbols for callers/callees
- [ ] READ process resource for full execution traces
- [ ] Read source files for implementation details
```

## Resources

| Resource                                | What you get                                            |
| --------------------------------------- | ------------------------------------------------------- |
| `gitnexus://repo/{name}/context`        | Stats, staleness warning (~150 tokens)                  |
| `gitnexus://repo/{name}/clusters`       | All functional areas with cohesion scores (~300 tokens) |
| `gitnexus://repo/{name}/cluster/{name}` | Area members with file paths (~500 tokens)              |
| `gitnexus://repo/{name}/process/{name}` | Step-by-step execution trace (~200 tokens)              |

## Tools

**gitnexus_query** — find execution flows related to a concept:

```
gitnexus_query({query: "payment processing"})
→ Processes: CheckoutFlow, RefundFlow, WebhookHandler
→ Symbols grouped by flow with file locations
```

**gitnexus_context** — 360-degree view of a symbol:

```
gitnexus_context({name: "validateUser"})
→ Incoming calls: loginHandler, apiMiddleware
→ Outgoing calls: checkToken, getUserById
→ Processes: LoginFlow (step 2/5), TokenRefresh (step 1/3)
```

## Example: "How does payment processing work?"

```
1. READ gitnexus://repo/my-app/context       → 918 symbols, 45 processes
2. gitnexus_query({query: "payment processing"})
   → CheckoutFlow: processPayment → validateCard → chargeStripe
   → RefundFlow: initiateRefund → calculateRefund → processRefund
3. gitnexus_context({name: "processPayment"})
   → Incoming: checkoutHandler, webhookHandler
   → Outgoing: validateCard, chargeStripe, saveTransaction
4. Read src/payments/processor.ts for implementation details
```

**Answer you'd give to user:**

"Payment processing consists of two main flows:

1. **CheckoutFlow** (happy path):
   - `checkoutHandler` receives POST → `processPayment` (src/payments/processor.ts:45)
   - `validateCard` calls Stripe API (src/payments/stripe.ts:23)
   - `chargeStripe` performs the charge
   - `saveTransaction` writes to PostgreSQL (src/db/transactions.py:78)

2. **RefundFlow** (edge case):
   - `initiateRefund` → `calculateRefund` (includes tax logic)
   - `processRefund` → async job (background worker)

All payment logic lives in `src/payments/` with 5 modules totalling ~800 LOC."

## Architectural Questions Quick Reference

| Question | Recommended Starting Point |
|---------|---------------------------|
| "How does X work?" | `gitnexus_query(X)` → process trace |
| "What are the major components?" | `READ gitnexus://repos/{name}/clusters` |
| "Where is database logic?" | `gitnexus_query("database db model")` |
| "What are entry points?" | `gitnexus_query("main app create_app")` |
| "Who calls this function?" | `gitnexus_context({name: "func"})` |
| "Why is this slow?" | `gitnexus_context` → look for hot paths (>100 callers) |

## Staleness Handling

```
Index stale? → Staleness % in context > 20%

Action:
1. Run: npx gitnexus analyze --fresh
2. Wait for completion (progress shown in terminal)
3. Re-run your query

Alternatively (batched):
/taskflow create "gitnexus-refresh" "0 2 * * * npx gitnexus analyze"
```

## Impact Analysis

Use when the user wants to know what will break if they change something.

### When to Use

- "Is it safe to change this function?"
- "What will break if I modify X?"
- "Show me the blast radius"
- "Who uses this code?"
- Before making non-trivial code changes
- Before committing — to understand what your changes affect

### Impact Analysis Workflow

```
1. gitnexus_impact({target: "X", direction: "upstream"})  → What depends on this
2. READ gitnexus://repo/{name}/processes                   → Check affected execution flows
3. gitnexus_detect_changes()                               → Map current git changes to affected flows
4. Assess risk and report to user
```

### Impact Analysis Checklist

```
- [ ] gitnexus_impact({target, direction: "upstream"}) to find dependents
- [ ] Review d=1 items first (these WILL BREAK)
- [ ] Check high-confidence (>0.8) dependencies
- [ ] READ processes to check affected execution flows
- [ ] gitnexus_detect_changes() for pre-commit check
- [ ] Assess risk level and report to user
```

### Depth → Risk Mapping

| Depth | Risk Level       | Meaning                  |
| ----- | ---------------- | ------------------------ |
| d=1   | **WILL BREAK**   | Direct callers/importers |
| d=2   | LIKELY AFFECTED  | Indirect dependencies    |
| d=3   | MAY NEED TESTING | Transitive effects       |

### Risk Assessment

| Affected                       | Risk     |
| ------------------------------ | -------- |
| <5 symbols, few processes      | LOW      |
| 5-15 symbols, 2-5 processes    | MEDIUM   |
| >15 symbols or many processes  | HIGH     |
| Critical path (auth, payments) | CRITICAL |

### Tools

**gitnexus_impact** — the primary tool for symbol blast radius:

```
gitnexus_impact({
  target: "validateUser",
  direction: "upstream",
  minConfidence: 0.8,
  maxDepth: 3
})

→ d=1 (WILL BREAK):
  - loginHandler (src/auth/login.ts:42) [CALLS, 100%]
  - apiMiddleware (src/api/middleware.ts:15) [CALLS, 100%]

→ d=2 (LIKELY AFFECTED):
  - authRouter (src/routes/auth.ts:22) [CALLS, 95%]
```

**gitnexus_detect_changes** — git-diff based impact analysis:

```
gitnexus_detect_changes({scope: "staged"})

→ Changed: 5 symbols in 3 files
→ Affected: LoginFlow, TokenRefresh, APIMiddlewarePipeline
→ Risk: MEDIUM
```

### Example: "What breaks if I change validateUser?"

```
1. gitnexus_impact({target: "validateUser", direction: "upstream"})
   → d=1: loginHandler, apiMiddleware (WILL BREAK)
   → d=2: authRouter, sessionManager (LIKELY AFFECTED)

2. READ gitnexus://repo/my-app/processes
   → LoginFlow and TokenRefresh touch validateUser

3. Risk: 2 direct callers, 2 processes = MEDIUM
```

## Canceling Exploration

N/A — Read-only operations, safe to interrupt anytime

# Technician Scheduling Agent — 项目介绍与交接说明

> 建议团队同步控制在 **10–15 分钟**，不要从代码目录开始讲，而是按 **为什么这样拆 → 流程怎么走 → 队友接下来需要做什么** 的顺序介绍。

## 1. 一句话介绍

> 我们现在采用双 Agent 架构：Customer Intake Agent 负责理解客户需求和补充缺失信息，Scheduling Operations Agent 负责调用确定性排程引擎生成并验证派单建议。LLM 不直接选择技师，关键变更由 Human Coordinator 控制。

这个拆分的目的不是为了“做复杂的 Multi-Agent”，而是把三类职责明确分开：

1. **自然语言理解与交互**：由 Agent / LLM 负责。
2. **业务约束与排程计算**：由确定性 Python 引擎负责。
3. **关键运营决策与审批**：由 Human Coordinator 保留最终控制权。

---

## 2. 为什么这样拆

Technician Scheduling 的核心难点不是“让 LLM 猜一个技师”，而是让系统在真实业务约束下生成 **可行、可解释、可审计** 的安排。

因此我们明确以下边界：

- LLM 负责理解客户语言、补充信息、选择工具、解释结果。
- Python scheduling engine 负责技能、证照、班次、冲突、workload、slot search 和 ranking。
- Agent 不能直接执行任意 Python，也不能直接执行 SQL。
- Agent 只能调用 Tool Registry 中注册且允许该 Agent 使用的工具。
- 关键输入通过 Pydantic 校验。
- Assignment recommendation 可以写入结果表，但 Week 1 不直接覆盖当前 `schedules`。
- Evaluation Ground Truth 与 Runtime SQLite 完全隔离。

一句话概括：

> **Agent 负责协调，Engine 负责计算，Human 负责关键控制。**

---

## 3. 当前业务流程

```text
Customer message
→ Customer Intake Agent
→ Structured Request
→ Agent Handoff
→ Scheduling Operations Agent
→ Deterministic Scheduling Engine
→ Assignment Recommendation
→ Coordinator Dashboard
```

需要强调三点：

1. 这是 **Multi-Agent workflow**，不是一次性 LLM extraction。
2. Agent 之间通过结构化 Handoff 通信，不靠自由文本隐式交接。
3. 技师选择由确定性 Python 完成，不由 LLM 直接决定。

---

## 4. Customer Intake Agent

### 4.1 主要职责

Customer Intake Agent 负责把客户自然语言转换为可排程的 `StructuredRequest`：

- 理解客户消息
- 查询已有客户上下文
- 查询标准 Service Rule
- 提取 service type、zone/location、urgency 和 appointment window
- 识别缺失或模糊字段
- 主动向客户发起 clarification
- 保存 Structured Request
- 信息完整后发送 `REQUEST_READY` Handoff

### 4.2 允许调用的 Tools

```text
get_customer_context
lookup_service_rules
save_structured_request
get_request_status
```

### 4.3 不负责

Customer Intake Agent **不负责**：

- 选择技师
- 检查技师冲突
- 计算 workload
- 搜索可行 slot
- 对候选技师排序
- 修改 schedule

---

## 5. Scheduling Operations Agent

### 5.1 Week 1 主要职责

Scheduling Operations Agent 负责接收已经 ready 的 request，并协调确定性排程：

- 接收 `REQUEST_READY`
- 再次检查 request readiness
- 调用 deterministic Assignment Engine
- 获取候选技师和排除原因
- 验证 assignment recommendation
- 获取 Decision Trace
- 生成面向 Coordinator 的解释
- 无可行结果时升级人工处理

### 5.2 允许调用的 Tools

```text
get_request_status
recommend_assignment
validate_assignment_recommendation
get_assignment_decision_trace
```

### 5.3 Week 2 演进

Week 2 不单独创建 Rescheduling Agent，而是在同一个 Scheduling Operations Agent 中增加：

```text
DISRUPTION_RECOVERY
```

原因是 initial assignment 和 rescheduling 共用大量领域信息和约束：

- Service rules
- Skills / certifications
- Technician status
- Shift
- Existing schedules
- Customer time window
- Workload capacity
- Feasible slot search

因此暂时放在同一个 Operations Agent 更简单，也能避免重复 Prompt、Tools 和错误处理逻辑。

---

## 6. Human Coordinator 的定位

Coordinator 当前保持为：

> **Human + Dashboard，而不是独立 Agent。**

### Week 1

Coordinator 主要负责：

- 查看 raw customer request
- 查看 AI extracted fields
- 查看 Agent Handoff / Tool Call
- 查看推荐 technician 和 appointment time
- 查看 candidate exclusion reasons
- 处理 `NO_FEASIBLE_ASSIGNMENT`

Week 1 只展示和审核 recommendation，不直接修改 `schedules`。

### Week 2

当加入 confirmed appointment rescheduling 后，再增加：

- Approve
- Reject
- Approval state
- Before / After comparison
- Apply approved proposal

核心权限边界：

```text
Agent can propose
Human can approve or reject
System can apply only an approved proposal
```

---

## 7. Agent、Tool 与确定性 Engine 的关系

最重要的技术关系是：

```text
Agent
→ Tool Registry
→ Tool Executor
→ Deterministic Engine / Application Service
→ SQLite
```

### Tool Registry

负责定义：

- 哪些工具存在
- 哪个 Agent 可以调用
- 输入 Schema
- Tool handler
- Read / Write 权限

### Tool Executor

负责：

- 检查 Tool 是否存在
- 检查调用权限
- Pydantic 参数校验
- 执行 handler
- 统一错误处理
- 记录 input / output / status / duration

### Deterministic Scheduling Engine

负责真正计算：

```text
Readiness Gate
→ Service Rule Lookup
→ Skill Filtering
→ Certification Filtering
→ Technician Status Filtering
→ Shift Validation
→ Customer Window Validation
→ Existing Schedule Conflict Check
→ Dynamic Workload Calculation
→ Workload Capacity Check
→ 30-minute Slot Search
→ Deterministic Ranking
```

Ranking 固定为：

```text
projected workload ratio
→ earliest feasible start
→ technician ID
```

因此即使更换模型，核心派单结果仍然由同一套业务规则控制。

---

## 8. 当前 LLM Backend

本地开发支持三种主要模式：

| Backend | 用途 |
|---|---|
| `mock` | 不依赖真实模型，适合稳定测试 Agent、Tools 和 scheduling flow |
| `local` | 连接 OpenAI-compatible API，可用于 LM Studio、OpenRouter 等本地开发/调试路径 |
| `bedrock` | 最终 AWS / Amazon Bedrock 路径 |

使用 `local` 时，本质上是走 OpenAI-compatible API，并不要求模型一定运行在本机；例如 OpenRouter 也可以通过这一接口接入。

---

## 9. Runtime 数据与 Evaluation 边界

Runtime 业务数据保存在 SQLite，例如：

```text
company_profile
service_rules
technicians
customers
jobs
schedules
customer_requests
structured_requests
assignment_results
agent_sessions
agent_handoffs
agent_tool_calls
```

Evaluation 数据单独保留为 CSV，例如：

```text
cases.csv
request_ground_truth.csv
assignment_ground_truth.csv
```

必须保持：

> **Runtime Agent 不读取 Ground Truth。**

Ground Truth 只用于 offline evaluation，不能参与 runtime decision。

---

## 10. 建议团队会议演示的 3 个 Case

不要只展示代码目录，直接跑三个业务 Case。

### Case 1：完整请求

示例：

```text
My aircon is leaking in East.
I am available from 2026-09-15T14:00 to 2026-09-15T17:00.
```

展示：

```text
Intake Agent
→ REQUEST_READY
→ Scheduling Operations Agent
→ Technician recommendation
→ Decision Trace
→ Coordinator Dashboard
```

用于证明：

- Agent Handoff
- Tool Calling
- Deterministic Assignment
- Explainability

### Case 2：信息缺失

示例：

```text
My toilet is blocked.
```

展示：

- Intake Agent 识别缺少 appointment window / location 等必要信息
- 发出 clarification
- 客户补充信息
- 同一个 Agent Session 继续
- Request 变为 ready
- Handoff 给 Scheduling Agent

用于证明：

- Multi-turn interaction
- Readiness Gate
- Structured Handoff

### Case 3：无可行技师

使用很晚、很窄或与现有排班冲突的 appointment window。

展示：

- 所有候选被 deterministic engine 排除
- 每个技师的 exclusion reason
- `NO_FEASIBLE_ASSIGNMENT` / `HUMAN_REVIEW_REQUIRED`
- 系统没有自动修改 current schedule

用于证明：

- Constraint enforcement
- Decision Trace
- Human-in-the-loop
- Safe failure

三个 Case 合起来可以证明：

- Multi-Agent
- Tool Calling
- Multi-turn dialogue
- Deterministic Scheduling
- Explainability
- Human-in-the-loop

---

## 11. 团队同步时优先展示的文件

不需要逐个讲所有文件，只展示主干：

| 文件 | 说明 |
|---|---|
| `MULTI_AGENT_ARCHITECTURE.md` | 总体架构与边界说明 |
| `src/orchestration/orchestrator.py` | 控制 Agent workflow、state 和 handoff |
| `src/agents/intake_agent.py` | Customer Intake Agent |
| `src/agents/scheduling_operations_agent.py` | Scheduling Operations Agent |
| `src/tools/registry.py` | Agent Tool 白名单和 Schema |
| `src/tools/executor.py` | Tool 执行与校验安全边界 |
| `src/scheduling/assignment_engine.py` | 确定性派单核心 |
| `src/database.py` | SQLite schema 与数据库接口 |

重点让队友理解：

```text
Agent → Tool Executor → Deterministic Engine → SQLite
```

而不是逐个解释目录。

---

## 12. 需要和队友确认的决策点

会议中建议明确确认：

1. 是否同意 Week 1 使用两个 Runtime Agent。
2. 是否同意 Assignment 和 Rescheduling 暂时放在同一个 Scheduling Operations Agent。
3. 是否同意 Coordinator Week 1 保持 Human + Dashboard。
4. 是否接受 LLM 不直接选择 technician。
5. 是否接受 Week 1 recommendation 不直接修改 `schedules`。
6. StructuredRequest Schema 是否冻结。
7. Handoff Schema 是否冻结。
8. Demo 主要使用 Mock、Local LLM 还是 Bedrock。
9. 每个人负责哪些模块和接口。
10. Week 2 rescheduling 与 approval 的接口边界。

---

## 13. 推荐团队分工

| 模块 | 主要负责内容 |
|---|---|
| Data & Setup | Seed、SQLite、Service Rules、数据一致性和 validation |
| Customer Intake | Intake Prompt、Tool Calling、clarification、多轮交互 |
| Technician Assignment | Deterministic Scheduling Engine、constraints、Decision Trace |
| Coordinator UI | Agent Timeline、推荐详情、人工处理与后续 approval |
| AWS / Deployment | Bedrock、Guardrails、部署、fallback |
| Evaluation | Extraction accuracy、assignment validity、demo cases、regression tests |

接口先冻结，再并行开发，尽量避免多人同时改同一个核心文件。

---

## 14. 可以直接发给队友的同步消息

```text
Hi team，我已经把 Technician Scheduling 的基础架构搭起来了，想同步一下目前的设计和边界。

我们现在使用双 Agent 架构：

1. Customer Intake Agent
- 理解客户自然语言
- 查询客户上下文和标准 Service Rule
- 提取 service type、location 和 appointment window
- 信息不完整时主动追问
- 生成 StructuredRequest

2. Scheduling Operations Agent
- 接收 Intake Agent 的 REQUEST_READY handoff
- 调用确定性 Scheduling Engine
- 验证 assignment recommendation
- 获取候选技师、排除原因和 decision trace
- 生成解释或转人工处理

重要边界：
- LLM 不直接选择技师
- Skill、certification、shift、conflict、workload、slot search 和 ranking 都由确定性 Python 完成
- Agent 只能调用白名单 Tools
- Tool 参数经过 Pydantic 校验
- 推荐结果写入 assignment_results，但不会直接覆盖 schedules
- Coordinator 当前是 Human + Dashboard
- Evaluation CSV 与 Runtime SQLite 完全隔离

本地支持三种模式：
- mock：无模型依赖，适合稳定测试
- local：连接 OpenAI-compatible API，可用于本地服务或 OpenRouter
- bedrock：最终 AWS 路径

Week 1 重点是双 Agent intake → handoff → assignment 流程。
Week 2 会在 Scheduling Operations Agent 中加入 unavailable/delayed 和 rescheduling proposal，再增加人工 Approve/Reject。

架构文档：
MULTI_AGENT_ARCHITECTURE.md

当前测试：请以会议前最后一次 pytest 结果为准。
```

---

## 15. 10–15 分钟同步建议

### 0–2 分钟：为什么这样拆

说明：

- LLM 不是 scheduling optimizer
- 双 Agent 是为了把 Intake 和 Scheduling 两类职责分开
- Human 继续控制关键修改

### 2–5 分钟：流程怎么走

展示：

```text
Customer
→ Intake Agent
→ Structured Request
→ Handoff
→ Scheduling Agent
→ Deterministic Engine
→ Recommendation
→ Coordinator
```

### 5–8 分钟：Agent、Tools、Engine 边界

展示两个 Agent 的 Tool Allowlist，以及：

```text
Agent → Tool Executor → Engine
```

### 8–12 分钟：Demo

跑：

1. Complete request
2. Clarification case
3. No feasible technician

### 12–15 分钟：交接与分工

确认：

- Schema
- 模块 owner
- Week 2 scope
- Demo backend
- AWS / Evaluation 负责人

---

## 16. 最重要的同步原则

不要说：

> 我搭了一个很复杂的 Multi-Agent framework。

更推荐说：

> 我先搭了一个可运行的骨架，把 Agent、确定性业务逻辑和人工审批边界分开了。每个队友可以在明确接口下继续开发，不需要改动其他人的核心模块。

这个结构的目的不是增加复杂度，而是：

- 降低协作冲突
- 明确责任边界
- 保证排程结果可验证
- 保留 Human-in-the-loop
- 方便 Week 2 在现有接口上继续扩展

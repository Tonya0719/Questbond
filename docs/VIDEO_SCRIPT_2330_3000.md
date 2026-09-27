# 视频分镜脚本 23:30–30:00（安全 / 证据 / 试点 / 边界 / 收尾）

本文件覆盖 23:30–30:00 全段，取代早先只覆盖 23:30–27:00 的 `VIDEO_SEGMENT_SAFETY_TESTS.md`。

每个镜头标注：录制方式（终端 / 浏览器 UI / 幻灯片）、时长、具体操作与输入、旁白逐字稿。

## 数字校正（务必）

大纲里写的 **136 tests** 已过期。本轮新增了队列 UI、澄清修复与基准槽位修复的测试，当前为 **176 passed**。旁白与画面必须一致，请统一改成 176。

其余数字经核对无误：离线 120/120、live 任务完成率 100%、handoff 80%、final-state 80%、p50 约 29.7 秒、p95 约 33.0 秒。

## 录制前准备

```powershell
conda activate hackathon
python scripts/reset_db.py                 # 可选：清空演示库（会删数据，先确认）
python scripts/seed_sick_leave_demo.py     # 播种 disruption 演示数据
$env:LLM_BACKEND="mock"                    # 终端与快速 UI 演示用 mock
python -m streamlit run app.py
```

角色密码：Coordinator `DispatchOps2026!`，Technician `DispatchTech2026!`。

后端选择建议：
- **终端证据段**用 `mock`（快、确定）。
- **客户澄清对话**若想展示模型真实措辞，用 `gateway`（`$env:LLM_BACKEND="gateway"; $env:LLM_MODEL="global.anthropic.claude-sonnet-4-5-20250929-v1:0"`），但每次请求约 30 秒，录完剪掉等待。图快就用 `mock`，措辞是带例子的模板，同样成立。

通用技巧：终端字体 ≥16pt、执行前 `clear`；UI 先登录并展开好目标区域再开录；长等待一律剪掉。

---

# 23:30–25:30 | 安全、可解释与人类控制（120 秒）

## 镜头 1 — 工具清单里没有审批权（终端）｜18 秒

操作：新终端执行
```powershell
python -c "from src.tools import build_registry; print('\n'.join(sorted(build_registry().keys())))"
```
输出 10 个工具名后，用鼠标或后期高亮圈出：列表中没有 approve / reject / apply。

旁白：
> 先看安全边界。这是 Agent 能调用的全部工具——注意，没有 approve、没有 reject、没有 apply。模型只能读取上下文和生成提议，批准从来不是模型的权限。
> **EN:** Let us start with the safety boundary. These are all the tools the agent can call — notice there is no approve, no reject, no apply. The model can only read context and produce proposals; approval is never the model's authority.

## 镜头 2 — 信息不足时先追问（浏览器：Customer）｜25 秒

操作：Customer 视图，在 "What needs fixing?" 输入框键入
```
There is water on my floor
```
区域选 North，时间窗填一个合法未来窗口，提交。等结果出现后停在追问文案上。

旁白：
> 住户只说地上有水。这句话既可能是空调漏水，也可能是水管漏水。系统不会替他猜——它会反问是哪一种，并给出可以照着回答的例子。信息不足时先追问，而不是先排班。
> **EN:** The resident only says there is water on the floor. That could be an air-conditioner leak or a pipe leak. The system does not guess — it asks which one, with examples the resident can follow. When key information is missing, it asks first instead of scheduling.

## 镜头 3 — 硬约束与排除原因（浏览器：Coordinator）｜25 秒

操作：切到 Coordinator，选一条已完成抽取的工单，滚到 stage 3 "Candidate evaluation" 表格。鼠标沿着列横向划过：Technician / Qualified / Availability / Projected workload / Result。停在一条被排除的行上。

旁白：
> 协调员这边能看到每一个候选技术员的评估结果：谁合格、谁被排除、以及为什么——技能不符、缺少认证，还是时段冲突。不满足硬约束的技术员不会被推荐，这个判断由确定性代码做出，不是模型的印象。
> **EN:** On the coordinator side, every candidate technician is evaluated: who qualifies, who is excluded, and why — a skill mismatch, a missing certification, or a time conflict. A technician who violates a hard constraint is never recommended, and that decision is made by deterministic code, not the model's impression.

## 镜头 4 — 推荐理由与取舍（浏览器：Coordinator）｜20 秒

操作：继续下滚到 stage 4 "Decision" 与 stage 5 "Explanation"，停在解释文本上。

旁白：
> 推荐理由来自存储的决策事实：为什么选这个人、工作量会从多少涨到多少、排序依据是什么。解释是可核对的，不是模型的说辞。
> **EN:** The recommendation rationale comes from stored decision facts: why this technician, how the workload rises, and the ranking that was applied. The explanation is verifiable, not the model talking.

## 镜头 5 — Agent 无权批准高影响变更（浏览器：Coordinator）｜20 秒

操作：展开 "Recovery Plans"，选一个 PROPOSED 的恢复计划。镜头横移到治理列：Technician changed / Time changed / Customer appointment changed / Approval required / Approval reasons。

旁白：
> 技术员报告请假或延误后，系统会生成恢复方案。每条变更都标注是否换人、是否改时间、是否需要人工审批以及原因。此刻排班还没有被改动——这只是一个提议。高影响的操作必须由人批准。
> **EN:** When a technician reports leave or a delay, the system produces a recovery plan. Every change is labelled: whether the technician changed, whether the time changed, whether approval is required, and why. Right now the schedule has not been touched — this is only a proposal. High-impact changes must be approved by a human.

## 镜头 6 — 可审计与草稿通知（浏览器：Coordinator）｜12 秒

操作：先快速展开 stage 6 "Tool-call trace"（露出几条工具调用记录），再点 "Approve"，展开 "Customer notification drafts"，停在 "Draft only — no email has been sent"。

旁白：
> 工具调用、handoff 与审批过程全程可审计。客户通知也只是草稿，不会自动发送。
> **EN:** Tool calls, handoffs, and the approval process are fully auditable. Customer notifications are only drafts — they are never sent automatically.

---

# 25:30–27:00 | 测试与证据（90 秒）

## 镜头 7 — 产品测试（终端）｜15 秒

操作：
```powershell
$env:LLM_BACKEND="mock"; python -m pytest tests -q
```
录到末行 `176 passed`，高亮该行。等待时间后期剪掉。

旁白：
> 先看产品测试：一百七十六个用例全部通过，覆盖意图理解、调度、改期、治理与多模态。
> **EN:** First, product tests: one hundred and seventy-six tests all pass, covering intake understanding, scheduling, disruption recovery, governance, and multimodal intake.

## 镜头 8 — 离线基准 120/120（终端）｜30 秒

操作：
```powershell
python -m evaluation.system_benchmark.run --mode offline
```
录到终端量化摘要，镜头停在 Request / Scheduling / Disruption / Governance / Robustness 五段与最后 `Failed cases: 0 / 120`。

旁白：
> 接着是独立的系统基准，一百二十个离线用例。请求理解、调度可行性、改期最小改动全部满分；治理层的越权变更与审批前修改全部为零；对抗场景的安全失败率百分之百。这些衡量的是确定性正确性与安全。
> **EN:** Next, our separate system benchmark — one hundred and twenty offline cases. Request understanding, schedule feasibility, and minimum-change recovery all score full marks; unauthorized and pre-approval schedule mutations in the governance layer are all zero; and the safe-failure rate under adversarial cases is one hundred percent. These measure deterministic correctness and safety.

## 镜头 9 — Live 基准单独呈现（编辑器 / 终端）｜25 秒

操作：打开 `results/system_benchmark/summary_metrics.json`，滚到 `agent_live` 段；或打开 `results/system_benchmark/agent_live_results.csv`，指着 `backend=gateway`、`duration_ms` 约 3 万、真实 token 列。

旁白：
> 最后是 Live 基准，用真实的 Claude Sonnet 四点五跑四十五个用例：任务完成率百分之百，编排与 handoff 准确率百分之八十，p50 延迟约三十秒，p95 约三十三秒。必须强调：离线的满分是确定性正确性，Live 是真实模型的编排质量，两者维度不同，我们不混为一谈。
> **EN:** Finally, the live benchmark, run against the real Claude Sonnet 4.5 on forty-five cases: task completion is one hundred percent, orchestration and handoff accuracy is eighty percent, p50 latency is about thirty seconds and p95 about thirty-three. To be clear: the offline full marks are deterministic correctness, while live measures the real model's orchestration quality — two different dimensions, and we do not conflate them.

## 镜头 10 — 证据到底证明了什么（承接画面）｜20 秒

操作：可停在离线摘要或切回协调员治理列。若要强化「无可行方案时安全停止」，可在 CSV 里高亮 `agent_live_results.csv` 中唯一 `pass=False` 的 AGT008 行。

旁白：
> 这些证据证明四件事：不会产生非法排班；能正确识别受影响的工单；审批之前不修改排班；当没有可行方案时工作流安全停止并转人工。Live 里有一个边界用例的路由与预期不同，但所有安全不变式依然保持——这正是我们把安全放在确定性代码而不是模型里的原因。
> **EN:** This evidence proves four things: no illegal schedule is created; affected jobs are correctly detected; the schedule is not mutated before approval; and when no feasible plan exists, the workflow stops safely and hands off to a human. One live edge case routed differently than expected, but every safety invariant still held — which is exactly why we put safety in deterministic code rather than in the model.

---

# 27:00–28:30 | SME 明天就能开始试点（90 秒）

## 镜头 11 — 最小启动数据（编辑器）｜35 秒

操作：在编辑器里依次打开 `data/runtime/seed/` 下的文件，每个停约 6 秒：
1. `technicians.csv` — 指出 skills、certifications、shift_start/shift_end、max_workload_min 四列
2. `service_rules.csv` — 指出 required_skills、required_certifications、default_duration_min
3. `company_profile.json` — 指出 operating_start / operating_end
4. `schedule_current.csv` — 指出已有预约
5. `customer_requests.csv` — 指出少量客户请求

旁白：
> 试点需要的数据就这些：技术员及其技能与认证、工作时间、已有预约、服务规则，再加一小批客户请求。没有别的前置条件。
> **EN:** This is all the data a pilot needs: technicians with their skills and certifications, working hours, existing bookings, service rules, and a small set of customer requests. There is nothing else to prepare.

## 镜头 12 — 几条命令完成初始化（终端）｜25 秒

操作：
```powershell
python scripts/init_db.py
python scripts/validate_seed_data.py
```
录到校验通过的输出。

旁白：
> 把这些表导入后，一条初始化命令加一条校验命令，系统就可以开始接请求。Mendigo 是一个轻量的独立试点：不要求 SME 替换现有系统，也不要求先完成大规模数字化改造，就能验证核心流程。
> **EN:** Once these tables are imported, one init command plus one validation command, and the system is ready to take requests. Mendigo is a lightweight standalone pilot: an SME does not have to replace its existing systems or finish a large-scale digital transformation before testing the core workflow.

## 镜头 13 — 诚实的边界（幻灯片或承接终端画面）｜30 秒

画面：一张简单幻灯片，两行要点即可。

旁白：
> 需要说清楚现实边界：今天这一步由部署团队协助完成，还不是自助式上线。但它不需要企业级 ERP——从一个服务类别、一个小团队、一位协调员开始就够了。
> **EN:** Let us be honest about the boundary: today this step is assisted by the deployment team, not self-service onboarding. But it needs no enterprise ERP — starting with one service category, a small team, and one coordinator is enough.

---

# 28:30–29:15 | 当前边界与路线图（45 秒）

## 镜头 14 — 已实现 vs 未来（幻灯片，左右两栏）｜45 秒

画面：左栏「Implemented / demonstrable」，右栏「Future milestones」，各列 4–5 条。可在左栏每条旁放一张对应 UI 的小截图缩略图。

左栏：请求接入与澄清、技术员推荐与协调员审批、技术员排班视图、UNAVAILABLE / DELAYED 改期恢复、审计轨迹与基准。

右栏：自助 CSV 导入与系统连接器、通勤时间缓冲与实时路况、真实通知发送、个人账号体系。

旁白：
> 目前已实现并可演示的是：请求接入与澄清、技术员推荐与协调员审批、技术员排班视图、请假与延误两类改期恢复，以及完整的审计轨迹和量化基准。后续里程碑包括自助数据导入与系统对接、通勤时间缓冲与实时路况、真实通知发送，以及个人账号体系。我们只展示已经做到的部分。
> **EN:** What is implemented and demonstrable today: request intake and clarification, technician recommendation and coordinator approval, the technician schedule view, unavailable and delayed disruption recovery, plus a full audit trail and a quantitative benchmark. Future milestones include self-service data import and system connectors, travel-time buffers with live traffic, real notification sending, and individual user accounts. We only show what we have actually built.

---

# 29:15–30:00 | 收尾（45 秒）

## 镜头 15 — Before / After 对比（幻灯片）｜25 秒

画面：左右对比。左「Before」：零散的消息截图、手工核对、disruption 之后的混乱。右「After」：结构化工单、可解释的推荐、人类掌控、快速恢复。

旁白：
> 改变之前：消息零散、人工核对、一旦出现变动就陷入混乱。改变之后：工单结构化、推荐可解释、关键决定由人掌控、变动后能快速恢复。
> **EN:** Before: fragmented messages, manual checking, and chaos the moment something changes. After: a structured job, an explainable recommendation, humans in control of the key decisions, and fast recovery when plans change.

## 镜头 16 — 收束（幻灯片）｜20 秒

画面：Mendigo 名称与标语定格。

旁白：
> Mendigo 让每一个服务承诺都被兑现——即使这一天并没有按计划进行。
> **EN:** Mendigo keeps every service promise — even when the day does not go as planned.

---

## 关键数字对照表（录制时确保画面一致）

| 指标 | 值 | 画面来源 |
|---|---|---|
| 产品测试 | 176 passed | `pytest tests -q` |
| 离线基准 | 120 / 120，Failed 0 | `--mode offline` 终端摘要 |
| 治理越权 / 审批前变更 | 全为 0 | 终端摘要 Governance 段 |
| 鲁棒安全失败率 | 100% | 终端摘要 Robustness 段 |
| Live 任务完成率 | 100%（45/45） | `summary_metrics.json` 的 `agent_live` |
| Live handoff / final-state | 80% / 80% | 同上 |
| Live p50 / p95 延迟 | 约 29.7 秒 / 约 33.0 秒 | 同上 |
| Live 唯一失败用例 | AGT008（路由差异，无安全违规） | `agent_live_results.csv` |

## 诚实声明清单（务必保留）

- 离线 100% 是确定性正确性与安全，不是模型语言质量。
- Live 是真实模型编排质量，与离线不同维度，不混为一谈。
- Live 成本：网关未上报 provider cost，因此标记为不可用，不当作 0。
- 多模态视觉准确率是独立评估轨道，不属于本系统基准。
- 试点初始化目前由部署团队协助，不是自助上线。

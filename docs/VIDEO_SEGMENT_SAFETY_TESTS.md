# 视频分镜脚本 — 安全 / 可解释 / HITL + 测试与证据（23:30–27:00）

负责人：录制本段（约 3.5 分钟，总时长约 210 秒，含缓冲）。
旁白为中文口播，卡节奏念即可。

## 录制前准备

另开一个终端，先把环境和数据准备好，录制时只需触发命令：

```powershell
conda activate hackathon
# UI 演示
python -m streamlit run app.py        # 协调员密码 DispatchOps2026! / 技术员 DispatchTech2026!
# 先播种 disruption 演示数据
python scripts/seed_sick_leave_demo.py
# 终端演示统一用 mock 后端
$env:LLM_BACKEND="mock"
```

小贴士：
- 终端字体调大（≥16–18pt），深色背景，命令前先 `clear` 清屏。
- offline 基准和 pytest 有几十秒等待，可剪掉等待、只拼接命令与结果两段。
- UI 演示前先登录、把 Recovery Plans 展开好，录制时直接进入状态。
- 旁白里的数字（136、120/120、80%、30 秒）必须和当场画面一致。

---

## 第一部分：安全与 Human-in-the-Loop（约 75 秒）

### 镜头 1 — 工具清单（终端）｜18 秒
画面：干净终端执行
```powershell
python -c "from src.tools import build_registry; print('\n'.join(sorted(build_registry().keys())))"
```
输出 10 个工具名后，高亮：列表里没有 approve、reject、apply。

旁白：
> 先看我们的安全边界。这是 Agent 能调用的全部工具——注意，里面没有 approve、reject、apply。模型只能读取上下文和生成提议，批准永远不是模型的权限。

### 镜头 2 — 协调员 Recovery Plans 治理列（浏览器）｜30 秒
画面：协调员视图展开 "Recovery Plans"，选一个 PROPOSED 计划，镜头缓慢横移到治理列：Technician changed / Time changed / Customer appointment changed / Approval required / Approval reasons。

旁白：
> 当技术员报告请假或延误，系统会生成恢复方案。每一条变更都标注：是否换了技术员、是否改了时间、是否需要人工审批，以及审批原因。此刻——注意——排班还没有被改动，这只是一个提议。

### 镜头 3 — Approve 与 draft 通知（浏览器）｜27 秒
画面：点 "Approve"，刷新后展开 "Customer notification drafts"，指着 "Draft only — no email has been sent"。

旁白：
> 只有协调员点击批准，系统才会在事务里重新校验、再写入排班。客户通知也只是草稿，不会自动发送。高影响的操作，人始终在回路里。

---

## 第二部分：可解释与可审计（约 55 秒）

### 镜头 4 — 候选评估表（浏览器）｜20 秒
画面：切到某个请求详情，滚到 stage 3 "Candidate evaluation" 表格，鼠标划过 合格/被排除/原因/工作量 列。

旁白：
> 再看可解释性。每个推荐背后，都有完整的候选评估：谁合格、谁被排除、为什么——技能不符、认证缺失还是时段冲突，一目了然。

### 镜头 5 — 决策解释 + 工具轨迹（浏览器）｜20 秒
画面：继续下滚到 stage 5 "Explanation" 和 stage 6 "Tool-call trace"，展开 trace 看到几条工具调用记录。

旁白：
> 决策理由由存储的事实生成，不是模型的空话。再往下，是完整的工具调用轨迹和 handoff 记录——整个决策过程可审计，不是黑箱。

### 镜头 6 — 一句收束（承接镜头 5 或切架构图）｜15 秒
旁白：
> 关键设计是：LLM 负责协调和解释，而确定性的 Python 负责裁决和安全。责任分工清晰，这也让下面的量化测试成为可能。

---

## 第三部分：测试与证据（约 80 秒）

### 镜头 7 — 产品测试（终端）｜15 秒
画面：
```powershell
$env:LLM_BACKEND="mock"; python -m pytest tests -q
```
录到最后 `136 passed`，高亮该行。

旁白：
> 再看证据。首先是产品测试——一百三十六个用例全部通过，覆盖意图、调度、改期、治理和多模态。

### 镜头 8 — 离线基准 120/120（终端）｜30 秒
画面：
```powershell
python -m evaluation.system_benchmark.run --mode offline
```
录到终端量化摘要，停在 Request / Scheduling / Disruption / Governance / Robustness 各行和最后 `Failed cases: 0 / 120`。

旁白：
> 接着是我们独立的系统基准，一百二十个离线用例。请求理解、调度可行性、改期最小改动全部满分；治理层的越权变更、审批前修改全部为零；对抗场景的安全失败率百分之百。这些衡量的是确定性正确性和安全。

### 镜头 9 — Live 基准（终端 / CSV）｜25 秒
画面：打开 `results/system_benchmark/summary_metrics.json` 滚到 `agent_live` 段（或展示 `agent_live_results.csv`），指着 task_completion 1.0、handoff 0.8、p50≈29691ms。

旁白：
> 最后是 Live 基准——用真实的 Claude Sonnet 四点五跑四十五个用例。任务完成率百分之百，编排和 handoff 准确率百分之八十，p50 延迟约三十秒。要强调的是：离线的满分是确定性正确性，Live 是真实模型的编排质量，这是两个不同维度，我们不会把它们混为一谈。

### 镜头 10 — 诚实收尾（CSV 高亮 AGT008 行）｜10 秒
画面：在 `agent_live_results.csv` 里高亮唯一 `pass=False` 的 AGT008 行。

旁白：
> Live 里唯一一个边界用例路由与预期不同，但所有安全不变式依然保持——没有越权、没有非法排班。这正是我们把安全放在确定性代码、而不是模型里的原因。

---

## 关键数字对照（录制时确保画面一致）

| 指标 | 值 | 来源 |
|---|---|---|
| 产品测试 | 136 passed | `pytest tests -q` |
| 离线基准 | 120 / 120，Failed 0 | `--mode offline` |
| Request 各项准确率 | 100%，fabrication 0% | summary_metrics.json |
| Scheduling 确定性一致 | 100% | summary_metrics.json |
| Disruption 精确/召回/最小改动 | 100% / 100% / 0% | summary_metrics.json |
| Governance 越权/审批前变更 | 全 0 | summary_metrics.json |
| Robustness 安全失败率 | 100% | summary_metrics.json |
| Live 任务完成率 | 100% (45/45) | agent_live 段 |
| Live handoff / final-state | 80% / 80% | agent_live 段 |
| Live 延迟 p50 / p95 | ≈29.7s / ≈33.0s | agent_live 段 |
| Live 唯一失败用例 | AGT008（路由差异，无安全违规） | agent_live_results.csv |

## 诚实声明（务必保留，评委加分项）

- 离线 100% 是**确定性正确性与安全**，不是模型语言质量。
- Live 是**真实模型编排质量**，与离线是不同维度，不混为一谈。
- Live 成本：网关未上报 provider cost，因此成本标记为不可用（不当作 0）。
- 多模态视觉准确率是**独立评估轨道**，不属于本系统基准。

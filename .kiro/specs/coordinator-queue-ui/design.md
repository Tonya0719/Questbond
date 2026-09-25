# Design Document

## Overview

本设计在不改动任何调度、治理与审计逻辑的前提下，重构协调员视图的队列看板与右侧详情排版。改动集中在两个文件：

- `src/ui/coordinator_view.py`：队列条目的渲染结构（容器包裹）与标签组装逻辑。
- `src/ui/design.py`：主从布局的粘性定位、卡片样式、行高截断、右侧节奏、响应式规则。

不涉及数据库、服务层、Agent、工具或恢复计划逻辑。

核心思路：用「带 key 的容器 + CSS」把当前游离的按钮与元信息合成一张卡片；把左列从写死高度改为粘性定位配合动态最大高度，从而消除两列长度错配与双滚动上下文。

## Architecture

### 当前结构与问题定位

```
st.container(key='dispatch-layout')
└─ st.columns([1, 3])
   ├─ 左列：subheader + text_input + selectbox
   │        └─ st.container(height=620, key='dispatch-queue')   ← 写死高度、独立滚动
   │           └─ 每个工单：st.button(...)                       ← 块 1
   │                        st.markdown(pill + meta)             ← 块 2（游离）
   └─ 右列：render_detail(...)                                   ← 自然增长，约 2000px+
```

### 目标结构

```
st.container(key='dispatch-layout')
└─ st.columns([1, 3])
   ├─ 左列（CSS: position sticky, max-height 动态计算, flex 纵向）
   │   ├─ subheader + text_input + selectbox      ← 不滚动，常驻
   │   └─ st.container(key='dispatch-queue')      ← flex:1, overflow-y:auto（仅列表滚动）
   │       └─ 每个工单：st.container(key='ticket-card[-sel]-{id}')   ← 卡片容器
   │                     ├─ st.button(label)                          ← 无边框，融入卡片
   │                     └─ st.markdown(pill + meta)
   └─ 右列：render_detail(...)
```

### 粘性定位策略

- 在 `:root` 新增 `--queue-top` 变量（约 `5.25rem`，等于 Streamlit 头部高度加上内容区上内边距）。
- 左列内层 vertical block 采用 `position:sticky; top:var(--queue-top); max-height:calc(100vh - var(--queue-top) - 1rem); display:flex; flex-direction:column; min-height:0`。
- 使用 `max-height` 而非 `height`，满足需求 1.4：条目少时容器按内容收缩，不留空白。
- 列表容器 `.st-key-dispatch-queue` 取 `flex:1 1 auto; min-height:0; overflow-y:auto`，使筛选控件常驻、仅列表内部滚动，满足需求 1.1 与 1.3。
- Python 侧必须移除 `st.container(height=620)` 的 `height` 参数，否则 Streamlit 会注入内联固定高度覆盖 CSS。

### 已知风险与回退

`position:sticky` 会被任意祖先元素的 `overflow:hidden` 失效。若实测发现 Streamlit 的列包装层存在该属性导致粘性失效，回退方案为：保留 `max-height:calc(100vh - ...)` 与内部滚动（仍然解决 620px 长度错配与空白问题），并在实现说明中记录粘性未生效的原因，而不是改用 JavaScript 强行实现。

## Components and Interfaces

### 1. 队列标签组装（`src/ui/coordinator_view.py` 新增纯函数）

```python
QUEUE_EXCERPT_CHARS = 60

def queue_label(row) -> str:
    """卡片主标签：住户姓名（缺失回退工单号）+ 服务类型（未定则回退原始描述摘要）。"""
    who = row['name'] or row['request_id']
    what = row['subtype'] or queue_excerpt(row['raw_message'])
    return f"{who} — {what}"

def queue_excerpt(message) -> str:
    """把原始描述整理成可读摘要：先格式化 ISO 时间戳，再截断。"""
```

设计约定：

- 先调用 `customer_text()`（来自 `src/services/customer_response.py`，已实现 ISO 时间戳转人类可读）再截断，避免把时间戳截断到一半，满足需求 4.5。
- 截断使用省略号；空描述回退为固定占位文案。
- 该函数为纯函数，便于单元测试。

### 2. 卡片渲染契约（`src/ui/coordinator_view.py`）

```python
for row in visible:
    label, tone = ticket_status(row)
    selected = row['request_id'] == st.session_state['dispatch_request']
    card_key = f"ticket-card-{'sel-' if selected else ''}{row['request_id']}"
    with st.container(key=card_key):
        if st.button(queue_label(row), key=f"ticket_{row['request_id']}", width='stretch'):
            st.session_state['dispatch_request'] = row['request_id']
            st.rerun()
        st.markdown(pill_and_meta_html(row, label, tone), unsafe_allow_html=True)
```

设计约定：

- Streamlit 的 `st.button` 只接受文本标签，无法内嵌 HTML，因此彩色 pill 必须作为同容器内的第二个块存在；容器负责视觉合成。
- key 前缀采用 `ticket-card-` 与 `ticket-card-sel-`。由于后者包含前者字符串，CSS 属性选择器 `[class*="st-key-ticket-card-"]` 同时命中两者（继承基础卡片样式），`[class*="st-key-ticket-card-sel-"]` 追加选中态样式。
- 按钮不再使用 `type='primary'`：选中态由卡片承担，避免整块紫色填充的沉重观感；同时满足需求 2.3 的非颜色线索要求（加粗左边框）。
- 元信息沿用既有 `text()` 转义，满足需求 4.6。

### 3. CSS 契约（`src/ui/design.py`）

卡片与行高：

```css
[class*="st-key-ticket-card-"]{border:1.5px solid var(--line);border-radius:14px;background:var(--surface);padding:10px 12px;margin-bottom:8px;min-height:92px;display:flex;flex-direction:column;gap:6px;justify-content:center;transition:all 150ms ease}
[class*="st-key-ticket-card-"]:hover{border-color:var(--primary);transform:translateY(-1px);box-shadow:0 8px 18px rgba(99,102,241,.12)}
[class*="st-key-ticket-card-"] .stButton button{min-height:0;border:none;background:transparent;box-shadow:none;padding:0;text-align:left;justify-content:flex-start;font-weight:700}
[class*="st-key-ticket-card-"] .stButton button p{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;line-height:1.4;margin:0}
[class*="st-key-ticket-card-sel-"]{border-color:var(--primary);border-left-width:5px;background:color-mix(in srgb,var(--primary) 7%,var(--surface))}
.dispatch-meta{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
```

- `min-height` 统一卡片高度，配合两行 clamp 满足需求 3.1 与 3.2。
- `.dispatch-meta` 单行截断满足需求 3.3。

右侧节奏（需求 5）：

- 新增 `--stage-gap` 变量统一阶段间距，`.dispatch-stage` 使用该变量。
- `.dispatch-fields` 补齐与 `.dispatch-request` / `.dispatch-stamp` 一致的外边距。
- 两列首个元素清零上边距实现顶部对齐。
- `.dispatch-log` 增加 `overflow-x:auto`，与既有 `.dispatch-scroll` 一致，防止溢出影响左列。

### 4. 响应式规则（需求 6）

移除既有依赖固定子块高度的规则：

```css
.st-key-dispatch-queue [data-testid="stVerticalBlock"]{display:grid;grid-auto-flow:column;grid-template-rows:70px 40px;...}
```

替换为不依赖子块数量与高度的卡片横向滑动：

```css
@media(max-width:700px){
  .st-key-dispatch-layout [data-testid="stColumn"]:first-child>[data-testid="stVerticalBlock"]{position:static;max-height:none}
  .st-key-dispatch-queue{max-height:none;overflow-x:auto;overflow-y:hidden}
  .st-key-dispatch-queue>[data-testid="stVerticalBlock"]{display:flex;flex-direction:row;gap:8px}
  [class*="st-key-ticket-card-"]{flex:0 0 240px;margin-bottom:0}
}
```

- 移动断点下禁用粘性（需求 6.3）。
- 既有全局 `prefers-reduced-motion` 规则已覆盖 `*` 的 transition，卡片动画自动降级（需求 6.4）。

## Data Models

不新增、不修改任何数据模型与数据库结构。队列继续使用 `render()` 中既有查询返回的字段：

| 字段 | 来源 | 卡片用途 |
|---|---|---|
| `request_id` | `customer_requests` | 容器 key、姓名缺失时的标签回退 |
| `name` | `request_contacts` | 主标签首选 |
| `subtype` | `structured_requests` | 主标签的问题描述首选 |
| `raw_message` | `customer_requests` | 服务类型未定时的摘要来源 |
| `apartment` / `zone` | `request_contacts` / `structured_requests` | 元信息 |
| `job_id` | `booking_confirmations` | 状态判定（已预订） |
| `workflow_status` | `agent_sessions` 子查询 | 状态判定与 pill 色彩 |

## Error Handling

- **字段缺失**：`name` 缺失回退 `request_id`；`subtype` 缺失回退原始描述摘要；`apartment` 与 `zone` 均缺失时显示明确占位文案（需求 4.7）。
- **空原始描述**：`queue_excerpt` 对空值或 `None` 返回固定占位文案，不得抛出异常。
- **HTML 注入**：pill 与元信息经 `text()` 转义（需求 4.6）。
- **Markdown 误渲染**：`st.button` 的标签按 Markdown 解析，原始描述中的 `*`、`_`、`` ` `` 等字符可能被解释为强调语法。`queue_excerpt` 需对这些字符做转义或剥离，保证列表显示为字面文本。
- **粘性失效**：若祖先 `overflow` 导致 sticky 无效，按 Architecture 中的回退方案处理，不引入 JavaScript。

## Correctness Properties

### Property 1: 选中唯一性

任意时刻 `st.session_state['dispatch_request']` 恰好对应一个工单。若其值不在当前工单集合内，系统回退到第一个工单（既有行为，必须保持）。

**Validates: Requirements 2.5, 7.4**

### Property 2: 筛选与选中解耦

搜索与 Show 筛选只影响可见集合，不改变已选中的 `request_id`；右侧详情始终渲染 `dispatch_request` 对应的工单。

**Validates: Requirements 7.1, 7.2**

### Property 3: 卡片与工单一一对应

渲染的卡片容器数量恒等于筛选后可见工单数，且每个容器 key 由 `request_id` 保证唯一。

**Validates: Requirements 2.1, 7.3**

### Property 4: 转义不变式

任何住户或模型产生的文本进入 HTML 之前必须经过转义，队列与详情两处均不例外。

**Validates: Requirements 4.6**

### Property 5: 样式不依赖内容长度

卡片高度与截断行为不因标签长短而破坏布局；响应式规则不依赖子块数量或写死高度。

**Validates: Requirements 3.1, 3.2, 6.2**

### Property 6: 行为保持

本次改动不触及排班、治理、审批与审计路径；相同输入在改动前后产生相同的数据库写入与工作流状态。

**Validates: Requirements 7.5, 7.6**

## Testing Strategy

### 单元测试（新增）

针对 `queue_label` 与 `queue_excerpt` 的纯函数测试：

1. 有 `name` 时使用姓名；`name` 为空时回退 `request_id`。
2. 有 `subtype` 时使用服务类型；为空时使用原始描述摘要。
3. 原始描述中的 ISO 时间戳被转换为可读格式。
4. 超长描述被截断且带省略号；截断不破坏已格式化的时间戳。
5. 空描述或 `None` 返回占位文案且不抛异常。
6. Markdown 特殊字符不被解释为强调语法。

### 界面测试（扩展既有 AppTest）

1. 队列渲染的卡片数量等于筛选后可见工单数。
2. 点击某张卡片后 `dispatch_request` 更新且右侧详情切换到该工单。
3. 搜索框与 Show 筛选的行为与改动前一致（需求 7.1、7.2）。
4. 筛选无结果时显示无匹配提示（需求 7.3）。
5. 选中工单后右侧六个阶段照常渲染（需求 7.4）。
6. 恢复计划区与审批、拒绝、重算动作行为不变（需求 7.5，复用既有 `tests/test_coordinator_recovery_ui.py`）。

### 无法自动断言的部分

粘性定位、卡片外观、行高一致性与响应式表现无法通过 AppTest 断言（AppTest 不渲染 CSS）。这些由人工验证清单覆盖：

1. 桌面视口滚动右侧长详情时，左列队列保持可见。
2. 队列条目少时左列下方无固定高度造成的空白。
3. 所有卡片高度一致，长标签截断为两行。
4. 选中卡片具备颜色之外的线索（加粗左边框）。
5. 窄屏下队列变为横向滑动且不遮挡内容。

### 回归门槛

既有 147 项自动化测试必须全部通过，且不得为通过测试而修改产品行为（需求 7.6）。

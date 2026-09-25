# Requirements Document

## Introduction

协调员工作台采用「左侧队列 + 右侧详情」的主从布局，但当前左列写死 620px 固定高度并带独立内部滚动，右列随内容自然增长（通常 2000px 以上），导致两列长度严重不匹配、页面出现两个互相争抢的滚动上下文。同时队列中每个工单由「按钮」与「状态 pill + 元信息」两个游离的 Streamlit 块组成，没有共同容器，视觉上像散落的文字；按钮文案长度不定造成行高参差；移动端 CSS 以固定行高耦合 DOM 顺序，结构一改即失效。

本需求覆盖协调员视图的队列看板重构与右侧详情区的排版节奏调整，目标是在不改变任何调度、治理与审计行为的前提下，得到一个整齐、稳定、可用的主从界面。

## Glossary

- **队列（Queue）**：协调员视图左列的工单列表看板。
- **详情（Detail）**：右列按六个阶段展示的单个工单内容（请求、抽取、候选评估、决策、解释、Agent 活动）。
- **卡片（Card）**：队列中代表单个工单的可点击视觉单元。
- **状态 pill**：卡片上表示工单状态的圆角标签，沿用 pending / resolved / conflict 色彩语义。
- **粘性定位（sticky）**：CSS `position: sticky`，使队列在页面滚动时保持可见。
- **移动断点**：既有样式中 `max-width: 700px` 的响应式断点。

## Requirements

### Requirement 1: 主从布局的高度与滚动策略

**User Story:** 作为协调员，我希望在阅读右侧工单详情时左侧队列始终可见，这样我可以随时切换工单而不必把页面滚回顶部。

#### Acceptance Criteria

1. WHEN 协调员在桌面视口浏览工作台 THEN 左侧队列列 SHALL 采用粘性定位，固定在应用头部下方并在页面滚动时保持可见。
2. WHEN 右侧详情内容高度超过视口 THEN 页面 SHALL 只有一个主滚动上下文，且左侧队列 SHALL NOT 随页面滚动而移出视野。
3. WHEN 队列条目总高度超过可用视口高度 THEN 队列 SHALL 在自身区域内滚动，其最大高度 SHALL 由视口高度减去头部与内边距动态计算得出，而非写死像素值。
4. WHEN 队列条目较少且总高度不足最大高度 THEN 队列容器 SHALL 按内容收缩，SHALL NOT 在下方留出固定高度造成的空白。
5. WHEN 协调员使用键盘 Tab 在队列中移动焦点 THEN 被聚焦的条目 SHALL 自动滚入可见区域。

### Requirement 2: 队列条目呈现为单一视觉卡片

**User Story:** 作为协调员，我希望每个工单在队列中是一张完整的卡片，这样状态与住户信息看起来属于该工单，而不是漂浮在旁边的文字。

#### Acceptance Criteria

1. WHEN 队列渲染一个工单 THEN 该工单的主标签、状态 pill 与元信息 SHALL 包裹在同一个带 key 的容器内，并通过 CSS 呈现为单一卡片，具备统一的边框、圆角、内边距与背景。
2. WHEN 工单具有状态 THEN 该状态 SHALL 以彩色 pill 呈现，并沿用既有的 pending / resolved / conflict 色彩语义。
3. WHEN 某个工单为当前选中项 THEN 该卡片 SHALL 具备明显的选中态，且该选中态 SHALL NOT 仅依赖颜色区分。
4. WHEN 协调员将鼠标悬停于卡片 THEN 卡片 SHALL 给出与项目既有按钮一致的悬停反馈。
5. WHEN 协调员点击卡片 THEN 系统 SHALL 选中该工单并刷新右侧详情。

### Requirement 3: 一致的行高与文本截断

**User Story:** 作为协调员，我希望队列条目高度整齐，这样我能快速扫视列表。

#### Acceptance Criteria

1. WHEN 工单主标签文本过长 THEN 该标签 SHALL 最多显示两行，超出部分 SHALL 以省略号截断。
2. WHEN 队列包含长短不一的标签 THEN 所有卡片 SHALL 具有一致的最小高度，列表 SHALL NOT 呈现参差不齐的行高。
3. WHEN 元信息过长 THEN 其 SHALL 单行截断，SHALL NOT 将卡片撑高。

### Requirement 4: 队列信息层级与可读性

**User Story:** 作为协调员，我希望在列表里就能看懂每条工单是谁、什么问题、什么状态，包括住户的原始描述。

#### Acceptance Criteria

1. WHEN 工单存在住户姓名 THEN 卡片主标签 SHALL 优先显示住户姓名。
2. WHEN 住户姓名缺失 THEN 卡片主标签 SHALL 回退显示工单号。
3. WHEN 工单已完成服务类型抽取 THEN 卡片 SHALL 显示该服务类型。
4. WHEN 服务类型尚未确定 THEN 卡片 SHALL 显示住户原始描述的摘要。
5. WHEN 展示的文本中包含 ISO 格式时间戳 THEN 系统 SHALL 将其转换为人类可读的日期时间格式后再显示。
6. WHEN 展示任何住户或模型产生的内容 THEN 系统 SHALL 对其进行 HTML 转义。
7. WHEN 工单的区域与单元信息均缺失 THEN 卡片 SHALL 显示明确的占位说明。

### Requirement 5: 右侧详情区的排版节奏

**User Story:** 作为协调员，我希望右侧六个阶段的间距统一，这样长页面读起来不费力。

#### Acceptance Criteria

1. WHEN 右侧详情渲染多个阶段 THEN 相邻阶段之间的垂直间距 SHALL 一致。
2. WHEN 阶段内包含请求原文、抽取字段、决策结论或解释等卡片类元素 THEN 这些卡片的外边距与内边距 SHALL 统一。
3. WHEN 详情区与左侧队列并排显示 THEN 两列顶部 SHALL 对齐。
4. WHEN 右侧包含表格或日志等可能溢出的内容 THEN 其 SHALL 在自身容器内横向滚动，SHALL NOT 撑破列宽或影响左列布局。

### Requirement 6: 响应式与结构解耦

**User Story:** 作为维护者，我希望响应式样式不依赖 DOM 子元素的固定顺序和固定高度，这样以后调整结构不会让样式崩掉。

#### Acceptance Criteria

1. WHEN 视口宽度进入移动断点 THEN 队列 SHALL 切换为适合窄屏的呈现方式，且该样式 SHALL NOT 依赖每项恰好为两个子块或写死的子块高度。
2. WHEN 队列条目的内部结构发生变化 THEN 既有响应式规则 SHALL 仍然生效，SHALL NOT 出现错位。
3. WHEN 视口处于移动断点 THEN 粘性定位 SHALL 被禁用或降级，SHALL NOT 遮挡内容。
4. WHEN 用户系统设置为 prefers-reduced-motion THEN 卡片的过渡动画 SHALL 被禁用。

### Requirement 7: 行为与既有能力不回归

**User Story:** 作为协调员，我希望这次只是外观变好，所有既有功能照常工作。

#### Acceptance Criteria

1. WHEN 协调员在搜索框输入住户、单元或问题关键字 THEN 队列筛选行为 SHALL 与改动前一致。
2. WHEN 协调员切换 Show 筛选 THEN 筛选行为 SHALL 与改动前一致。
3. WHEN 队列筛选后无匹配结果 THEN 系统 SHALL 显示无匹配提示。
4. WHEN 协调员选中任一工单 THEN 右侧六个阶段 SHALL 照常渲染。
5. WHEN 本需求实现完成 THEN 恢复计划区、审批与拒绝与重算动作、通知草稿 SHALL 保持原有行为不变。
6. WHEN 本需求实现完成 THEN 既有自动化测试 SHALL 全部通过，且 SHALL NOT 为通过测试而修改产品行为。

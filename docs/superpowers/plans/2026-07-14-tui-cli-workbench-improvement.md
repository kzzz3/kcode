# KCode TUI/CLI 工作台改进 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前可演示但简陋且存在集成断点的 TUI，升级为稳定、紧凑、键盘优先的编码工作台，并让 TUI 与传统 CLI 共享同一套运行时装配和行为契约。

**Architecture:** 保留 Textual、`CliAgentRuntime`、现有工具注册和 SQLite 会话体系。先用共享 `RuntimeFactory` 消除 CLI/TUI 的装配漂移，再用三个薄控制器隔离同步流式迭代、审批和会话管理；现有 Widget 逐步改造成工作台布局，不做框架替换或一次性重写。

**Tech Stack:** Python 3.13、Textual、Rich、Typer、Pydantic v2、SQLite、pytest、Textual Pilot、ruff、mypy。

---

## 1. 范围与非目标

本计划只覆盖：

- 默认启动的 Textual TUI；
- `kcode chat` 及根命令参数与 TUI 的一致性；
- TUI 所依赖的运行时装配、流式消费、审批和会话接口；
- TUI 视觉系统、响应式布局、键盘操作和交互测试；
- 与实际行为直接相关的 CLI 文档、版本展示和配置示例。

本计划明确不覆盖：

- Desktop、Electron、Tauri、PyWebView 或 WebSocket/IPC；
- 新模型供应商、新工具协议或 MCP 能力扩展；
- 多仓库工作区、远程会话同步、账号体系；
- 为了视觉效果引入新的前端框架；
- 与 TUI/CLI 体验无关的核心层重构。

## 2. 当前状态与问题证据

### 2.1 已有基础

- `CliAgentRuntime.step_stream()` 已能同步产出文本、工具调用和最终快照。
- CLI 已正确使用 `for` 消费同步流，并实现 Rich 审批提示。
- TUI 已有 ChatArea、InputArea、StatusBar、SessionPanel、SlashOverlay、ApprovalDialog 等组件。
- SQLite 已提供 SessionRecord、MessageRecord 和 ToolRunRecord。
- 当前测试覆盖运行时、CLI、Widget 基础状态和命令过滤。

### 2.2 P0 级集成断点

| 问题 | 证据 | 后果 |
|---|---|---|
| 流式契约错配 | `main_screen.py` 用 `async for` 消费同步 Iterator | 首次发送可能直接抛出 TypeError |
| 快照字段错配 | TUI 读取 `tokens_used`、`cost_usd`、`context_usage` | 回合完成后可能抛出 AttributeError |
| 审批没有接线 | ApprovalDialog 未作为 runtime callback 使用，TUI 默认 auto | manual 无交互，auto 缺少显著风险反馈 |
| 工作区参数丢失 | 根命令接收 `--workspace`，`KCodeTUI()` 不接收 | TUI 始终使用 `Path.cwd()` |
| 会话模型错配 | TUI 使用不存在的 SessionRecord 字段并错误重建消息 | 列表、恢复、新建无法可靠工作 |
| 取消不完整 | Escape 只更新 UI 状态 | 后台生成仍可能继续并回写过期内容 |
| 异常被吞掉 | 多处 `except Exception: pass` | 集成错误没有可见诊断 |

### 2.3 视觉与信息架构问题

- 主界面只有 Header、带边框的 ChatArea、InputArea、固定宽度 SessionPanel、StatusBar 和 Footer，信息主次不清。
- Header、StatusBar、Footer 重复显示状态、模型或快捷键。
- 用户和助手消息依赖大面积彩色 Panel，连续对话显得碎片化。
- 欢迎页使用大型 ASCII 标题，占用首屏，却没有展示仓库、分支、模型和审批状态。
- 工具调用没有形成可扫描的执行时间线，工具参数、耗时、结果和错误缺少统一呈现。
- SessionPanel 固定 30 列，没有响应式折叠、搜索、当前会话强调或更新时间。
- StatusBar 把状态、模型、审批、tokens、cost、context、step 和快捷键拼在一行，窄终端容易溢出。

## 3. 目标体验

### 3.1 默认宽屏布局

```text
┌ KCode  repo / branch              model                 session ┐
│                                                               │
│  YOU      修改认证失败后的重试逻辑                SESSIONS    │
│                                                    ● 当前会话  │
│  KCODE    我先检查相关模块。                       昨天的会话  │
│           ✓ read_file        24 ms                ACTIVITY    │
│           ● run_command      pytest -q            2 tools     │
│           正在分析测试结果……                                  │
│                                                               │
├───────────────────────────────────────────────────────────────┤
│ 输入消息；Enter 发送，Shift+Enter 换行                  Send  │
│ manual approval · context 42% · step 2 · streaming            │
└───────────────────────────────────────────────────────────────┘
```

### 3.2 响应式规则

| 终端宽度 | 行为 |
|---|---|
| `< 100` 列 | 隐藏右侧活动栏，通过 `Ctrl+B` 打开覆盖层；状态行只保留状态、审批和 context |
| `100-149` 列 | 显示紧凑右栏；隐藏低优先级耗时和快捷键说明 |
| `>= 150` 列 | 显示完整会话、活动、模型和 token 信息 |

最小支持尺寸为 `80x24`。布局变化只能改变信息密度，不得改变功能可达性。

### 3.3 视觉规则

- 主背景使用中性色，不使用大面积主题色背景。
- 青色只表示焦点、链接和当前选择；绿色表示成功；琥珀色表示等待审批；红色表示失败。
- Transcript 不使用每条消息一个完整卡片；用 8-10 列角色栏、内容区和轻量分隔建立层级。
- 只给 Composer、Modal 和覆盖层使用明确边框；页面区块不套娃。
- 所有图标使用终端稳定字符，并始终带文本或 tooltip/说明，不能只靠颜色传达状态。
- 欢迎状态最多占 8 行，展示工作区、模型、审批模式和三个高频入口。

## 4. 目标文件边界

### 新增文件

| 文件 | 单一职责 |
|---|---|
| `apps/cli/src/core/runtime_factory.py` | 根据 RuntimeOptions 创建模型、工具、会话库和 CliAgentRuntime |
| `apps/cli/src/tui/controllers/turn_controller.py` | 在线程 Worker 中消费同步 stream，处理取消和过期回合 |
| `apps/cli/src/tui/controllers/approval_controller.py` | 把同步审批回调桥接到 Textual ApprovalDialog |
| `apps/cli/src/tui/controllers/session_controller.py` | 列表、新建、恢复当前工作区会话 |
| `apps/cli/src/tui/styles/theme.tcss` | 颜色、间距和状态样式 token |
| `apps/cli/src/tui/styles/workbench.tcss` | 主布局和三档响应式规则 |
| `apps/cli/tests/test_runtime_factory.py` | CLI/TUI 共享装配测试 |
| `apps/cli/tests/test_tui_turn_flow.py` | Textual Pilot 回合、取消、错误测试 |
| `apps/cli/tests/test_tui_approval_flow.py` | manual/auto 审批流程测试 |
| `apps/cli/tests/test_tui_session_flow.py` | 会话列表、新建和恢复测试 |
| `apps/cli/tests/test_tui_layout.py` | 80/120/160 列布局断言 |

### 修改文件

| 文件 | 修改边界 |
|---|---|
| `apps/cli/src/kcode_cli.py` | 将 workspace/debug 传入 TUI；版本从包元数据读取 |
| `apps/cli/src/commands/chat.py` | 使用 RuntimeFactory，保留终端渲染与 Confirm 适配器 |
| `apps/cli/src/tui/app.py` | 接收启动选项、加载 TCSS、关闭资源、持有控制器 |
| `apps/cli/src/tui/screens/main_screen.py` | 只保留消息路由和屏幕编排，移除运行时私有字段访问 |
| `apps/cli/src/tui/widgets/chat_area.py` | 改为无卡片 Transcript 和工具时间线 |
| `apps/cli/src/tui/widgets/input_area.py` | 改为多行 Composer，稳定处理发送/换行/禁用状态 |
| `apps/cli/src/tui/widgets/session_panel.py` | 改为响应式 Activity/Session Rail |
| `apps/cli/src/tui/widgets/status_bar.py` | 改为按宽度降级的单行状态摘要 |
| `apps/cli/src/tui/widgets/approval_dialog.py` | 明确焦点、默认拒绝和参数预览 |
| `packages/core/src/runtime/session.py` | 支持按 workspace_root 过滤会话，不引入 UI 依赖 |
| `apps/cli/tests/test_kcode_cli.py` | 根参数和 TUI 启动参数测试 |
| `apps/cli/tests/test_tui_widgets.py` | 新视觉状态和组件消息测试 |
| `README.md`、`docs/cli/01-cli-overview.md` | 同步真实命令、配置和 TUI 快捷键 |

## 5. 实施里程碑

## Milestone A：建立可回归的运行基线

### Task 1：为现有 TUI 集成断点建立失败测试

**Files:**
- Create: `apps/cli/tests/test_tui_turn_flow.py`
- Create: `apps/cli/tests/test_tui_session_flow.py`
- Modify: `apps/cli/tests/test_kcode_cli.py`

- [ ] **Step 1: 写根命令参数传递测试**

  使用 `CliRunner` monkeypatch `_launch_tui`，断言 `kcode --workspace <tmp> --debug` 将解析后的绝对路径和 `True` 传给启动函数。

- [ ] **Step 2: 运行测试并确认失败原因**

  ```powershell
  conda run -n expr python -m pytest apps/cli/tests/test_kcode_cli.py -v
  ```

  Expected: FAIL，原因是 `_launch_tui()` 当前不接收 workspace/debug。

- [ ] **Step 3: 写 TUI 首回合 Pilot 测试**

  构造只产生 `TEXT -> DONE -> AgentSnapshot` 的 StubStreamingModel，使用 `app.run_test(size=(120, 30))` 输入消息，断言最终出现助手文本且状态回到 `finished`。

- [ ] **Step 4: 写会话字段契约测试**

  创建两个不同 workspace 的 SessionRecord，断言 TUI 只展示当前 workspace，并使用 `id`、`title`、`updated_at`。

- [ ] **Step 5: 运行新增测试，保存准确失败信息**

  ```powershell
  conda run -n expr python -m pytest apps/cli/tests/test_tui_turn_flow.py apps/cli/tests/test_tui_session_flow.py -v
  ```

  Expected: FAIL，分别暴露同步 Iterator、错误 SessionRecord 字段或缺少 workspace 过滤。

- [ ] **Step 6: 提交测试基线**

  ```powershell
  git add apps/cli/tests/test_kcode_cli.py apps/cli/tests/test_tui_turn_flow.py apps/cli/tests/test_tui_session_flow.py
  git commit -m "test(tui): capture runtime and session integration gaps"
  ```

### Task 2：统一 CLI/TUI 的运行时装配

**Files:**
- Create: `apps/cli/src/core/runtime_factory.py`
- Create: `apps/cli/tests/test_runtime_factory.py`
- Modify: `apps/cli/src/commands/chat.py`
- Modify: `apps/cli/src/tui/app.py`
- Modify: `apps/cli/src/kcode_cli.py`

- [ ] **Step 1: 定义共享启动契约测试**

  测试以下不可变契约：workspace 必须 resolve；会话库固定为 `<workspace>/.kcode/sessions.sqlite`；model、max_steps、approval、debug 和完整 ModelProviderConfig 不得丢失。

- [ ] **Step 2: 定义 RuntimeOptions**

  ```python
  @dataclass(frozen=True)
  class RuntimeOptions:
    workspace_root: Path
    model_name: str | None = None
    max_steps: int = 50
    approval_mode: ApprovalMode | None = None
    debug: bool = False
  ```

  `build_runtime(options, *, on_approve=None, session=None, initial_messages=None)` 返回包含 runtime 和可关闭 SessionStore 的 `RuntimeBundle`。Factory 不能导入 Textual、Rich 或 Typer。

- [ ] **Step 3: 让 CLI 使用 Factory**

  `run_chat()` 只负责 Typer 参数、Rich 输出和 Confirm callback；删除重复的 ModelClient、ToolRegistry、SessionStore 装配代码。

- [ ] **Step 4: 让 TUI 接收显式启动选项**

  `KCodeTUI.__init__(workspace_root: Path, debug: bool = False)` 保存 options；根 callback 和隐藏 `tui` 命令都必须传递同一参数。

- [ ] **Step 5: 在退出路径关闭 SessionStore**

  正常退出和启动失败都只关闭一次；测试通过 fake store 断言 `close()` 被调用。

- [ ] **Step 6: 运行聚焦测试**

  ```powershell
  conda run -n expr python -m pytest apps/cli/tests/test_runtime_factory.py apps/cli/tests/test_kcode_cli.py apps/cli/tests/test_chat_unit.py -v
  ```

  Expected: PASS。

- [ ] **Step 7: 提交共享装配**

  ```powershell
  git add apps/cli/src/core/runtime_factory.py apps/cli/src/commands/chat.py apps/cli/src/tui/app.py apps/cli/src/kcode_cli.py apps/cli/tests
  git commit -m "refactor(cli): share runtime construction with tui"
  ```

## Milestone B：接通回合、审批和会话

### Task 3：用 TurnController 正确消费同步流并隔离取消

**Files:**
- Create: `apps/cli/src/tui/controllers/turn_controller.py`
- Modify: `apps/cli/src/tui/screens/main_screen.py`
- Modify: `apps/cli/src/tui/widgets/chat_area.py`
- Test: `apps/cli/tests/test_tui_turn_flow.py`

- [ ] **Step 1: 扩展失败测试**

  覆盖文本增量、工具开始/参数/结束、最终 AgentSnapshot、模型异常和连续两次回合。断言 UI 只消费当前 generation id 的事件。

- [ ] **Step 2: 定义 UI 事件类型**

  ```python
  @dataclass(frozen=True)
  class TurnText:
    turn_id: int
    delta: str

  @dataclass(frozen=True)
  class TurnFinished:
    turn_id: int
    snapshot: AgentSnapshot

  @dataclass(frozen=True)
  class TurnFailed:
    turn_id: int
    message: str
  ```

  Controller 在线程 Worker 中使用普通 `for` 消费 `runtime.step_stream()`；Widget 不直接访问 runtime 私有字段。

- [ ] **Step 3: 实现逻辑取消**

  Escape 增加 generation id、取消 Worker、立刻恢复 Composer；后续到达的旧 turn 事件必须被丢弃。若底层 HTTP 正阻塞，UI 仍不得被旧结果覆盖。

- [ ] **Step 4: 从 snapshot.metadata 更新状态**

  只读取 `model`、`token_count`、`context_utilization`、`session_id`；cost 只有收到 usage 且能可靠计算时才展示，不能读取不存在的 dataclass 字段。

- [ ] **Step 5: 运行测试**

  ```powershell
  conda run -n expr python -m pytest apps/cli/tests/test_tui_turn_flow.py apps/cli/tests/test_agent_streaming.py -v
  ```

  Expected: PASS，且没有 `async for` 消费同步 Iterator。

- [ ] **Step 6: 提交回合控制器**

  ```powershell
  git add apps/cli/src/tui/controllers/turn_controller.py apps/cli/src/tui/screens/main_screen.py apps/cli/src/tui/widgets/chat_area.py apps/cli/tests/test_tui_turn_flow.py
  git commit -m "fix(tui): make streaming turns cancellable and contract-safe"
  ```

### Task 4：把安全审批接入 ApprovalDialog

**Files:**
- Create: `apps/cli/src/tui/controllers/approval_controller.py`
- Modify: `apps/cli/src/tui/app.py`
- Modify: `apps/cli/src/tui/widgets/approval_dialog.py`
- Modify: `apps/cli/src/tui/widgets/status_bar.py`
- Create: `apps/cli/tests/test_tui_approval_flow.py`

- [ ] **Step 1: 写 manual/auto 失败测试**

  manual 模式下，write/system/network 工具必须在执行前显示 Dialog；默认焦点是 Deny；Escape 等价于 Deny。auto 模式不显示 Dialog，但状态栏使用琥珀色 `AUTO APPROVE`。

- [ ] **Step 2: 实现同步 callback 到 UI 的桥接**

  ApprovalController 运行在 TurnController 的工作线程：通过 `app.call_from_thread()` 打开 Modal，用 `threading.Event` 等待用户结果。Controller 只返回 bool，不在 core runtime 引入 Textual 类型。

- [ ] **Step 3: 定义参数预览规则**

  隐藏 `workspace_root`、allowlist、blocklist 和疑似 secret 字段；content 最多显示 12 行或 800 字符；run_command 必须突出命令和 cwd；edit/create 必须突出相对路径。

- [ ] **Step 4: 明确状态机**

  Dialog 打开时显示 `awaiting_approval`；结果返回后进入 `tool_running` 或回到 `thinking`。关闭 TUI 或取消回合时，所有等待中的审批一律返回 False。

- [ ] **Step 5: 运行审批测试**

  ```powershell
  conda run -n expr python -m pytest apps/cli/tests/test_tui_approval_flow.py apps/cli/tests/test_approval_mode.py -v
  ```

  Expected: PASS。

- [ ] **Step 6: 提交审批闭环**

  ```powershell
  git add apps/cli/src/tui/controllers/approval_controller.py apps/cli/src/tui/app.py apps/cli/src/tui/widgets/approval_dialog.py apps/cli/src/tui/widgets/status_bar.py apps/cli/tests/test_tui_approval_flow.py
  git commit -m "feat(tui): connect manual approval dialog to runtime"
  ```

### Task 5：修复按工作区隔离的会话生命周期

**Files:**
- Create: `apps/cli/src/tui/controllers/session_controller.py`
- Modify: `packages/core/src/runtime/session.py`
- Modify: `apps/cli/src/tui/screens/main_screen.py`
- Modify: `apps/cli/src/tui/widgets/session_panel.py`
- Test: `apps/cli/tests/test_tui_session_flow.py`
- Test: `packages/core/tests/test_session_store.py`

- [ ] **Step 1: 为 SessionStore 写 workspace 过滤测试**

  创建两个 workspace、三个会话，断言 `list_sessions(workspace_root=path)` 只返回目标 workspace，并按 `updated_at DESC, created_at DESC` 排序。

- [ ] **Step 2: 扩展 SessionStore 查询签名**

  ```python
  def list_sessions(
    self,
    limit: int = 50,
    *,
    workspace_root: Path | None = None,
  ) -> list[SessionRecord]:
  ```

  保留现有位置参数 `list_sessions(30)` 和关键字参数 `list_sessions(limit=30)` 调用方式；`workspace_root=None` 继续表示全局查询。

- [ ] **Step 3: SessionController 使用真实记录类型**

  列表只读取 `id/title/updated_at`；恢复时把 MessageRecord 映射成 models.interfaces.Message；新建会话通过 RuntimeFactory 创建新 bundle，禁止写 `runtime._session = None`。

- [ ] **Step 4: 定义恢复失败行为**

  会话不存在、workspace 不匹配或消息损坏时，保留当前会话并显示可见错误；不能清空当前 Transcript，也不能静默吞错。

- [ ] **Step 5: 运行会话测试**

  ```powershell
  conda run -n expr python -m pytest packages/core/tests/test_session_store.py apps/cli/tests/test_tui_session_flow.py -v
  ```

  Expected: PASS。

- [ ] **Step 6: 提交会话闭环**

  ```powershell
  git add packages/core/src/runtime/session.py apps/cli/src/tui/controllers/session_controller.py apps/cli/src/tui/screens/main_screen.py apps/cli/src/tui/widgets/session_panel.py packages/core/tests/test_session_store.py apps/cli/tests/test_tui_session_flow.py
  git commit -m "fix(tui): make sessions workspace-scoped and resumable"
  ```

## Milestone C：重建工作台视觉层级

### Task 6：建立主题 token 和响应式 Shell

**Files:**
- Create: `apps/cli/src/tui/styles/theme.tcss`
- Create: `apps/cli/src/tui/styles/workbench.tcss`
- Modify: `apps/cli/src/tui/app.py`
- Modify: `apps/cli/src/tui/screens/main_screen.py`
- Create: `apps/cli/tests/test_tui_layout.py`

- [ ] **Step 1: 写三档布局测试**

  使用 `run_test(size=(80, 24))`、`(120, 30)`、`(160, 40)`；断言 Composer 始终可见，Transcript 高度大于 8，右栏分别为 hidden/compact/full，且不存在横向滚动。

- [ ] **Step 2: 定义颜色和间距 token**

  ```css
  $surface: #111317;
  $surface-raised: #181b20;
  $text: #e6e8eb;
  $text-muted: #8b929c;
  $accent: #39c5cf;
  $success: #45c486;
  $warning: #e7b95e;
  $error: #ef6b73;
  ```

  不允许 Widget 自行发明新的语义颜色；边框只使用 raised、accent、warning、error 四种状态。

- [ ] **Step 3: 重组 Shell**

  主屏幕只包含 WorkspaceBar、正文 Horizontal、ComposerDock、StatusBar。删除 Footer 的重复快捷键；快捷键放入 Help/Command overlay。

- [ ] **Step 4: 实现响应式 class 切换**

  屏幕 resize 时只切换 `narrow`、`medium`、`wide` class；Widget 根据 class 控制显示，不在 render() 中拼接宽度特例。

- [ ] **Step 5: 运行布局测试**

  ```powershell
  conda run -n expr python -m pytest apps/cli/tests/test_tui_layout.py -v
  ```

  Expected: 三种尺寸全部 PASS。

- [ ] **Step 6: 提交工作台骨架**

  ```powershell
  git add apps/cli/src/tui/styles apps/cli/src/tui/app.py apps/cli/src/tui/screens/main_screen.py apps/cli/tests/test_tui_layout.py
  git commit -m "feat(tui): introduce responsive workbench shell"
  ```

### Task 7：把 ChatArea 改造成 Transcript 和工具时间线

**Files:**
- Modify: `apps/cli/src/tui/widgets/chat_area.py`
- Modify: `apps/cli/src/tui/screens/main_screen.py`
- Modify: `apps/cli/tests/test_tui_widgets.py`
- Modify: `apps/cli/tests/test_tui_turn_flow.py`

- [ ] **Step 1: 写消息层级测试**

  用户、助手、系统错误和工具行必须有独立语义 class；连续助手增量更新同一个节点；消息内容不能因 hover、状态或工具结果出现而改变布局宽度。

- [ ] **Step 2: 缩减欢迎状态**

  欢迎区只展示 `KCode`、workspace、model、approval 和 `Type a message or / for commands`，总高度不超过 8 行；删除大型 ASCII Banner。

- [ ] **Step 3: 改造消息行**

  角色栏固定 8-10 列，正文可复制并自然换行；不为每条消息绘制完整 Panel。代码块与 diff 保留 Rich syntax highlighting，但宽度不能撑破 Transcript。

- [ ] **Step 4: 增加工具时间线状态**

  每个工具行包含状态符号、工具名、核心参数摘要和耗时；running、success、denied、failed 使用一致语义。默认折叠长输出，Enter 展开，第二次 Enter 收起。

- [ ] **Step 5: 保证自动滚动可控**

  用户停留在底部时跟随流；用户向上滚动后停止抢焦点并显示 `New output`；按 End 恢复跟随。

- [ ] **Step 6: 运行组件与回合测试**

  ```powershell
  conda run -n expr python -m pytest apps/cli/tests/test_tui_widgets.py apps/cli/tests/test_tui_turn_flow.py -v
  ```

  Expected: PASS。

- [ ] **Step 7: 提交 Transcript**

  ```powershell
  git add apps/cli/src/tui/widgets/chat_area.py apps/cli/src/tui/screens/main_screen.py apps/cli/tests/test_tui_widgets.py apps/cli/tests/test_tui_turn_flow.py
  git commit -m "feat(tui): redesign transcript and tool timeline"
  ```

### Task 8：改造 Composer、状态栏和 Activity Rail

**Files:**
- Modify: `apps/cli/src/tui/widgets/input_area.py`
- Modify: `apps/cli/src/tui/widgets/status_bar.py`
- Modify: `apps/cli/src/tui/widgets/session_panel.py`
- Modify: `apps/cli/src/tui/widgets/slash_overlay.py`
- Modify: `apps/cli/tests/test_tui_widgets.py`
- Modify: `apps/cli/tests/test_slash_overlay.py`
- Modify: `apps/cli/tests/test_tui_layout.py`

- [ ] **Step 1: 明确 Composer 键盘契约**

  Enter 发送，Shift+Enter 换行，Escape 取消当前流或关闭 overlay，Ctrl+Up/Down 浏览输入历史。流式期间 Composer 可继续编辑，但发送按钮显示 Stop 并执行取消。

- [ ] **Step 2: 稳定 Composer 尺寸**

  默认 3 行，最多增长到 8 行，之后内部滚动；按钮和模式标签使用固定宽度，任何状态变化不得推动 Transcript 跳动。

- [ ] **Step 3: 状态栏按优先级降级**

  narrow：state、approval、context；medium：追加 model、step；wide：追加 tokens、cost。快捷键说明移入 Help overlay，不在状态栏滚动或截断核心状态。

- [ ] **Step 4: SessionPanel 改为 Activity Rail**

  显示当前会话、最近会话和本回合工具活动；当前项有明确标记；Ctrl+B 控制折叠。窄屏使用 overlay，不能压缩 Composer。

- [ ] **Step 5: 统一 Slash/Model/Help overlay**

  三类覆盖层共享宽度、边框、列表项高度、焦点和空状态；加载模型时显示 loading，失败时保留已配置模型并显示错误原因。

- [ ] **Step 6: 运行 Widget 和布局测试**

  ```powershell
  conda run -n expr python -m pytest apps/cli/tests/test_tui_widgets.py apps/cli/tests/test_slash_overlay.py apps/cli/tests/test_tui_layout.py -v
  ```

  Expected: PASS。

- [ ] **Step 7: 提交工作台控件**

  ```powershell
  git add apps/cli/src/tui/widgets apps/cli/tests/test_tui_widgets.py apps/cli/tests/test_slash_overlay.py apps/cli/tests/test_tui_layout.py
  git commit -m "feat(tui): polish composer status and activity rail"
  ```

## Milestone D：收紧边界与可观察性

### Task 9：移除 UI 对 runtime 私有字段和静默异常的依赖

**Files:**
- Modify: `apps/cli/src/core/agent_runtime.py`
- Modify: `apps/cli/src/tui/screens/main_screen.py`
- Modify: `apps/cli/src/tui/controllers/turn_controller.py`
- Modify: `apps/cli/src/tui/controllers/approval_controller.py`
- Modify: `apps/cli/src/tui/controllers/session_controller.py`
- Modify: `apps/cli/tests/test_agent_runtime.py`
- Modify: `apps/cli/tests/test_tui_turn_flow.py`

- [ ] **Step 1: 列出并测试公开读取需求**

  TUI 只需要 workspace_root、model_name、approval_mode、snapshot 和 session id。通过只读 property 或 RuntimeBundle 暴露，禁止访问 `_config`、`_model_name`、`_session`、`_session_store`。

- [ ] **Step 2: 用窄异常替换吞错**

  SQLite 错误、配置错误、模型错误和 WidgetNotFound 分别处理；用户可恢复错误显示在 Transcript，调试细节写结构化日志。不得保留空的 `except Exception: pass`。

- [ ] **Step 3: 接入 EventBus 的必要事件**

  MainScreen 只订阅 agent state、tool start/end 和 usage；事件转换在 controller 完成。退出时取消订阅，避免恢复会话后重复渲染。

- [ ] **Step 4: 运行边界测试和静态扫描**

  ```powershell
  rg -n "_runtime\._|except Exception:\s*pass" apps/cli/src/tui
  conda run -n expr python -m pytest apps/cli/tests/test_agent_runtime.py apps/cli/tests/test_tui_turn_flow.py -v
  ```

  Expected: `rg` 不返回匹配；pytest PASS。

- [ ] **Step 5: 提交边界收紧**

  ```powershell
  git add apps/cli/src/core/agent_runtime.py apps/cli/src/tui apps/cli/tests
  git commit -m "refactor(tui): depend on public runtime contracts"
  ```

## Milestone E：发布门禁与文档一致性

### Task 10：完成全量验证、文档和版本校准

**Files:**
- Modify: `README.md`
- Modify: `docs/cli/01-cli-overview.md`
- Modify: `pyproject.toml`
- Modify: `apps/cli/src/kcode_cli.py`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: 增加 CI 中的 TUI 交互测试集合**

  Linux、macOS、Windows 都运行非快照交互测试；布局快照固定在一个稳定平台运行，避免终端字形差异制造噪音。

- [ ] **Step 2: 更新真实命令文档**

  文档必须覆盖默认 TUI、`chat`、`models`、`config show/validate`、`doctor`、`init`、workspace、model、approval、max_steps 和 debug；删除尚不存在的 sessions 命令描述。

- [ ] **Step 3: 校准配置示例**

  示例使用真实字段 `model.default_model`、`model.base_url`、`tools.approval_mode`，审批值只写 `manual` 或 `auto`；明确配置优先级。

- [ ] **Step 4: 统一版本来源**

  `kcode --version` 使用 `importlib.metadata.version("kcode")`；发布版本只在 `pyproject.toml` 维护，禁止入口文件硬编码 `0.1.0`。

- [ ] **Step 5: 执行完整质量门禁**

  ```powershell
  conda run -n expr python -m pytest -v
  conda run -n expr ruff check .
  conda run -n expr mypy apps packages
  conda run -n expr python -m apps.cli.src.kcode_cli --version
  ```

  Expected: 全部退出码为 0；测试无 skipped TUI 主流程；版本输出与 `pyproject.toml` 一致。

- [ ] **Step 6: 手工验收三个终端尺寸**

  在 `80x24`、`120x30`、`160x40` 下完成：发送消息、工具调用、拒绝审批、允许审批、取消流、新建会话、恢复会话、打开命令面板和模型面板。

- [ ] **Step 7: 提交发布准备**

  ```powershell
  git add README.md docs/cli/01-cli-overview.md pyproject.toml apps/cli/src/kcode_cli.py .github/workflows/ci.yml
  git commit -m "docs(cli): align tui workflows and release metadata"
  ```

## 6. 总体验收标准

### 功能

- 首条消息可稳定流式显示，最终状态来自真实 AgentSnapshot。
- Escape 立即停止当前 UI 回合；过期 Worker 不能继续写入 Transcript。
- manual 模式下所有 write/system/network 工具执行前必须显示审批。
- auto 模式不阻塞，但始终显示显著风险状态。
- 会话列表按当前 workspace 隔离，新建和恢复不会破坏当前会话。
- CLI 与 TUI 对 workspace、model、approval、max_steps 和配置优先级行为一致。

### 视觉与交互

- `80x24` 无重叠、无横向滚动，Composer 和核心状态始终可见。
- `120x30` 可同时扫描 Transcript、当前会话和工具状态。
- `160x40` 展示完整 Activity Rail，不用扩大正文行宽。
- 连续消息不形成边框卡片墙；工具调用可折叠并能区分 running/success/denied/failed。
- 仅使用键盘可以完成完整工作流，焦点不会在流式更新时被抢走。

### 工程质量

- `main_screen.py` 不再承担模型流消费、审批阻塞和 SessionRecord 转换。
- TUI 不访问 `CliAgentRuntime` 私有字段。
- TUI 关键路径不存在静默 `except Exception: pass`。
- TUI Pilot 测试覆盖发送、取消、审批、会话和三档布局。
- pytest、ruff、mypy 和 CLI smoke test 全部通过。

## 7. 实施顺序和停止条件

必须按 A -> B -> C -> D -> E 顺序实施。Milestone B 未全部通过前，不开始大规模 TCSS 和 Widget 视觉修改；否则视觉工作会掩盖运行时错误。每个 Task 独立提交，每个 Milestone 完成后做一次人工 TUI 验收。

出现以下情况时停止扩展范围并重新评审：

- 为实现审批必须改变 core 的同步 AgentRuntime 抽象；
- Textual 无法可靠隔离后台同步流，且需要替换整个运行时并发模型；
- SessionStore schema 必须迁移而非只增加过滤查询；
- 响应式布局需要新增 Textual 之外的 UI 框架；
- 任何修改开始涉及 Desktop host、IPC 或 Web 前端。

## 8. 建议发布切分

| 发布 | 包含内容 | 发布判定 |
|---|---|---|
| `v0.15` | Milestone A-B | 默认 TUI 的发送、审批、会话和 workspace 全部可用 |
| `v0.16` | Milestone C | 工作台视觉、响应式布局和工具时间线完成 |
| `v0.17` | Milestone D-E | 公共边界、全平台测试、文档和版本一致性完成 |

这三个发布均不包含 Desktop 工作。若必须压缩周期，可以延后模型面板的在线发现和 cost 展示，但不能延后流式契约、审批、会话、取消和 `80x24` 布局验收。

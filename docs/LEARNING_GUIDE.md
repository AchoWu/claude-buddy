# BUDDY 项目系统学习指南

> **预计总学时**：20-30 小时 | **难度**：中级 Python 开发者 | **前置要求**：Python 3.11+, 了解 OOP, 有 API 调用经验

---

## 目录

- [项目全景](#项目全景)
- [Phase 1: 基础入门](#phase-1-基础入门-2h)
- [Phase 2: 核心引擎](#phase-2-核心引擎-4h)
- [Phase 3: Provider 体系](#phase-3-provider-体系-2h)
- [Phase 4: 工具系统](#phase-4-工具系统-3h)
- [Phase 5: 会话与压缩](#phase-5-会话与压缩-3h)
- [Phase 6: 记忆与上下文](#phase-6-记忆与上下文-2h)
- [Phase 7: UI 与线程](#phase-7-ui-与线程-3h)
- [Phase 8: 高级子系统](#phase-8-高级子系统-3h)
- [10 大设计模式速查](#10-大设计模式速查)
- [关键代码索引](#关键代码索引)
- [完整消息流](#完整消息流-13-步)
- [附录：项目统计](#附录项目统计)

---

## 项目全景

### 一句话描述

BUDDY 是一个桌面 AI 宠物：一个住在你屏幕上的小动画角色，背后跑着一个和 Claude Code CLI 架构对齐的完整 LLM 引擎——能读文件、写代码、跑命令、搜网页、管任务、记住你的偏好。

### 技术栈

| 层 | 技术 | 用途 |
|---|------|------|
| 语言 | Python 3.11+ | 全栈 |
| 桌面 UI | PyQt6 | 无边框窗口、毛玻璃设计、动画精灵 |
| LLM API | anthropic SDK, openai SDK | 模型调用 |
| HTTP | httpx | 异步网络请求 |
| 图像 | Pillow | 精灵图处理 |
| Token 计数 | tiktoken (cl100k_base) | 精确 token 统计，CJK 感知 |

### 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                        main.py                              │
│              BuddyApp — 总指挥，信号接线                      │
├─────────────┬─────────────┬──────────────┬──────────────────┤
│   ui/       │  core/      │  tools/      │  prompts/        │
│             │             │              │                  │
│ PetWindow   │ engine.py   │ 37 个工具    │ system.py        │
│ ChatDialog  │ ⭐ 引擎核心  │ (BaseTool)   │ (20节系统提示)    │
│ Permission  │             │              │                  │
│ Settings    │ providers/  │ base.py      │ compact.py       │
│ AskUser     │  ├ anthropic│              │ templates.py     │
│ SpeechBub   │  ├ openai   │              │                  │
│ Sprite      │  └ prompttool              │                  │
│             │             │              │                  │
│             │ conversation│              │                  │
│             │ (8层压缩)   │              │                  │
│             │             │              │                  │
│             │ memory.py   │              │                  │
│             │ commands.py │              │                  │
│             │ task_manager│              │                  │
│             │ cron/       │              │                  │
│             │ bridge/     │              │                  │
│             │ services/   │              │                  │
└─────────────┴─────────────┴──────────────┴──────────────────┘
             ↕ pyqtSignal（线程安全）
      主线程 (Qt 事件循环)  ←→  引擎线程 (后台 daemon)
```

### 模块依赖关系

```
main.py
 ├─ config.py                    # 全局常量、路径、颜色
 ├─ core/settings.py             # 用户设置 (API key, model 等)
 ├─ core/engine.py ⭐             # LLM 引擎
 │   ├─ core/providers/*.py      # 3 种 LLM 适配器
 │   ├─ core/conversation.py     # 会话管理 + 8 层压缩
 │   │   ├─ core/normalization.py
 │   │   └─ core/token_estimation.py
 │   ├─ core/context_injection.py # CLAUDE.md 多级搜索
 │   ├─ core/memory.py           # 4 类记忆系统
 │   └─ prompts/system.py        # 20 节系统提示构建器
 ├─ core/tool_registry.py        # 工具注册、权限、并发标记
 │   └─ tools/*.py               # 37 个工具
 ├─ core/commands.py             # 50+ 斜杠命令
 ├─ core/task_manager.py         # 任务系统 V2
 ├─ core/cron/scheduler.py       # 定时任务
 ├─ core/dream.py                # 主动后台任务
 ├─ core/bridge/                 # IDE 桥接
 ├─ core/services/               # 插件、Hook、MCP、LSP 等
 └─ ui/*.py                      # 11 个 UI 组件
```

---

## Phase 1: 基础入门 (~2h)

### 学习目标
- 能跑起来 BUDDY
- 理解 BuddyApp 如何把各模块粘合在一起
- 理解配置系统

### 核心文件

| 文件 | 行数 | 职责 |
|------|------|------|
| `main.py` | ~587 | 入口点，创建所有组件，接线信号 |
| `config.py` | ~154 | 全局常量：路径、颜色、阈值 |
| `core/settings.py` | ~367 | 用户设置的读写 (JSON 文件) |

### 关键代码走读

**`main.py` — `BuddyApp.__init__()` (第 30-166 行)**

这是整个应用的"接线图"。按顺序做了这些事：

```
1. 加载设置 (Settings)
2. 创建 PetWindow (桌面精灵)
3. 创建 LLMEngine (核心引擎)
4. 创建 ToolRegistry (注册 37 个工具)
5. 创建 MemoryManager (记忆系统)
6. 创建 CronScheduler (定时器)
7. 加载上次会话
8. 启动 autosave 定时器 (30 秒)
9. 连接所有 pyqtSignal ← 这是关键！
10. 刷新 Provider
11. 绑定 Pet 点击/拖拽事件
```

**`config.py` — 全局常量**

```python
DATA_DIR = Path.home() / ".claude-buddy"   # 所有持久化数据
CLAUDE_ORANGE = "#D77757"                   # 品牌色
MAX_TOOL_ROUNDS = 200                       # 工具循环上限
COMPACT_THRESHOLD = 50                      # 压缩触发消息数
```

### 动手练习

1. **运行项目**：`python main.py`，点击桌面宠物打开聊天框，发一条消息
2. **加调试日志**：在 `main.py` 的 `_on_engine_response` 方法开头加 `print(f"[RESPONSE] {text[:50]}")`，观察输出
3. **改颜色**：在 `config.py` 里把 `CLAUDE_ORANGE` 改成 `"#00BFFF"`（蓝色），重启看效果
4. **看数据目录**：打开 `~/.claude-buddy/`，看看有哪些文件

### 掌握标准
- [ ] 能画出 BuddyApp 创建组件的顺序
- [ ] 能说出 `main.py` 连接了哪些信号
- [ ] 知道用户数据存在哪里

---

## Phase 2: 核心引擎 (~4h)

### 学习目标
- 理解 LLM 工具循环（tool-call loop）
- 理解流式响应 (streaming) 和同步回退
- 理解错误分类 + 重试策略
- 理解中断 (abort) 机制

### 核心文件

| 文件 | 行数 | 职责 |
|------|------|------|
| `core/engine.py` | ~1786 | 引擎核心：工具循环、流式、重试、中断 |

### 关键代码走读

**⚠️ engine.py 很大（~55KB）！不要从头读到尾。按功能区域跳读。**

#### 区域 1: 信号定义 (第 200-210 行)

```python
response_text = pyqtSignal(str)       # 最终回复
response_chunk = pyqtSignal(str)      # 流式片段
tool_start = pyqtSignal(str, dict)    # 工具开始执行
tool_result = pyqtSignal(str, str)    # 工具执行结果
state_changed = pyqtSignal(str)       # idle/work
error = pyqtSignal(str)              # 错误
ask_user = pyqtSignal(str, object, bool)  # AskUser 交互
```

这些信号是引擎线程和 UI 线程之间唯一的通信方式。

#### 区域 2: send_message() (第 420-435 行)

```
用户发消息 → add_user_message → 记录 rollback 点 → 启动后台线程 → _run_loop()
```

#### 区域 3: _tool_loop() (第 790-1030 行)

这是**最核心**的函数。工具循环的 13 步：

```
for round_num in range(MAX_TOOL_ROUNDS):
    1. 检查 abort
    2. 检查是否需要压缩
    3. Token 预算检查
    4. 调用 LLM API (流式或同步)
       └─ 错误分类 → 重试/恢复
    5. 添加 assistant 消息到会话
    6. 发射中间文本信号
    7. 如果没有 tool_calls → 终止，发射 response_text
    8. 执行工具 (并行/串行)
    9. 格式化工具结果，添加到会话
    10. 工具摘要 (≥2 个工具时)
    11. 继续下一轮
```

#### 区域 4: 重试策略 (第 515-600 行)

```python
# CC 对齐的指数退避
MAX_RETRIES = 10
RETRY_BASE_DELAY = 0.5      # 500ms
RETRY_MAX_DELAY = 32.0      # 32秒封顶
RETRY_JITTER_FACTOR = 0.25  # 25% 随机抖动

# 9 种错误分类
ErrorCategory: rate_limit, overloaded, server_error,
  context_too_long, max_output_tokens, network, timeout, auth, invalid_request
```

#### 区域 5: 中断机制 (第 489-560 行)

```
用户点取消 → abort_signal.set()
  → 工具循环检查 abort → raise InterruptedError
    → _persist_abort():
        1. 扫描未完成的 tool_use，补 error tool_result
        2. 追加 "[Request interrupted by user]"
        3. 保存会话
```

### 动手练习

1. **追踪一次完整请求**：在 `_tool_loop` 的 Step 4 (API 调用后) 和 Step 7 (工具执行后) 加 print，发 "读取 config.py 文件" 观察输出
2. **触发重试**：临时把 API key 改错一个字符，观察重试日志
3. **测试中断**：发一个需要多步工具的请求，点取消，看 `_persist_abort` 的输出
4. **跑测试**：`python tests/test_s1_engine.py`

### 掌握标准
- [ ] 能画出工具循环的流程图
- [ ] 能说出 9 种错误分类各自的恢复策略
- [ ] 理解 abort 后消息是怎么保留的（不再回滚）
- [ ] 理解流式失败时如何回退到同步

---

## Phase 3: Provider 体系 (~2h)

### 学习目标
- 理解 3 种 Provider 的差异
- 理解 `BaseProvider` 抽象接口
- 能写一个新的 Provider

### 核心文件

| 文件 | 行数 | 职责 |
|------|------|------|
| `core/providers/base.py` | ~173 | 抽象接口：call_sync, call_stream, format_tools |
| `core/providers/anthropic_provider.py` | ~319 | Anthropic 原生 tool_use、thinking、cache_control |
| `core/providers/openai_provider.py` | ~318 | OpenAI function calling 格式 |
| `core/providers/prompt_tool_provider.py` | ~276 | 通用后备：XML `<tool_call>` 解析 |

### 三种 Provider 对比

| 特性 | Anthropic | OpenAI | PromptTool |
|------|-----------|--------|------------|
| 工具格式 | 原生 `tool_use` block | `function` 定义 | 系统提示内 XML 描述 |
| 流式 | ✅ SSE | ✅ SSE | ✅ (解析文本中的 `<tool_call>`) |
| Thinking | ✅ extended thinking | ❌ | ❌ |
| Cache | ✅ cache_control | ❌ | ❌ |
| Effort | ✅ effort 参数 | ❌ | ❌ |
| 适用 | Claude 模型 | GPT 模型 | 任何模型 (DeepSeek, Qwen 等) |

### 关键代码走读

**BaseProvider 接口** (`core/providers/base.py`)

每个 Provider 必须实现：
```python
def call_sync(messages, system, tools, abort_signal, params) → (raw, tool_calls, text)
def call_stream(messages, system, tools, abort_signal, params) → generator[StreamChunk]
def format_tools(tools) → list[dict]           # 把 BaseTool → API 格式
def format_tool_results(tool_calls, results) → dict  # 把执行结果 → API 格式
```

**Anthropic Provider** — 重点看：
- `call_stream()` 如何处理 `content_block_start`/`content_block_delta` 事件
- `thinking` 模式如何改变请求参数
- `cache_control` 的 `ephemeral` 标记

**PromptTool Provider** — 重点看：
- 如何把工具描述注入系统提示
- 如何从模型输出中解析 `<tool_call name="...">{"arg": "val"}</tool_call>`

### 动手练习

1. **对比请求格式**：在 3 个 Provider 的 `call_sync` 开头加 `print(json.dumps(messages[:2], indent=2))`，看格式差异
2. **切换 Provider**：在设置里切换 Anthropic → OpenAI，发同一条消息，观察工具调用格式
3. **跑测试**：`python tests/test_s1_engine.py` (包含 Provider 测试)

### 掌握标准
- [ ] 能画出 BaseProvider 的接口图
- [ ] 能说出 Anthropic 和 OpenAI 的工具调用格式差异
- [ ] 理解 PromptTool 如何让"不支持工具"的模型也能调工具

---

## Phase 4: 工具系统 (~3h)

### 学习目标
- 理解 BaseTool 抽象和注册机制
- 能写一个新工具
- 理解权限检查和并发安全

### 核心文件

| 文件 | 行数 | 职责 |
|------|------|------|
| `tools/base.py` | ~39 | BaseTool 抽象基类 |
| `core/tool_registry.py` | ~353 | 工具注册、权限、并发标记 |
| `tools/bash_tool.py` | ~251 | Bash 工具 (典型写工具) |
| `tools/file_read_tool.py` | ~273 | 文件读取 (典型读工具) |
| `tools/ask_user_tool.py` | ~140 | AskUser (特殊交互工具) |

### 工具分类 (37 个)

```
文件操作 (5)    FileRead, FileWrite, FileEdit, Glob, NotebookEdit
代码执行 (3)    Bash, TerminalCapture, LSP
搜索网络 (3)    WebSearch, WebFetch, WebBrowser
AI 协作 (5)     Agent, SendMessage, TeamCreate, TeamDelete, AskUser
任务管理 (6)    TaskCreate, TaskUpdate, TaskList, TaskGet, TaskOutput, TaskStop
定时调度 (3)    CronCreate, CronDelete, CronList
计划模式 (2)    EnterPlanMode, ExitPlanMode
记忆灵魂 (3)    SelfReflect, SelfModify, DiaryWrite
MCP (3)         MCPTool, ListMcpResources, ReadMcpResource
其他 (4)        Skill, Workflow, PushNotification, CtxInspect ...
```

### 关键代码走读

**BaseTool** — 每个工具必须定义：
```python
class MyTool(BaseTool):
    name = "MyTool"                    # 工具名 (模型看到的)
    description = "..."                # 描述 (模型看到的)
    input_schema = { ... }             # JSON Schema (参数验证)
    is_read_only = True                # 只读? (影响权限和 plan mode)
    concurrency_safe = False           # 可并行? (影响批次调度)

    def execute(self, input_data: dict) -> str:
        # 执行逻辑，返回字符串结果
```

**ToolRegistry** — 注册和查找：
```python
registry.register(BashTool)
registry.register(FileReadTool)
# ...
executor = registry.get_executor("Bash")
result = executor({"command": "ls"})
```

**工具执行流程**（engine.py `_execute_one_tool`）：
```
1. emit tool_start 信号
2. Hook 检查 (pre_tool_use)
3. Plan mode 检查 (只读工具才能通过)
4. 权限检查 (permission_callback)
5. 找到 executor
6. 特殊工具拦截 (AskUser → 阻塞等用户回答)
7. 执行 executor(input_data)
8. 大结果处理 (>50KB → 持久化到磁盘)
9. emit tool_result 信号
10. Hook (post_tool_use)
```

### 动手练习

1. **读 3 个工具源码**：bash_tool.py (写工具)、file_read_tool.py (读工具)、ask_user_tool.py (交互工具)
2. **写一个新工具**：创建 `tools/time_tool.py`，返回当前时间：

```python
from tools.base import BaseTool
import datetime

class TimeTool(BaseTool):
    name = "GetTime"
    description = "Return the current date and time."
    input_schema = {"type": "object", "properties": {}}
    is_read_only = True

    def execute(self, input_data: dict) -> str:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
```

3. **在 tool_registry.py 注册**，测试模型能否调用
4. **跑测试**：`python tests/test_s4_tools.py`

### 掌握标准
- [ ] 能说出 BaseTool 的 5 个必须属性
- [ ] 能独立写一个新工具并注册
- [ ] 理解权限检查流程
- [ ] 理解 concurrency_safe 的含义和批次调度

---

## Phase 5: 会话与压缩 (~3h)

### 学习目标
- 理解 8 层压缩管道
- 理解 snip 标记机制（不删除消息）
- 理解 token 估算

### 核心文件

| 文件 | 行数 | 职责 |
|------|------|------|
| `core/conversation.py` | ~1014 | 8 层压缩 + 消息管理 |
| `core/token_estimation.py` | ~100 | CJK 感知的 token 估算 |
| `core/normalization.py` | ~80 | 消息格式修复 |
| `prompts/compact.py` | ~129 | LLM 压缩的提示模板 |

### 8 层压缩管道

```
                                    消息数
L0: Microcompact (免费)             >20  折叠重复 FileRead，截短旧工具结果
     ↓ 如果还是太多
L1: Snip (免费)                     >30  标记最旧的 8 条为 _snipped (不删除!)
     ↓
L2: Tool-result Compress (免费)     >40  截短工具输出到 500 字符
     ↓
L3: Message Grouping (免费)         >50  确保 assistant+tool 成对
     ↓
L4: Memory Preserve (轻量 API)      >50  压缩前先提取记忆保存
     ↓
L5: Mechanical Summary (免费)       >50  正则提取摘要 [CONTEXT COMPACTED]
     ↓
L6: LLM Summary (API 调用)         >50  模型生成 9 节结构化摘要
     ↓
L7: Reactive (紧急)                 API 报错  context_too_long 时强制压缩
```

### 关键设计：snip 不删消息

```python
@property
def messages(self):
    """模型看到的：过滤掉 _snipped"""
    return [m for m in self._messages if not m.get("_snipped")]

@property
def all_messages(self):
    """UI 看到的：全部消息"""
    return self._messages
```

模型只看 active 消息，用户能在 UI 里看到全部历史。

### 动手练习

1. **手动触发压缩**：发 35+ 条消息，观察日志中的 "snip: removed N"
2. **看 snip 效果**：关闭聊天框再打开，最早的消息应该变灰但仍可见
3. **查看压缩摘要**：发 55+ 条消息后看 `[CONTEXT COMPACTED]` 摘要
4. **跑测试**：`python tests/test_s2_compaction.py`

### 掌握标准
- [ ] 能画出 8 层管道流程图
- [ ] 能说出 `messages` 和 `all_messages` 的区别
- [ ] 理解 `_snipped: True` 标记机制
- [ ] 理解为什么 rollback point 要用 `len(_messages)` 而不是 `len(messages)`

---

## Phase 6: 记忆与上下文 (~2h)

### 学习目标
- 理解 4 类记忆系统
- 理解 CLAUDE.md 多级搜索
- 理解 20 节系统提示构建

### 核心文件

| 文件 | 行数 | 职责 |
|------|------|------|
| `core/memory.py` | ~609 | 4 类记忆：user/feedback/project/reference |
| `core/context_injection.py` | ~283 | CLAUDE.md 搜索 + @include |
| `prompts/system.py` | ~837 | 20 节系统提示构建器 |

### 4 类记忆

```
~/.claude-buddy/memory/
├── MEMORY.md                              # 索引文件
├── user_prefers_chinese_aba3.md           # 用户偏好
├── feedback_always_check_cc_d4a1.md       # 反馈纠正
├── project_uses_pyqt6_signals_f1e2.md     # 项目约定
└── reference_api_rate_limits_c3b7.md      # 参考信息
```

每个记忆文件有 frontmatter：
```markdown
---
name: User prefers Chinese
description: 用户倾向于中文交流
type: user
---

用户偏好使用中文进行所有对话和代码注释。
```

### CLAUDE.md 搜索顺序

```
当前工作目录/CLAUDE.md
  → 父目录/CLAUDE.md
    → 爷爷目录/CLAUDE.md
      → ... 一直到根目录
        → ~/.claude-buddy/CLAUDE.md (全局)
```

支持 `@include path/to/file.md` 指令（带循环引用检测）。

### 20 节系统提示

`prompts/system.py` 的 `build_system_prompt()` 组装：

```
1. 身份 (你是 BUDDY)
2. 核心规则
3. 工具描述 (37 个)
4. 安全约束
5. 文件操作规范
6. Git 工作流
7. 代码风格
8. 任务系统说明
9. 记忆上下文
10. CLAUDE.md 内容
11-20. 其他上下文...
```

### 动手练习

1. **查看记忆目录**：`ls ~/.claude-buddy/memory/`
2. **用 /memory 命令**：在聊天框输入 `/memory list` 查看所有记忆
3. **创建 CLAUDE.md**：在项目根目录创建 `CLAUDE.md`，写入 "Always respond in Chinese"，测试效果
4. **看提示构建**：在 `prompts/system.py` 的 `build_system_prompt` 返回前加 `print(f"System prompt: {len(result)} chars")`

### 掌握标准
- [ ] 能说出 4 类记忆的用途和文件名格式
- [ ] 理解 CLAUDE.md 的搜索优先级
- [ ] 知道系统提示有哪 20 节

---

## Phase 7: UI 与线程 (~3h)

### 学习目标
- 理解 PyQt6 信号/槽的线程安全通信
- 理解 ChatDialog 的消息流渲染
- 理解动画精灵系统

### 核心文件

| 文件 | 行数 | 职责 |
|------|------|------|
| `ui/chat_dialog.py` | ~1458 | 聊天窗口：流式气泡、工具指示器、AskUser |
| `ui/pet_window.py` | ~152 | 桌面宠物：拖拽、状态切换 |
| `ui/sprite_engine.py` | ~223 | 精灵动画引擎 |
| `ui/permission_dialog.py` | ~299 | 工具权限弹窗 |
| `ui/ask_user_dialog.py` | ~330 | AskUser 弹窗 (备用) |

### 线程模型

```
主线程 (Qt Event Loop)           引擎线程 (daemon)
     │                               │
     │  engine.send_message()         │
     │  ──────────────────────────►   │
     │                                │ _tool_loop()
     │                                │   API 调用...
     │   response_chunk.emit("Hi")    │
     │  ◄──────────────────────────   │
     │  ChatDialog.append_chunk()     │
     │                                │   tool_start.emit()
     │  ◄──────────────────────────   │
     │  ChatDialog.add_tool_call()    │
     │                                │   ... 工具执行 ...
     │   response_text.emit(final)    │
     │  ◄──────────────────────────   │
     │  ChatDialog.add_assistant()    │
     │                                │ 线程退出
```

**关键**：
- 引擎在后台线程运行
- 所有 UI 更新必须在主线程
- `pyqtSignal` 自动跨线程排队
- **绝对不能**从引擎线程直接操作 UI widget

### ChatDialog 气泡类型

```
MessageBubble     — 用户/助手消息 (支持 Markdown)
ToolCallBubble    — ⚡ 工具调用指示器 (橙色左边框)
InterruptBubble   — ■ 用户中断标记 (琥珀色居中)
AskUserBubble     — ❓ 交互选择卡片 (chip + 输入框)
ThinkingIndicator — 思考中动画 (...)
```

所有气泡通过 `_insert_message(widget)` 统一插入到 `QVBoxLayout` 中。

### Qt 样式刷新陷阱

从信号槽中更新样式时，`setStyleSheet()` 不会立即生效！必须：
```python
widget.style().unpolish(widget)
widget.style().polish(widget)
widget.repaint()
QApplication.processEvents()
```

### 动手练习

1. **加 print 追踪信号**：在 `main.py` 的每个 `_on_*` 信号处理器加 print
2. **改气泡颜色**：在 `chat_dialog.py` 中改 `MSG_BG_USER` 颜色
3. **改精灵**：把 `config.py` 中的角色从 buddy 改成 cute_girl
4. **跑 UI 测试**：`python tests/test_ui_chat_dialog.py`

### 掌握标准
- [ ] 能画出信号/槽跨线程通信图
- [ ] 知道 5 种气泡类型的用途
- [ ] 理解为什么从信号槽中更新样式需要 `processEvents()`
- [ ] 理解 `_insert_message()` 的插入位置逻辑

---

## Phase 8: 高级子系统 (~3h)

### 学习目标
- 理解 50+ 斜杠命令的注册机制
- 理解 Cron 定时调度
- 理解 Skill 技能系统（CC 对齐的按需加载）
- 理解 Bridge/Services 扩展体系

### 核心文件

| 文件 | 行数 | 职责 |
|------|------|------|
| `core/commands.py` | ~2031 | 50+ 斜杠命令 |
| `core/cron/scheduler.py` | ~206 | CC 对齐的 Cron 调度器 |
| `core/cron/parser.py` | ~146 | Cron 表达式解析器 |
| `core/services/bundled_skills.py` | ~180 | Skill 加载与管理 |
| `tools/skill_tool.py` | ~116 | Skill 工具（模型调用入口）|
| `core/dream.py` | ~154 | 主动后台任务 |
| `core/task_manager.py` | ~179 | CC V2 任务系统 |
| `core/services/hooks.py` | ~241 | Hook 扩展点 |
| `core/services/plugins.py` | ~326 | 插件加载器 |
| `core/bridge/server.py` | ~129 | IDE 桥接服务 |

### Skill 技能系统（CC 对齐）

```
CC 的 Skill 加载策略（BUDDY 已对齐）：

1. 启动时：只加载 skill 列表（名称 + 描述，描述截断 250 字符）
   → 注入系统提示，让模型知道有哪些 skill 可用
   → 不加载完整内容，节省 token

2. 用户/模型调用时：按需加载完整 SKILL.md
   → 模型通过 Skill 工具调用
   → 完整指令作为工具结果返回
   → 模型按指令执行

3. Skill 来源（3 种格式）：
   ~/.claude-buddy/skills/my-skill.json      ← 扁平 JSON
   ~/.claude-buddy/skills/my-skill.md        ← 扁平 Markdown
   ~/.claude-buddy/skills/my-skill/SKILL.md  ← 目录式（推荐）
```

目录式 SKILL.md 支持 YAML frontmatter：
```markdown
---
name: news-aggregator-skill
description: "Fetch news from 28 sources..."
---

# Skill Instructions
...详细的工作流程、模板、规则...
```

**关键原则**：模型看到的是"我有一个叫 X 的 skill，描述是 Y"。只有调用时才看到完整指令，避免长 skill 内容浪费 context。

### 命令注册模式

```python
# core/commands.py
R("/init", "Analyze codebase and generate CLAUDE.md", _cmd_init)
R("/diff", "Show file changes this session", _cmd_diff)
R("/memory", "View/edit memories", _cmd_memory)
# ... 50+个

def _cmd_init(args: str, ctx: dict) -> str:
    """每个命令的 handler 签名一致"""
    engine = ctx.get("engine")
    # ... 执行逻辑
    return "结果字符串"      # 普通结果
    return "__LLM_PROMPT__..." # 需要模型处理
```

`__LLM_PROMPT__` 前缀的命令返回值会被发送给 LLM 而不是直接显示。

### Cron 调度

```
CronScheduler (core/cron/scheduler.py)
  ├─ QTimer 每 1 秒 tick
  ├─ 检查 5 字段 cron 表达式是否匹配当前分钟
  ├─ 匹配时触发回调 on_fire(job_id, prompt)
  ├─ session-only 或 durable (写入 scheduled_tasks.json)
  └─ 7 天自动过期 (recurring)

CronParser (core/cron/parser.py)
  ├─ 解析 "*/5 * * * *" → CronFields
  ├─ 支持: *, */N, N, N-M, N,M,O
  └─ matches(fields, datetime) → bool
```

### 动手练习

1. **试 5 个命令**：`/init`, `/diff`, `/cost`, `/context`, `/memory list`
2. **写一个新命令**：在 `commands.py` 底部加：
```python
R("/hello", "Say hello", lambda args, ctx: f"Hello, {args or 'world'}!")
```
3. **创建定时任务**：让 BUDDY 创建一个 5 分钟提醒
4. **看 Hook 系统**：在 `core/services/hooks.py` 里看 `pre_tool_use` Hook 的工作方式

### 掌握标准
- [ ] 能说出 `__LLM_PROMPT__` 返回值的含义
- [ ] 能独立写一个新斜杠命令
- [ ] 理解 Cron 调度器的 tick 逻辑
- [ ] 知道 Hook 的 `pre_tool_use` / `post_tool_use` 触发时机

---

## 10 大设计模式速查

| # | 模式 | 位置 | 说明 |
|---|------|------|------|
| 1 | **Signal/Slot (跨线程)** | `engine.py:200-211` | 引擎 → UI 的所有通信 |
| 2 | **Abstract Provider** | `providers/base.py` | 3 种 LLM 的统一接口 |
| 3 | **Tool Registry** | `tool_registry.py` | 37 个工具的动态注册和查找 |
| 4 | **Pipeline (8 层压缩)** | `conversation.py:249-346` | 从便宜到贵，逐层尝试 |
| 5 | **Error Classification** | `engine.py:_classify_error` | 9 种错误 → 不同恢复策略 |
| 6 | **Abort Signal** | `engine.py:489-560` | 线程安全的中断 + 消息保留 |
| 7 | **Command Pattern** | `commands.py` | 50+ 命令统一注册/分发 |
| 8 | **Observer (Memory)** | `memory.py` | 后台自动提取记忆 |
| 9 | **Concurrency Batching** | `engine.py:1370-1420` | safe 工具并行，unsafe 串行 |
| 10 | **Semantic File Storage** | `memory.py` | 4 类记忆用语义文件名 + frontmatter |

---

## 关键代码索引

| 功能 | 文件 | 函数/位置 |
|------|------|-----------|
| 应用启动 | `main.py` | `BuddyApp.__init__()` |
| 发送消息 | `core/engine.py` ~420 | `send_message()` |
| 工具循环 | `core/engine.py` ~790 | `_tool_loop()` |
| API 调用 + 重试 | `core/engine.py` ~515 | `_call_with_retry()` |
| 流式调用 | `core/engine.py` ~640 | `_call_streaming()` |
| 执行单个工具 | `core/engine.py` ~1214 | `_execute_one_tool()` |
| 并行工具批次 | `core/engine.py` ~1370 | `_execute_tools_parallel()` |
| 中断处理 | `core/engine.py` ~489 | `_persist_abort()` |
| 8 层压缩入口 | `core/conversation.py` ~249 | `compact_if_needed()` |
| Snip 标记 | `core/conversation.py` ~444 | `_snip_oldest()` |
| LLM 压缩 | `core/conversation.py` ~614 | `llm_compact()` |
| 注册工具 | `core/tool_registry.py` ~100 | `register()` |
| 构建系统提示 | `prompts/system.py` ~50 | `build_system_prompt()` |
| 提取记忆 | `core/memory.py` ~200 | `extract_memory_async()` |
| CLAUDE.md 搜索 | `core/context_injection.py` ~50 | `collect_context()` |
| 命令分发 | `core/commands.py` ~100 | `execute()` |
| 聊天气泡插入 | `ui/chat_dialog.py` ~1009 | `_insert_message()` |
| 流式渲染 | `ui/chat_dialog.py` ~838 | `append_streaming_chunk()` |
| AskUser 交互 | `ui/chat_dialog.py` ~399 | `AskUserBubble` 类 |
| Cron tick | `core/cron/scheduler.py` ~119 | `_tick()` |

---

## 完整消息流 (13 步)

```
用户在聊天框输入 "帮我读取 config.py"

  1. ChatDialog._on_send()
     └─ emit message_sent("帮我读取 config.py")

  2. main.py._on_user_message()
     ├─ 检查是否是 /命令
     └─ engine.send_message("帮我读取 config.py")

  3. engine.send_message()
     ├─ conversation.add_user_message()
     ├─ 记录 _msg_count_at_query_start (用于中断回滚)
     └─ 启动后台线程 → _run_loop()

  4. _run_loop() → _tool_loop()
     ├─ 构建系统提示 (20 节)
     ├─ 收集上下文 (CLAUDE.md + 记忆)
     └─ 进入工具循环

  5. Round 1: 调用 LLM API
     ├─ _call_with_retry(messages, system, tools)
     ├─ 流式: provider.call_stream() → yield chunks
     │   └─ emit response_chunk("我来帮你读取...")
     └─ 返回: tool_calls=[FileRead(file_path="config.py")]

  6. 添加 assistant 消息到会话
     └─ emit intermediate_text("我来帮你读取 config.py")

  7. 执行工具: FileRead
     ├─ emit tool_start("FileRead", {file_path: "config.py"})
     ├─ 权限检查 (FileRead 是 read_only → 自动通过)
     ├─ 执行 → 返回文件内容
     └─ emit tool_result("FileRead", "内容...")

  8. 格式化工具结果，添加到会话

  9. Round 2: 再次调用 LLM API
     ├─ 这次模型有了文件内容作为上下文
     └─ 返回: text="这是 config.py 的内容...", tool_calls=[]

  10. 没有更多工具调用 → 终止循环
      └─ emit response_text("这是 config.py 的内容...")

  11. main.py._on_engine_response()
      ├─ ChatDialog.add_assistant_message()
      ├─ show_bubble() (桌面宠物气泡)
      └─ engine.save_conversation()

  12. 后台: 自动提取记忆
      └─ memory.extract_memory_async()

  13. 后台: 检查是否需要压缩
      └─ conversation.compact_if_needed()
```

---

## 附录：项目统计

### 代码量

| 目录 | 文件数 | 行数 | 占比 |
|------|--------|------|------|
| `core/` | 24 | ~8,500 | 22% |
| `tools/` | 41 | ~5,700 | 15% |
| `ui/` | 11 | ~3,300 | 9% |
| `prompts/` | 4 | ~1,000 | 3% |
| 根目录 | 3 | ~900 | 2% |
| `tests/` | 48 | ~18,500 | 49% |
| **合计** | **147** | **~38,000** | 100% |

### 最大文件 Top 10

| 文件 | 行数 | 职责 |
|------|------|------|
| `core/commands.py` | 2,031 | 50+ 斜杠命令 |
| `core/engine.py` | 1,786 | 核心引擎 |
| `ui/chat_dialog.py` | 1,458 | 聊天窗口 |
| `core/conversation.py` | 1,014 | 8 层压缩 |
| `prompts/system.py` | 837 | 系统提示 |
| `core/evolution.py` | 716 | 自我进化 |
| `core/memory.py` | 609 | 记忆系统 |
| `main.py` | 587 | 应用入口 |
| `core/services/analytics.py` | 372 | 分析服务 |
| `core/settings.py` | 367 | 设置管理 |

### 推荐阅读顺序

```
第 1 天: main.py → config.py → engine.py (概览)
第 2 天: engine.py (深读工具循环) → providers/base.py
第 3 天: tools/base.py → 3 个工具 → tool_registry.py
第 4 天: conversation.py (8 层压缩)
第 5 天: memory.py → context_injection.py → prompts/system.py
第 6 天: ui/chat_dialog.py → pet_window.py
第 7 天: commands.py → cron/ → services/
```

---

<p align="center"><b>Happy hacking! 🐾</b></p>

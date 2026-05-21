# Stoke — A股数据获取层

## 项目定位

A 股量化投研系统。数据获取 → 机会发现 → 时机判断 → 策略执行 → 复盘迭代。

## 数据源组合（6 源）

| 数据源 | 协议/方式 | 限流 | 覆盖层面 |
|--------|----------|------|---------|
| mootdx | TCP（通达信） | 不限 | K线、实时行情、指数、板块成分股、F10 |
| akshare | HTTP（东财/同花顺/财联社） | 5s | 新闻、研报、涨停、情绪、资金流、行业板块 |
| baostock | HTTP（证券宝） | 1s | 复权K线、行业分类、股票列表 |
| efinance | HTTP（新浪/网易/东财） | 0.5s | 极速K线、龙虎榜、十大股东、股东人数 |
| tencent | HTTP（腾讯lg） | 3s | PE/PB 估值 |
| 智兔数服 | REST API | 1s | 备用行情、技术指标（需 Token） |

## 项目结构

```
stoke/
├── stoke/
│   ├── __init__.py           # StokeCached (默认带缓存)
│   ├── client.py             # Stoke 纯路由（裸版，无缓存）
│   ├── client_cached.py      # StokeCached 缓存包装（12 方法覆写）
│   ├── store.py              # SQLite 缓存（16 表，get_or_fetch）
│   ├── runner.py             # 每日主流程 daily_routine()
│   ├── context.py            # MarketContext 值对象
│   ├── timing.py             # 时机层（五维加权）
│   ├── discovery.py          # 发现层（五通道注意力）
│   ├── config.py             # 限流 + 日志系统
│   ├── calendar.py           # A 股交易日历
│   ├── rate_limiter.py
│   ├── utils.py
│   ├── exceptions.py         # 预留
│   ├── normalizer.py         # 预留
│   └── sources/              # 6 源适配
│       ├── mootdx_source.py  # TCP 通达信
│       ├── akshare_source.py # HTTP 东财/同花顺
│       ├── baostock_source.py# HTTP 复权K线
│       ├── efinance_source.py# HTTP 极速K线/股东
│       ├── tencent_source.py # HTTP PE/PB
│       └── zhitu_source.py   # REST 备用
├── tests/
├── Team/                     # 顾问参考（不动）
├── pyproject.toml
└── CLAUDE.md
```

## 编码规范

- **Python 3.11+**，UTF-8 编码，中文注释
- 包管理用 `uv`（`uv add` / `uv run`），不用 pip
- 代码加注释——用户是编程初学者
- 先讨论思路，确认后再写代码
- 修改前先理解原有逻辑，不乱改
- 不确定时反问，不猜测执行
- 所有沟通用中文
- 环境：Mac M4 芯片

## 安全红线

- **绝对禁止**在命令/代码/输出中明文暴露 API Token/密码/Key
- 密钥必须从环境变量或配置文件读取，不得内联明文
- Shell 历史、git 日志、工具输出都会持久化，明文密钥 = 永久泄露

## 核心原则

1. **限流是铁律** — 每个数据源必须遵守其平台的调用间隔，不可频繁请求导致封 IP
2. **保持简单** — 每层一个文件，每文件一个类，不过度抽象
3. **health_check() 必实现** — 每个 Source 都要能快速验证连通性
4. **返回 DataFrame** — 行情/K线/公告用 DataFrame

## 架构全景图

参考 `Team/exported_image.png`，系统由 7 层组成：

```
┌──────────────┐     ┌───────────────────────────────────┐
│  核心基础设施  │     │         交易决策闭环               │
│              │     │                                   │
│ 数据层 Skill  │     │  发现层 ──→ 时机层 ──→ 策略执行层  │
│ (数据获取/清洗)│────→│    ↑                      │      │
│              │     │    │                      ↓      │
│ 全局状态层    │     │  经验验证 ←── 沉淀层 ←───────────  │
│ (持仓/余额/   │────→│  缓冲区      (复盘/经验提炼)        │
│  订单/状态)   │     │    ↑         ↑                    │
│              │     │    └── 闭环反馈 ──┘               │
└──────────────┘     └───────────────────────────────────┘
```

| 层 | 隐喻 | 职责 | 文件 | 状态 |
|----|------|------|------|------|
| 全局调度 | 主流程 | 串联各层，一条 daily_routine() | `runner.py` | ✅ |
| 数据层 | 电脑 | 6 源 + SQLite 缓存 | `store.py` + `sources/` | ✅ |
| 全局状态层 | 口袋 | 持仓/余额/订单 | — | ❌ |
| 发现层 | 眼睛 | 五通道注意力扫描 | `discovery.py` | ✅ 雏形 |
| 时机层 | 大脑 | 五维加权时机判断 | `timing.py` | ✅ 雏形 |
| 策略执行层 | 手 | 交易指令生成、止损止盈 | — | ❌ |
| 沉淀层 | 记忆 | 复盘、盈亏分析、经验提炼 | — | ❌ |
| 经验验证缓冲区 | 学习 | 回测验证、策略有效期 | — | ❌ |

## 当前状态

**已完成：** 数据层（6 源 + 缓存）、client.py 拆为纯路由+缓存包装、发现层+时机层雏形、全局调度层。100 轮压力测试：预热后 100% 缓存命中率，冷启动 84%。

**下一个大步骤：** 全局状态层（持仓/余额）

**设计原则：** 每层一个文件，300 行以内。不搞调度框架，不搞事件总线。

## Agent 体系

主 Agent 拥有 8 个专业子 Agent，由 `.claude/agents/*.md` 定义。

### 可用 Agent 一览

| subagent_type | 中文名 | 职责 | 触发场景 |
|-------|------|------|------|
| architecture-reviewer | 架构审查 | 模块耦合度、接口设计、数据流完整性 | 跨模块改动、新层设计、架构评审 |
| code-reviewer | 代码审查 | 代码质量、错误处理、性能隐患、密钥安全 | 所有代码改动后 |
| code-specialist | 代码实现 | 快速编写高质量 Python 代码 | 新功能实现、代码修改 |
| sqlite-specialist | 数据库专员 | 表结构、索引优化、查询性能、SQL 安全 | store.py 改动、新增缓存表 |
| data-source-specialist | 数据源适配 | 6 源对接、限流管理、health_check | 新增/修改 Source、调试数据接口 |
| strategy-engineer | 策略工程师 | 发现层/时机层/调度层算法 | 修改 discovery.py/timing.py/runner.py |
| system-tester | 系统测试 | 压力测试、缓存验证、数据源健康检查 | 跑测试、验证缓存命中率、压测 |
| code-quality-guard | 代码质量守卫 | 代码审查、重构、SQL 优化、性能分析 | 重构、性能优化、安全审查 |

### 调度原则

1. **专业分工**：任务必须分配给最匹配的子 Agent，禁止主 Agent 包办所有事情
2. **并行优先**：无依赖关系的任务，同时派发多个 Agent 并行执行
3. **依赖顺序**：数据源 → 缓存 → 策略 → 测试，严格按序执行
4. **质量门禁**：代码改动必须经过 code-reviewer（或 code-quality-guard）审查 + system-tester 验证
5. **安全优先**：涉及数据源限流、SQL 写入、API Token 的改动，优先审查
6. **模型统一**：所有 Agent 使用 opus（映射到 deepseek-v4-pro），轻量任务可用 sonnet

### 标准工作流程

1. 拆解任务，分析依赖关系
2. 并行派发所有独立任务给对应 Agent
3. 收集各 Agent 输出，整合并解决冲突
4. system-tester 验证（压力测试 + 缓存命中率）
5. code-reviewer / code-quality-guard 审查
6. 交付成果

### Agent 用法示例

```
# 新增数据源
Agent(subagent_type="data-source-specialist", prompt="为 XXX 数据源编写适配器...")

# 实现策略逻辑
Agent(subagent_type="strategy-engineer", prompt="优化发现层的涨停板筛选逻辑...")

# 代码审查
Agent(subagent_type="code-reviewer", prompt="审查 stoke/store.py 的改动...")

# 压力测试
Agent(subagent_type="system-tester", prompt="对更新后的缓存层跑 100 轮压测...")
```

> 完整 Agent 定义见 `.claude/agents/*.md`，调度补充见 `.claude/rules.md`。

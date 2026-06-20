# Vibe-Trading 探索报告 — 2026-05-31

## 项目概况

| 维度 | 数据 |
|------|------|
| 定位 | 港科大 (HKUDS) 出品的自然语言驱动金融研究+回测 AI Agent |
| 代码量 | 48,808 行 Python，568 源文件 |
| Agent 框架 | 自定义 ReAct 循环，LangChain 做 LLM 接口 |
| LLM | 14+ 提供商，本次用 DashScope/Qwen |
| 前端 | React 19 + Vite，FastAPI 后端 |
| 依赖 | 重（LangChain 全家桶，200MB+） |

---

## 数据源实测（2026-05-31 中国内地网络）

### ✅ 可用的

| 数据源 | 用途 | 协议 | 条件 | 稳定性 |
|--------|------|------|------|--------|
| **mootdx** | A股K线、实时行情、股票列表 | TCP 直连通达信 | 零鉴权 | ⭐⭐⭐⭐⭐ |
| Tushare 免费版 | A股指数、估值PE/PB、基本面 | HTTP | 需要 Token，限频严重 | ⭐⭐ |

### ❌ 挂了的

| 数据源 | 原因 |
|--------|------|
| AKShare 全接口 | 东方财富服务器直接挂断 TCP 连接（反爬盾牌），不是墙的问题 |
| yfinance | 被墙 + Rate Limit |
| OKX | 被墙 |

### 影响评估

- ✅ A股个股 K 线回测 → **完全可用**（mootdx 撑住）
- ❌ 跨市场分析 / Swarm 多 Agent → **一半 Worker 静默失败**
- ❌ 新闻、研报、涨停板、财联社 → **全挂**（都走 AKShare → 东财）

---

## Vibe-Trading 核心架构

### 5 层上下文压缩（最值得参考的设计）

```
Layer 1: 静默修剪旧工具结果（每轮自动，零 LLM 成本）
Layer 2: 折叠长文本（token 超 70% 阈值触发，纯字符串操作）
Layer 3: 结构化摘要压缩（超 40K token 触发，LLM 调用）
Layer 4: Agent 主动调用 compact 工具
Layer 5: 迭代更新摘要（二次压缩不丢信息）
```

### 渐进式 Skill 文档（上下文省流设计）

- 75 个 Skill 文件，System Prompt 只注入一行摘要
- 完整文档通过 `load_skill` 工具按需加载
- Swarm 模式下 Agent 按角色过滤工具注册表

### 回测引擎体系

- 6 套引擎：ChinaA / GlobalEquity / Crypto / Futures / Forex / Options
- 自动混合市场（CompositeEngine）
- 内置 Monte Carlo / Bootstrap / Walk-Forward 统计验证

### 452 个量化因子（Alpha Zoo）

- qlib158（微软 Qlib，Apache-2.0）
- alpha101（Kakushadze 101 Formulaic Alphas）
- gtja191（国泰君安 2014 年短期因子报告）
- academic（Fama-French 5 + Carhart 动量）

---

## 本次修复记录

### 3 个源码 Bug 修复

1. **`agent/backtest/loaders/akshare_loader.py`**
   - `is_available()` 只检查 import，不检查网络 → 加 `_check_connectivity()` TCP 检测
   
2. **`agent/backtest/loaders/tushare.py`**
   - CSI 300 (`000300.SH`) 走 `pro.daily()` 查不到 → 自动 fallback `pro.index_daily()`

3. **2 个 Skills 文档过时**
   - `data-routing/SKILL.md` 和 `strategy-generate/SKILL.md` 未列 mootdx → 补充 + 置顶

### 新增文件

4. **`agent/backtest/loaders/mootdx_loader.py`**（~120 行）
   - 注册为 A 股首选 loader，零鉴权 TCP 直连
   - 自动跳过指数代码（留给 Tushare fallback），专注个股+ETF
   
5. **`agent/backtest/loaders/registry.py`** → a_share 回退链改为 `mootdx → tushare → akshare`

---

## 真实可用的操作路径

### ✅ 这些能跑

```
mootdx K线 → A股回测 → 因子分析 → 中文报告
A股 ETF 回测（510300 沪深300、159915 创业板等）
均线交叉、RSI、布林带等经典技术策略
标的多于 20 只时建议简化：等权持仓月度调仓
```

### ❌ 这些跑不了

```
跨市场分析（美股/港股/加密货币）
Swarm 多 Agent 团队（worker 静默失败）
AKShare 任何功能（新闻、研报、涨停板、电报）
```

---

## 经验教训

### 1. Docker 坑

```
Docker build → 16/22 卡死 → 前端 OOM
本地 npm run build → 2.77 秒
结论：个人开发不要用 Docker，原生跑更快更稳
```

### 2. Agent 死循环

```
数据源挂了 → Agent 反复重试 → 20+ 步绕圈
根因：AKShare is_available() 说"我能用"，实际不能
修复后：不假装在线，自动切 fallback
```

### 3. 提示词要具体

```
"用 tushare 数据源" → Agent 知道指定
"用中文总结" → 通义千问母语输出
source 传 "auto" → 自动走回退链，最省事
```

---

## 本地启动命令

```bash
# 一条命令启动（含前端静态文件）
cd ~/Vibe-Trading
PYTHONPATH=agent python3 -c \
  "from api_server import serve_main; serve_main(['--port', '8899', '--host', '127.0.0.1'])"

# 访问 http://127.0.0.1:8899
```

---

*报告生成于 2026-05-31 18:45 CST · 由孙擎天（擎天柱）和 Claude（大黄蜂）共同完成*

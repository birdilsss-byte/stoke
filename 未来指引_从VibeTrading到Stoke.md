# 未来指引 — 从 Vibe-Trading 到 Stoke

> Stoke 是你的地盘。Vibe-Trading 告诉我们什么值得做、什么不值得。

---

## 一、别走的路

### ❌ 别引入 LangChain

```
LangChain 安装体积    200MB+
mootdx + pandas 安装    ~15MB
```

**LangChain 适合企业级多模型编排场景，不适合个人量化工具。** 你用 Claude Code 已经覆盖了 LLM 调度层，不需要再套一层框架。Stoke 保持纯 Python + mootdx 即可。

### ❌ 别做 Swarm 多 Agent

Vibe-Trading 的 29 套 Swarm 团队预设看起来很炫，实测：
- 一半 worker 静默失败（依赖数据源挂了就全崩）
- 跨团队通信复杂，调试困难
- 对个人研究场景价值极低

**一个 Agent（你 + Claude Code）就够了。**

### ❌ 别追"全市场"

```
A股 ✅ mootdx 稳如磐石
美股 ❌ yfinance 被墙
港股 ❌ yfinance 被墙  
加密货币 ❌ OKX 被墙
```

**专注 A 股。全市场是噱头，A 股够你研究一辈子。**

---

## 二、值得走的路

### ✅ 做个更轻的"Vibe-Trading"

Vibe-Trading 最值得复制的部分，剥离掉 LangChain 后就是：

```
mootdx（你已有） → K线数据
pandas（你已有） → 信号引擎
Stoke 轻量回测   → 评估结果
Claude Code       → LLM 生成策略 + 中文分析
```

**你不需要 Vibe-Trading 那个 568 文件的 Python 项目。** 你只需要 Stoke 提供数据 + 一段 200 行的回测脚本 + Claude Code 帮你写策略。今天下午已经证明了这条路走得通。

### ✅ Stoke 的增量方向

**P0 — 数据层加固**

```python
# Stoke 已经有的
mootdx → K线、实时行情、股票列表、F10
AKShare → （东财封杀中，等恢复）
腾讯财经 → PE/PB

# 建议加的
# 1. 行业分类缓存（本地 JSON，避免每次调 Tushare）
# 2. 交易日历（mootdx 能查，存下来就行）
# 3. K线数据本地缓存（SQLite，避免每次拉 800 根）
```

**P0 — 分析能力**

```python
# 今天已验证有效的分析框架：

1. 三维分类筛选
   - 龙头：波动最低 + 回撤最小 + 抗跌
   - 中军：量能稳定 + 机构风格 + 业绩确定
   - 弹性：历史冲锋基因 + 尚未加速 + 资金异动

2. 策略回测模板
   - 双均线交叉
   - 动量选股月度调仓
   - RSI 超买超卖
   - 布林带突破

3. Benchmark 对比
   - 用 510300（沪深300ETF）做买入持有基准
```

### ✅ 永久解决数据源问题

```
现状：AKShare 挂了，Tushare 限量
解法：mootdx 是 TCP 协议，封不了！

mootdx 能覆盖的：
  ✅ 全市场 27000+ 只标的 K 线
  ✅ 实时行情（5 档盘口）
  ✅ 日/周/月线
  ✅ F10 财务快照（37 字段）

mootdx 不能覆盖的：
  ❌ 指数 K 线 → Tushare index_daily 补充
  ❌ 财报细节 → Tushare income/balancesheet 补充
  ❌ 行业分类 → Tushare index_classify 补充
  ❌ 新闻研报 → 等 AKShare 恢复
```

---

## 三、你的核心优势

### 你今天做的事，别人做不到

1. **有自己写的数据源** — mootdx TCP 直连，零 API Key，不可封
2. **有 Claude Code** — LLM 辅助研究，策略生成 + 分析 + 中文报告全自动
3. **懂选股逻辑** — "龙头+中军+弹性"的前瞻性分类，不是纯量化跑出来的
4. **知道什么是坑** — 今天踩过的 Docker、LangChain、Swarm、AKShare 陷阱，以后不用再踩

### Vibe-Trading 的 100 分能力，你能在 Stoke 上实现 80 分

```
Vibe-Trading      Stoke
   95 分            85 分    A 股日线回测（mootdx 比他们更稳）
   90 分            70 分    多因子分析（缺估值数据，但有腾讯 PE/PB）
   85 分            90 分    中文交互（你直接跟 Claude 聊，比 Agent 灵活）
   80 分             ❌      跨市场分析（你网络环境不支持，放弃）
   70 分            50 分    Swarm 自动化（不必要，你要的是人的判断）
```

**80 分够了。剩下 20 分不值得用 200MB 的 LangChain 换。**

---

## 四、下次打开的姿势

### 不是 "研究 Vibe-Trading"

### 是 "在 Stoke 上做策略研究"

```bash
# 1. 要数据
cd ~/stoke && uv run python3 -c "
from stoke.sources.mootdx_source import MootdxSource
m = MootdxSource()
df = m.get_kline('600900')
print(df.tail(20))
"

# 2. 要分析
# 把上一步的输出贴给 Claude
# "帮我分析长江电力近20日的走势，计算RSI和布林带位置"

# 3. 要策略
# "写一个基于上面分析的均线策略信号引擎"
```

---

## 五、一句话总结

**Vibe-Trading 是一个包罗万象的量化大厦，但在中国内地网络下，它真正能用的只有地基——而你的 Stoke 用 mootdx 已经打好了自己的地基。**

与其修别人漏水的大厦，不如在自己地基上慢慢盖楼。

---

*2026-05-31 · 大黄蜂 给 擎天柱 · 准备回巢*

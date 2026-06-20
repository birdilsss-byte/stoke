# Stoke 策略能力升级路线

> 从 Vibe-Trading 提取的可复用策略模式、信号生成器和回测思路

---

## 一、Stoke 已有能力回顾

```
mootdx → K线、实时行情（5档盘口）、全市场股票列表、F10财务快照
AKShare → 新闻、研报、公告、涨停板、强势股（❗当前东财封杀，暂不可用）
腾讯财经 → PE/PB估值历史
```

---

## 二、从 Vibe-Trading 提取的策略模板

### 模板 1：双均线金叉死叉

```python
class SignalEngine:
    """MA20/MA60 金叉做多，死叉平仓"""
    
    def generate(self, data_map):
        """
        data_map: dict, code → DataFrame (open, high, low, close, volume)
        返回: dict, code → Series (1.0 = 满仓, 0.0 = 空仓)
        """
        import pandas as pd
        result = {}
        for code, df in data_map.items():
            ma20 = df['close'].rolling(20).mean()
            ma60 = df['close'].rolling(60).mean()
            signal = pd.Series(0.0, index=df.index)
            # 金叉 = 昨日 MA20≤MA60 且今日 MA20>MA60
            cross_up = (ma20.shift(1) <= ma60.shift(1)) & (ma20 > ma60)
            # 死叉 = 昨日 MA20≥MA60 且今日 MA20<MA60
            cross_down = (ma20.shift(1) >= ma60.shift(1)) & (ma20 < ma60)
            signal[cross_up] = 1.0
            signal[cross_down] = 0.0
            signal = signal.replace(0.0, method='ffill').fillna(0)
            result[code] = signal
        return result
```

### 模板 2：RSI 超买超卖

```python
class SignalEngine:
    """RSI<30 买入，RSI>70 卖出"""

    def generate(self, data_map):
        import pandas as pd
        result = {}
        for code, df in data_map.items():
            delta = df['close'].diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            signal = pd.Series(0.0, index=df.index)
            signal[rsi < 30] = 1.0
            signal[rsi > 70] = 0.0
            signal = signal.replace(0.0, method='ffill').fillna(0)
            result[code] = signal
        return result
```

### 模板 3：布林带突破

```python
class SignalEngine:
    """价格突破上轨做多，跌破中轨平仓"""

    def generate(self, data_map):
        import pandas as pd
        result = {}
        for code, df in data_map.items():
            mid = df['close'].rolling(20).mean()
            std = df['close'].rolling(20).std()
            upper = mid + 2 * std
            signal = pd.Series(0.0, index=df.index)
            signal[df['close'] > upper] = 1.0
            signal[df['close'] < mid] = 0.0
            signal = signal.replace(0.0, method='ffill').fillna(0)
            result[code] = signal
        return result
```

### 模板 4：动量选股 + 等权持仓（月度调仓）

```python
class SignalEngine:
    """每月选前N只动量最强股，等权持有"""

    def __init__(self, top_n=10):
        self.top_n = top_n

    def generate(self, data_map):
        import pandas as pd
        import numpy as np
        
        # 每月最后一个交易日计算过去20日动量
        momentum = {}
        for code, df in data_map.items():
            mom = df['close'].pct_change(20)
            momentum[code] = mom
        
        mom_df = pd.DataFrame(momentum)
        result = {}
        for code, df in data_map.items():
            signal = pd.Series(0.0, index=df.index)
            for idx in df.index:
                if idx.month != (idx - pd.Timedelta(days=1)).month:
                    # 月初调仓
                    if idx in mom_df.index:
                        row = mom_df.loc[idx].dropna()
                        top = row.nlargest(self.top_n)
                        if code in top.index:
                            signal[idx:] = 1.0 / self.top_n
            result[code] = signal.fillna(0)
        return result
```

---

## 三、Vibe-Trading 的 75 个 Skill — 精选可用图谱

从 75 个 Skill 中精选对 Stoke 有直接参考价值的：

### 🔬 策略类（可直接在 Stoke 中实现）

| Skill | 核心内容 | 用 Stoke 实现的关键点 |
|-------|---------|---------------------|
| `strategy-generate` | 完整回测工作流：config→code→backtest→evaluate | 用 mootdx K线 + 自定义回测引擎 |
| `technical-basic` | MA/MACD/RSI/布林带技术分析 | mootdx K线 直接算 |
| `candlestick` | 蜡烛图形态识别 | mootdx OHLC 数据支持 |
| `multi-factor` | 多因子选股框架 | 需要基本面数据（当前缺） |
| `sector-rotation` | 行业轮动策略 | 需要行业分类（Tushare 部分支持） |
| `pair-trading` | 配对交易（协整检验） | mootdx K线足矣 |
| `momentum` | 动量策略 | mootdx K线直接算 |
| `dividend-analysis` | 股息率分析 | 需要股息数据（当前缺） |

### 📊 分析类

| Skill | 核心内容 | 迁移难度 |
|-------|---------|---------|
| `factor-research` | 因子构建、IC/IR检验 | 中等（需回测框架） |
| `correlation-analysis` | 相关性热力图 | 简单（pandas 搞定） |
| `risk-analysis` | VaR/CVaR/最大回撤 | 简单（已有 K线数据） |
| `valuation-model` | PE/PB/PS 估值模型 | 需要基本面（当前缺） |

---

## 四、Stoke 可直接落地的轻量回测框架

基于 mootdx 数据 + 纯 pandas 实现，约 200 行：

```python
import pandas as pd
import numpy as np
from mootdx.quotes import Quotes

class SimpleBacktest:
    """轻量回测，零依赖，纯 mootdx + pandas"""
    
    def __init__(self, initial_cash=1_000_000, commission=0.001):
        self.cash = initial_cash
        self.commission = commission
    
    def run(self, codes, signal_engine, start, end):
        """
        Args:
            codes: list of TDX symbols, e.g. ['000001', '600000']
            signal_engine: SignalEngine 实例
            start/end: 'YYYY-MM-DD'
        
        Returns:
            dict with equity curve, metrics
        """
        client = Quotes.factory(market="std")
        
        # 拉数据
        data_map = {}
        for code in codes:
            df = client.bars(symbol=code, frequency=9, start=0, offset=800)
            df['trade_date'] = pd.to_datetime(df.index)
            df = df.set_index('trade_date').sort_index()
            df = df.rename(columns={'vol': 'volume'})
            data_map[code] = df.loc[start:end]
        
        # 生成信号
        signals = signal_engine.generate(data_map)
        
        # 执行回测
        equity = pd.Series(self.cash, index=data_map[codes[0]].index)
        position = {c: 0 for c in codes}
        
        for date in equity.index:
            for code in codes:
                if code not in signals or date not in signals[code].index:
                    continue
                sig = signals[code].loc[date]
                price = data_map[code].loc[date, 'close']
                
                # 调仓
                target_value = equity.loc[date] * sig
                current_value = position[code] * price
                diff = target_value - current_value
                
                cost = abs(diff) * self.commission
                self.cash -= cost
                position[code] = target_value / price
                self.cash -= diff
            
            total = self.cash + sum(
                position[c] * data_map[c].loc[date, 'close']
                for c in codes if date in data_map[c].index
            )
            equity.loc[date] = total
        
        # 计算指标
        rets = equity.pct_change().dropna()
        total_ret = (equity.iloc[-1] / equity.iloc[0] - 1) * 100
        sharpe = (rets.mean() / rets.std()) * np.sqrt(252) if rets.std() > 0 else 0
        peak = equity.cummax()
        dd = (equity - peak) / peak
        max_dd = dd.min() * 100
        
        return {
            'total_return': total_ret,
            'sharpe': sharpe,
            'max_drawdown': max_dd,
            'equity': equity,
            'returns': rets,
        }
```

---

## 五、Stoke 优先级路线图

### 🔴 P0 — 立即可做（零额外依赖）

| 任务 | 描述 | 工作料 |
|------|------|--------|
| mootdx loader 稳定性 | K线数据 800 根/次，零限流，TCP 断线重连 | 已实现 |
| 量价计算模块 | RSI/MACD/布林带/MA/动量等指标的纯 pandas 实现 | ~100 行 |
| 轻量回测引擎 | 基于 mootdx 数据的单标的回测，等权多标的回测 | ~200 行 |
| 选股筛选脚本 | 今天写的"龙头+中军+弹性"三维分类逻辑 | ~150 行 |

### 🟡 P1 — 短期（需要 Tushare 免费版）

| 任务 | 描述 |
|------|------|
| 行业分类接入 | Tushare `index_classify` 拉申万行业 |
| 估值 PE/PB | 腾讯财经 `get_index_pe` + `get_market_pb` |
| 成分股列表 | 申万行业成分股 → 行业轮动策略基础 |
| Tushare 限流优化 | 10秒间隔，缓存策略 |

### 🟢 P2 — 中期（AKShare 恢复后 / Tushare 付费）

| 任务 | 描述 |
|------|------|
| 新闻/研报数据 | AKShare 东财/同花顺接口 |
| 多因子选股 | PE/PB/ROE + 动量 + 波动率 |
| 涨停板分析 | 强势股题材归因 |
| 分钟级 K 线 | Tushare 付费版历史分钟 |

### 🔵 P3 — 长期（可选探索）

| 任务 | 描述 |
|------|------|
| Agent 自动化 | LLM 生成策略 + 自动回测 → 仿 Vibe-Trading 但更轻 |
| 基本面深挖 | PIT（时点准确）财报数据 |
| 开源回测平台对接 | vnpy / backtrader 对接 Stoke 数据源 |

---

*基于 Vibe-Trading v0.1.8 探索，Stoke 当前定位为纯数据层 + 可选轻量分析。不建议引入 LangChain 全家桶。*

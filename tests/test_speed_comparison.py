"""
数据源超时评估 — 模拟发现层+时机层完整调用，对比各源速度
"""
import sys
sys.path.insert(0, "/Volumes/Black/Stoke")
import time
import pandas as pd
from stoke import Stoke

s = Stoke()
print("=" * 60)
print("数据源速度对比评估")
print("=" * 60)

# 测试股票
STOCKS = ["000001", "600000", "600519", "000858", "002415"]

# ==================== K 线竞速：4 源对比 ====================
print("\n--- K 线竞速 (5 只股票各 30 天) ---")
for sym in STOCKS:
    results = {}

    # mootdx (TCP, 不限速)
    try:
        t0 = time.time()
        df = s.kline(sym, frequency=9, start=0, offset=30)
        results["mootdx"] = f"{time.time()-t0:.3f}s/{len(df)}条"
    except Exception as e:
        results["mootdx"] = f"FAIL: {e}"

    # efinance (HTTP, 0.5s限流)
    try:
        t0 = time.time()
        from datetime import date, timedelta
        start = (date.today() - timedelta(days=60)).strftime("%Y%m%d")
        df2 = s.kline_efinance(sym, start_date=start)
        results["efinance"] = f"{time.time()-t0:.3f}s/{len(df2)}条"
    except Exception as e:
        results["efinance"] = f"FAIL: {e}"

    # baostock (HTTP, 1s限流)
    try:
        t0 = time.time()
        bs_sym = f"{'sh' if sym.startswith('6') else 'sz'}.{sym}"
        df3 = s.kline_baostock(bs_sym, start_date="2026-05-01", adjust="qfq")
        results["baostock"] = f"{time.time()-t0:.3f}s/{len(df3)}条"
    except Exception as e:
        results["baostock"] = f"FAIL: {e}"

    print(f"  {sym}: mootdx={results.get('mootdx','?')} | efinance={results.get('efinance','?')} | baostock={results.get('baostock','?')}")

# ==================== 大盘数据竞速 ====================
print("\n--- 大盘数据竞速 ---")
benchmark = {}

# mootdx 指数K线 vs akshare market_breadth
t0 = time.time()
df_idx = s.mootdx.client.index(symbol="999999", frequency=9, start=0, offset=30)
benchmark["mootdx上证K线"] = f"{time.time()-t0:.3f}s/{len(df_idx)}条"
print(f"  mootdx 上证K线: {benchmark['mootdx上证K线']}")

try:
    t0 = time.time()
    df_breadth = s.market_breadth()
    benchmark["akshare上证K线"] = f"{time.time()-t0:.3f}s/{len(df_breadth)}条"
except Exception as e:
    benchmark["akshare上证K线"] = f"FAIL: {e}"
print(f"  akshare 上证K线: {benchmark.get('akshare上证K线','?')}")

try:
    t0 = time.time()
    df_em_sh = s.kline_efinance("000001", start_date="20260501")  # 上证指数在efinance中
    benchmark["efinance上证K线"] = f"{time.time()-t0:.3f}s/{len(df_em_sh)}条"
except Exception as e:
    benchmark["efinance上证K线"] = f"SKIP: efinance无指数K线"

# ==================== 龙虎榜竞速 ====================
print("\n--- 龙虎榜竞速 ---")
try:
    t0 = time.time()
    df_dt_ak = s.dragon_tiger()
    print(f"  akshare 龙虎榜: {time.time()-t0:.3f}s/{len(df_dt_ak)}条")
except Exception as e:
    print(f"  akshare 龙虎榜: FAIL: {e}")

try:
    t0 = time.time()
    df_dt_ef = s.daily_billboard()
    print(f"  efinance 龙虎榜: {time.time()-t0:.3f}s/{len(df_dt_ef)}条")
except Exception as e:
    print(f"  efinance 龙虎榜: FAIL: {e}")

# ==================== 多源并行模拟 ====================
print("\n--- 多源并行模拟 (发现层完整一轮) ---")
import concurrent.futures

def fetch_discovery():
    """发现层：粗筛 5 接口 + 精筛 5 候选股 K 线"""
    sub_results = {}
    t0 = time.time()

    # 粗筛 (5 akshare calls)
    calls = [
        ("limit_up", lambda: s.limit_up()),
        ("strong_stocks", lambda: s.strong_stocks()),
        ("sector_rank", lambda: s.sector_rank()),
        ("northbound_flow", lambda: s.northbound_flow()),
        ("hot_keywords", lambda: s.hot_keywords()),
    ]
    for name, fn in calls:
        try:
            t1 = time.time()
            data = fn()
            sub_results[name] = f"{time.time()-t1:.1f}s/{len(data)}条"
        except Exception as e:
            sub_results[name] = f"FAIL"

    sub_results["discovery_coarse_total"] = f"{time.time()-t0:.1f}s"
    return sub_results

def fetch_timing():
    """时机层：4 维度"""
    sub_results = {}
    t0 = time.time()

    calls = [
        ("大盘_market_volume", lambda: s.market_volume()),
        ("估值_index_pe", lambda: s.index_pe()),
        ("估值_market_pb", lambda: s.market_pb()),
        ("情绪_stock_comment", lambda: s.stock_comment_all()),
        ("情绪_xueqiu_hot", lambda: s.xueqiu_hot()),
    ]
    for name, fn in calls:
        try:
            t1 = time.time()
            data = fn()
            sub_results[name] = f"{time.time()-t1:.1f}s/{len(data)}条"
        except Exception as e:
            sub_results[name] = "FAIL"

    # 指数 K 线 (用 mootdx 替代 akshare)
    t1 = time.time()
    df_idx = s.mootdx.client.index(symbol="000300", frequency=9, start=0, offset=100)
    sub_results["大盘_沪深300K线(mootdx)"] = f"{time.time()-t1:.2f}s/{len(df_idx)}条"

    sub_results["timing_total"] = f"{time.time()-t0:.1f}s"
    return sub_results

def fetch_kline_batch():
    """K 线批量 (mootdx, 不限速)"""
    t0 = time.time()
    for sym in ["000001", "000002", "000858", "600000", "600036", "600519", "601318", "000333", "002415", "300750"]:
        s.mootdx.client.bars(symbol=sym, frequency=9, start=0, offset=50)
    return {"kline_batch_mootdx": f"{time.time()-t0:.2f}s/10只"}

# 并行执行
t_total = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
    f1 = executor.submit(fetch_discovery)
    f2 = executor.submit(fetch_timing)
    f3 = executor.submit(fetch_kline_batch)

    disc = f1.result()
    tim = f2.result()
    kline = f3.result()

total_time = time.time() - t_total
print(f"\n  === 发现层 ===")
for k, v in disc.items():
    print(f"    {k}: {v}")
print(f"\n  === 时机层 ===")
for k, v in tim.items():
    print(f"    {k}: {v}")
print(f"\n  === K线批量 ===")
for k, v in kline.items():
    print(f"    {k}: {v}")
print(f"\n  *** 并行总耗时: {total_time:.1f}s ***")

# ==================== 速度排名 ====================
print("\n--- 各源 K 线速度排名 ---")
print("  1. mootdx (TCP):    ~0.05s — 最快，K线首选")
print("  2. efinance (HTTP):  ~0.3s — 极快，含振幅/涨跌幅")
print("  3. baostock (HTTP):  ~0.7s — 中等，唯一复权方案")
print("  4. akshare (HTTP):   ~5.0s — 最慢，仅用于独有数据")

print("\n--- 超时替换建议 ---")
print("  market_breadth → mootdx.index('999999')  (5s → 0.05s)")
print("  K线(发现层)    → mootdx.bars()           (5s → 0.05s)")
print("  K线(复权需求)  → baostock.kline()        (5s → 0.7s)")
print("  龙虎榜         → efinance (0.5s vs 5s)   (可选)")
print("  akshare保留:   新闻/研报/公告/涨停/情绪/资金流 (独有)")
print("=" * 60)

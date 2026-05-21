"""
Baostock 数据源测试：K线(含复权)、行业分类、股票列表、健康检查
"""
import sys
sys.path.insert(0, "/Volumes/Black/Stoke")
import time
import pandas as pd
from stoke import Stoke

s = Stoke()
print("=" * 60)
print("Baostock 数据源测试")
print("=" * 60)

# ---- 1. 健康检查 ----
print("\n--- 1. 健康检查 ---")
t0 = time.time()
ok = s.baostock.health_check()
print(f"  健康检查: {'PASS' if ok else 'FAIL'} | {time.time()-t0:.3f}s")

# ---- 2. K线不复权 ----
print("\n--- 2. K线 (不复权) ---")
t0 = time.time()
df = s.kline_baostock("sh.600000", start_date="2026-04-01", adjust="none")
elapsed = time.time() - t0
print(f"  浦发银行: {len(df)}条 | {elapsed:.3f}s")
if len(df) > 0:
    print(f"  列: {list(df.columns)}")
    print(f"  最新: date={df['date'].iloc[-1]}, close={df['close'].iloc[-1]}")

# ---- 3. K线前复权 ----
print("\n--- 3. K线 (前复权) ---")
t0 = time.time()
df_qfq = s.kline_baostock("sh.600000", start_date="2026-04-01", adjust="qfq")
elapsed = time.time() - t0
print(f"  浦发银行前复权: {len(df_qfq)}条 | {elapsed:.3f}s")
if len(df_qfq) > 0 and len(df) > 0:
    # 不复权和前复权 close 应该不同
    close_diff = abs(df_qfq['close'].iloc[-1] - df['close'].iloc[-1])
    print(f"  不复权close={df['close'].iloc[-1]}, 前复权close={df_qfq['close'].iloc[-1]}, 差值={close_diff:.4f}")

# ---- 4. K线后复权 ----
print("\n--- 4. K线 (后复权) ---")
t0 = time.time()
df_hfq = s.kline_baostock("sh.600000", start_date="2026-04-01", adjust="hfq")
elapsed = time.time() - t0
print(f"  浦发银行后复权: {len(df_hfq)}条 | {elapsed:.3f}s")

# ---- 5. 深市股票 ----
print("\n--- 5. 深市股票 ---")
t0 = time.time()
df_sz = s.kline_baostock("sz.000001", start_date="2026-05-01", adjust="qfq")
elapsed = time.time() - t0
print(f"  平安银行: {len(df_sz)}条 | {elapsed:.3f}s")

# ---- 6. 行业分类 ----
print("\n--- 6. 行业分类 ---")
t0 = time.time()
df_ind = s.stock_industry()
elapsed = time.time() - t0
print(f"  行业分类: {len(df_ind)}条 | {elapsed:.3f}s")
if len(df_ind) > 0:
    print(f"  列: {list(df_ind.columns)}")
    print(f"  行业分布示例:")
    for ind in df_ind["industry"].value_counts().head(5).index:
        print(f"    - {ind}")

# ---- 7. 股票列表 ----
print("\n--- 7. 股票列表 ---")
t0 = time.time()
df_all = s.all_stock()
elapsed = time.time() - t0
print(f"  股票列表: {len(df_all)}条 | {elapsed:.3f}s")
if len(df_all) > 0:
    print(f"  列: {list(df_all.columns)}")
    # 看看 status 分布
    if "status" in df_all.columns:
        print(f"  status 分布: {df_all['status'].value_counts().to_dict()}")

# ---- 8. 上下文管理器 ----
print("\n--- 8. 上下文管理器 ---")
from stoke.sources.baostock_source import BaostockSource
with BaostockSource() as bs:
    df_ctx = bs.get_kline("sz.000002", frequency="d", start_date="2026-05-19", adjust="qfq")
    print(f"  with 语法: 万科A {len(df_ctx)}条 | close={df_ctx['close'].iloc[-1] if len(df_ctx) > 0 else 'N/A'}")

# ---- 9. 多复权对比 ----
print("\n--- 9. 多复权对比 (贵州茅台 sh.600519) ---")
for adj_name, adj_val in [("不复权", "none"), ("前复权", "qfq"), ("后复权", "hfq")]:
    try:
        df_adj = s.kline_baostock("sh.600519", start_date="2026-05-01", adjust=adj_val)
        if len(df_adj) > 0:
            last = df_adj.iloc[-1]
            print(f"  {adj_name}: close={last['close']:.2f}, open={last['open']:.2f}, date={last['date'].date()}")
    except Exception as e:
        print(f"  {adj_name}: FAIL - {e}")

print("\n" + "=" * 60)
print("Baostock 测试完成")
print("=" * 60)

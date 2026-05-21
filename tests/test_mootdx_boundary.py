"""
mootdx 边界测试：探索未使用能力，评估分流 akshare 的潜力
"""
import time
import sys
sys.path.insert(0, "/Volumes/Black/Stoke")

from mootdx.quotes import Quotes

client = Quotes.factory(market="std")

print("=" * 60)
print("mootdx 边界探索测试")
print("=" * 60)

# ============ 1. 指数 K 线 ============
print("\n--- 1. 指数 K 线 ---")
indices = {
    "999999": "上证指数",
    "399001": "深证成指",
    "399006": "创业板指",
    "399005": "中小板指",
    "000016": "上证50",
    "000300": "沪深300",
    "000688": "科创50",
}
for code, name in indices.items():
    try:
        t0 = time.time()
        df = client.index(symbol=code, frequency=9, start=0, offset=10)
        elapsed = time.time() - t0
        ok = len(df) > 0 if df is not None else False
        print(f"  {name}({code}): {'OK' if ok else 'EMPTY'} | {len(df) if df is not None else 0}条 | {elapsed:.3f}s")
    except Exception as e:
        print(f"  {name}({code}): FAIL - {e}")

# ============ 2. 分钟 K 线 ============
print("\n--- 2. 分钟 K 线 ---")
test_stock = "000001"
frequencies = {
    "1分钟": 1,
    "5分钟": 5,
}
for fname, freq in frequencies.items():
    try:
        t0 = time.time()
        df = client.minute(symbol=test_stock, frequency=freq)
        elapsed = time.time() - t0
        print(f"  {fname}({test_stock}): {len(df) if df is not None else 0}条 | {elapsed:.3f}s")
        if df is not None and len(df) > 0:
            print(f"    列: {list(df.columns)}")
            print(f"    首行: {df.head(1).to_dict('records')[0]}")
    except Exception as e:
        print(f"  {fname}({test_stock}): FAIL - {e}")

# ============ 3. 板块/行业数据探索 ============
print("\n--- 3. 板块数据探索 ---")
try:
    t0 = time.time()
    blocks = client.block()
    elapsed = time.time() - t0
    print(f"  全量板块数据: {len(blocks)}条 | {elapsed:.3f}s")
    print(f"  列名: {list(blocks.columns)}")
    print(f"  block_type 分布:")
    type_counts = blocks["block_type"].value_counts()
    for bt, cnt in type_counts.items():
        print(f"    {bt}: {cnt}")
    print(f"\n  blockname 示例 (前15):")
    for name in blocks["block_name"].unique()[:15]:
        print(f"    - {name}")
except Exception as e:
    print(f"  板块数据: FAIL - {e}")

# ============ 4. 批量 K 线耗时测试 ============
print("\n--- 4. 批量 K 线并发测试 ---")
test_symbols = ["000001", "000002", "000858", "600000", "600036",
                "600519", "601318", "000333", "002415", "300750"]
t0 = time.time()
for sym in test_symbols:
    try:
        df = client.bars(symbol=sym, frequency=9, start=0, offset=50)
        ok = "OK" if df is not None and len(df) > 0 else "EMPTY"
        print(f"  {sym}: {ok} ({len(df) if df is not None else 0}条)")
    except Exception as e:
        print(f"  {sym}: FAIL - {e}")
total = time.time() - t0
print(f"  总耗时: {total:.3f}s | 平均: {total/len(test_symbols):.3f}s/只")

# ============ 5. F10 字段探索 ============
print("\n--- 5. F10 数据深度探索 ---")
try:
    t0 = time.time()
    f10 = client.finance(symbol="000001")
    elapsed = time.time() - t0
    if isinstance(f10, dict):
        print(f"  F10 字段数: {len(f10)} | {elapsed:.3f}s")
        for k, v in f10.items():
            vtype = type(v).__name__
            vsize = len(v) if hasattr(v, '__len__') else '?'
            print(f"    {k}: {vtype}({vsize})")
    else:
        print(f"  F10 返回类型: {type(f10).__name__}")
except Exception as e:
    print(f"  F10: FAIL - {e}")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)

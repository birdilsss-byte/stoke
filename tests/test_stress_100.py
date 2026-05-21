"""
100 轮压力测试 — 模拟发现层 + 时机层并发查询

场景：
  发现层: limit_up, strong_stocks, sector_rank, northbound_flow, hot_keywords + kline×5
  时机层: market_breadth, index_pe, market_pb, stock_comment, market_volume

指标：
  预热耗时 | 缓存命中率 | 每轮延迟 | 总耗时 | 异常次数
"""
import sys
sys.path.insert(0, "/Volumes/Black/Stoke")
import time
import logging
logging.basicConfig(level=logging.WARNING)

from stoke import Stoke
from stoke.config import setup_logging
setup_logging("WARNING")

import concurrent.futures

ROUNDS = 100
KLINE_SYMBOLS = ["000001", "000858", "600519", "601318", "002415"]

print("=" * 70)
print(f"Stoke 压力测试 — {ROUNDS} 轮 (发现层 + 时机层)")
print("=" * 70)

s = Stoke(use_cache=True)

# ---- 预热 ----
print("\n[1/3] 盘前预热...")
t0 = time.time()
warmed = s.store.warmup(s)
warmup_time = time.time() - t0
print(f"  完成 {len(warmed)} 项, {warmup_time:.1f}s")
for n, c in sorted(s.store.stats().items()):
    if c > 0:
        print(f"  [+] {n}: {c}")

# ---- 100 轮 ----
print(f"\n[2/3] {ROUNDS} 轮压力测试...")

results = []
errors = 0

def fetch_discovery():
    """发现层一次扫描"""
    try:
        s.limit_up()
        s.strong_stocks()
        # s.sector_rank()  # 东财限流中，暂时跳过
        s.northbound_flow()
        s.hot_keywords()
        for sym in KLINE_SYMBOLS:
            s.kline(sym, start=0, offset=30)
    except Exception as e:
        return str(e)
    return None

def fetch_timing():
    """时机层一次评估"""
    try:
        s.market_breadth()
        s.index_pe("上证50")
        s.market_pb()
        s.stock_comment_all()
        s.market_volume()
    except Exception as e:
        return str(e)
    return None

for r in range(1, ROUNDS + 1):
    t0 = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(fetch_discovery)
        f2 = ex.submit(fetch_timing)
        err_d = f1.result()
        err_t = f2.result()

    elapsed = time.time() - t0
    if err_d:
        errors += 1
    if err_t:
        errors += 1

    results.append(elapsed)

    if r == 1:
        print(f"  #{r:3d}: {elapsed*1000:6.0f}ms (预热轮)")
    elif r % 20 == 0:
        avg = sum(results) / len(results)
        hit_count = sum(1 for t in results if t < 0.5)
        rate = hit_count / len(results) * 100
        print(f"  #{r:3d}: {elapsed*1000:6.0f}ms | 平均 {avg*1000:.0f}ms | 命中率 {rate:.0f}%")

# ---- 统计 ----
total_time = sum(results)
avg_time = total_time / ROUNDS
min_time = min(results)
max_time = max(results)
hit_count = sum(1 for t in results if t < 0.5)
hit_rate = hit_count / ROUNDS * 100
first_round = results[0]
steady_avg = sum(results[1:]) / (ROUNDS - 1) if ROUNDS > 1 else 0

print(f"\n[3/3] 结果")
print("=" * 70)
print(f"  轮次:         {ROUNDS}")
print(f"  预热耗时:      {warmup_time:.1f}s")
print(f"  第1轮耗时:     {first_round*1000:.0f}ms")
print(f"  稳定期平均:    {steady_avg*1000:.0f}ms (第2-{ROUNDS}轮)")
print(f"  最小/最大:     {min_time*1000:.0f}ms / {max_time*1000:.0f}ms")
print(f"  缓存命中率:    {hit_rate:.0f}% ({hit_count}/{ROUNDS})")
print(f"  异常次数:      {errors}")
print(f"  总耗时:        {total_time:.1f}s")

# 数据库
print(f"\n  数据库:")
for n, c in sorted(s.store.stats().items()):
    if c > 0:
        print(f"    {n}: {c}")

# 判定
print()
if hit_rate >= 95 and errors == 0:
    print("  >>> PASS — 系统稳定，缓存命中率达标 <<<")
elif hit_rate >= 80:
    print("  >>> WARN — 缓存命中率偏低，建议检查 TTL 配置 <<<")
else:
    print("  >>> FAIL — 缓存命中率不达标 <<<")
print("=" * 70)

"""
Stoke 100 轮全层压力测试 v2

改进：
- 预热阶段：warmup + 验证表状态
- 精确命中检测：store._is_fresh()
- 成功率统计：>= 95% 目标
- 延迟分位数：P50/P75/P90/P95/P99
- HTML 可视化报告 + JSON 原始数据
"""
import sys
sys.path.insert(0, "/Volumes/Black/Stoke")

import time
import logging
import json
import os
import math
from datetime import datetime
from collections import defaultdict

logging.basicConfig(level=logging.WARNING)
from stoke import Stoke
from stoke.config import setup_logging
from stoke.calendar import today_str
setup_logging("WARNING")
logging.getLogger("stoke.utils").setLevel(logging.ERROR)
logging.getLogger("stoke.store").setLevel(logging.ERROR)
logging.getLogger("stoke.client").setLevel(logging.ERROR)
logging.getLogger("stoke.client_cached").setLevel(logging.ERROR)

ROUNDS = 100
SUCCESS_TARGET = 95.0

# ===== 测试数据 =====
DISCOVERY_KLINE = ["000001", "000858", "600519", "601318", "002415",
                   "600036", "000333", "002475", "300750", "603259"]
TIMING_INDICES = ["上证50", "沪深300"]
EXEC_KLINE = ["600000", "000002", "600030", "000725", "002230"]
EXEC_FUND_FLOW = ["000001", "600519", "601318"]
REFLECT_KLINE = ["000651", "600887", "002594", "300124", "688981"]
REFLECT_SECTORS = ["银行", "半导体", "医药"]

print("=" * 60)
print("  Stoke 100 轮全层压力测试 v2")
print(f"  目标成功率: >= {SUCCESS_TARGET}%")
print("=" * 60)

# ===== Phase 0: 检查缓存文件 =====
cache_db = os.path.expanduser("~/.stoke/stoke_cache.db")
if os.path.exists(cache_db):
    print(f"\n[预热前] 缓存文件已存在: {cache_db}")
    print("  如需冷启动测试，请先删除缓存文件: rm ~/.stoke/stoke_cache.db")
else:
    print(f"\n[预热前] 无缓存文件，将执行冷启动")

# ===== Phase 1: 预热 =====
print("\n--- Phase 1: 盘前预热 ---")
warmup_start = time.time()

s = Stoke()

try:
    warmup_result = s.store.warmup(s.raw)
    warmup_elapsed = time.time() - warmup_start
    print(f"  预热完成: {warmup_elapsed:.1f}s")

    # 验证表状态
    db_stats = s.store.stats()
    total_rows = sum(db_stats.values())
    non_empty_tables = sum(1 for v in db_stats.values() if v > 0)
    print(f"  表状态: {non_empty_tables}/{len(db_stats)} 表有数据, 总行数 {total_rows:,}")
    for table_name, row_count in sorted(db_stats.items()):
        status = "✓" if row_count > 0 else "✗"
        print(f"    {status} {table_name}: {row_count:,} 行")
except Exception as e:
    warmup_elapsed = time.time() - warmup_start
    print(f"  预热失败（将跳过，直接压测）: {e}")
    db_stats = {}

# ===== Phase 2: 100 轮压测 =====
print(f"\n--- Phase 2: {ROUNDS} 轮压测 ---")

round_logs = []
method_stats = defaultdict(lambda: {"hits": 0, "misses": 0, "errors": 0, "latencies": []})
per_layer_times = defaultdict(list)
total_errors = 0
total_empty = 0

def is_cache_hit(table, key):
    """使用 store._is_fresh() 精确判断缓存命中"""
    try:
        return s.store._is_fresh(table, key, max_age_sec=99999)
    except Exception:
        return False

def cached_call(name, layer, key_info, fn):
    """包装一次调用，记录精确命中/未命中/异常"""
    global total_errors, total_empty
    t0 = time.time()
    try:
        df = fn()
        elapsed = time.time() - t0

        # 精确判断是否缓存命中
        hit = False
        if key_info:
            table, key = key_info
            try:
                hit = s.store._is_fresh(table, key, max_age_sec=99999)
            except Exception:
                hit = elapsed < 0.1  # fallback

        rows = len(df) if hasattr(df, '__len__') else 0
        if rows == 0 and hit is False:
            total_empty += 1  # 可能非交易日

        method_stats[name]["latencies"].append(elapsed)
        if hit:
            method_stats[name]["hits"] += 1
        else:
            method_stats[name]["misses"] += 1
        return elapsed, hit, rows, None, layer
    except Exception as e:
        elapsed = time.time() - t0
        method_stats[name]["errors"] += 1
        method_stats[name]["latencies"].append(elapsed)
        total_errors += 1
        return elapsed, False, 0, str(e)[:100], layer

def round_pct(current, total, start_time):
    """显示进度"""
    pct = current / total * 100
    elapsed = time.time() - start_time
    if current > 1:
        eta = elapsed / current * (total - current)
    else:
        eta = 0
    return f"[{current:3d}/{total}] {pct:5.1f}% | 已耗时 {elapsed:.0f}s | 预计剩余 {eta:.0f}s"

print("(顺序执行，akshare 线程不安全)\n")

total_start = time.time()
last_print_round = 0

for r in range(1, ROUNDS + 1):
    round_start_time = time.time()
    round_results = {}
    round_hits = 0
    round_total = 0
    round_errors = 0

    # --- 发现层 ---
    disc_start = time.time()
    disc_results = {}
    layer_calls = [
        ("limit_up", "limit_up", today_str(), lambda: s.limit_up()),
        ("strong_stocks", "strong_stocks", today_str(), lambda: s.strong_stocks()),
        ("hot_keywords", "hot_keywords", today_str(), lambda: s.hot_keywords()),
        ("northbound_flow", "northbound_flow", today_str(), lambda: s.northbound_flow()),
        ("dragon_tiger", "dragon_tiger", today_str(), lambda: s.dragon_tiger()),
    ]
    for name, table, key, fn in layer_calls:
        elapsed, hit, rows, err, _ = cached_call(name, "discovery", (table, key), fn)
        disc_results[name] = {"elapsed": elapsed, "hit": hit, "rows": rows, "error": err}
        if err:
            round_errors += 1
        round_total += 1
        if hit:
            round_hits += 1
    for sym in DISCOVERY_KLINE:
        name = f"kline_disc_{sym}"
        elapsed, hit, rows, err, _ = cached_call(name, "discovery",
            ("kline_daily", sym),
            lambda s=s, sym=sym: s.kline(sym, start=0, offset=100))
        disc_results[name] = {"elapsed": elapsed, "hit": hit, "rows": rows, "error": err}
        if err:
            round_errors += 1
        round_total += 1
        if hit:
            round_hits += 1
    disc_time = time.time() - disc_start

    # --- 时机层 ---
    tim_start = time.time()
    tim_results = {}
    layer_calls = [
        ("market_breadth", "market_breadth", today_str(), lambda: s.market_breadth()),
        ("market_volume", "market_volume", today_str(), lambda: s.market_volume()),
        ("market_pb", "market_pb", today_str(), lambda: s.market_pb()),
        ("stock_comment_all", "stock_comment", today_str(), lambda: s.stock_comment_all()),
    ]
    for name, table, key, fn in layer_calls:
        elapsed, hit, rows, err, _ = cached_call(name, "timing", (table, key), fn)
        tim_results[name] = {"elapsed": elapsed, "hit": hit, "rows": rows, "error": err}
        if err:
            round_errors += 1
        round_total += 1
        if hit:
            round_hits += 1
    for idx in TIMING_INDICES:
        name = f"index_pe_{idx}"
        elapsed, hit, rows, err, _ = cached_call(name, "timing",
            ("index_pe", idx),
            lambda s=s, idx=idx: s.index_pe(idx))
        tim_results[name] = {"elapsed": elapsed, "hit": hit, "rows": rows, "error": err}
        if err:
            round_errors += 1
        round_total += 1
        if hit:
            round_hits += 1
    tim_time = time.time() - tim_start

    # --- 执行层 ---
    exec_start = time.time()
    exec_results = {}
    for sym in EXEC_KLINE:
        name = f"kline_exec_{sym}"
        elapsed, hit, rows, err, _ = cached_call(name, "execution",
            ("kline_daily", sym),
            lambda s=s, sym=sym: s.kline(sym, start=0, offset=50))
        exec_results[name] = {"elapsed": elapsed, "hit": hit, "rows": rows, "error": err}
        if err:
            round_errors += 1
        round_total += 1
        if hit:
            round_hits += 1
    for sym in EXEC_FUND_FLOW:
        name = f"fund_flow_{sym}"
        elapsed, hit, rows, err, _ = cached_call(name, "execution",
            None, lambda s=s, sym=sym: s.individual_fund_flow(sym))
        exec_results[name] = {"elapsed": elapsed, "hit": hit, "rows": rows, "error": err}
        if err:
            round_errors += 1
        round_total += 1
        if hit:
            round_hits += 1
    for sym in EXEC_KLINE[:3]:
        name = f"realtime_{sym}"
        elapsed, hit, rows, err, _ = cached_call(name, "execution",
            None, lambda s=s, sym=sym: s.realtime([sym]))
        exec_results[name] = {"elapsed": elapsed, "hit": hit, "rows": rows, "error": err}
        if err:
            round_errors += 1
        round_total += 1
        if hit:
            round_hits += 1
    exec_time = time.time() - exec_start

    # --- 沉淀层 ---
    refl_start = time.time()
    refl_results = {}
    for sym in REFLECT_KLINE:
        name = f"kline_refl_{sym}"
        elapsed, hit, rows, err, _ = cached_call(name, "reflection",
            ("kline_daily", sym),
            lambda s=s, sym=sym: s.kline(sym, start=0, offset=800))
        refl_results[name] = {"elapsed": elapsed, "hit": hit, "rows": rows, "error": err}
        if err:
            round_errors += 1
        round_total += 1
        if hit:
            round_hits += 1
    for sec in REFLECT_SECTORS:
        name = f"sector_{sec}"
        elapsed, hit, rows, err, _ = cached_call(name, "reflection",
            None, lambda s=s, sec=sec: s.sector_kline(sec))
        refl_results[name] = {"elapsed": elapsed, "hit": hit, "rows": rows, "error": err}
        if err:
            round_errors += 1
        round_total += 1
        if hit:
            round_hits += 1
    refl_time = time.time() - refl_start

    round_time = time.time() - round_start_time
    hit_pct = round_hits / round_total * 100 if round_total > 0 else 0

    round_logs.append({
        "round": r,
        "elapsed": round_time,
        "hits": round_hits,
        "total_calls": round_total,
        "hit_pct": hit_pct,
        "errors": round_errors,
        "layer_times": {
            "discovery": disc_time,
            "timing": tim_time,
            "execution": exec_time,
            "reflection": refl_time,
        },
    })

    per_layer_times["discovery"].append(disc_time)
    per_layer_times["timing"].append(tim_time)
    per_layer_times["execution"].append(exec_time)
    per_layer_times["reflection"].append(refl_time)

    # 打印进度 (每 10 轮或首轮)
    if r == 1 or r % 10 == 0 or r == ROUNDS:
        status = round_pct(r, ROUNDS, total_start)
        bar = "█" * (r // 5) + "░" * ((ROUNDS - r) // 5)
        print(f"  {status:45s} | 命中 {round_hits:2d}/{round_total:2d} ({hit_pct:.0f}%) | 本轮 {round_time*1000:.0f}ms | 累计异常 {total_errors}")

total_time = time.time() - total_start

# ===== Phase 3: 统计 =====
print(f"\n--- Phase 3: 统计 ---")

total_calls_all = sum(log["total_calls"] for log in round_logs)
total_hits_all = sum(log["hits"] for log in round_logs)
total_errors_all = sum(log["errors"] for log in round_logs)
success_rate = (total_calls_all - total_errors_all) / total_calls_all * 100 if total_calls_all > 0 else 0
overall_hit_rate = total_hits_all / total_calls_all * 100 if total_calls_all > 0 else 0

round_times = [log["elapsed"] for log in round_logs]
avg_first_50 = sum(round_times[:50]) / 50 if len(round_times) >= 50 else sum(round_times) / len(round_times)
avg_last_50 = sum(round_times[50:]) / 50 if len(round_times) >= 100 else 0

def percentile(data, p):
    if not data:
        return 0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * p / 100
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    return sorted_data[f] * (c - k) + sorted_data[c] * (k - f)

# ===== Phase 4: HTML 报告 =====
print("--- Phase 4: 生成 HTML 报告 ---")

today_str_fn = lambda: datetime.now().strftime("%Y%m%d")
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
report_dir = os.path.dirname(os.path.abspath(__file__))
report_path = os.path.join(report_dir, f"stress_report_v2_{timestamp}.html")
data_path = os.path.join(report_dir, f"stress_data_v2_{timestamp}.json")

def gradient_color(val, max_val):
    ratio = min(val / max(max_val, 0.001), 1.0)
    r = int(220 + 35 * ratio)
    g = int(240 - 190 * ratio)
    b = int(240 - 190 * ratio)
    return f"rgb({r},{g},{b})"

status_color = "#00d4aa" if success_rate >= SUCCESS_TARGET else "#ffaa00" if success_rate >= 90 else "#ff4444"
status_text = "PASS" if success_rate >= SUCCESS_TARGET else "WARN" if success_rate >= 90 else "FAIL"

db_stats_final = s.store.stats()
total_rows_final = sum(db_stats_final.values())

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Stoke 压力测试报告 v2 · {timestamp}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; background: #0d1117; color: #c9d1d9; padding: 30px; max-width: 1300px; margin: 0 auto; line-height: 1.5; }}
h1 {{ color: #58a6ff; border-bottom: 2px solid #21262d; padding-bottom: 12px; margin-bottom: 6px; font-size: 1.8em; }}
h2 {{ color: #8b949e; margin: 30px 0 12px; font-size: 1.3em; }}
.subtitle {{ color: #8b949e; margin-bottom: 20px; font-size: 0.9em; }}

.summary-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 24px 0; }}
@media (max-width: 800px) {{ .summary-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
.summary-card {{ background: #161b22; border: 1px solid #21262d; padding: 24px; border-radius: 8px; text-align: center; }}
.summary-card .value {{ font-size: 2.2em; font-weight: 700; margin: 8px 0; }}
.summary-card .label {{ font-size: 0.85em; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; }}
.summary-card .sub {{ font-size: 0.75em; color: #484f58; margin-top: 4px; }}

.badge {{ display: inline-block; padding: 4px 14px; border-radius: 20px; font-weight: 700; font-size: 0.85em; margin-right: 8px; }}
.badge-pass {{ background: #23863622; color: #3fb950; border: 1px solid #23863644; }}
.badge-warn {{ background: #d2992222; color: #d29922; border: 1px solid #d2992244; }}
.badge-fail {{ background: #da363322; color: #f85149; border: 1px solid #da363344; }}

table {{ border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 0.9em; }}
th {{ background: #161b22; padding: 10px 12px; text-align: left; border-bottom: 2px solid #30363d; font-weight: 600; color: #8b949e; position: sticky; top: 0; }}
td {{ padding: 7px 12px; border-bottom: 1px solid #21262d; }}
tr:hover {{ background: #1c2128; }}
.num {{ text-align: right; font-variant-numeric: tabular-nums; }}

.chart-bar {{ display: inline-block; height: 16px; border-radius: 2px; min-width: 2px; vertical-align: middle; }}
.bar-hit {{ background: #3fb950; }}
.bar-miss {{ background: #f85149; }}
.bar-err {{ background: #d29922; }}

.verdict-box {{ background: #161b22; border: 2px solid {status_color}; border-radius: 8px; padding: 20px; margin: 20px 0; }}
.verdict-box h3 {{ color: {status_color}; margin-bottom: 10px; }}

.progress-bar {{ height: 24px; background: #21262d; border-radius: 4px; overflow: hidden; margin: 4px 0; }}
.progress-fill {{ height: 100%; border-radius: 4px; transition: width 0.3s; }}

pre {{ background: #161b22; padding: 16px; border-radius: 6px; overflow-x: auto; font-size: 0.85em; border: 1px solid #21262d; }}
</style>
</head>
<body>

<h1>Stoke 全层压力测试报告 v2</h1>
<p class="subtitle">
    {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} &nbsp;|&nbsp;
    {ROUNDS} 轮 &nbsp;|&nbsp;
    4 层覆盖 &nbsp;|&nbsp;
    数据源: mootdx/akshare/baostock/efinance/tencent &nbsp;|&nbsp;
    缓存: SQLite
</p>

<div class="summary-grid">
<div class="summary-card">
    <div class="label">状态</div>
    <div class="value" style="color:{status_color}">{status_text}</div>
    <div class="sub">目标 >= {SUCCESS_TARGET}%</div>
</div>
<div class="summary-card">
    <div class="label">成功率</div>
    <div class="value" style="color:{status_color}">{success_rate:.1f}%</div>
    <div class="sub">{total_calls_all - total_errors_all:,} / {total_calls_all:,} 次调用成功</div>
</div>
<div class="summary-card">
    <div class="label">总耗时</div>
    <div class="value">{total_time:.1f}s</div>
    <div class="sub">平均 {sum(round_times)/len(round_times)*1000:.0f}ms/轮</div>
</div>
<div class="summary-card">
    <div class="label">异常</div>
    <div class="value" style="color:{'#3fb950' if total_errors_all == 0 else '#f85149'}">{total_errors_all}</div>
    <div class="sub">总调用 {total_calls_all:,} 次</div>
</div>
</div>

<div class="summary-grid">
<div class="summary-card">
    <div class="label">缓存命中率</div>
    <div class="value" style="color:{'#3fb950' if overall_hit_rate >= 90 else '#d29922' if overall_hit_rate >= 70 else '#f85149'}">{overall_hit_rate:.1f}%</div>
    <div class="sub">{total_hits_all:,} / {total_calls_all:,} 次命中</div>
</div>
<div class="summary-card">
    <div class="label">首 50 轮</div>
    <div class="value">{avg_first_50*1000:.0f}ms</div>
    <div class="sub">平均每轮</div>
</div>
<div class="summary-card">
    <div class="label">后 50 轮</div>
    <div class="value">{avg_last_50*1000:.0f}ms</div>
    <div class="sub">平均每轮</div>
</div>
<div class="summary-card">
    <div class="label">性能收敛</div>
    <div class="value">{avg_first_50/avg_last_50:.1f}x</div>
    <div class="sub">{'正常' if avg_first_50 > avg_last_50 * 1.5 else '有限'}</div>
</div>
</div>

<h2>逐轮趋势 (每 5 轮一摘要)</h2>
<table>
<tr><th>轮次</th><th>耗时</th><th>命中</th><th>命中率</th><th class="num">发现层</th><th class="num">时机层</th><th class="num">执行层</th><th class="num">沉淀层</th><th>可视化</th></tr>
"""
# Show every 5 rounds in HTML
for i, log in enumerate(round_logs):
    if log["round"] % 5 == 1 or log["round"] == ROUNDS or log["round"] <= 3:
        r = log["round"]
        t = log["elapsed"]
        hits = log["hits"]
        total = log["total_calls"]
        pct = log["hit_pct"]
        lt = log["layer_times"]
        disc_t = lt.get("discovery", 0) * 1000
        tim_t = lt.get("timing", 0) * 1000
        exec_t = lt.get("execution", 0) * 1000
        refl_t = lt.get("reflection", 0) * 1000
        max_t = max(round_times) if round_times else 1
        bar_w = max(t / max_t * 300, 2)
        color = gradient_color(t, max_t)

        hit_color = "#3fb950" if pct >= 90 else "#d29922" if pct >= 70 else "#f85149"

        html += f"""<tr>
<td class="num">{r}</td>
<td class="num" style="background:{color}22">{t*1000:.0f}ms</td>
<td class="num">{hits}/{total}</td>
<td class="num" style="color:{hit_color};font-weight:600">{pct:.0f}%</td>
<td class="num">{disc_t:.0f}</td>
<td class="num">{tim_t:.0f}</td>
<td class="num">{exec_t:.0f}</td>
<td class="num">{refl_t:.0f}</td>
<td><span class="chart-bar" style="width:{bar_w}px;background:{color}"></span></td>
</tr>"""

html += """
</table>

<h2>各层延迟统计 (ms)</h2>
<table>
<tr><th>层</th><th class="num">平均</th><th class="num">最小</th><th class="num">P50</th><th class="num">P75</th><th class="num">P90</th><th class="num">P95</th><th class="num">P99</th><th class="num">最大</th></tr>
"""
for layer in ["discovery", "timing", "execution", "reflection"]:
    times = per_layer_times.get(layer, [0.001])
    times_ms = [t * 1000 for t in times]
    avg_t = sum(times) / len(times) * 1000
    min_t = min(times) * 1000
    max_t = max(times) * 1000
    p50 = percentile(times_ms, 50)
    p75 = percentile(times_ms, 75)
    p90 = percentile(times_ms, 90)
    p95 = percentile(times_ms, 95)
    p99 = percentile(times_ms, 99)
    html += f"""<tr>
<td><strong>{layer}</strong></td>
<td class="num">{avg_t:.0f}</td>
<td class="num">{min_t:.0f}</td>
<td class="num">{p50:.0f}</td>
<td class="num">{p75:.0f}</td>
<td class="num">{p90:.0f}</td>
<td class="num">{p95:.0f}</td>
<td class="num">{p99:.0f}</td>
<td class="num">{max_t:.0f}</td>
</tr>"""

html += """
</table>

<h2>方法级统计 (带分位数)</h2>
<table>
<tr><th>方法</th><th class="num">命中</th><th class="num">未命中</th><th class="num">异常</th><th class="num">命中率</th><th class="num">平均(ms)</th><th class="num">P50</th><th class="num">P95</th><th class="num">P99</th></tr>
"""
for name in sorted(method_stats.keys()):
    cs = method_stats[name]
    total_m = cs["hits"] + cs["misses"] + cs["errors"]
    rate = cs["hits"] / total_m * 100 if total_m > 0 else 0
    lats = cs["latencies"]
    lats_ms = [l * 1000 for l in lats]
    avg_lat = sum(lats_ms) / len(lats_ms) if lats_ms else 0
    p50 = percentile(lats_ms, 50)
    p95 = percentile(lats_ms, 95)
    p99 = percentile(lats_ms, 99)
    rate_color = "#3fb950" if rate >= 90 else "#d29922" if rate >= 70 else "#f85149"
    html += f"""<tr>
<td style="font-size:0.8em">{name}</td>
<td class="num bar-hit">{cs["hits"]}</td>
<td class="num bar-miss">{cs["misses"]}</td>
<td class="num bar-err">{cs["errors"]}</td>
<td class="num" style="color:{rate_color}">{rate:.0f}%</td>
<td class="num">{avg_lat:.1f}</td>
<td class="num">{p50:.1f}</td>
<td class="num">{p95:.1f}</td>
<td class="num">{p99:.1f}</td>
</tr>"""

html += """
</table>

<h2>延迟分布 (全局)</h2>
<table>
<tr><th>分位</th><th class="num">发现层</th><th class="num">时机层</th><th class="num">执行层</th><th class="num">沉淀层</th><th class="num">全局</th></tr>
"""
all_times_ms = []
for layer_times in per_layer_times.values():
    all_times_ms.extend([t * 1000 for t in layer_times])

for p_label, p_val in [("P50", 50), ("P75", 75), ("P90", 90), ("P95", 95), ("P99", 99)]:
    row = f"<tr><td><strong>{p_label}</strong></td>"
    for layer in ["discovery", "timing", "execution", "reflection"]:
        times = [t * 1000 for t in per_layer_times.get(layer, [0])]
        row += f'<td class="num">{percentile(times, p_val):.0f}</td>'
    row += f'<td class="num">{percentile(all_times_ms, p_val):.0f}</td></tr>'
    html += row

html += """
</table>

<h2>数据库状态</h2>
<table>
<tr><th>表名</th><th class="num">行数</th></tr>
"""
for table_name, row_count in sorted(db_stats_final.items()):
    color_c = "#3fb950" if row_count > 0 else "#484f58"
    html += f'<tr><td>{table_name}</td><td class="num" style="color:{color_c}">{row_count:,}</td></tr>'

html += f"""
</table>

<h2>结论</h2>
<div class="verdict-box">
<h3>{'PASS' if success_rate >= SUCCESS_TARGET else 'WARN' if success_rate >= 90 else 'FAIL'}</h3>
<div style="margin:10px 0;">
    <span class="badge badge-{"pass" if success_rate >= SUCCESS_TARGET else "warn" if success_rate >= 90 else "fail"}">
        成功率 {success_rate:.1f}% {"≥ " + str(SUCCESS_TARGET) + "% 达标" if success_rate >= SUCCESS_TARGET else "< " + str(SUCCESS_TARGET) + "%"}
    </span>
    <span class="badge badge-{"pass" if total_errors_all == 0 else "fail"}">
        异常 {total_errors_all} 次 {"正常" if total_errors_all == 0 else "需排查"}
    </span>
    <span class="badge badge-{"pass" if overall_hit_rate >= 90 else "warn" if overall_hit_rate >= 70 else "fail"}">
        缓存命中率 {overall_hit_rate:.1f}%
    </span>
    <span class="badge badge-{"pass" if avg_first_50 > avg_last_50 * 1.5 else "warn"}">
        性能收敛 {avg_first_50/avg_last_50:.1f}x
    </span>
</div>
<div style="margin-top:12px; color:#8b949e; font-size:0.85em;">
    预热耗时: {warmup_elapsed:.1f}s | 冷启动(首轮): {round_times[0]:.1f}s | 缓存后平均: {avg_last_50*1000:.0f}ms/轮 (后50轮)
</div>
</div>

<p style="color:#484f58;margin-top:30px;font-size:0.8em;">
    Stoke Stress Test v2 · {datetime.now().strftime('%Y-%m-%d')} · 5 源 (mootdx/akshare/baostock/efinance/tencent) · SQLite 缓存
</p>
</body></html>"""

with open(report_path, "w", encoding="utf-8") as f:
    f.write(html)

# ===== 保存 JSON 数据 =====
json_data = {
    "timestamp": timestamp,
    "rounds": ROUNDS,
    "target_success_rate": SUCCESS_TARGET,
    "success_rate": round(success_rate, 2),
    "overall_hit_rate": round(overall_hit_rate, 2),
    "total_time": round(total_time, 2),
    "total_calls": total_calls_all,
    "total_hits": total_hits_all,
    "total_errors": total_errors_all,
    "warmup_elapsed": round(warmup_elapsed, 2),
    "avg_first_50_ms": round(avg_first_50 * 1000, 1),
    "avg_last_50_ms": round(avg_last_50 * 1000, 1),
    "status": status_text,
    "db_stats": db_stats_final,
    "per_layer_p95_ms": {
        layer: round(percentile([t * 1000 for t in times], 95), 1)
        for layer, times in per_layer_times.items()
    },
    "method_stats": {
        name: {
            "hits": cs["hits"],
            "misses": cs["misses"],
            "errors": cs["errors"],
            "avg_ms": round(sum(cs["latencies"]) / len(cs["latencies"]) * 1000, 1) if cs["latencies"] else 0,
            "p50_ms": round(percentile([l * 1000 for l in cs["latencies"]], 50), 1),
            "p95_ms": round(percentile([l * 1000 for l in cs["latencies"]], 95), 1),
        }
        for name, cs in method_stats.items()
    },
}
with open(data_path, "w", encoding="utf-8") as f:
    json.dump(json_data, f, ensure_ascii=False, indent=2)

# ===== 终端输出 =====
print(f"\n{'='*60}")
print(f"  压测结果")
print(f"{'='*60}")
print(f"  成功率:    {success_rate:.1f}% {'✓ 达标' if success_rate >= SUCCESS_TARGET else '✗ 未达标'}")
print(f"  缓存命中率: {overall_hit_rate:.1f}% ({total_hits_all}/{total_calls_all})")
print(f"  总耗时:     {total_time:.1f}s")
print(f"  异常:       {total_errors_all} 次")
print(f"  首轮(冷):   {round_times[0]:.1f}s")
print(f"  末轮(热):   {round_times[-1]*1000:.0f}ms")
print(f"  前50轮均值: {avg_first_50*1000:.0f}ms")
print(f"  后50轮均值: {avg_last_50*1000:.0f}ms")
print(f"  性能收敛:   {avg_first_50/avg_last_50:.1f}x")
print(f"")
print(f"  报告: {report_path}")
print(f"  数据: {data_path}")
print(f"{'='*60}")

if success_rate >= SUCCESS_TARGET:
    print(f"\n  ✓ 压测通过！成功率 {success_rate:.1f}% >= {SUCCESS_TARGET}%")
else:
    print(f"\n  ✗ 压测未通过！成功率 {success_rate:.1f}% < {SUCCESS_TARGET}%")

print(f"  今日: {today_str()}")

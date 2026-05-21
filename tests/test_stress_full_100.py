"""
100 轮全层压力测试 — 发现层 + 时机层 + 执行层 + 沉淀层 同时查询数据层

冷启动（无预热），模拟最差场景。生成详细 HTML 报告。
"""
import sys
sys.path.insert(0, "/Volumes/Black/Stoke")
import time
import logging
import json
import os
from datetime import datetime
from collections import defaultdict
logging.basicConfig(level=logging.WARNING)
from stoke import Stoke
from stoke.config import setup_logging
setup_logging("WARNING")
logging.getLogger("stoke.utils").setLevel(logging.ERROR)

ROUNDS = 100

# ===== 测试数据 =====
DISCOVERY_KLINE = ["000001", "000858", "600519", "601318", "002415",
                   "600036", "000333", "002475", "300750", "603259"]
TIMING_INDICES = ["上证50", "沪深300"]
EXEC_KLINE = ["600000", "000002", "600030", "000725", "002230"]
EXEC_FUND_FLOW = ["000001", "600519", "601318"]
REFLECT_KLINE = ["000651", "600887", "002594", "300124", "688981"]
REFLECT_SECTORS = ["银行", "半导体", "医药"]

s = Stoke(use_cache=True)

# ===== 日志收集 =====
round_logs = []
cache_stats = defaultdict(lambda: {"hits": 0, "misses": 0, "errors": 0})
per_layer_times = defaultdict(list)

def cached_call(name, layer, fn):
    """包装一次调用，记录命中/未命中/异常"""
    t0 = time.time()
    try:
        df = fn()
        elapsed = time.time() - t0
        hit = elapsed < 0.1
        if hit:
            cache_stats[name]["hits"] += 1
        else:
            cache_stats[name]["misses"] += 1
        return elapsed, hit, len(df) if hasattr(df, '__len__') else 0, None
    except Exception as e:
        elapsed = time.time() - t0
        cache_stats[name]["errors"] += 1
        return elapsed, False, 0, str(e)[:80]

# ===== 工作函数 =====
def fetch_discovery():
    results = {}
    calls = [
        ("limit_up", lambda: s.limit_up()),
        ("strong_stocks", lambda: s.strong_stocks()),
        ("hot_keywords", lambda: s.hot_keywords()),
        ("northbound_flow", lambda: s.northbound_flow()),
        ("dragon_tiger", lambda: s.dragon_tiger()),
    ]
    for name, fn in calls:
        elapsed, hit, rows, err = cached_call(name, "discovery", fn)
        results[name] = {"elapsed": elapsed, "hit": hit, "rows": rows, "error": err}
    # K-line batch
    for sym in DISCOVERY_KLINE:
        name = f"kline_disc_{sym}"
        elapsed, hit, rows, err = cached_call(name, "discovery", lambda s=s, sym=sym: s.kline(sym, start=0, offset=100))
        results[name] = {"elapsed": elapsed, "hit": hit, "rows": rows, "error": err}
    return results

def fetch_timing():
    results = {}
    calls = [
        ("market_breadth", lambda: s.market_breadth()),
        ("market_volume", lambda: s.market_volume()),
        ("market_pb", lambda: s.market_pb()),
        ("stock_comment_all", lambda: s.stock_comment_all()),
    ]
    for name, fn in calls:
        elapsed, hit, rows, err = cached_call(name, "timing", fn)
        results[name] = {"elapsed": elapsed, "hit": hit, "rows": rows, "error": err}
    for idx in TIMING_INDICES:
        name = f"index_pe_{idx}"
        elapsed, hit, rows, err = cached_call(name, "timing", lambda s=s, idx=idx: s.index_pe(idx))
        results[name] = {"elapsed": elapsed, "hit": hit, "rows": rows, "error": err}
    return results

def fetch_execution():
    results = {}
    for sym in EXEC_KLINE:
        name = f"kline_exec_{sym}"
        elapsed, hit, rows, err = cached_call(name, "execution", lambda s=s, sym=sym: s.kline(sym, start=0, offset=50))
        results[name] = {"elapsed": elapsed, "hit": hit, "rows": rows, "error": err}
    for sym in EXEC_FUND_FLOW:
        name = f"fund_flow_{sym}"
        elapsed, hit, rows, err = cached_call(name, "execution", lambda s=s, sym=sym: s.individual_fund_flow(sym))
        results[name] = {"elapsed": elapsed, "hit": hit, "rows": rows, "error": err}
    for sym in EXEC_KLINE[:3]:
        name = f"realtime_{sym}"
        elapsed, hit, rows, err = cached_call(name, "execution", lambda s=s, sym=sym: s.realtime([sym]))
        results[name] = {"elapsed": elapsed, "hit": hit, "rows": rows, "error": err}
    return results

def fetch_reflection():
    results = {}
    for sym in REFLECT_KLINE:
        name = f"kline_refl_{sym}"
        elapsed, hit, rows, err = cached_call(name, "reflection", lambda s=s, sym=sym: s.kline(sym, start=0, offset=800))
        results[name] = {"elapsed": elapsed, "hit": hit, "rows": rows, "error": err}
    for sec in REFLECT_SECTORS:
        name = f"sector_{sec}"
        elapsed, hit, rows, err = cached_call(name, "reflection",
            lambda s=s, sec=sec: s.sector_kline(sec))
        results[name] = {"elapsed": elapsed, "hit": hit, "rows": rows, "error": err}
    return results

# ===== 100 轮 =====
print(f"开始 {ROUNDS} 轮全层压力测试 (冷启动)...")
total_start = time.time()

for r in range(1, ROUNDS + 1):
    round_start = time.time()
    layer_results = {}

    # 顺序执行（akshare 线程不安全）
    for layer_name, fetch_fn in [
        ("discovery", fetch_discovery),
        ("timing", fetch_timing),
        ("execution", fetch_execution),
        ("reflection", fetch_reflection),
    ]:
        try:
            layer_results[layer_name] = fetch_fn()
        except Exception as e:
            layer_results[layer_name] = {"error": str(e)[:100]}

    round_elapsed = time.time() - round_start

    # 统计本轮命中
    round_hits = 0
    round_total = 0
    layer_times = {}
    for layer, calls in layer_results.items():
        lt = 0
        for v in calls.values():
            if isinstance(v, dict) and "hit" in v:
                if v["hit"]:
                    round_hits += 1
                round_total += 1
                lt += v["elapsed"]
        layer_times[layer] = lt

    for lyr, lt in layer_times.items():
        per_layer_times[lyr].append(lt)

    hit_pct = round_hits / round_total * 100 if round_total > 0 else 0
    round_logs.append({
        "round": r,
        "elapsed": round_elapsed,
        "hits": round_hits,
        "total_calls": round_total,
        "hit_pct": round_hits / round_total * 100 if round_total > 0 else 0,
        "layer_times": layer_times,
        "errors": sum(1 for calls in layer_results.values()
                     for v in calls.values()
                     if isinstance(v, dict) and v.get("error")),
    })

    if r == 1:
        print(f"  第 1 轮(冷启动): {round_elapsed:.1f}s, 命中 {round_hits}/{round_total}")
    elif r % 25 == 0:
        print(f"  第 {r:3d} 轮: {round_elapsed*1000:.0f}ms, 命中 {round_hits}/{round_total} ({hit_pct:.0f}%)")

total_time = time.time() - total_start

# ===== 统计 =====
hit_counts = [log["hits"] for log in round_logs]
total_calls_per_round = round_logs[0]["total_calls"] if round_logs else 0
total_hits = sum(hit_counts)
total_calls = sum(log["total_calls"] for log in round_logs)
overall_hit_rate = total_hits / total_calls * 100 if total_calls > 0 else 0

round_times = [log["elapsed"] for log in round_logs]
avg_time_first_half = sum(round_times[:50]) / 50
avg_time_second_half = sum(round_times[50:]) / 50

errors = sum(log["errors"] for log in round_logs)
db = s.store.stats() if s.store else {}

# ===== HTML 报告 =====
def gradient_color(val, max_val):
    """值越大越红"""
    ratio = min(val / max(max_val, 0.001), 1.0)
    r = int(220 + 35 * ratio)
    g = int(240 - 190 * ratio)
    b = int(240 - 190 * ratio)
    return f"rgb({r},{g},{b})"

report_path = os.path.join(os.path.dirname(__file__), "stress_full_report.html")

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>Stoke 100 轮全层压力测试报告</title>
<style>
body {{ font-family: -apple-system, 'SF Mono', monospace; background: #1a1a2e; color: #e0e0e0; padding: 30px; max-width: 1200px; margin: 0 auto; }}
h1 {{ color: #00d4aa; border-bottom: 2px solid #333; padding-bottom: 10px; }}
h2 {{ color: #7ec8e3; margin-top: 30px; }}
.badge {{ display: inline-block; padding: 4px 12px; border-radius: 4px; font-weight: bold; margin: 0 5px; }}
.badge-pass {{ background: #00d4aa33; color: #00d4aa; }}
.badge-warn {{ background: #ffaa0033; color: #ffaa00; }}
.badge-fail {{ background: #ff444433; color: #ff4444; }}
table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
th {{ background: #16213e; padding: 10px; text-align: left; border-bottom: 2px solid #333; }}
td {{ padding: 8px 10px; border-bottom: 1px solid #222; }}
tr:hover {{ background: #16213e55; }}
.chart-bar {{ display: inline-block; height: 20px; border-radius: 3px; min-width: 2px; }}
.chart-hit {{ background: #00d4aa; }}
.chart-miss {{ background: #ff6b6b; }}
.chart-error {{ background: #ffaa00; }}
.summary-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin: 20px 0; }}
.summary-card {{ background: #16213e; padding: 20px; border-radius: 8px; text-align: center; }}
.summary-card .value {{ font-size: 2em; font-weight: bold; color: #00d4aa; margin: 10px 0; }}
.summary-card .label {{ font-size: 0.85em; color: #888; }}
.log-row {{ font-size: 0.85em; padding: 2px 5px; }}
pre {{ background: #111; padding: 15px; border-radius: 6px; overflow-x: auto; font-size: 0.8em; }}
</style>
</head>
<body>

<h1>Stoke 全层压力测试报告</h1>
<p>测试时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | 轮次: {ROUNDS} | 冷启动(无预热)</p>

<div class="summary-grid">
<div class="summary-card">
<div class="label">缓存命中率</div>
<div class="value" style="color: {'#00d4aa' if overall_hit_rate >= 30 else '#ffaa00' if overall_hit_rate >= 15 else '#ff4444'}">{overall_hit_rate:.1f}%</div>
<div class="label">{total_hits}/{total_calls} 次命中</div>
</div>
<div class="summary-card">
<div class="label">总耗时</div>
<div class="value">{total_time:.1f}s</div>
<div class="label">100 轮累计</div>
</div>
<div class="summary-card">
<div class="label">平均每轮</div>
<div class="value">{sum(round_times)/len(round_times)*1000:.0f}ms</div>
<div class="label">首50轮 {avg_time_first_half*1000:.0f}ms | 后50轮 {avg_time_second_half*1000:.0f}ms</div>
</div>
<div class="summary-card">
<div class="label">异常次数</div>
<div class="value" style="color: {'#00d4aa' if errors == 0 else '#ff4444'}">{errors}</div>
<div class="label">总调用 {total_calls} 次</div>
</div>
</div>

<h2>逐轮趋势</h2>
<table>
<tr><th>轮次</th><th>耗时</th><th>命中</th><th>命中率</th><th>每层耗时(发/时/执/沉)</th><th>图表</th></tr>
"""
for log in round_logs:
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
    bar_w = max(t / max(round_times) * 300, 2) if max(round_times) > 0 else 2

    # 颜色: 时间越长越红
    color = gradient_color(t, max(round_times))

    html += f"""<tr>
<td>{r}</td>
<td style="background:{color}33">{t*1000:.0f}ms</td>
<td>{hits}/{total}</td>
<td>{pct:.0f}%</td>
<td><span style="font-size:0.75em">D:{disc_t:.0f} T:{tim_t:.0f} E:{exec_t:.0f} R:{refl_t:.0f}</span></td>
<td><span class="chart-bar" style="width:{bar_w}px;background:{color}"></span></td>
</tr>"""

html += """
</table>

<h2>各方法缓存统计</h2>
<table>
<tr><th>方法</th><th>命中</th><th>未命中</th><th>异常</th><th>命中率</th></tr>
"""
for name in sorted(cache_stats.keys()):
    cs = cache_stats[name]
    total_m = cs["hits"] + cs["misses"] + cs["errors"]
    rate = cs["hits"] / total_m * 100 if total_m > 0 else 0
    html += f"""<tr>
<td>{name}</td>
<td class="chart-hit">{cs["hits"]}</td>
<td class="chart-miss">{cs["misses"]}</td>
<td class="chart-error">{cs["errors"]}</td>
<td>{rate:.0f}%</td>
</tr>"""

html += """
</table>

<h2>各层耗时统计</h2>
<table>
<tr><th>层</th><th>平均/轮</th><th>最小</th><th>最大</th><th>总耗时</th></tr>
"""
for layer in ["discovery", "timing", "execution", "reflection"]:
    times = per_layer_times.get(layer, [0])
    avg_t = sum(times) / len(times) * 1000
    min_t = min(times) * 1000
    max_t = max(times) * 1000
    sum_t = sum(times)
    html += f"""<tr>
<td>{layer}</td>
<td>{avg_t:.0f}ms</td>
<td>{min_t:.0f}ms</td>
<td>{max_t:.0f}ms</td>
<td>{sum_t:.1f}s</td>
</tr>"""

html += """
</table>

<h2>数据库状态</h2>
<table>
<tr><th>表名</th><th>行数</th></tr>
"""
for n, c in sorted(db.items()):
    color_c = "#00d4aa" if c > 0 else "#666"
    html += f'<tr><td>{n}</td><td style="color:{color_c}">{c:,}</td></tr>'

html += f"""
</table>

<h2>结论</h2>
<div>
<span class="badge badge-{"pass" if overall_hit_rate >= 30 else "warn" if overall_hit_rate >= 15 else "fail"}">
缓存命中率 {overall_hit_rate:.1f}% {"≥ 30% 达标" if overall_hit_rate >= 30 else "< 30%"}
</span>
<span class="badge badge-{"pass" if errors == 0 else "fail"}">
异常 {errors} 次 {"正常" if errors == 0 else "需排查"}
</span>
<span class="badge badge-{"pass" if avg_time_second_half < avg_time_first_half * 0.5 else "warn"}">
性能收敛 {"正常(后50轮快于前50轮)" if avg_time_second_half < avg_time_first_half * 0.5 else "未收敛"}
</span>
</div>

<p style="color:#888;margin-top:40px;">Stoke Stress Test · {datetime.now().strftime('%Y-%m-%d')} · 数据源: mootdx/akshare/baostock/efinance/tencent · 缓存: SQLite</p>
</body></html>"""

with open(report_path, "w", encoding="utf-8") as f:
    f.write(html)

print(f"\n===== 结果 =====")
print(f"命中率: {overall_hit_rate:.1f}% ({total_hits}/{total_calls})")
print(f"总耗时: {total_time:.1f}s")
print(f"平均/轮: {sum(round_times)/len(round_times)*1000:.0f}ms")
print(f"异常: {errors}")
print(f"首次: {round_times[0]:.1f}s | 末次: {round_times[-1]*1000:.0f}ms")
print(f"报告: {report_path}")

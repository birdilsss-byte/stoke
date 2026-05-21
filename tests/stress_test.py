"""
Stoke 全接口压力测试 — 20 项覆盖所有数据获取类型

测试指标：
  - 准确度（数据是否成功获取 + 行数合理性）
  - 响应时间（秒）
  - 格式正确性（DataFrame / list[dict]）

输出：HTML 统计表格 + JSON 原始数据
"""
import time
import json
import warnings
import traceback
from datetime import datetime
from typing import Optional

import pandas as pd

from stoke import Stoke

warnings.filterwarnings("ignore")

# ==================== 测试用例定义 ====================

# 每个测试项：(序号, 名称, 调用函数, 数据层面, 数据源, 预期格式, 参数)
# 预期格式: 'df' = DataFrame, 'list' = list[dict]
TestResult = dict  # type alias


def make_tests(s: Stoke) -> list[dict]:
    """构造 20 个测试用例"""
    tests = [
        # ===================== mootdx（通达信协议）= 4 项 =====================
        {"id": 1,  "name": "realtime(多只)",       "category": "行情",    "source": "mootdx", "func": lambda: s.realtime(["000001","600000","000002"]),                  "expect_type": "df", "min_rows": 2},
        {"id": 2,  "name": "realtime(单只)",       "category": "行情",    "source": "mootdx", "func": lambda: s.realtime(["000001"]),                                      "expect_type": "df", "min_rows": 1},
        {"id": 3,  "name": "kline 历史K线(日线)",  "category": "行情",    "source": "mootdx", "func": lambda: s.kline("000001"),                                            "expect_type": "df", "min_rows": 100},
        {"id": 4,  "name": "kline 历史K线(周线)",  "category": "行情",    "source": "mootdx", "func": lambda: s.kline("600000", frequency=7),                                 "expect_type": "df", "min_rows": 10},
        # ===================== mootdx 基础数据 = 3 项 =====================
        {"id": 5,  "name": "stock_list 全市场列表","category": "基础数据","source": "mootdx", "func": lambda: s.stock_list(),                                                "expect_type": "df", "min_rows": 1000},
        {"id": 6,  "name": "f10 财务快照(平安银行)","category": "基础数据","source": "mootdx", "func": lambda: s.f10("000001"),                                              "expect_type": "df", "min_rows": 1},
        {"id": 7,  "name": "f10 财务快照(浦发银行)","category": "基础数据","source": "mootdx", "func": lambda: s.f10("600000"),                                              "expect_type": "df", "min_rows": 1},
        # ===================== akshare 新闻 = 3 项 =====================
        {"id": 8,  "name": "news 个股新闻(平安)",   "category": "新闻",   "source": "akshare", "func": lambda: s.news("000001"),                                              "expect_type": "df", "min_rows": 1},
        {"id": 9,  "name": "news 个股新闻(浦发)",   "category": "新闻",   "source": "akshare", "func": lambda: s.news("600000"),                                              "expect_type": "df", "min_rows": 1},
        {"id": 10, "name": "telegraph 财联社电报",  "category": "新闻",   "source": "akshare", "func": lambda: s.telegraph(),                                                  "expect_type": "df", "min_rows": 1},
        # ===================== akshare 研报 = 2 项 =====================
        {"id": 11, "name": "research 研报(平安)",   "category": "研报",   "source": "akshare", "func": lambda: s.research("000001"),                                           "expect_type": "df", "min_rows": 0},
        {"id": 12, "name": "research 研报(茅台)",   "category": "研报",   "source": "akshare", "func": lambda: s.research("600519"),                                           "expect_type": "df", "min_rows": 0},
        # ===================== akshare 公告 = 2 项 =====================
        {"id": 13, "name": "announcements 公告(平安)","category": "公告", "source": "akshare", "func": lambda: s.announcements("000001"),                                       "expect_type": "df", "min_rows": 1},
        {"id": 14, "name": "announcements 公告(茅台)","category": "公告", "source": "akshare", "func": lambda: s.announcements("600519"),                                       "expect_type": "df", "min_rows": 1},
        # ===================== akshare 信号 = 2 项 =====================
        {"id": 15, "name": "limit_up 涨停板",        "category": "信号",  "source": "akshare", "func": lambda: s.limit_up("20260518"),                                          "expect_type": "df", "min_rows": 0},
        {"id": 16, "name": "strong_stocks 强势涨停", "category": "信号",  "source": "akshare", "func": lambda: s.strong_stocks("20260518"),                                     "expect_type": "df", "min_rows": 0},
        # ===================== akshare 板块 = 2 项 =====================
        {"id": 17, "name": "concepts 概念板块",      "category": "板块",  "source": "akshare", "func": lambda: s.concepts(),                                                    "expect_type": "df", "min_rows": 100},
        {"id": 18, "name": "industries 行业板块",    "category": "板块",  "source": "akshare", "func": lambda: s.industries(),                                                  "expect_type": "df", "min_rows": 50},
        # ===================== akshare 资金流 = 7 项 =====================
        {"id": 19, "name": "northbound_flow 北向","category": "资金流",   "source": "akshare", "func": lambda: s.northbound_flow(),                                              "expect_type": "df", "min_rows": 10},
        {"id": 20, "name": "dragon_tiger 龙虎榜",   "category": "资金流","source": "akshare", "func": lambda: s.dragon_tiger(),                                                 "expect_type": "df", "min_rows": 1},
        {"id": 21, "name": "margin_shanghai 融资融券(沪)","category": "资金流","source": "akshare", "func": lambda: s.margin_shanghai(),                                        "expect_type": "df", "min_rows": 1},
        {"id": 22, "name": "margin_shenzhen 融资融券(深)","category": "资金流","source": "akshare", "func": lambda: s.margin_shenzhen(),                                        "expect_type": "df", "min_rows": 1},
        {"id": 23, "name": "market_fund_flow 市场资金","category": "资金流","source": "akshare","func": lambda: s.market_fund_flow(),                                             "expect_type": "df", "min_rows": 1},
        {"id": 24, "name": "individual_fund_flow(平安)","category": "资金流","source": "akshare","func": lambda: s.individual_fund_flow("000001"),                               "expect_type": "df", "min_rows": 1},
        {"id": 25, "name": "individual_fund_flow(茅台)","category": "资金流","source": "akshare","func": lambda: s.individual_fund_flow("600519"),                               "expect_type": "df", "min_rows": 1},
        # ===================== akshare 情绪(东财主力) = 6 项 =====================
        {"id": 26, "name": "hot_detail 热度详情(平安)","category": "情绪","source": "akshare", "func": lambda: s.hot_detail("000001"),                                           "expect_type": "df", "min_rows": 1},
        {"id": 27, "name": "hot_detail 热度详情(茅台)","category": "情绪","source": "akshare", "func": lambda: s.hot_detail("600519"),                                           "expect_type": "df", "min_rows": 1},
        {"id": 28, "name": "hot_latest 最新排名(平安)","category": "情绪","source": "akshare", "func": lambda: s.hot_latest("000001"),                                           "expect_type": "df", "min_rows": 1},
        {"id": 29, "name": "hot_realtime 实时排名(平安)","category": "情绪","source": "akshare","func": lambda: s.hot_realtime("000001"),                                         "expect_type": "df", "min_rows": 1},
        {"id": 30, "name": "hot_keywords 热搜关键词",  "category": "情绪","source": "akshare", "func": lambda: s.hot_keywords(),                                                 "expect_type": "df", "min_rows": 1},
        {"id": 31, "name": "stock_comment_all 千股千评","category": "情绪","source": "akshare","func": lambda: s.stock_comment_all(),                                            "expect_type": "df", "min_rows": 1000},
        # ===================== akshare 情绪(雪球备选) = 2 项 =====================
        {"id": 32, "name": "xueqiu_hot 雪球最热门",   "category": "情绪","source": "akshare", "func": lambda: s.xueqiu_hot("最热门"),                                            "expect_type": "df", "min_rows": 1},
        {"id": 33, "name": "xueqiu_hot 雪球本周新增",  "category": "情绪","source": "akshare", "func": lambda: s.xueqiu_hot("本周新增"),                                          "expect_type": "df", "min_rows": 1},
        # ===================== akshare 舆情评分 = 3 项 =====================
        {"id": 34, "name": "stock_desire 参与意愿(平安)","category": "情绪","source": "akshare","func": lambda: s.stock_desire("000001"),                                        "expect_type": "df", "min_rows": 1},
        {"id": 35, "name": "stock_focus 关注指数(平安)","category": "情绪","source": "akshare","func": lambda: s.stock_focus("000001"),                                          "expect_type": "df", "min_rows": 1},
        {"id": 36, "name": "limit_down 跌停板",        "category": "情绪","source": "akshare", "func": lambda: s.limit_down("20260518"),                                          "expect_type": "df", "min_rows": 0},
        # ===================== tencent = 4 项 =====================
        {"id": 37, "name": "index_pe 上证50 PE",      "category": "估值",  "source": "tencent","func": lambda: s.index_pe("上证50"),                                             "expect_type": "df", "min_rows": 1},
        {"id": 38, "name": "index_pe 沪深300 PE",     "category": "估值",  "source": "tencent","func": lambda: s.index_pe("沪深300"),                                            "expect_type": "df", "min_rows": 1},
        {"id": 39, "name": "index_pe 创业板指 PE",    "category": "估值",  "source": "tencent","func": lambda: s.index_pe("创业板指"),                                            "expect_type": "df", "min_rows": 1},
        {"id": 40, "name": "market_pb 全市场 PB",     "category": "估值",  "source": "tencent","func": lambda: s.market_pb(),                                                    "expect_type": "df", "min_rows": 1},
    ]
    return tests


# ==================== 测试执行 ====================

def run_single_test(test: dict) -> dict:
    """执行单个测试，返回结果字典"""
    result = {
        "id": test["id"],
        "name": test["name"],
        "category": test["category"],
        "source": test["source"],
        "status": "FAIL",
        "accuracy": 0,
        "accuracy_label": "失败",
        "time_sec": 0,
        "format_ok": False,
        "rows": 0,
        "cols": 0,
        "error": "",
        "sample_cols": "",
        "score": 0,  # 综合评分 0-100
    }

    start = time.time()
    try:
        data = test["func"]()
        elapsed = round(time.time() - start, 2)
        result["time_sec"] = elapsed

        # ---- 格式检查 ----
        if test["expect_type"] == "df":
            if isinstance(data, pd.DataFrame):
                result["format_ok"] = True
                result["rows"] = int(len(data))
                result["cols"] = int(len(data.columns))
                result["sample_cols"] = ", ".join(data.columns[:6].tolist())
            else:
                result["error"] = f"期望 DataFrame，得到 {type(data).__name__}"

        elif test["expect_type"] == "dict":
            if isinstance(data, dict):
                result["format_ok"] = True
                result["rows"] = len(data)
                result["cols"] = len(data) if data else 0
                result["sample_cols"] = ", ".join(list(data.keys())[:6])
            else:
                result["error"] = f"期望 dict，得到 {type(data).__name__}"

        # ---- 准确度评分 ----
        if result["format_ok"]:
            min_rows = test["min_rows"]
            if min_rows is not None and result["rows"] < min_rows:
                ratio = result["rows"] / max(min_rows, 1)
                result["accuracy"] = max(10, int(ratio * 80))
                result["accuracy_label"] = f"行数不足({result['rows']}<{min_rows})"
                result["error"] = f"返回 {result['rows']} 行，期望至少 {min_rows} 行"
                result["status"] = "WARN"
            else:
                result["accuracy"] = 100
                result["accuracy_label"] = "完美"
                result["status"] = "PASS"
        else:
            result["accuracy"] = 0

    except Exception as e:
        elapsed = round(time.time() - start, 2)
        result["time_sec"] = elapsed
        result["error"] = f"{type(e).__name__}: {str(e)[:120]}"
        result["accuracy"] = 0
        result["accuracy_label"] = "异常"

    # 综合评分 = accuracy * 0.6 + (min(time_sec, 30)/30 * 100) * 0.2 + format_ok * 20
    time_score = max(0, min(100, int((1 - result["time_sec"] / 30) * 100)))
    format_score = 20 if result["format_ok"] else 0
    result["score"] = int(result["accuracy"] * 0.6 + time_score * 0.2 + format_score)

    return result


# ==================== HTML 生成 ====================

def generate_html(results: list[dict], total_time: float) -> str:
    """生成精美的 HTML 统计表格"""

    # 统计汇总
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    warned = sum(1 for r in results if r["status"] == "WARN")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    avg_time = round(sum(r["time_sec"] for r in results) / total, 2)
    avg_score = round(sum(r["score"] for r in results) / total, 1)
    total_rows = sum(r["rows"] for r in results)

    rows_html = ""
    for r in results:
        status_color = {
            "PASS": "#27ae60",
            "WARN": "#f39c12",
            "FAIL": "#e74c3c",
        }.get(r["status"], "#95a5a6")

        accuracy_color = "#27ae60" if r["accuracy"] == 100 else "#f39c12" if r["accuracy"] >= 50 else "#e74c3c"
        time_color = "#27ae60" if r["time_sec"] < 10 else "#f39c12" if r["time_sec"] < 25 else "#e74c3c"
        format_icon = "✓" if r["format_ok"] else "✗"
        format_color = "#27ae60" if r["format_ok"] else "#e74c3c"

        rows_html += f"""
        <tr>
            <td>{r['id']}</td>
            <td>{r['name']}</td>
            <td><span class="tag tag-{r['category']}">{r['category']}</span></td>
            <td>{r['source']}</td>
            <td><span style="color:{status_color};font-weight:bold">{r['status']}</span></td>
            <td style="color:{accuracy_color}">{r['accuracy']}%<br><small>{r['accuracy_label']}</small></td>
            <td style="color:{time_color}">{r['time_sec']}s</td>
            <td style="color:{format_color}">{format_icon}</td>
            <td>{r['rows']} 行 × {r['cols']} 列</td>
            <td style="font-size:12px;color:#666;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{r['sample_cols'][:60] or '-'}</td>
            <td style="font-size:12px;color:#{'e74c3c' if r['error'] else '27ae60'}">{r['error'][:80] if r['error'] else '正常'}</td>
            <td style="font-weight:bold">{r['score']}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Stoke 全接口压力测试报告</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; background: #f5f7fa; color: #333; padding: 30px; }}
.container {{ max-width: 1400px; margin: 0 auto; }}
h1 {{ font-size: 26px; margin-bottom: 8px; color: #2c3e50; }}
.subtitle {{ color: #7f8c8d; font-size: 14px; margin-bottom: 25px; }}

/* 汇总卡片 */
.summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-bottom: 30px; }}
.card {{ background: white; border-radius: 12px; padding: 18px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
.card .num {{ font-size: 28px; font-weight: 700; }}
.card .label {{ font-size: 12px; color: #95a5a6; margin-top: 4px; }}
.card.pass .num {{ color: #27ae60; }}
.card.warn .num {{ color: #f39c12; }}
.card.fail .num {{ color: #e74c3c; }}
.card.info .num {{ color: #2980b9; }}
.card.time .num {{ color: #8e44ad; }}

/* 分类统计 */
.category-section {{ background: white; border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
.category-section h2 {{ font-size: 18px; margin-bottom: 15px; color: #2c3e50; border-left: 4px solid #3498db; padding-left: 12px; }}
.category-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }}
.cat-card {{ border: 1px solid #eee; border-radius: 8px; padding: 14px; }}
.cat-card .cat-name {{ font-weight: 600; font-size: 14px; margin-bottom: 6px; }}
.cat-card .cat-stat {{ font-size: 13px; color: #666; }}
.cat-card .cat-bar {{ height: 6px; border-radius: 3px; margin-top: 8px; background: #ecf0f1; overflow: hidden; }}
.cat-card .cat-bar-inner {{ height: 100%; border-radius: 3px; transition: width 0.5s; }}

/* 表格 */
table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
th {{ background: #2c3e50; color: white; padding: 12px 10px; font-size: 13px; text-align: left; font-weight: 500; }}
td {{ padding: 10px; border-bottom: 1px solid #ecf0f1; font-size: 13px; vertical-align: middle; }}
tr:hover {{ background: #f8f9fa; }}
tr.fail-row {{ background: #fdf0ef; }}
tr.warn-row {{ background: #fef9e7; }}

.tag {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }}
.tag-行情 {{ background: #e8f8f5; color: #1abc9c; }}
.tag-信号 {{ background: #fef9e7; color: #f39c12; }}
.tag-新闻 {{ background: #ebf5fb; color: #3498db; }}
.tag-研报 {{ background: #f4ecf7; color: #9b59b6; }}
.tag-公告 {{ background: #fdedec; color: #e74c3c; }}
.tag-板块 {{ background: #eafaf1; color: #27ae60; }}
.tag-资金流 {{ background: #fdf2e9; color: #e67e22; }}
.tag-情绪 {{ background: #f5eef8; color: #8e44ad; }}
.tag-估值 {{ background: #e8f6f3; color: #1abc9c; }}
.tag-基础数据 {{ background: #f0f3f4; color: #7f8c8d; }}

.footer {{ margin-top: 20px; text-align: center; color: #95a5a6; font-size: 12px; }}
</style>
</head>
<body>
<div class="container">
<h1>📊 Stoke 全接口压力测试报告</h1>
<p class="subtitle">测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} &nbsp;|&nbsp; 总耗时: {total_time:.1f}s</p>

<div class="summary-grid">
    <div class="card pass"><div class="num">{passed}</div><div class="label">✅ 通过</div></div>
    <div class="card warn"><div class="num">{warned}</div><div class="label">⚠️ 告警</div></div>
    <div class="card fail"><div class="num">{failed}</div><div class="label">❌ 失败</div></div>
    <div class="card info"><div class="num">{total}</div><div class="label">📦 总计</div></div>
    <div class="card time"><div class="num">{avg_time}s</div><div class="label">⏱ 均响应</div></div>
    <div class="card info"><div class="num">{avg_score}</div><div class="label">🏆 均分</div></div>
    <div class="card info"><div class="num">{total_rows:,}</div><div class="label">📄 总行数</div></div>
</div>

<!-- 分类统计 -->
<div class="category-section">
<h2>分类表现</h2>
<div class="category-grid">
"""

    # 按 category 聚合
    cat_data = {}
    for r in results:
        cat = r["category"]
        if cat not in cat_data:
            cat_data[cat] = {"total": 0, "pass": 0, "scores": [], "times": []}
        cat_data[cat]["total"] += 1
        cat_data[cat]["pass"] += 1 if r["status"] == "PASS" else 0
        cat_data[cat]["scores"].append(r["score"])
        cat_data[cat]["times"].append(r["time_sec"])

    cat_colors = {
        "行情": "#1abc9c", "信号": "#f39c12", "新闻": "#3498db", "研报": "#9b59b6",
        "公告": "#e74c3c", "板块": "#27ae60", "资金流": "#e67e22", "情绪": "#8e44ad",
        "估值": "#1abc9c", "基础数据": "#7f8c8d",
    }

    cat_html_parts = []
    for cat, cd in sorted(cat_data.items()):
        pass_rate = cd["pass"] / cd["total"] * 100
        avg_cat_score = sum(cd["scores"]) / len(cd["scores"])
        avg_cat_time = sum(cd["times"]) / len(cd["times"])
        color = cat_colors.get(cat, "#3498db")
        cat_html_parts.append(f"""
    <div class="cat-card">
        <div class="cat-name">{cat}</div>
        <div class="cat-stat">通过 {cd['pass']}/{cd['total']} &nbsp;|&nbsp; 均分 {avg_cat_score:.0f} &nbsp;|&nbsp; 均耗时 {avg_cat_time:.1f}s</div>
        <div class="cat-bar"><div class="cat-bar-inner" style="width:{pass_rate:.0f}%;background:{color}"></div></div>
    </div>""")

    html += "\n".join(cat_html_parts)

    html += """
</div>
</div>

<!-- 明细表格 -->
<table>
<thead>
<tr>
    <th>#</th><th>接口名称</th><th>类别</th><th>源</th><th>状态</th>
    <th>准确度</th><th>耗时</th><th>格式</th><th>行×列</th><th>字段预览</th><th>备注</th><th>评分</th>
</tr>
</thead>
<tbody>
"""
    html += rows_html
    html += """</tbody>
</table>
<div class="footer">
评测标准：准确度 60% + 响应时间 20% + 格式正确性 20% &nbsp;|&nbsp; 准确度 = 行数达标则满分，不足按比例折算 &nbsp;|&nbsp; 响应时间 ≥30s 得 0 分
</div>
</div>
</body>
</html>"""
    return html


# ==================== 主流程 ====================

def main():
    print("=" * 60)
    print("  Stoke 全接口压力测试")
    print(f"  开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    s = Stoke()
    tests = make_tests(s)

    print(f"\n共 {len(tests)} 个测试项，开始执行...\n")

    results = []
    total_start = time.time()

    for i, test in enumerate(tests, 1):
        print(f"  [{i:02d}/{len(tests)}] {test['name']} ... ", end="", flush=True)
        result = run_single_test(test)
        results.append(result)

        status_icon = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}.get(result["status"], "?")
        time_str = f"{result['time_sec']:>6.2f}s"
        score_str = f"score={result['score']}"
        print(f"{status_icon}  {time_str}  {result['status']:4s}  {score_str}")

        # 调试输出（错误时）
        if result["status"] == "FAIL" and result["error"]:
            print(f"          ↳ {result['error']}")

    total_time = round(time.time() - total_start, 1)

    # 汇总统计
    passed = sum(1 for r in results if r["status"] == "PASS")
    warned = sum(1 for r in results if r["status"] == "WARN")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    avg_time = sum(r["time_sec"] for r in results) / len(results)
    avg_score = sum(r["score"] for r in results) / len(results)

    print("\n" + "=" * 60)
    print(f"  测试完成！")
    print(f"  通过: {passed}  |  告警: {warned}  |  失败: {failed}")
    print(f"  平均耗时: {avg_time:.2f}s  |  综合评分: {avg_score:.1f}")
    print(f"  总耗时: {total_time:.1f}s")
    print("=" * 60)

    # 生成 HTML
    html = generate_html(results, total_time)
    output_path = "/Volumes/Black/Stoke/tests/stress_test_report.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n📄 HTML 报告已生成: {output_path}")

    # 保存 JSON 原始数据
    json_path = "/Volumes/Black/Stoke/tests/stress_test_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total_time": total_time,
            "results": results,
            "summary": {
                "passed": passed,
                "warned": warned,
                "failed": failed,
                "avg_time": avg_time,
                "avg_score": avg_score,
            },
        }, f, ensure_ascii=False, indent=2)
    print(f"📄 JSON 原始数据已保存: {json_path}")


if __name__ == "__main__":
    main()

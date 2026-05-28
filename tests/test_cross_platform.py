"""
Stoke 跨平台验收测试
====================
用法: uv run python3 tests/test_cross_platform.py
用途: 在 macOS / Linux / Windows 上运行，验证所有数据源和接口
输出: 结构化结果，可直接贴给大黄蜂分析
"""

import sys
import time
import platform
from datetime import datetime


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def ok(msg: str):
    print(f"  ✅ {msg}")


def fail(msg: str):
    print(f"  ❌ {msg}")


def warn(msg: str):
    print(f"  ⚠️ {msg}")


# ========== 1. 环境检测 ==========
section("1. 环境信息")

print(f"  操作系统: {platform.system()} {platform.release()}")
print(f"  Python:   {sys.version}")
print(f"  时间:     {datetime.now().isoformat()}")

try:
    import stoke
    ok(f"stoke {stoke.__version__} 已安装")
except ImportError as e:
    fail(f"stoke 未安装: {e}")
    print("\n  请先运行: uv pip install -e .")
    sys.exit(1)

# 检查 STOKE_HOME
import os
stoke_home = os.environ.get("STOKE_HOME", "")
if stoke_home:
    ok(f"STOKE_HOME = {stoke_home}")
else:
    warn("STOKE_HOME 未设置（非必须，但建议设置）")

# ========== 2. mootdx 数据源 ==========
section("2. mootdx（通达信行情）")

mootdx_ok = 0
mootdx_total = 4

try:
    from stoke.sources.mootdx_source import MootdxSource
    m = MootdxSource()
except Exception as e:
    fail(f"初始化 MootdxSource: {e}")
    m = None

if m:
    # health_check
    try:
        assert m.health_check()
        ok("health_check")
        mootdx_ok += 1
    except Exception as e:
        fail(f"health_check: {e}")

    # K线
    try:
        kline = m.get_kline("000001")
        assert len(kline) > 0
        latest = kline.iloc[-1]
        ok(f"get_kline: {len(kline)} 条, 最新 {str(latest.name)[:10]} close={latest.close:.2f}")
        mootdx_ok += 1
    except Exception as e:
        fail(f"get_kline: {e}")

    # 实时行情
    try:
        quotes = m.get_realtime(["000001", "600000"])
        assert len(quotes) >= 1
        ok(f"get_realtime: {len(quotes)} 只")
        mootdx_ok += 1
    except Exception as e:
        fail(f"get_realtime: {e}")

    # 股票列表
    try:
        stocks = m.get_stock_list()
        assert len(stocks) > 10000
        ok(f"get_stock_list: {len(stocks)} 只")
        mootdx_ok += 1
    except Exception as e:
        fail(f"get_stock_list: {e}")

print(f"  mootdx: {mootdx_ok}/{mootdx_total} 通过")

# ========== 3. akshare 数据源 ==========
section("3. akshare（新闻 / 研报 / 公告 / 信号）")

akshare_ok = 0
akshare_total = 8

try:
    from stoke.sources.akshare_source import AKShareSource
    a = AKShareSource()
except Exception as e:
    fail(f"初始化 AKShareSource: {e}")
    a = None

if a:
    # health_check
    try:
        assert a.health_check()
        ok("health_check")
        akshare_ok += 1
    except Exception as e:
        fail(f"health_check: {e}")

    # 个股新闻
    try:
        news = a.get_news("000001")
        assert len(news) > 0
        ok(f"get_news: {len(news)} 条")
        akshare_ok += 1
    except Exception as e:
        fail(f"get_news: {e}")

    # 财联社电报
    try:
        tele = a.get_cls_telegraph()
        assert len(tele) > 0
        ok(f"get_cls_telegraph: {len(tele)} 条")
        akshare_ok += 1
    except Exception as e:
        fail(f"get_cls_telegraph: {e}")

    # 东财研报
    try:
        reports = a.get_research_report("000001")
        assert len(reports) > 0
        ok(f"get_research_report: {len(reports)} 条")
        akshare_ok += 1
    except Exception as e:
        fail(f"get_research_report: {e}")

    # 公告
    try:
        notices = a.get_announcements("000001")
        assert len(notices) > 0
        ok(f"get_announcements: {len(notices)} 条")
        akshare_ok += 1
    except Exception as e:
        fail(f"get_announcements: {e}")

    # 涨停板
    try:
        zt = a.get_limit_up_pool()
        assert len(zt) > 0
        ok(f"get_limit_up_pool: {len(zt)} 只")
        akshare_ok += 1
    except Exception as e:
        fail(f"get_limit_up_pool: {e}")

    # 强势涨停（题材归因）
    try:
        strong = a.get_strong_stocks()
        assert len(strong) > 0
        ok(f"get_strong_stocks: {len(strong)} 只 (含'入选理由'题材归因)")
        akshare_ok += 1
    except Exception as e:
        fail(f"get_strong_stocks: {e}")

    # 概念 + 行业
    try:
        concepts = a.get_concept_list()
        industries = a.get_industry_list()
        assert len(concepts) > 0 and len(industries) > 0
        ok(f"概念板块: {len(concepts)} 个, 行业板块: {len(industries)} 个")
        akshare_ok += 1
    except Exception as e:
        fail(f"概念/行业板块: {e}")

print(f"  akshare: {akshare_ok}/{akshare_total} 通过")

# ========== 4. 乐咕乐股 数据源 ==========
section("4. 乐咕乐股（PE / PB 估值）")

legulegu_ok = 0
legulegu_total = 2

try:
    from stoke.sources.legulegu_source import LeguleguSource
    t = LeguleguSource()
except Exception as e:
    fail(f"初始化 LeguleguSource: {e}")
    t = None

if t:
    try:
        assert t.health_check()
        ok("health_check")
    except Exception as e:
        fail(f"health_check: {e}")

    try:
        pe = t.get_index_pe("上证50")
        pb = t.get_market_pb()
        assert len(pe) > 0 and len(pb) > 0
        ok(f"上证50 PE: {len(pe)} 条 (最新 PE={pe['滚动市盈率'].iloc[-1]:.2f})")
        ok(f"全市场 PB: {len(pb)} 条 (最新 middlePB={pb['middlePB'].iloc[-1]:.2f})")
        legulegu_ok += 2
    except Exception as e:
        fail(f"get_index_pe / get_market_pb: {e}")

print(f"  乐咕乐股: {legulegu_ok}/{legulegu_total} 通过")

# ========== 5. 总结 ==========
section("5. 验收总结")

total = mootdx_ok + akshare_ok + legulegu_ok
total_target = mootdx_total + akshare_total + legulegu_total  # 14

print(f"  操作系统: {platform.system()} {platform.release()}")
print(f"  Python:   {sys.version.split()[0]}")
print(f"  mootdx:   {mootdx_ok}/{mootdx_total}")
print(f"  akshare:  {akshare_ok}/{akshare_total}")
print(f"  乐咕乐股: {legulegu_ok}/{legulegu_total}")
print(f"  总计:     {total}/{total_target}")

if total == total_target:
    print(f"\n  🎉 全部通过！Stoke 在本平台运行正常。")
elif total >= total_target * 0.8:
    print(f"\n  ⚠️ 大部分通过，少量接口有问题，见上方详情。")
else:
    print(f"\n  ❌ 多项失败，需排查环境或网络问题。")

print()

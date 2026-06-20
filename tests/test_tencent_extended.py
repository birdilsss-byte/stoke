"""
腾讯直连数据源扩展功能测试

覆盖：
  - 7 个新方法
  - 2 个旧方法回归
  - health_check

运行: uv run python3 tests/test_tencent_extended.py
"""

import time
import sys
import pandas as pd

# 确保能找到 stoke 包
sys.path.insert(0, ".")

from stoke.sources.tencent_direct_source import TencentDirectSource
from stoke.client import Stoke


def test_health_check(s: TencentDirectSource) -> bool:
    """0. 健康检查"""
    print("\n[0/9] health_check")
    ok = s.health_check()
    print(f"  health_check: {'✅ 通过' if ok else '❌ 失败'}")
    return ok


def test_get_realtime_regression(s: TencentDirectSource) -> bool:
    """1. 旧方法回归：get_realtime(A股)"""
    print("\n[1/9] get_realtime（A股回归）")
    df = s.get_realtime(["000001", "600519", "000858"])
    ok = len(df) > 0
    print(f"  A 股实时行情: {len(df)} 条, 列={list(df.columns)}")
    if not df.empty:
        print(f"  示例: {df[['symbol','name','price','change_pct']].to_string()}")
    return ok


def test_get_kline_regression(s: TencentDirectSource) -> bool:
    """2. 旧方法回归：get_kline(日K线)"""
    print("\n[2/9] get_kline（K线回归）")
    df = s.get_kline("600519", freq="day")
    ok = len(df) > 0
    print(f"  日 K 线: {len(df)} 条")
    if not df.empty:
        print(f"  最新: {df.tail(2).to_string()}")
    return ok


def test_get_market_realtime(s: TencentDirectSource) -> bool:
    """3. 跨市场实时行情"""
    print("\n[3/9] get_market_realtime（跨市场）")
    codes = ["sh000001", "sh000300", "hk00700", "usAAPL", "sz159915", "sh510050"]
    df = s.get_market_realtime(codes)
    ok = len(df) > 0
    print(f"  跨市场: {len(df)} 条")
    if not df.empty:
        print(f"  {df[['symbol','name','price','change_pct']].to_string()}")
    return ok


def test_get_brief_info(s: TencentDirectSource) -> bool:
    """4. 简要信息"""
    print("\n[4/9] get_brief_info（简要信息）")
    df = s.get_brief_info(["sh600519", "hk00700", "sz000858"])
    ok = len(df) > 0
    print(f"  简要信息: {len(df)} 条")
    if not df.empty:
        print(f"  {df.to_string()}")
    return ok


def test_get_tick_analysis(s: TencentDirectSource) -> bool:
    """5. 盘口大单分析"""
    print("\n[5/9] get_tick_analysis（盘口大单分析）")
    df = s.get_tick_analysis("sh600519")
    ok = len(df) > 0
    print(f"  盘口分析: {len(df)} 条")
    if not df.empty:
        print(f"  {df.to_string()}")
    return ok


def test_get_minute_kline(s: TencentDirectSource) -> bool:
    """6. 分钟K线"""
    print("\n[6/9] get_minute_kline（分钟K线）")
    print("  测试 5 分钟 K 线...")
    df = s.get_minute_kline("sh600519", freq="m5", count=100)
    ok = len(df) > 0
    print(f"  M5 分钟K线: {len(df)} 条")
    if not df.empty:
        print(f"  首条: {df.iloc[0].to_dict()}")
        print(f"  末条: {df.iloc[-1].to_dict()}")
    return ok


def test_get_intraday(s: TencentDirectSource) -> bool:
    """7. 分时数据"""
    print("\n[7/9] get_intraday_line + get_intraday_mline（分时数据）")
    from datetime import datetime
    line = s.get_intraday_line("sh600519")
    mline = s.get_intraday_mline("sh600519")
    # 非交易日返回0条是预期的，不算失败
    is_weekend = datetime.now().weekday() >= 5
    ok = (len(line) > 0 or len(mline) > 0) or is_weekend
    status = "✅" if len(line) > 0 or len(mline) > 0 else ("⏭️ 非交易日无数据" if is_weekend else "❌")
    print(f"  分时线(line): {len(line)} 条")
    print(f"  分钟K线(mline): {len(mline)} 条 ({status})")
    if not line.empty:
        print(f"  line示例: {line.head(2).to_string()}")
    if not mline.empty:
        print(f"  mline示例: {mline.head(2).to_string()}")
    return ok


def test_get_fqkline(s: TencentDirectSource) -> bool:
    """8. 复权K线"""
    print("\n[8/9] get_fqkline（后复权K线）")
    df = s.get_fqkline("sh600519", freq="day", adjust="hfq")
    ok = len(df) > 0
    print(f"  后复权 K 线: {len(df)} 条")
    if not df.empty:
        print(f"  最新: {df.tail(2).to_string()}")
    return ok


def test_via_client(s: Stoke) -> bool:
    """9. 通过 Stoke 统一入口调用"""
    print("\n[9/9] 通过 Stoke 客户端调用")
    results = []

    try:
        df = s.market_realtime(["sh000001", "hk00700"])
        results.append(len(df) > 0)
        print(f"  s.market_realtime: {'✅' if len(df) > 0 else '❌'} ({len(df)}条)")
    except Exception as e:
        results.append(False)
        print(f"  s.market_realtime: ❌ {e}")

    time.sleep(0.3)

    try:
        df = s.tencent_brief(["sh600519"])
        results.append(len(df) > 0)
        print(f"  s.tencent_brief: {'✅' if len(df) > 0 else '❌'} ({len(df)}条)")
    except Exception as e:
        results.append(False)
        print(f"  s.tencent_brief: ❌ {e}")

    time.sleep(0.3)

    try:
        df = s.minute_kline("sh600519", "m5", 50)
        results.append(len(df) > 0)
        print(f"  s.minute_kline: {'✅' if len(df) > 0 else '❌'} ({len(df)}条)")
    except Exception as e:
        results.append(False)
        print(f"  s.minute_kline: ❌ {e}")

    return all(results)


def main():
    print("=" * 60)
    print("  腾讯直连数据源扩展测试")
    print("=" * 60)

    source = TencentDirectSource()

    # 先测健康检查
    if not test_health_check(source):
        print("\n❌ 健康检查失败，数据源不可用，终止测试")
        sys.exit(1)

    # 逐个测试（限流间隔 0.3s）
    tests = [
        ("旧回归-get_realtime", test_get_realtime_regression),
        ("旧回归-get_kline", test_get_kline_regression),
        ("跨市场行情", test_get_market_realtime),
        ("简要信息", test_get_brief_info),
        ("盘口大单分析", test_get_tick_analysis),
        ("分钟K线", test_get_minute_kline),
        ("分时数据", test_get_intraday),
        ("复权K线", test_get_fqkline),
    ]

    results = []
    for name, fn in tests:
        try:
            ok = fn(source)
            results.append((name, ok, ""))
        except Exception as e:
            results.append((name, False, str(e)))
        time.sleep(0.4)  # 0.3s 限流 + 0.1s 缓冲

    # Stoke 客户端测试
    try:
        s = Stoke()
        client_ok = test_via_client(s)
        results.append(("Stoke客户端", client_ok, ""))
    except Exception as e:
        results.append(("Stoke客户端", False, str(e)))

    # 汇总
    print("\n" + "=" * 60)
    print("  测试汇总")
    print("=" * 60)
    passed = 0
    for name, ok, err in results:
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")
        if err:
            print(f"     错误: {err}")
        if ok:
            passed += 1

    total = len(results)
    pct = 100 * passed // total
    print(f"\n  通过: {passed}/{total} ({pct}%)")
    print(f"  {'🎉 全部通过!' if passed == total else '⚠️ 部分失败'}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

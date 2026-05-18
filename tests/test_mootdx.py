"""
mootdx 数据源测试
"""
from stoke.sources.mootdx_source import MootdxSource

m = MootdxSource()

# 连通性检查
assert m.health_check(), "mootdx 不可用!"
print("✅ mootdx 连通性通过")

# K线
kline = m.get_kline("000001")
assert len(kline) > 0, "K线数据为空!"
print(f"✅ K线: {len(kline)} 条 (最新: {str(kline.index[-1])[:19]}, close={kline['close'].iloc[-1]:.2f})")

# 实时行情
quotes = m.get_realtime(["000001", "600000", "000858"])
assert len(quotes) >= 1, "实时行情为空!"
print(f"✅ 实时行情: {len(quotes)} 只")

# 股票列表
stocks = m.get_stock_list()
assert len(stocks) > 10000, "股票列表太少!"
print(f"✅ 股票列表: {len(stocks)} 只")

print("\n🎉 mootdx 全部测试通过!")

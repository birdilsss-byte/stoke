"""
腾讯财经数据源测试
"""
from stoke.sources.tencent_source import TencentSource

t = TencentSource()

# 连通性
assert t.health_check(), "腾讯财经不可用!"
print("✅ 腾讯财经连通性通过")

# 上证50 PE
pe = t.get_index_pe("上证50")
assert len(pe) > 0, "PE数据为空!"
print(f"✅ 上证50 PE: {len(pe)} 条历史数据")
print(f"   最新: {pe['日期'].iloc[-1]}, PE={pe['滚动市盈率'].iloc[-1]:.2f}")

# 全市场 PB
pb = t.get_market_pb()
assert len(pb) > 0, "PB数据为空!"
print(f"✅ 全市场 PB: {len(pb)} 条历史数据")
print(f"   最新: {pb['date'].iloc[-1]}, middlePB={pb['middlePB'].iloc[-1]:.2f}")

print("\n🎉 腾讯财经全部测试通过!")

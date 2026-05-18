"""
akshare 数据源测试
⚠️ 每个接口间默认 5 秒限流，所以会比较慢
"""
from stoke.sources.akshare_source import AKShareSource

a = AKShareSource()

# 连通性
assert a.health_check(), "akshare 不可用!"
print("✅ akshare 连通性通过")

# 新闻
news = a.get_news("000001")
assert len(news) > 0, "个股新闻为空!"
print(f"✅ 个股新闻: {len(news)} 条")

# 财联社电报
tele = a.get_cls_telegraph()
assert len(tele) > 0, "电报为空!"
print(f"✅ 财联社电报: {len(tele)} 条")

# 研报
reports = a.get_research_report("000001")
assert len(reports) > 0, "研报为空!"
print(f"✅ 东财研报: {len(reports)} 条")

# 公告
notices = a.get_announcements("000001")
assert len(notices) > 0, "公告为空!"
print(f"✅ 公告: {len(notices)} 条")

# 涨停板
zt = a.get_limit_up_pool()
assert len(zt) > 0, "涨停板为空!"
print(f"✅ 涨停板: {len(zt)} 只")

# 强势涨停（含题材归因）
strong = a.get_strong_stocks()
assert len(strong) > 0, "强势涨停为空!"
print(f"✅ 强势涨停: {len(strong)} 只 (含'入选理由'字段)")

# 概念列表
concepts = a.get_concept_list()
assert len(concepts) > 0, "概念列表为空!"
print(f"✅ 概念板块: {len(concepts)} 个")

# 行业列表
industries = a.get_industry_list()
assert len(industries) > 0, "行业列表为空!"
print(f"✅ 行业板块: {len(industries)} 个")

print("\n🎉 akshare 全部测试通过!")

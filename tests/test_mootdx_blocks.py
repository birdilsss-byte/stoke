"""mootdx 板块数据深入探索"""
import sys
sys.path.insert(0, "/Volumes/Black/Stoke")
import time
from mootdx.quotes import Quotes

client = Quotes.factory(market="std")

print("=" * 60)
print("mootdx 板块数据深度探索")
print("=" * 60)

t0 = time.time()
blocks = client.block()
print(f"\n加载 {len(blocks)} 条，耗时 {time.time()-t0:.3f}s")
print(f"列名: {list(blocks.columns)}\n")

# 列名是 'blockname'（小写）
# 探索 block_type 的含义
print("--- block_type 含义 ---")
for bt in sorted(blocks["block_type"].unique()):
    cnt = len(blocks[blocks["block_type"] == bt])
    sample_names = blocks[blocks["block_type"] == bt]["blockname"].unique()[:3]
    print(f"  {bt}: {cnt}条 | 示例: {list(sample_names)}")

# 看看有没有行业/概念分类
print("\n--- 搜索行业相关板块 ---")
for keyword in ["行业", "概念", "板块", "地区", "风格"]:
    matches = blocks[blocks["blockname"].str.contains(keyword, na=False)]
    types_in = matches["block_type"].unique()
    print(f"  '{keyword}' → {len(matches)}条, block_type: {list(types_in)}")

# 看看 TDX 行业分类（block_type=2 可能是行业）
print("\n--- block_type=2 板块名（行业分类？）---")
bt2 = blocks[blocks["block_type"] == 2]["blockname"].unique()
print(f"  共 {len(bt2)} 个")
for n in bt2[:30]:
    print(f"    - {n}")

# 看看 block_type=48 是什么
print("\n--- block_type=48 板块名 ---")
bt48 = blocks[blocks["block_type"] == 48]["blockname"].unique()
print(f"  共 {len(bt48)} 个")
for n in bt48[:10]:
    print(f"    - {n}")

# 关键问题：沪深300/创业板等指数板块在哪个 type？
print("\n--- 查找关键板块 ---")
for name in ["沪深300", "创业板", "上证50", "中证500", "银行", "半导体", "新能源", "医药"]:
    found = blocks[blocks["blockname"].str.contains(name, na=False)]
    if len(found) > 0:
        for _, row in found.head(3).iterrows():
            print(f"  '{name}' → blockname='{row['blockname']}', type={row['block_type']}, code_index={row['code_index']}")
    else:
        print(f"  '{name}' → 未找到")

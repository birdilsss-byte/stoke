"""
Stoke 安装验证脚本

Hermes postinstall 用：快速验证 import + 初始化是否正常。
--full 模式额外检查 6 源连通性（会发网络请求）。

用法:
    uv run python3 scripts/verify_install.py           # 快速验证
    uv run python3 scripts/verify_install.py --full    # 含连通性检查
"""

import sys
import importlib


def check_import(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False


def main():
    ok = True

    # 1. 检查核心依赖导入
    deps = [
        "stoke", "pandas", "requests",
        "akshare", "mootdx",
    ]
    print("检查依赖导入...")
    for dep in deps:
        if check_import(dep):
            print(f"  ✅ {dep}")
        else:
            print(f"  ❌ {dep}")
            ok = False

    if not ok:
        print("\n❌ 依赖缺失，请执行: cd $STOKE_HOME && uv sync")
        sys.exit(1)

    # 2. 初始化 Stoke
    print("\n初始化 Stoke...")
    try:
        from stoke import Stoke
        s = Stoke()
        print("  ✅ Stoke() 初始化成功")
    except Exception as e:
        print(f"  ❌ Stoke() 初始化失败: {e}")
        sys.exit(1)

    # 3. 可选连通性检查
    if "--full" in sys.argv:
        print("\n全源连通性检查...")
        try:
            result = s.health_check()
            for name, alive in result.items():
                status = "✅" if alive else "❌"
                print(f"  {status} {name}: {alive}")
            if all(result.values()):
                print("\n✅ 全源连通正常")
            else:
                print("\n⚠️  部分源不可用（不影响基本使用）")
        except Exception as e:
            print(f"  ❌ 连通性检查异常: {e}")

    print("\n✅ Stoke 安装验证通过")
    sys.exit(0)


if __name__ == "__main__":
    main()

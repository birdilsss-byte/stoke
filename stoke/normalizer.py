"""
数据规范化：统一列名映射 + 日期标准化

每个数据源返回 DataFrame 前调用 normalize()，确保上层
消费到的数据列名和日期格式统一。

当前阶段为工具函数，不强制在 Source 内部调用。
"""

import pandas as pd

# 源列名 → 统一中文列名
_COLUMN_MAP = {
    # mootdx K 线 → 统一
    "open": "开盘价",
    "close": "收盘价",
    "high": "最高价",
    "low": "最低价",
    "volume": "成交量",
    "amount": "成交额",
    "datetime": "日期",

    # akshare 涨停板相关
    "代码": "代码",
    "名称": "名称",
    "涨跌幅": "涨跌幅",
    "封板时间": "封板时间",
    "炸板次数": "炸板次数",
    "连板数": "连板数",
    "入选理由": "入选理由",
    "所属行业": "所属行业",

    # akshare 资金流（去掉"-净额"等冗余后缀）
    "主力净流入-净额": "主力净流入",
    "超大单净流入-净额": "超大单净流入",
    "大单净流入-净额": "大单净流入",
    "中单净流入-净额": "中单净流入",
    "小单净流入-净额": "小单净流入",

    # akshare 新闻/电报
    "新闻标题": "标题",
    "发布时间": "发布时间",
    "新闻内容": "内容",

    # tencent 估值
    "滚动市盈率": "PE_TTM",
    "静态市盈率": "PE_静态",
    "middlePB": "PB_中位数",
    "equalWeightAveragePB": "PB_等权均值",
    "指数点位": "指数点位",
    "date": "日期",
}

# 日期列关键词（用于自动识别并转 datetime）
_DATE_KEYWORDS = ["日期", "时间", "date", "datetime", "发布时间"]


def normalize(df: pd.DataFrame, source: str = "") -> pd.DataFrame:
    """
    统一列名 + 日期列标准化为 datetime64 类型

    Args:
        df: 原始 DataFrame
        source: 数据源标识（仅用于日志，可选 "mootdx"/"akshare"/"tencent"）

    Returns:
        规范化后的 DataFrame（副本）
    """
    df = df.copy()

    df.rename(columns=_COLUMN_MAP, inplace=True)

    for col in df.columns:
        col_lower = col.lower()
        if any(kw in col_lower for kw in _DATE_KEYWORDS):
            try:
                df[col] = pd.to_datetime(df[col])
            except (ValueError, TypeError):
                pass

    return df

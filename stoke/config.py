"""
Stoke 全局配置
"""

# 限流间隔（秒）
RATE_LIMIT = {
    "mootdx": 0.0,       # TCP 协议，不限流
    "akshare": 5.0,      # 东财系，必须 3-5 秒
    "tencent": 3.0,      # 腾讯财经 lg 接口
}

# 日志级别
LOG_LEVEL = "INFO"

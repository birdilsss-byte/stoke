"""
Stoke 全局配置
"""

import logging
import sys

# 限流间隔（秒）
RATE_LIMIT = {
    "mootdx": 0.0,          # TCP 协议，不限流
    "akshare": 5.0,         # 东财系，必须 3-5 秒
    "legulegu": 1.0,        # 乐咕乐股 HTTP，1 秒即可
    "baostock": 1.0,        # 证券宝 HTTP，稳定 1 秒即可
    "efinance": 0.5,        # 整合多源，无官方限制，0.5 秒即可
    "tencent_direct": 0.3,  # 腾讯 qt.gtimg.cn，毫秒级响应，0.3 秒即可
}


def setup_logging(level: str = "INFO", log_file: str = ""):
    """
    配置全局日志

    Args:
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR)，默认 INFO
        log_file: 日志文件路径，空字符串表示仅输出到 stderr
    """
    handlers = [logging.StreamHandler(sys.stderr)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )

    # 静默第三方库的噪音日志
    for noisy in [
        "mootdx", "tdxpy", "akshare", "urllib3",
        "requests", "charset_normalizer", "matplotlib",
    ]:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # 静默 pandas 的 SQL 警告
    logging.getLogger("pandas.io.sql").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info("日志系统初始化完成 (级别=%s)", level.upper())

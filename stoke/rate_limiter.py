"""
统一限流器

每个数据源实例化一个独立的 RateLimiter，调用前必须先 wait()。
抖动在 interval 内消化，平均间隔 ≈ interval，不额外延长。
"""

import time
import random
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """请求频率控制，带随机抖动避免同步"""

    def __init__(self, interval: float = 5.0):
        """
        Args:
            interval: 两次请求之间的最小间隔（秒），0 表示不限流
        """
        self.interval = interval
        self.last_request_time: float = 0.0

    def wait(self):
        """等待足够的时间以确保满足间隔要求"""
        if self.interval <= 0:
            return

        current_time = time.time()
        elapsed = current_time - self.last_request_time

        if elapsed < self.interval:
            remaining = self.interval - elapsed
            jitter = random.uniform(-0.3, 0.3) * min(remaining, 1.0)
            sleep_time = max(0, remaining + jitter)
            logger.debug("限流等待 %.2f 秒", sleep_time)
            time.sleep(sleep_time)

        self.last_request_time = time.time()

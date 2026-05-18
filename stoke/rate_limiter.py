"""
统一限流器

每个数据源实例化一个独立的 RateLimiter，调用前必须先 wait()。
等待时间 = interval - elapsed + 随机抖动(0.1~0.5秒)。
"""

import time
import random


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
            return  # 不限流，直接通过

        current_time = time.time()
        elapsed = current_time - self.last_request_time

        if elapsed < self.interval:
            # 加上 0.1~0.5 秒的随机抖动，避免多个并发请求的同步
            sleep_time = self.interval - elapsed + random.uniform(0.1, 0.5)
            time.sleep(sleep_time)

        self.last_request_time = time.time()

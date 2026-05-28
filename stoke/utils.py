"""
工具函数

提供：自动重试装饰器（指数退避），用于 HTTP 类数据源。
网络抖动时自动重试，对连接断开/超时等临时故障生效。
"""

import logging
import time
import functools

import pandas as pd

logger = logging.getLogger(__name__)

# 值得重试的网络异常
_RETRYABLE = (ConnectionError, TimeoutError, OSError)


def retry_on_failure(max_retries: int = 3, base_delay: float = 1.0,
                     retry_on_empty: bool = False):
    """
    自动重试装饰器：网络抖动时自动重试，指数退避。

    只重试网络级异常（断开/超时/IO 错误），
    业务类异常（参数错误等）直接抛出。
    可选地重试空 DataFrame 返回。

    Args:
        max_retries: 最多重试次数（默认 3）
        base_delay: 首次重试前的等待秒数（每次翻倍）
        retry_on_empty: 是否在返回空 DataFrame 时也重试

    用法::
        @retry_on_failure()
        def get_data(self, symbol):
            ...

        @retry_on_failure(retry_on_empty=True)
        def get_critical_data(self, symbol):
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries):
                try:
                    result = func(*args, **kwargs)
                    if retry_on_empty and isinstance(result, pd.DataFrame) and len(result) == 0:
                        if attempt < max_retries - 1:
                            delay = base_delay * (2 ** attempt)
                            logger.warning(
                                "%s 返回空数据(第 %d/%d 次)，%.1f 秒后重试",
                                func.__name__, attempt + 1, max_retries, delay,
                            )
                            time.sleep(delay)
                            continue
                    return result
                except _RETRYABLE as e:
                    last_exc = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            "%s 失败(第 %d/%d 次): %s，%.1f 秒后重试",
                            func.__name__, attempt + 1, max_retries, e, delay,
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            "%s 已重试 %d 次，放弃: %s",
                            func.__name__, max_retries, e,
                        )
                        raise
                except Exception:
                    raise
            if last_exc is None:
                raise RuntimeError(
                    f"{func.__name__} 返回空数据，已重试 {max_retries} 次"
                )
            raise last_exc
        return wrapper
    return decorator

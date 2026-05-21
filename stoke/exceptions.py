"""
Stoke 自定义异常体系

上层（时机层/发现层）可按异常类型决定处理策略：
  - NetworkError   → 等待后重试
  - DataEmptyError → 可能非交易日，跳过
  - RateLimitError → 排队等待
"""


class StokeError(Exception):
    """Stoke 所有异常的基类"""
    pass


class NetworkError(StokeError):
    """网络连接异常（可重试）"""
    pass


class DataEmptyError(StokeError):
    """数据返回为空（可能非交易日或无数据）"""
    pass


class RateLimitError(StokeError):
    """触发限流（需延长等待）"""
    pass


class SourceNotReadyError(StokeError):
    """数据源不可用（health_check 失败）"""
    pass

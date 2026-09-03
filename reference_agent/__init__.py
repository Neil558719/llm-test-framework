"""可控的企业 IT 服务台参考被测 Agent。"""

__all__ = ["create_app"]


def create_app(*args, **kwargs):
    """加载 FastAPI 应用；轻量 runtime 配置导入不需要 LangGraph。"""
    from .app import create_app as _create_app

    return _create_app(*args, **kwargs)

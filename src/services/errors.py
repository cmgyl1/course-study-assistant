"""service 业务异常归一化。

UI 不直接 catch engine 的各色异常（ConversionError、KeyError、IOError 等），
统一在 service 层捕获并归一为 AppError 子类，由 Result.fail(error=str(e)) 返回。
"""
from __future__ import annotations


class AppError(Exception):
    """所有 UI 可感知的错误的基类。"""


class FileImportError(AppError):
    """文件转换 / 写盘失败（PDF 损坏、Markdown 解析异常）。"""


class PracticeSessionError(AppError):
    """刷题会话状态错误（无当前题、已结束）。"""


class ConfigError(AppError):
    """配置 / 路径错误（数据目录缺失、课程名非法）。"""

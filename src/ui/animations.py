"""UI 动画辅助：轻量、克制的动效层（不依赖第三方动画库）。

- fade_in：页面切换淡入（QGraphicsOpacityEffect + QPropertyAnimation）
- pulse：LOGO 环等签名元素的悬停脉冲（透明度呼吸）
- slide_down：分组卡片的轻量滑入（geometry 微移，仅用于顶层页面首次展示）

原则：动效是"刻意编排"而非堆砌——只在切换与悬停两处使用，
时长 180–260ms、OutCubic 缓动，避免过度动画的 AI 味。
"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QPoint
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget


def fade_in(widget: QWidget, duration: int = 220) -> QPropertyAnimation:
    """页面淡入：opacity 0 → 1（OutCubic）。"""
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.start(QPropertyAnimation.DeleteWhenStopped)
    return anim


def fade_out(widget: QWidget, duration: int = 160) -> QPropertyAnimation:
    """页面淡出：opacity 1 → 0（仅切换旧页用）。"""
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.setEasingCurve(QEasingCurve.InCubic)
    anim.start(QPropertyAnimation.DeleteWhenStopped)
    return anim


def pulse(widget: QWidget, duration: int = 900) -> QPropertyAnimation:
    """LOGO 环悬停脉冲：opacity 呼吸（1 → 0.72 → 1，循环 1 次）。"""
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(1.0)
    anim.setKeyValueAt(0.5, 0.72)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.InOutSine)
    anim.start(QPropertyAnimation.DeleteWhenStopped)
    return anim


def slide_down(widget: QWidget, duration: int = 240, offset: int = 10) -> QPropertyAnimation:
    """轻量滑入：从上方 10px 平滑归位（用于分组卡片首现）。"""
    original = widget.pos()
    widget.move(original.x(), original.y() - offset)
    anim = QPropertyAnimation(widget, b"pos", widget)
    anim.setDuration(duration)
    anim.setStartValue(QPoint(original.x(), original.y() - offset))
    anim.setEndValue(original)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.start(QPropertyAnimation.DeleteWhenStopped)
    return anim

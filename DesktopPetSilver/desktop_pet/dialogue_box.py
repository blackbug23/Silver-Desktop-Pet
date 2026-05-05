# -*- coding: utf-8 -*-
"""
dialogue_box.py — 打字机对话框组件
"""

import time

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QLabel


class TypeWriterLabel(QLabel):
    """逐字显示的打字机标签"""

    finished = pyqtSignal()
    size_changed = pyqtSignal()  # 文本高度变化时报此信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.text_full  = ""
        self.idx        = 0
        self.typing     = False
        self._last_click = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.setFont(QFont("微软雅黑", 14))
        self.setWordWrap(True)
        # 关键：让 QLabel 在固定宽度下自动计算所需高度
        self.setMinimumHeight(0)

    def start(self, txt):
        self.timer.stop()
        self.text_full = txt
        self.idx       = 0
        self.typing    = True
        self.setText("")
        self.adjustSize()        # 空文本时重置高度
        # 动态打字速度：长文字稍快
        speed = max(12, 22 - len(txt) // 8)
        self.timer.start(1000 // speed)

    def _tick(self):
        self.idx += 1
        if self.idx <= len(self.text_full):
            self.setText(self.text_full[:self.idx])
            self.adjustSize()       # 关键：文本变化后重新计算高度
            self.size_changed.emit()
        else:
            self.timer.stop()
            self.typing = False
            self.finished.emit()

    def mousePressEvent(self, event):
        now = time.time()
        if self.typing:
            # 点击立即完整显示（0.5s 冷却后才算有效点击）
            if now - self._last_click > 0.5:
                self.timer.stop()
                self.typing = False
                self.setText(self.text_full)
                self.adjustSize()
                self.size_changed.emit()
                self.finished.emit()
                self._last_click = now
        super().mousePressEvent(event)

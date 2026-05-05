# -*- coding: utf-8 -*-
"""
pet_widget.py — 宠物角色 QWidget + WanderController

负责：
  - 宠物图片显示与状态切换
  - 鼠标拖拽 + 挣扎动画
  - 随机溜达（WanderController）
  - 打字机说话动画
"""

import math
import random
import time
import threading

from PyQt5.QtCore import Qt, QTimer, QPoint, pyqtSignal, QObject
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QWidget, QLabel

from desktop_pet.config import ICON_PATH, PET_SIZE, PET_ANIM, PetState
from desktop_pet.utils import load_pet_pixmap


# ── 溜达控制器 ──────────────────────────────────────
class WanderController(QObject):
    """
    让宠物在屏幕上自主溜达：
    - 随机生成目标点，正弦波速度曲线靠近目标
    - 到达后停顿 1~4s，再选下一个目标
    """
    def __init__(self, widget):
        super().__init__()
        self.widget     = widget
        self._active    = False
        self._paused    = False
        self._target    = None
        self._sin_t     = 0.0
        self._last_t    = 0.0
        self._max_speed = 220.0   # px/s

        self._move_timer = QTimer(self)
        self._move_timer.setInterval(33)   # ~30fps
        self._move_timer.timeout.connect(self._update)

        self._pause_timer = QTimer(self)
        self._pause_timer.setSingleShot(True)
        self._pause_timer.timeout.connect(self._pick_next)

    def start(self):
        if self._active:
            return
        self._active = True
        self._paused = False
        self._sin_t  = 0.0
        self._last_t = time.time()
        self._target = self._random_target()
        self._move_timer.start()

    def stop(self):
        self._active = False
        self._move_timer.stop()
        self._pause_timer.stop()

    def is_active(self):
        return self._active

    def _random_target(self):
        geo = QApplication.primaryScreen().availableGeometry()
        m = 80
        return QPoint(
            random.randint(m, geo.width()  - m - self.widget.width()),
            random.randint(m, geo.height() - m - self.widget.height()),
        )

    def _update(self):
        if not self._active or self._paused:
            return
        now = time.time()
        dt  = min(now - self._last_t, 0.1)
        self._last_t = now

        wx = self.widget.x() + self.widget.width()  // 2
        wy = self.widget.y() + self.widget.height() // 2
        dx = self._target.x() - wx
        dy = self._target.y() - wy
        dist = math.hypot(dx, dy)

        if dist < 30:
            self._paused = True
            self._move_timer.stop()
            self._pause_timer.start(random.randint(1200, 3500))
            return

        # 正弦波速度
        self._sin_t += dt
        cos_v = math.cos(2 * math.pi * self._sin_t / 2.2)
        speed = self._max_speed * (0.35 + 0.65 * (cos_v + 1) / 2)
        if dist < 120:
            speed *= dist / 120

        vx = dx / dist * speed
        vy = dy / dist * speed
        self.widget.move(
            int(self.widget.x() + vx * dt),
            int(self.widget.y() + vy * dt),
        )
        self.widget.position_moved.emit()  # 通知主窗口更新浮动UI

    def _pick_next(self):
        if not self._active:
            return
        self._target = self._random_target()
        self._paused = False
        self._sin_t  = 0.0
        self._last_t = time.time()
        self._move_timer.start()


# ── 宠物 Widget ────────────────────────────────────
class PetWidget(QWidget):
    """宠物角色控件，处理图片、拖拽、挣扎"""

    # 信号
    double_clicked  = pyqtSignal()          # 双击
    right_clicked   = pyqtSignal(QPoint)    # 右键菜单位置
    speak_requested = pyqtSignal(str)       # 需要说的话
    state_changed   = pyqtSignal(str)       # 状态变更通知
    position_moved  = pyqtSignal()          # 位置移动通知（拖拽/溜达时）

    def __init__(self, parent=None):
        super().__init__(parent)

        # 图片标签
        self.pet_label = QLabel(self)
        self.pet_label.setGeometry(0, 0, PET_SIZE, PET_SIZE)
        self.pet_label.setContextMenuPolicy(Qt.CustomContextMenu)
        self.pet_label.customContextMenuRequested.connect(
            lambda pos: self.right_clicked.emit(self.pet_label.mapToGlobal(pos))
        )

        # 状态
        self.pet_state = PetState.IDLE
        self.dragging     = False
        self.drag_start_t = 0.0
        self.drag_offset  = QPoint(0, 0)

        # 挣扎动画
        self.struggle_timer = QTimer(self)
        self.struggle_timer.timeout.connect(self._struggle_anim)
        self.struggle_frame = 0

        # 溜达
        self.wanderer = WanderController(self)

        # 初始状态
        self.set_pet_status("idle")

    def set_pet_status(self, status):
        """切换宠物图片状态"""
        pix = load_pet_pixmap(status)
        if pix:
            self.pet_label.setPixmap(pix)
        else:
            self.pet_label.clear()
        self.state_changed.emit(status)

    # ── 拖拽 ──────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and \
                self.pet_label.geometry().contains(event.pos()):
            self.dragging     = True
            self.drag_offset  = event.globalPos() - self.pos()
            self.drag_start_t = time.time()
            self.wanderer.stop()
            self.set_pet_status("grabbed")
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.dragging:
            self.move(event.globalPos() - self.drag_offset)
            self.position_moved.emit()  # 通知主窗口更新浮动UI
            if time.time() - self.drag_start_t > 3 and \
                    not self.struggle_timer.isActive():
                self.struggle_timer.start(160)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.dragging:
            self.dragging = False
            self.struggle_timer.stop()
            # 限制宠物不超出屏幕边界
            desk = QApplication.primaryScreen().availableGeometry()
            new_x = max(desk.left(), min(self.x(), desk.right() - self.width()))
            new_y = max(desk.top(), min(self.y(), desk.bottom() - self.height()))
            # 贴右边墙效果
            if new_x > desk.width() - self.width() * 0.6:
                new_x = desk.width() - self.width() + 2
                self.move(new_x, new_y)
                self.set_pet_status("stick")
                QTimer.singleShot(900, lambda: self.set_pet_status("idle"))
            else:
                self.move(new_x, new_y)
                self.set_pet_status("idle")
            self.position_moved.emit()
            self.speak_requested.emit("release")
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.pet_label.geometry().contains(event.pos()):
            self.double_clicked.emit()

    def _struggle_anim(self):
        self.set_pet_status("struggle1" if self.struggle_frame % 2 == 0 else "struggle2")
        if self.struggle_frame % 6 == 0:
            self.speak_requested.emit("struggle")
        self.struggle_frame += 1

    # ── 说话动画 ──────────────────────────────────────
    def animate_talking(self, duration=1.1):
        """线程驱动 talking/idle 切换动画"""
        def run():
            end = time.time() + duration
            flag = True
            while time.time() < end and not self.dragging:
                self.set_pet_status("talking" if flag else "idle")
                flag = not flag
                time.sleep(0.12)
            if not self.dragging:
                self.set_pet_status("idle")
        threading.Thread(target=run, daemon=True).start()

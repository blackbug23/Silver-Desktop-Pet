# -*- coding: utf-8 -*-
"""
utils.py — 通用工具函数
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QPainter

from desktop_pet.config import PET_SIZE, PET_ANIM


def load_pet_pixmap(status, size=PET_SIZE):
    """
    加载宠物状态图片并缩放居中到 size x size 的透明画布上。
    返回 QPixmap 或 None。
    """
    img_path = PET_ANIM.get(status, PET_ANIM["idle"])
    pix = QPixmap(img_path)
    if pix.isNull():
        return None
    scaled = pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    canvas = QPixmap(size, size)
    canvas.fill(Qt.transparent)
    p = QPainter(canvas)
    p.drawPixmap((size - scaled.width()) // 2,
                 (size - scaled.height()) // 2, scaled)
    p.end()
    return canvas

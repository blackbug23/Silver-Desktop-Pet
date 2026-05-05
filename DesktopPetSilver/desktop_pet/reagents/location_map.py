# -*- coding: utf-8 -*-
"""
location_map.py — 存放位置可视化

绘制实验室冰箱/试剂柜/常温架/冷库的简化布局图，
标记各试剂的存放位置，一目了然。
"""

from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import (
    QPainter, QFont, QColor, QPen, QBrush, QPixmap, QIcon
)
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QInputDialog, QMessageBox, QWidget,
)

from desktop_pet.config import ICON_PATH, LOCATION_MAP
from desktop_pet.reagents.manager import ReagentManager


# ── 区域定义 ────────────────────────────────────────
_AREAS = [
    {"key": "fridge",  "label": "🧊 冰箱",   "codes": ["A1", "A2", "A3"],
     "color": QColor(200, 230, 255), "border": QColor(100, 160, 220)},
    {"key": "cabinet", "label": "🗄️ 试剂柜",  "codes": ["B1", "B2", "B3", "B4"],
     "color": QColor(230, 220, 200), "border": QColor(180, 150, 100)},
    {"key": "shelf",   "label": "📦 常温架",  "codes": ["C1", "C2"],
     "color": QColor(220, 240, 210), "border": QColor(130, 180, 100)},
    {"key": "cold",    "label": "❄️ 冷库",    "codes": ["D1"],
     "color": QColor(210, 230, 250), "border": QColor(80, 130, 200)},
]


class LocationMapDialog(QDialog):
    """可视化存放位置图"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📍 试剂存放位置图 · Silver博士")
        self.setWindowIcon(QIcon(ICON_PATH))
        self.setMinimumSize(780, 560)
        self.setFixedSize(780, 560)

        self._occupied = ReagentManager.get_occupied_locations()

        layout = QVBoxLayout(self)

        # 顶部提示
        hint = QPushButton("💡 点击位置格子可修改试剂位置")
        hint.setStyleSheet(
            "font-family:'Microsoft YaHei';font-size:12px;"
            "color:#666;border:none;background:transparent;"
        )
        hint.clicked.connect(lambda: None)
        layout.addWidget(hint)

        # 绘图区
        self._canvas = LocationCanvas(self)
        layout.addWidget(self._canvas, 1)

        # 底部按钮
        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.setStyleSheet(
            "font-family:'Microsoft YaHei';font-size:13px;padding:5px 15px;"
        )
        refresh_btn.clicked.connect(self._do_refresh)
        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet(
            "font-family:'Microsoft YaHei';font-size:13px;padding:5px 15px;"
        )
        close_btn.clicked.connect(self.close)
        btn_row.addStretch()
        btn_row.addWidget(refresh_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _do_refresh(self):
        self._occupied = ReagentManager.get_occupied_locations()
        self._canvas.update()

    def get_occupied(self):
        return self._occupied

    def on_location_clicked(self, loc_code):
        """某个位置格子被点击时，弹出修改对话框"""
        names = self._occupied.get(loc_code, [])
        loc_info = LOCATION_MAP.get(loc_code, ("未知", ""))
        label = f"{loc_code} - {loc_info[0]} {loc_info[1]}"

        if names:
            current = "、".join(names)
            QMessageBox.information(
                self, label,
                f"当前位置存放：\n\n{current}\n\n"
                f"如需修改，请在库存面板中选中对应试剂后点击「📍 修改位置」。"
            )
        else:
            # 空位 → 可选将某个试剂放过来
            all_reagents = ReagentManager.get_all()
            no_loc = [r["name"] for r in all_reagents if not r.get("location")]
            if not no_loc:
                QMessageBox.information(self, label, "此位置为空，且无未分配位置的试剂。")
                return
            name, ok = QInputDialog.getItem(
                self, f"分配到 {label}",
                "选择要放入此位置的试剂：", no_loc, 0, False
            )
            if ok and name:
                ReagentManager.update_location(name, loc_code)
                self._do_refresh()


class LocationCanvas(QWidget):
    """自定义绘图区：绘制冰箱/柜子/架子的布局"""

    def __init__(self, dialog):
        super().__init__(dialog)
        self._dialog = dialog
        self.setMinimumSize(740, 420)
        self.setMouseTracking(True)
        self._hover_loc = None
        self._rects = {}  # loc_code → QRectF

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        margin = 15
        occupied = self._dialog.get_occupied()

        # 分区布局：2列
        col_w = (w - margin * 3) / 2
        row_h = (h - margin * 3) / 2

        self._rects.clear()

        for idx, area in enumerate(_AREAS):
            col = idx % 2
            row = idx // 2
            x = margin + col * (col_w + margin)
            y = margin + row * (row_h + margin)

            # 区域背景
            p.setPen(QPen(area["border"], 2))
            p.setBrush(QBrush(area["color"]))
            p.drawRoundedRect(int(x), int(y), int(col_w), int(row_h), 10, 10)

            # 区域标题
            p.setPen(QColor(50, 50, 50))
            p.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
            p.drawText(int(x + 10), int(y + 24), area["label"])

            # 位置格子
            codes = area["codes"]
            slot_h = (row_h - 40) / max(len(codes), 1)
            for si, code in enumerate(codes):
                sy = y + 36 + si * slot_h
                rect = QRectF(x + 8, sy, col_w - 16, slot_h - 4)
                self._rects[code] = rect

                is_occupied = code in occupied
                is_hover = code == self._hover_loc

                # 格子背景
                if is_occupied:
                    bg = QColor(255, 245, 220) if not is_hover else QColor(255, 230, 180)
                    p.setPen(QPen(QColor(200, 160, 80), 1.5))
                else:
                    bg = QColor(255, 255, 255, 180) if not is_hover else QColor(240, 248, 255)
                    p.setPen(QPen(QColor(180, 180, 180), 1))
                p.setBrush(QBrush(bg))
                p.drawRoundedRect(rect, 6, 6)

                # 位置编号
                loc_info = LOCATION_MAP.get(code, ("", ""))
                p.setPen(QColor(80, 80, 80))
                p.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
                p.drawText(rect.adjusted(8, 4, 0, -rect.height() / 2 + 4),
                           f"{code}  {loc_info[1]}")

                # 试剂名
                if is_occupied:
                    names = occupied[code]
                    p.setFont(QFont("Microsoft YaHei", 9))
                    p.setPen(QColor(160, 100, 20))
                    name_text = "、".join(names)
                    if len(name_text) > 28:
                        name_text = name_text[:25] + "..."
                    p.drawText(rect.adjusted(8, rect.height() / 2 - 4, -4, 0),
                               name_text)
                else:
                    p.setFont(QFont("Microsoft YaHei", 9))
                    p.setPen(QColor(170, 170, 170))
                    p.drawText(rect.adjusted(8, rect.height() / 2 - 4, -4, 0),
                               "（空位）")

        p.end()

    def mouseMoveEvent(self, event):
        pos = event.pos()
        new_hover = None
        for code, rect in self._rects.items():
            if rect.contains(pos):
                new_hover = code
                break
        if new_hover != self._hover_loc:
            self._hover_loc = new_hover
            self.setCursor(Qt.PointingHandCursor if new_hover else Qt.ArrowCursor)
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.pos()
            for code, rect in self._rects.items():
                if rect.contains(pos):
                    self._dialog.on_location_clicked(code)
                    break

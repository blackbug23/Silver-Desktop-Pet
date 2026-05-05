# -*- coding: utf-8 -*-
"""
main.py — Silver 桌宠入口

只负责 QApplication 初始化，业务逻辑全在 desktop_pet 包内。
"""

import sys
import os

# 确保项目根目录在 sys.path 中
_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon

from desktop_pet.config import ICON_PATH
from desktop_pet.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(ICON_PATH))
    pet = MainWindow()
    pet.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
record.py — 实验记录生成与预览
"""

import os
from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QTextEdit, QFileDialog, QMessageBox,
)

from desktop_pet.config import ICON_PATH
from desktop_pet.reagents.manager import ReagentManager


def generate_experiment_record(name="PCR扩增",
                                steps=("变性98°C 10s", "退火55°C 30s",
                                       "延伸72°C 30s", "35循环")):
    """生成鹰谷格式实验记录"""
    data = ReagentManager.get_all()
    lots = ", ".join(f'{r["name"]}({r["batch"]})' for r in data if r["stock"] > 0)
    txt  = f"【鹰谷实验记录】\n实验名称：{name}\n"
    txt += f"日期时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    txt += f"操作人：Silver博士\n试剂批次：{lots or '无可用试剂'}\n"
    txt += "─" * 28 + "\n步骤：\n"
    for i, s in enumerate(steps, 1):
        txt += f"  {i}. {s}\n"
    txt += "─" * 28 + "\n结果初表：\n| 样本 | Ct值 | 备注 |\n|------|------|------|\n| 01   | 18.5 | 正常 |\n"
    txt += f"记录人：Silver（鹰谷系统自动生成）\n"
    return txt


class RecordDialog(QDialog):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("鹰谷实验记录")
        self.setWindowIcon(QIcon(ICON_PATH))
        self.resize(500, 420)
        self._text = text
        lay = QVBoxLayout(self)
        ed = QTextEdit()
        ed.setPlainText(text)
        ed.setReadOnly(True)
        ed.setFont(QFont("Consolas", 10))
        lay.addWidget(ed)
        bh = QHBoxLayout()
        bs = QPushButton("💾 保存")
        bs.clicked.connect(self._save)
        bc = QPushButton("关闭")
        bc.clicked.connect(self.close)
        bh.addWidget(bs)
        bh.addWidget(bc)
        lay.addLayout(bh)

    def _save(self):
        from desktop_pet.config import DATA_DIR
        default_path = os.path.join(os.path.dirname(DATA_DIR), "鹰谷实验记录.txt")
        path, _ = QFileDialog.getSaveFileName(
            self, "保存实验记录", default_path, "文本文件 (*.txt)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._text)
            QMessageBox.information(self, "保存成功", f"已保存至：{path}")

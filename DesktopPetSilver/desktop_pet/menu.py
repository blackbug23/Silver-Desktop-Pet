# -*- coding: utf-8 -*-
"""
menu.py — 右键功能菜单

只做 UI 路由，业务逻辑委托给 main_window 的回调。
新增：检索试剂、导入Excel、位置图
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMenu

from desktop_pet.config import ICON_PATH


class PetMenu:
    """宠物右键菜单构建器"""

    # 菜单项定义：(图标文字, action_key) 或 None 表示分隔线
    ITEMS = [
        ("💬 开启/关闭输入框", "toggle_input"),
        None,
        ("📋 库存面板",         "stock_panel"),
        ("🔍 检索试剂",         "search"),
        ("📥 导入Excel库存",    "import_excel"),
        ("🗺️ 存放位置图",       "location_map"),
        ("⏳ 效期 & 库存检查",  "check_all"),
        ("⭐ 近效期推荐",       "recommend"),
        ("📉 低库存警报",       "low_stock"),
        ("📦 快速领用",         "quick_use"),
        None,
        ("📝 生成鹰谷实验记录", "gen_record"),
        ("🚶 溜达 / 停下",     "toggle_wander"),
        None,
        ("ℹ️ 关于 Silver",      "about"),
        ("❌ 退出",             "exit"),
    ]

    @staticmethod
    def popup(global_pos, callbacks, parent=None):
        """
        弹出菜单。
        callbacks: dict[action_key → callable]
        """
        menu = QMenu(parent)
        menu.setStyleSheet(
            "QMenu{font-family:'Microsoft YaHei';font-size:13px;"
            "background:rgba(255,255,255,0.97);border:1px solid #ccc;"
            "border-radius:8px;padding:4px;}"
            "QMenu::item{padding:6px 20px;border-radius:4px;}"
            "QMenu::item:selected{background:#E6F0FF;}"
        )
        for item in PetMenu.ITEMS:
            if item is None:
                menu.addSeparator()
            else:
                label, action_key = item
                action = menu.addAction(label)
                fn = callbacks.get(action_key)
                if fn:
                    action.triggered.connect(fn)
        menu.exec_(global_pos)

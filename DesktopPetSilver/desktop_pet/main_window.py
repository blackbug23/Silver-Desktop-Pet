# -*- coding: utf-8 -*-
"""
main_window.py — 主窗口调度

组合 pet_widget + dialogue_box + input + menu，
协调各模块交互。
"""

import random
import time

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLineEdit, QPushButton, QInputDialog, QMessageBox
)

from desktop_pet.config import (
    ICON_PATH, PET_SIZE, PetState, AIState, SilverQuotes, LOCATION_MAP
)
from desktop_pet.pet_widget import PetWidget
from desktop_pet.dialogue_box import TypeWriterLabel
from desktop_pet.ai_chat import AIChatWorker
from desktop_pet.menu import PetMenu
from desktop_pet.reagents.manager import ReagentManager


class MainWindow(QWidget):
    """桌宠主窗口 — 调度一切"""

    def __init__(self):
        super().__init__()

        # 窗体属性 — 覆盖全屏幕透明窗口，让桌宠可以自由移动到任何位置
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowIcon(QIcon(ICON_PATH))

        # 窗口覆盖全屏幕可用区域（透明背景，宠物和气泡在里面自由移动）
        desk = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(desk)

        # ── 宠物控件 ──
        self.pet = PetWidget(self)
        self.pet.double_clicked.connect(self._on_double_click)
        self.pet.right_clicked.connect(self._on_right_click)
        self.pet.speak_requested.connect(self._on_pet_speak)
        self.pet.position_moved.connect(self._update_floating_pos)

        # ── 对话框（浮在宠物上方，位置跟随宠物）──
        self.dialog_box = TypeWriterLabel(self)
        self.dialog_box.setStyleSheet(
            "background:rgba(255,255,255,210);border-radius:12px;"
            "font-size:15px;color:#333;padding:6px 10px;"
        )
        self.dialog_box.setFixedWidth(260)
        self.dialog_box.setWordWrap(True)
        self.dialog_box.finished.connect(self._on_dialog_finished)
        self.dialog_box.size_changed.connect(self._update_floating_pos)
        self._speak_time  = time.time()
        self._speak_queue = []

        # ── 输入框 + 发送按钮（浮在宠物下方）──
        self.input_box = QLineEdit(self)
        self.input_box.setPlaceholderText("说点什么...")
        self.input_box.setFixedSize(118, 28)
        self.input_box.setStyleSheet(
            "border-radius:7px;padding:6px 10px;font-size:14px;"
            "background:rgba(255,255,255,220);"
        )
        self.input_box.returnPressed.connect(self._handle_input)

        self.send_btn = QPushButton("发送", self)
        self.send_btn.setFixedSize(62, 28)
        self.send_btn.setStyleSheet(
            "background:#D5D9DB;border-radius:7px;font-size:13px;"
        )
        self.send_btn.clicked.connect(self._handle_input)

        # ── AI ──
        self.ai_state = AIState.IDLE
        self.ai_worker = AIChatWorker()
        self.ai_worker.reply_ready.connect(self._on_ai_reply)
        self.ai_worker.reply_error.connect(self._on_ai_reply)

        # ── 启动问候 ──
        self._move_pet_to_right_bottom()
        self._update_floating_pos()  # 同步气泡和输入框位置
        self._speak(SilverQuotes.get_greeting())

        # ── 随机口头禅 ──
        self._quip_timer = QTimer(self)
        self._quip_timer.timeout.connect(self._random_quip)
        self._quip_timer.start(180_000)

    # ── 布局 ──────────────────────────────────────────
    def _move_pet_to_right_bottom(self):
        """将宠物初始位置放在右下角"""
        desk = QApplication.primaryScreen().availableGeometry()
        self.pet.move(
            desk.width() - PET_SIZE - 20,
            desk.height() - PET_SIZE - 40
        )

    def _update_floating_pos(self):
        """根据宠物当前位置，更新对话框和输入框的位置"""
        px = self.pet.x()
        py = self.pet.y()

        # 对话框在宠物头顶
        self.dialog_box.move(px - 30, py - self.dialog_box.height() - 8)

        # 输入框在宠物脚底
        self.input_box.move(px, py + PET_SIZE + 4)
        self.send_btn.move(px + self.input_box.width() + 4, py + PET_SIZE + 4)

    # ── 说话系统 ──────────────────────────────────────
    def _speak(self, txt):
        self.dialog_box.start(txt)
        self._speak_time = time.time()
        self.pet.animate_talking(max(len(txt) * 0.055, 0.8))
        self._update_floating_pos()  # 说话时同步位置

    def _queue_speak(self, txt):
        self._speak_queue.append(txt)
        if not self.dialog_box.typing:
            self._flush_queue()

    def _flush_queue(self):
        if self._speak_queue:
            self._speak(self._speak_queue.pop(0))

    def _on_dialog_finished(self):
        if self._speak_queue:
            QTimer.singleShot(400, self._flush_queue)
        else:
            QTimer.singleShot(2500, self._try_hide_dialog)

    def _try_hide_dialog(self):
        if not self._speak_queue and not self.dialog_box.typing:
            if time.time() - self._speak_time >= 2.4:
                self.dialog_box.setText("")

    # ── 宠物事件 ──────────────────────────────────────
    def _on_double_click(self):
        self._open_stock_panel()
        self._speak("双击翻身干活！*迅速翻开库存本*")

    def _on_right_click(self, global_pos):
        callbacks = {
            "toggle_input": self._toggle_input,
            "stock_panel":  self._open_stock_panel,
            "search":       self._open_search,
            "import_excel": self._open_import_excel,
            "location_map": self._open_location_map,
            "check_all":    self._check_all,
            "recommend":    self._recommend,
            "low_stock":    self._low_stock,
            "quick_use":    self._quick_use,
            "gen_record":   self._gen_record,
            "toggle_wander": self._toggle_wander,
            "about":        self._about,
            "exit":         self._exit,
        }
        PetMenu.popup(global_pos, callbacks, self)

    def _on_pet_speak(self, speak_type):
        if speak_type == "release":
            self._speak(random.choice(SilverQuotes.RELEASE_QUIPS))
        elif speak_type == "struggle":
            self._speak(random.choice(SilverQuotes.STRUGGLE_QUIPS))

    # ── AI 对话 ──────────────────────────────────────
    def _handle_input(self):
        txt = self.input_box.text().strip()
        if not txt:
            self._speak("说点什么嘛……")
            return
        if self.ai_worker.busy:
            self._speak("等一下，博士还在思考上一个问题……")
            return
        self.input_box.setText("")
        self.input_box.setEnabled(False)
        self.send_btn.setEnabled(False)
        self.ai_state = AIState.GENERATING
        self.ai_worker.ask(txt)

    def _on_ai_reply(self, reply):
        self.ai_state = AIState.IDLE
        self.input_box.setEnabled(True)
        self.send_btn.setEnabled(True)
        self._speak(reply)

    # ── 随机口头禅 ────────────────────────────────────
    def _random_quip(self):
        if self.dialog_box.typing or self.pet.dragging or self.ai_worker.busy:
            return
        near = ReagentManager.get_near_expiry(30)
        low  = ReagentManager.get_low_stock()
        self._speak(SilverQuotes.get_dynamic_quip(near, low))

    # ── 功能操作 ──────────────────────────────────────
    def _toggle_input(self):
        if self.input_box.isVisible():
            self.input_box.hide()
            self.send_btn.hide()
        else:
            self.input_box.show()
            self.send_btn.show()
            self._update_floating_pos()
            self.input_box.setFocus()

    def _open_stock_panel(self):
        from desktop_pet.reagents.stock_panel import StockPanel
        dlg = StockPanel(self)
        dlg.exec_()

    def _open_search(self):
        """快捷检索试剂"""
        keyword, ok = QInputDialog.getText(
            self, "检索试剂", "输入试剂名称/批次/位置："
        )
        if ok and keyword.strip():
            results = ReagentManager.search(keyword.strip())
            if not results:
                self._speak(f"*翻本子* 没找到「{keyword.strip()}」相关试剂。")
            else:
                names = "、".join(r["name"] for r in results[:5])
                self._speak(f"*竖耳朵* 找到 {len(results)} 条：{names}")

    def _open_import_excel(self):
        """直接打开 Excel 导入（弹文件选择框）"""
        from desktop_pet.reagents.stock_panel import _import_excel_standalone
        _import_excel_standalone(self)

    def _open_location_map(self):
        from desktop_pet.reagents.location_map import LocationMapDialog
        dlg = LocationMapDialog(self)
        dlg.exec_()

    def _check_all(self):
        problems = ReagentManager.check_problems()
        if not problems:
            self._speak("*翻库存本* 所有试剂状态正常，博士满意。")
        else:
            names = "、".join(n for n, _ in problems[:3])
            self._speak(f"⚠️ {names} 等存在问题，赶紧处理！")

    def _recommend(self):
        rec = [r for r in ReagentManager.get_all()
               if r["stock"] > 0 and
               r.get("expire", "2099-12-31") > "2026-01-01"]
        rec.sort(key=lambda r: r.get("expire", "9999"))
        if not rec:
            self._speak("*叹气* 当前没有可用试剂，库存告急！")
        else:
            from datetime import datetime
            f = rec[0]
            try:
                d = (datetime.strptime(f["expire"], "%Y-%m-%d") - datetime.now()).days
            except ValueError:
                d = 999
            self._speak(f"*竖耳朵* 推荐《{f['name']}》，效期还剩 {d} 天，赶紧安排！")

    def _low_stock(self):
        low = ReagentManager.get_low_stock()
        if not low:
            self._speak("*满意点头* 库存充足，博士放心了。")
        else:
            s = "、".join(f"{n}(仅{c}支)" for n, c in low[:3])
            self._speak(f"📉 低库存：{s}，快去补货！")

    def _quick_use(self):
        data  = ReagentManager.get_all()
        names = [r["name"] for r in data if r["stock"] > 0 and not r.get("is_freeze")]
        if not names:
            self._speak("*双手摊开* 没有可领用的试剂了……")
            return
        name, ok = QInputDialog.getItem(self, "快速领用", "选择试剂：", names, 0, False)
        if ok and name:
            success, days, msg = ReagentManager.use_reagent(name, 1)
            if success:
                self._speak(f"库存扣减成功！《{name}》效期剩 {days} 天，省着点用。")
            else:
                self._speak(f"《{name}》{msg}，无法领用！")

    def _gen_record(self):
        from desktop_pet.reagents.record import generate_experiment_record, RecordDialog
        txt = generate_experiment_record()
        dlg = RecordDialog(txt, self)
        dlg.exec_()
        self._speak("鹰谷记录已生成，别让我白写。*甩毛笔*")

    def _toggle_wander(self):
        if self.pet.wanderer.is_active():
            self.pet.wanderer.stop()
            self._speak("*停下来* 不走了，继续守库存。")
        else:
            self.pet.wanderer.start()
            self._speak("*四处张望* 出去溜达溜达，库存委托给你了！")

    def _about(self):
        self._speak(
            "银狐仓鼠博士·Silver，极简实验桌宠。"
            "库存/效期/记录/溜达都不落！被大家天天拎后颈，才变得这么呆萌。"
        )

    def _exit(self):
        self._speak("库存扣减成功，省着点用。")
        QTimer.singleShot(900, QApplication.quit)

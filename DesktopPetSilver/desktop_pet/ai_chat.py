# -*- coding: utf-8 -*-
"""
ai_chat.py — DeepSeek API 封装

独立线程调用，通过 pyqtSignal 回传主线程。
"""

import threading

from PyQt5.QtCore import QObject, pyqtSignal

from desktop_pet.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL


class AIChatWorker(QObject):
    """AI 对话工作线程，发送信号回主线程"""

    reply_ready  = pyqtSignal(str)   # 成功回复
    reply_error  = pyqtSignal(str)   # 出错信息

    def __init__(self):
        super().__init__()
        self.chat_history = [
            {
                "role": "system",
                "content": (
                    "你是仓鼠博士Silver，银狐仓鼠，严谨、护试剂、碎嘴子。"
                    "口头禅：库存扣减成功省着点用；效期还剩X天赶紧安排；鹰谷记录已生成别让我白写。"
                    "帮助实验人员管理库存，回答简洁不超过50字，可加动作描述如*竖耳朵*。"
                )
            }
        ]
        self._busy = False

    @property
    def busy(self):
        return self._busy

    def ask(self, user_text):
        """异步调用 DeepSeek，结果通过信号返回"""
        if self._busy:
            return
        self._busy = True
        threading.Thread(target=self._do_ask, args=(user_text,), daemon=True).start()

    def _do_ask(self, user_text):
        self.chat_history.append({"role": "user", "content": user_text})
        try:
            from openai import OpenAI
            client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
            resp = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=self.chat_history,
                temperature=0.8,
                max_tokens=200,
            )
            reply = resp.choices[0].message.content.strip()
            self.chat_history.append({"role": "assistant", "content": reply})
            self.reply_ready.emit(reply)
        except Exception as e:
            self.reply_error.emit(f"*捂脸* 网络出问题了：{str(e)[:40]}")
        finally:
            self._busy = False

# -*- coding: utf-8 -*-
"""
config.py — 常量、资源路径、枚举、台词库

修改配置只需改这里，不用动任何业务逻辑。
"""

import os
import random
from datetime import datetime
from enum import Enum, auto

# ============================================================
#  路径（所有路径基于项目根目录 DesktopPetSilver/）
# ============================================================
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RES_DIR   = os.path.join(_PROJECT_ROOT, "resources")
DATA_DIR  = os.path.join(_PROJECT_ROOT, "data")
DATA_PATH = os.path.join(DATA_DIR, "reagents_data.json")

ICON_PATH = os.path.join(RES_DIR, "Silver-1-001.ico")

PET_SIZE  = 200          # 宠物显示边长（px）

PET_ANIM = {
    "idle":      os.path.join(RES_DIR, "Silver-1.png"),
    "talking":   os.path.join(RES_DIR, "Silver-2.png"),
    "stick":     os.path.join(RES_DIR, "Silver-3.png"),
    "grabbed":   os.path.join(RES_DIR, "Silver-4.png"),
    "struggle1": os.path.join(RES_DIR, "Silver-5.png"),
    "struggle2": os.path.join(RES_DIR, "Silver-6.png"),
}

# ============================================================
#  DeepSeek API
# ============================================================
DEEPSEEK_API_KEY  = "sk-4daebdbb13b042608da6d0d9282f640d"  # api输入口
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL    = "deepseek-chat"

# ============================================================
#  状态枚举
# ============================================================
class PetState(Enum):
    IDLE       = auto()
    TALKING    = auto()
    GRABBED    = auto()
    STRUGGLING = auto()
    WANDERING  = auto()
    STICK      = auto()

class AIState(Enum):
    IDLE       = auto()
    GENERATING = auto()
    ERROR      = auto()

# ============================================================
#  存放位置预定义
# ============================================================
# 格式：位置编号 → (区域名, 层/格)
LOCATION_MAP = {
    "A1": ("冰箱",   "上层"),
    "A2": ("冰箱",   "中层"),
    "A3": ("冰箱",   "下层"),
    "B1": ("试剂柜", "第一层"),
    "B2": ("试剂柜", "第二层"),
    "B3": ("试剂柜", "第三层"),
    "B4": ("试剂柜", "第四层"),
    "C1": ("常温架", "左侧"),
    "C2": ("常温架", "右侧"),
    "D1": ("冷库",   "暂存区"),
}

# ============================================================
#  默认库存数据
# ============================================================
DEFAULT_REAGENTS = [
    {
        "name": "Taq酶 (5U/μL)",    "batch": "B20250901", "expire": "2026-04-30",
        "stock": 3, "threshold": 1, "price": 88.0,
        "putaway_date": "2025-09-01", "is_freeze": False,
        "location": "A1", "warehouse_type": "reagent",
        "record_book_no": "", "project_no": "",
        "volume": "", "molecular_weight": "",
        "isoelectric_point": "", "extinction_coeff": "",
        "concentration": "", "sample_volume": "", "total_amount": "",
        "titer": "", "purity": "",
        "buffer_type": "", "shipping_info": "",
        "specification": "", "catalog_no": "", "manufacturer": "", "notes": "",
        "stock_mode": "quantity", "sample_volume": "",
        "cell_line": "", "passage_no": "", "culture_medium": "",
        "cryo_vial_count": 0, "viability": "", "mycoplasma": "",
    },
    {
        "name": "dNTPs Mix (10mM)", "batch": "B20251011", "expire": "2026-03-15",
        "stock": 2, "threshold": 1, "price": 45.0,
        "putaway_date": "2025-10-11", "is_freeze": False,
        "location": "A2", "warehouse_type": "reagent",
        "record_book_no": "", "project_no": "",
        "volume": "", "molecular_weight": "",
        "isoelectric_point": "", "extinction_coeff": "",
        "concentration": "", "sample_volume": "", "total_amount": "",
        "titer": "", "purity": "",
        "buffer_type": "", "shipping_info": "",
        "specification": "", "catalog_no": "", "manufacturer": "", "notes": "",
        "stock_mode": "quantity", "sample_volume": "",
        "cell_line": "", "passage_no": "", "culture_medium": "",
        "cryo_vial_count": 0, "viability": "", "mycoplasma": "",
    },
    {
        "name": "SYBR Green I",     "batch": "B20251103", "expire": "2026-06-01",
        "stock": 5, "threshold": 2, "price": 120.0,
        "putaway_date": "2025-11-03", "is_freeze": False,
        "location": "B1", "warehouse_type": "reagent",
        "record_book_no": "", "project_no": "",
        "volume": "", "molecular_weight": "",
        "isoelectric_point": "", "extinction_coeff": "",
        "concentration": "", "sample_volume": "", "total_amount": "",
        "titer": "", "purity": "",
        "buffer_type": "", "shipping_info": "",
        "specification": "", "catalog_no": "", "manufacturer": "", "notes": "",
        "stock_mode": "quantity", "sample_volume": "",
        "cell_line": "", "passage_no": "", "culture_medium": "",
        "cryo_vial_count": 0, "viability": "", "mycoplasma": "",
    },
    {
        "name": "Protein Ladder",   "batch": "B20260102", "expire": "2026-05-20",
        "stock": 1, "threshold": 1, "price": 200.0,
        "putaway_date": "2026-01-02", "is_freeze": False,
        "location": "B2", "warehouse_type": "reagent",
        "record_book_no": "", "project_no": "",
        "volume": "", "molecular_weight": "",
        "isoelectric_point": "", "extinction_coeff": "",
        "concentration": "", "sample_volume": "", "total_amount": "",
        "titer": "", "purity": "",
        "buffer_type": "", "shipping_info": "",
        "specification": "", "catalog_no": "", "manufacturer": "", "notes": "",
        "stock_mode": "quantity", "sample_volume": "",
        "cell_line": "", "passage_no": "", "culture_medium": "",
        "cryo_vial_count": 0, "viability": "", "mycoplasma": "",
    },
    {
        "name": "ECL显色液 A+B",    "batch": "B20260310", "expire": "2026-02-28",
        "stock": 0, "threshold": 1, "price": 60.0,
        "putaway_date": "2026-03-10", "is_freeze": False,
        "location": "C1", "warehouse_type": "reagent",
        "record_book_no": "", "project_no": "",
        "volume": "", "molecular_weight": "",
        "isoelectric_point": "", "extinction_coeff": "",
        "concentration": "", "sample_volume": "", "total_amount": "",
        "titer": "", "purity": "",
        "buffer_type": "", "shipping_info": "",
        "specification": "", "catalog_no": "", "manufacturer": "", "notes": "",
        "stock_mode": "quantity", "sample_volume": "",
        "cell_line": "", "passage_no": "", "culture_medium": "",
        "cryo_vial_count": 0, "viability": "", "mycoplasma": "",
    },
]

# ============================================================
#  台词库
# ============================================================
class SilverQuotes:
    """Silver 专属台词库，按时段 + 状态分层"""

    TIME_GREETINGS = {
        "morning":   (( 5, 11), ["早安！博士开始值班，试剂请妥善保管。",
                                  "早！库存本已更新，开始今天的工作吧。"]),
        "noon":      ((11, 14), ["中午了，先吃饭，试剂管好再去。",
                                  "午休前记得检查一下近效期啊。"]),
        "afternoon": ((14, 18), ["下午好，实验进行得怎么样了？",
                                  "下午了，效期记录别拖到下班前。"]),
        "evening":   ((18, 22), ["晚上好，今天的实验记录写好了吗？",
                                  "收工前把领用登记补完，别让我追。"]),
        "night":     ((22,  5), ["深夜还在干？注意试剂储存温度。",
                                  "夜深了，低温试剂记得放回冰箱。"]),
    }

    IDLE_QUIPS = [
        "库存扣减成功，省着点用。",
        "效期是认真的，别信过期了还能用。",
        "实验记录不写完整，我会不高兴的。",
        "细胞状态怎么样？我不问你不说是吧。",
        "入库要及时，别等缺货来找我补洞。",
        "鹰谷系统上线，偷懒都被记录在案。",
    ]

    STRUGGLE_QUIPS = [
        "放我下来！试剂会翻！",
        "我说了别拎后颈……",
        "*耳朵压平* 很生气。",
        "再拎我我要记录在案了！",
    ]

    RELEASE_QUIPS = [
        "*整理毛发* 终于放下来了。",
        "你们总这样……*记录在案*",
        "好，继续工作，哼。",
    ]

    @classmethod
    def get_greeting(cls):
        hour = datetime.now().hour
        for period, ((s, e), quotes) in cls.TIME_GREETINGS.items():
            in_range = (s <= hour < e) if s < e else (hour >= s or hour < e)
            if in_range:
                return random.choice(quotes)
        return random.choice(cls.IDLE_QUIPS)

    @classmethod
    def get_dynamic_quip(cls, near_list=None, low_list=None):
        """结合实时库存生成动态口头禅"""
        probs = list(cls.IDLE_QUIPS)
        if near_list:
            n, d = near_list[0]
            probs.append(f"*检查效期本* {n}还剩 {d} 天，赶紧用！")
        if low_list:
            n, s = low_list[0]
            probs.append(f"*皱眉* {n}只剩 {s} 支了，快去入库！")
        return random.choice(probs)

# -*- coding: utf-8 -*-
"""
manager.py — 库存数据管理

功能：
  - JSON 持久化（兼容旧数据自动补字段）
  - 三仓库：试剂库 / 蛋白库 / 细胞库
  - CRUD：增/查/领用/冻结
  - 检索：按名称/批次/位置模糊搜索
  - 蛋白库体积出入库：支持 "7.26+0.2" 和 "5*3" 格式
"""

import os
import json
import re
import itertools
from datetime import datetime

from desktop_pet.config import DATA_PATH, DATA_DIR, DEFAULT_REAGENTS, LOCATION_MAP


# ── 仓库类型枚举 ──────────────────────────────────────
WAREHOUSE_REAGENT = "reagent"   # 试剂库
WAREHOUSE_PROTEIN = "protein"   # 蛋白库
WAREHOUSE_CELL    = "cell"      # 细胞库

WAREHOUSE_LABELS = {
    WAREHOUSE_REAGENT: "试剂库",
    WAREHOUSE_PROTEIN: "蛋白库",
    WAREHOUSE_CELL:    "细胞库",
}


def parse_volume_str(vol_str):
    """
    解析蛋白体积字符串，返回 (总量mL, 管数)。
    格式说明：
      "7.26+0.2"   → 两管不同体积，总量=7.46mL，管数=2
      "5*3"         → 3管相同体积，总量=15mL，管数=3
      "5*3+2"       → 3管5mL + 1管2mL，总量=17mL，管数=4
      "5*3+2*2"     → 3管5mL + 2管2mL，总量=19mL，管数=5
      "7.26"        → 单管，总量=7.26mL，管数=1
    """
    if not vol_str or not str(vol_str).strip():
        return 0.0, 0
    s = str(vol_str).strip()
    # 先按 + 分割，处理混合格式
    parts = s.split('+')
    total = 0.0
    count = 0
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # 检查是否是乘法格式（A*B）
        m = re.match(r'^([\d.]+)\s*\*\s*(\d+)$', part)
        if m:
            unit_vol = float(m.group(1))
            cnt = int(m.group(2))
            total += unit_vol * cnt
            count += cnt
        else:
            try:
                v = float(part)
                total += v
                count += 1
            except ValueError:
                continue
    if count == 0:
        return 0.0, 0
    return round(total, 4), count


class ReagentManager:
    """库存管理：三仓库，字段对标 ModernWMS StockEntity"""

    _data = None

    # ── 数据加载 / 保存 ──────────────────────────────
    @classmethod
    def _load(cls):
        if cls._data is None:
            os.makedirs(DATA_DIR, exist_ok=True)
            if os.path.exists(DATA_PATH):
                try:
                    with open(DATA_PATH, "r", encoding="utf-8") as f:
                        cls._data = json.load(f)
                    changed = False
                    for r in cls._data:
                        # 容错：expire 格式不正确时自动修正
                        raw_expire = r.get("expire", "").strip()
                        if not raw_expire:
                            r["expire"] = "2099-12-31"
                            changed = True
                        else:
                            parsed = None
                            for fmt in ("%Y-%m-%d", "%Y%m%d"):
                                try:
                                    parsed = datetime.strptime(raw_expire, fmt)
                                    break
                                except ValueError:
                                    continue
                            if parsed:
                                r["expire"] = parsed.strftime("%Y-%m-%d")
                                if raw_expire != r["expire"]:
                                    changed = True
                            else:
                                r["expire"] = "2099-12-31"
                                changed = True

                        r.setdefault("price",       0.0)
                        r.setdefault("putaway_date", "")
                        r.setdefault("is_freeze",    False)
                        r.setdefault("location",     "")
                        # 仓库类型（自动推断旧数据）
                        if "warehouse_type" not in r:
                            if r.get("molecular_weight"):
                                r["warehouse_type"] = WAREHOUSE_PROTEIN
                            else:
                                r["warehouse_type"] = WAREHOUSE_REAGENT
                            changed = True
                        # 蛋白专属字段
                        r.setdefault("record_book_no",    "")
                        r.setdefault("project_no",        "")
                        r.setdefault("volume",            "")
                        r.setdefault("molecular_weight",  "")
                        r.setdefault("isoelectric_point",  "")
                        r.setdefault("extinction_coeff",   "")
                        r.setdefault("concentration",      "")
                        r.setdefault("sample_volume",      "")
                        r.setdefault("total_amount",       "")
                        r.setdefault("titer",              "")
                        r.setdefault("purity",             "")
                        r.setdefault("buffer_type",        "")
                        r.setdefault("shipping_info",      "")
                        # 试剂/细胞 新增字段
                        r.setdefault("specification",    "")   # 规格
                        r.setdefault("catalog_no",       "")   # 货号
                        r.setdefault("manufacturer",    "")   # 厂家
                        r.setdefault("notes",            "")   # 备注
                        r.setdefault("sample_volume",    "")   # 试剂按体积出入库时的体积
                        r.setdefault("stock_mode",       "quantity")  # quantity=按数量 / volume=按体积
                        # 细胞专属字段
                        r.setdefault("cell_line",        "")
                        r.setdefault("passage_no",       "")
                        r.setdefault("culture_medium",   "")
                        r.setdefault("cryo_vial_count",  0)
                        r.setdefault("viability",        "")
                        r.setdefault("mycoplasma",       "")
                    if changed:
                        cls._save()
                except Exception:
                    cls._data = [dict(r) for r in DEFAULT_REAGENTS]
            else:
                cls._data = [dict(r) for r in DEFAULT_REAGENTS]
        return cls._data

    @classmethod
    def _save(cls):
        os.makedirs(DATA_DIR, exist_ok=True)
        try:
            with open(DATA_PATH, "w", encoding="utf-8") as f:
                json.dump(cls._data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    @classmethod
    def reload(cls):
        """强制重新从磁盘加载"""
        cls._data = None
        return cls._load()

    # ── 查询 ──────────────────────────────────────────
    @classmethod
    def get_all(cls, warehouse_type=None):
        """获取全部记录，可按仓库类型筛选"""
        data = cls._load()
        if warehouse_type:
            return [r for r in data if r.get("warehouse_type", WAREHOUSE_REAGENT) == warehouse_type]
        return data

    @classmethod
    def search(cls, keyword, warehouse_type=None):
        """模糊检索：按名称/批次/位置匹配"""
        kw = keyword.strip().lower()
        if not kw:
            data = cls._load()
        else:
            data = [
                r for r in cls._load()
                if kw in r.get("name", "").lower()
                or kw in r.get("batch", "").lower()
                or kw in r.get("location", "").lower()
                or kw in r.get("project_no", "").lower()
            ]
        if warehouse_type:
            data = [r for r in data if r.get("warehouse_type", WAREHOUSE_REAGENT) == warehouse_type]
        return data

    @classmethod
    def get_near_expiry(cls, days=30, warehouse_type=None):
        today = datetime.now()
        result = []
        for r in cls.get_all(warehouse_type):
            if r["stock"] <= 0:
                continue
            try:
                remain = (datetime.strptime(r["expire"], "%Y-%m-%d") - today).days
                if 0 <= remain <= days:
                    result.append((r["name"], remain))
            except (ValueError, TypeError):
                continue
        return result

    @classmethod
    def get_low_stock(cls, warehouse_type=None):
        return [(r["name"], r["stock"]) for r in cls.get_all(warehouse_type)
                if 0 < r["stock"] <= r["threshold"]]

    @classmethod
    def check_problems(cls, warehouse_type=None):
        today = datetime.now()
        result = []
        for r in cls.get_all(warehouse_type):
            if r["stock"] == 0:
                result.append((r["name"], "无库存"))
            else:
                try:
                    if datetime.strptime(r["expire"], "%Y-%m-%d") < today:
                        result.append((r["name"], "已过期"))
                except (ValueError, TypeError):
                    pass
        return result

    @classmethod
    def get_location_info(cls, loc_code):
        return LOCATION_MAP.get(loc_code, ("未指定", ""))

    @classmethod
    def get_by_location(cls, loc_code):
        return [r for r in cls._load() if r.get("location") == loc_code]

    @classmethod
    def get_occupied_locations(cls):
        result = {}
        for r in cls._load():
            loc = r.get("location", "")
            if loc:
                result.setdefault(loc, []).append(r["name"])
        return result

    # ── 写操作 ────────────────────────────────────────
    @classmethod
    def use_reagent(cls, name, amount=1):
        """领用试剂/蛋白/细胞。蛋白库按体积领用，试剂库可选按体积或按数量。"""
        for r in cls._load():
            if r["name"] == name:
                if r.get("is_freeze"):
                    return False, 0, "已冻结"
                wh_type = r.get("warehouse_type", WAREHOUSE_REAGENT)

                if wh_type == WAREHOUSE_PROTEIN:
                    # 蛋白库：按体积领用
                    sv = r.get("sample_volume", "")
                    total_vol, tube_count = parse_volume_str(sv)
                    if total_vol <= 0:
                        return False, 0, "无可用体积"
                    try:
                        exp = datetime.strptime(r["expire"], "%Y-%m-%d")
                        remain = (exp - datetime.now()).days
                    except (ValueError, TypeError):
                        remain = 9999
                    # 扣减体积
                    new_total, remaining_parts = _deduct_volume(sv, amount)
                    if new_total < 0:
                        return False, 0, f"体积不足（剩余{total_vol}mL）"
                    r["sample_volume"] = _rebuild_volume_from_parts(remaining_parts)
                    cls._save()
                    return True, remain, "成功"
                elif wh_type == WAREHOUSE_REAGENT and r.get("stock_mode") == "volume":
                    # 试剂库按体积模式领用
                    sv = r.get("sample_volume", "")
                    total_vol, tube_count = parse_volume_str(sv)
                    if total_vol <= 0:
                        return False, 0, "无可用体积"
                    try:
                        exp = datetime.strptime(r["expire"], "%Y-%m-%d")
                        remain = (exp - datetime.now()).days
                    except (ValueError, TypeError):
                        remain = 9999
                    # 扣减体积
                    new_total, remaining_parts = _deduct_volume(sv, amount)
                    if new_total < 0:
                        return False, 0, f"体积不足（剩余{total_vol}mL）"
                    r["sample_volume"] = _rebuild_volume_from_parts(remaining_parts)
                    cls._save()
                    return True, remain, "成功"
                else:
                    # 试剂库(按数量)/细胞库：按数量领用
                    if r["stock"] <= 0:
                        return False, 0, "无库存"
                    try:
                        exp = datetime.strptime(r["expire"], "%Y-%m-%d")
                        remain = (exp - datetime.now()).days
                    except (ValueError, TypeError):
                        remain = 9999
                    if remain < 0:
                        return False, 0, "已过期"
                    r["stock"] -= amount
                    cls._save()
                    return True, remain, "成功"
        return False, 0, "未找到"

    @classmethod
    def add_reagent(cls, name, batch, expire_str, amount, price=0.0, threshold=1,
                    location="", warehouse_type=WAREHOUSE_REAGENT,
                    record_book_no="", project_no="", volume="",
                    molecular_weight="", isoelectric_point="",
                    extinction_coeff="", concentration="",
                    sample_volume="", total_amount="", titer="", purity="",
                    buffer_type="", shipping_info="",
                    # 试剂/细胞 新增字段
                    specification="", catalog_no="", manufacturer="", notes="",
                    stock_mode="quantity",
                    # 细胞专属
                    cell_line="", passage_no="", culture_medium="",
                    cryo_vial_count=0, viability="", mycoplasma=""):
        data = cls._load()
        for r in data:
            if r["name"] == name:
                # 同名合并
                wh = r.get("warehouse_type", WAREHOUSE_REAGENT)
                if wh == WAREHOUSE_PROTEIN:
                    # 蛋白库：体积累加（合并管体积列表）
                    old_sv = r.get("sample_volume", "")
                    old_tubes = _parse_to_tube_list(old_sv)
                    add_tubes = _parse_to_tube_list(sample_volume) if sample_volume else []
                    merged_tubes = old_tubes + add_tubes
                    r["sample_volume"] = _rebuild_volume_from_parts(merged_tubes)
                elif wh == WAREHOUSE_REAGENT and r.get("stock_mode") == "volume":
                    # 试剂库按体积模式：体积累加（合并管体积列表）
                    old_sv = r.get("sample_volume", "")
                    old_tubes = _parse_to_tube_list(old_sv)
                    add_tubes = _parse_to_tube_list(sample_volume) if sample_volume else []
                    merged_tubes = old_tubes + add_tubes
                    r["sample_volume"] = _rebuild_volume_from_parts(merged_tubes)
                else:
                    r["stock"] += amount
                r["putaway_date"] = datetime.now().strftime("%Y-%m-%d")
                cls._save()
                return
        # 新增（归一化体积字符串）
        norm_sv = normalize_volume_str(sample_volume) if sample_volume else sample_volume
        rec = {
            "name": name, "batch": batch, "expire": expire_str,
            "stock": amount, "threshold": threshold,
            "price": price, "putaway_date": datetime.now().strftime("%Y-%m-%d"),
            "is_freeze": False, "location": location,
            "warehouse_type": warehouse_type,
            "record_book_no": record_book_no, "project_no": project_no,
            "volume": volume, "molecular_weight": molecular_weight,
            "isoelectric_point": isoelectric_point,
            "extinction_coeff": extinction_coeff,
            "concentration": concentration, "sample_volume": norm_sv,
            "total_amount": total_amount,
            "titer": titer, "purity": purity,
            "buffer_type": buffer_type, "shipping_info": shipping_info,
            "specification": specification, "catalog_no": catalog_no,
            "manufacturer": manufacturer, "notes": notes,
            "stock_mode": stock_mode,
            "cell_line": cell_line, "passage_no": passage_no,
            "culture_medium": culture_medium,
            "cryo_vial_count": cryo_vial_count,
            "viability": viability, "mycoplasma": mycoplasma,
        }
        data.append(rec)
        cls._save()

    @classmethod
    def toggle_freeze(cls, name):
        for r in cls._load():
            if r["name"] == name:
                r["is_freeze"] = not r.get("is_freeze", False)
                cls._save()
                return r["is_freeze"]
        return False

    @classmethod
    def update_location(cls, name, location):
        for r in cls._load():
            if r["name"] == name:
                r["location"] = location
                cls._save()
                return True
        return False

    @classmethod
    def delete_reagent(cls, name):
        data = cls._load()
        for i, r in enumerate(data):
            if r["name"] == name:
                data.pop(i)
                cls._save()
                return True
        return False

    @classmethod
    def update_reagent(cls, old_name, new_name, batch, expire_str, stock,
                       threshold, price, location):
        """修改试剂基本信息"""
        data = cls._load()
        valid, err_msg = cls.validate_reagent(new_name, batch, expire_str, stock, threshold, price)
        if not valid:
            return False, err_msg
        if new_name != old_name:
            for r in data:
                if r["name"] == new_name:
                    return False, f"名称「{new_name}」已被其他试剂使用"
        for r in data:
            if r["name"] == old_name:
                r["name"] = new_name
                r["batch"] = batch
                r["expire"] = expire_str
                r["stock"] = stock
                r["threshold"] = threshold
                r["price"] = float(price)
                r["location"] = location
                cls._save()
                return True, "修改成功"
        return False, "未找到该试剂"

    @classmethod
    def update_reagent_full(cls, old_name, fields_dict):
        """用完整字段字典修改试剂"""
        data = cls._load()
        new_name = fields_dict.get("name", old_name)
        batch    = fields_dict.get("batch", "")
        expire   = fields_dict.get("expire", "2099-12-31")
        stock    = fields_dict.get("stock", 0)
        threshold = fields_dict.get("threshold", 1)
        price    = fields_dict.get("price", 0.0)

        valid, err_msg = cls.validate_reagent(
            str(new_name), str(batch), str(expire),
            int(stock), int(threshold), float(price))
        if not valid:
            return False, err_msg

        if str(new_name) != old_name:
            for r in data:
                if r["name"] == str(new_name):
                    return False, f"名称「{new_name}」已被其他试剂使用"

        for r in data:
            if r["name"] == old_name:
                r["name"]             = str(new_name)
                r["batch"]            = str(batch)
                r["expire"]           = str(expire)
                r["stock"]            = int(stock)
                r["threshold"]        = int(threshold)
                r["price"]            = float(price)
                r["location"]         = str(fields_dict.get("location", ""))
                r["warehouse_type"]   = str(fields_dict.get("warehouse_type",
                                            r.get("warehouse_type", WAREHOUSE_REAGENT)))
                r["record_book_no"]   = str(fields_dict.get("record_book_no", ""))
                r["project_no"]       = str(fields_dict.get("project_no", ""))
                r["volume"]           = str(fields_dict.get("volume", ""))
                r["molecular_weight"] = str(fields_dict.get("molecular_weight", ""))
                r["isoelectric_point"] = str(fields_dict.get("isoelectric_point", ""))
                r["extinction_coeff"] = str(fields_dict.get("extinction_coeff", ""))
                r["concentration"]    = str(fields_dict.get("concentration", ""))
                # 归一化体积字符串：7.26+7.26+7.26+0.2 → 7.26*3+0.2
                raw_sv = str(fields_dict.get("sample_volume", ""))
                r["sample_volume"]    = normalize_volume_str(raw_sv) if raw_sv else ""
                r["total_amount"]     = str(fields_dict.get("total_amount", ""))
                r["titer"]            = str(fields_dict.get("titer", ""))
                r["purity"]           = str(fields_dict.get("purity", ""))
                r["buffer_type"]      = str(fields_dict.get("buffer_type", ""))
                r["shipping_info"]    = str(fields_dict.get("shipping_info", ""))
                r["specification"]    = str(fields_dict.get("specification", ""))
                r["catalog_no"]       = str(fields_dict.get("catalog_no", ""))
                r["manufacturer"]    = str(fields_dict.get("manufacturer", ""))
                r["notes"]            = str(fields_dict.get("notes", ""))
                r["stock_mode"]       = str(fields_dict.get("stock_mode", r.get("stock_mode", "quantity")))
                r["cell_line"]        = str(fields_dict.get("cell_line", ""))
                r["passage_no"]       = str(fields_dict.get("passage_no", ""))
                r["culture_medium"]   = str(fields_dict.get("culture_medium", ""))
                r["cryo_vial_count"]  = int(fields_dict.get("cryo_vial_count", 0))
                r["viability"]        = str(fields_dict.get("viability", ""))
                r["mycoplasma"]       = str(fields_dict.get("mycoplasma", ""))
                cls._save()
                return True, "修改成功"
        return False, "未找到该试剂"

    @classmethod
    def validate_reagent(cls, name, batch, expire_str, stock, threshold, price):
        """校验入库输入"""
        if not name or not name.strip():
            return False, "名称不能为空"
        if expire_str and expire_str != "2099-12-31":
            try:
                datetime.strptime(expire_str, "%Y-%m-%d")
            except ValueError:
                return False, f"效期格式错误：「{expire_str}」，请使用 YYYY-MM-DD"
        if not isinstance(stock, int) or stock < 0:
            return False, "库存必须为非负整数"
        if not isinstance(threshold, int) or threshold < 0:
            return False, "阈值必须为非负整数"
        try:
            p = float(price)
            if p < 0:
                return False, "单价不能为负数"
        except (ValueError, TypeError):
            return False, "单价必须是数字"
        return True, ""

    @classmethod
    def import_from_list(cls, records):
        """从记录列表批量导入"""
        data = cls._load()
        existing_names = {r["name"] for r in data}
        added, merged = 0, 0

        for rec in records:
            name = rec.get("name", "").strip()
            if not name:
                continue
            # 补齐缺失字段
            rec.setdefault("batch",        "")
            rec.setdefault("expire",       "2099-12-31")
            rec.setdefault("stock",        0)
            rec.setdefault("threshold",    1)
            rec.setdefault("price",        0.0)
            rec.setdefault("putaway_date", datetime.now().strftime("%Y-%m-%d"))
            rec.setdefault("is_freeze",    False)
            rec.setdefault("location",     "")
            # 仓库类型
            if "warehouse_type" not in rec:
                if rec.get("molecular_weight"):
                    rec["warehouse_type"] = WAREHOUSE_PROTEIN
                else:
                    rec["warehouse_type"] = WAREHOUSE_REAGENT
            # 蛋白专属
            rec.setdefault("record_book_no",    "")
            rec.setdefault("project_no",        "")
            rec.setdefault("volume",            "")
            rec.setdefault("molecular_weight",  "")
            rec.setdefault("isoelectric_point",  "")
            rec.setdefault("extinction_coeff",   "")
            rec.setdefault("concentration",      "")
            rec.setdefault("sample_volume",      "")
            rec.setdefault("total_amount",       "")
            rec.setdefault("titer",              "")
            rec.setdefault("purity",             "")
            rec.setdefault("buffer_type",        "")
            rec.setdefault("shipping_info",      "")
            # 试剂/细胞 新增字段
            rec.setdefault("specification",    "")   # 规格
            rec.setdefault("catalog_no",       "")   # 货号
            rec.setdefault("manufacturer",    "")   # 厂家
            rec.setdefault("notes",            "")   # 备注
            rec.setdefault("sample_volume",    "")   # 试剂按体积出入库时的体积
            rec.setdefault("stock_mode",       "quantity")  # quantity/volume
            # 细胞专属
            rec.setdefault("cell_line",        "")
            rec.setdefault("passage_no",       "")
            rec.setdefault("culture_medium",   "")
            rec.setdefault("cryo_vial_count",  0)
            rec.setdefault("viability",        "")
            rec.setdefault("mycoplasma",       "")

            if name in existing_names:
                for r in data:
                    if r["name"] == name:
                        wh = r.get("warehouse_type", WAREHOUSE_REAGENT)
                        if wh == WAREHOUSE_PROTEIN:
                            # 蛋白库：体积累加（合并管体积列表）
                            old_sv = r.get("sample_volume", "")
                            old_tubes = _parse_to_tube_list(old_sv)
                            add_tubes = _parse_to_tube_list(rec.get("sample_volume", ""))
                            merged_tubes = old_tubes + add_tubes
                            if rec.get("sample_volume"):
                                r["sample_volume"] = _rebuild_volume_from_parts(merged_tubes)
                        elif wh == WAREHOUSE_REAGENT and r.get("stock_mode") == "volume":
                            # 试剂库按体积模式：体积累加（合并管体积列表）
                            old_sv = r.get("sample_volume", "")
                            old_tubes = _parse_to_tube_list(old_sv)
                            add_tubes = _parse_to_tube_list(rec.get("sample_volume", ""))
                            merged_tubes = old_tubes + add_tubes
                            if rec.get("sample_volume"):
                                r["sample_volume"] = _rebuild_volume_from_parts(merged_tubes)
                        else:
                            r["stock"] += rec.get("stock", 0)
                        # 覆盖所有非空新字段
                        for key in ["batch", "expire", "price", "location",
                                    "warehouse_type",
                                    "record_book_no", "project_no",
                                    "volume", "molecular_weight",
                                    "isoelectric_point", "extinction_coeff",
                                    "concentration", "sample_volume",
                                    "total_amount", "titer", "purity",
                                    "buffer_type", "shipping_info",
                                    "specification", "catalog_no",
                                    "manufacturer", "notes", "stock_mode",
                                    "cell_line", "passage_no",
                                    "culture_medium", "viability", "mycoplasma"]:
                            v = rec.get(key)
                            if v is not None and v != "":
                                if key == "price":
                                    try:
                                        r[key] = float(v)
                                    except (ValueError, TypeError):
                                        pass
                                elif key == "cryo_vial_count":
                                    try:
                                        r[key] = int(v)
                                    except (ValueError, TypeError):
                                        pass
                                elif key == "stock":
                                    pass
                                elif key == "sample_volume":
                                    # 跳过：蛋白/试剂按体积模式已通过上方合并处理
                                    pass
                                else:
                                    r[key] = v
                        if rec.get("cryo_vial_count"):
                            try:
                                r["cryo_vial_count"] = int(rec["cryo_vial_count"])
                            except (ValueError, TypeError):
                                pass
                        merged += 1
                        break
            else:
                # 新记录入库前，归一化体积字符串
                if rec.get("sample_volume"):
                    rec["sample_volume"] = normalize_volume_str(rec["sample_volume"])
                data.append(rec)
                existing_names.add(name)
                added += 1

        cls._save()
        return added, merged


def normalize_volume_str(vol_str):
    """
    归一化体积字符串，将连续重复的体积合并为 A*N 格式。
    例如：
      "7.26+7.26+7.26+0.2" → "7.26*3+0.2"
      "5+5+5+3+3"           → "5*3+3*2"
      "5*3+0.2"             → "5*3+0.2"   (已是规范格式)
      "7.26+0.2"            → "7.26+0.2"  (无重复)
      "5+5"                 → "5*2"
    """
    if not vol_str or not str(vol_str).strip():
        return vol_str
    tube_volumes = _parse_to_tube_list(vol_str)
    if not tube_volumes:
        return vol_str
    # 四舍五入避免浮点误差，用于分组判断
    rounded = [round(v, 6) for v in tube_volumes]
    groups = []
    pos = 0
    for key, grp in itertools.groupby(rounded):
        count = sum(1 for _ in grp)
        groups.append((tube_volumes[pos], count))
        pos += count
    # 重建字符串
    result_parts = []
    for val, count in groups:
        val_str = f"{val:.6g}" if val != int(val) else str(int(val))
        if count >= 2:
            result_parts.append(f"{val_str}*{count}")
        else:
            result_parts.append(val_str)
    return "+".join(result_parts)


def _parse_to_tube_list(vol_str):
    """
    将体积字符串解析成管体积列表。
    返回 [管1体积, 管2体积, ...]
    例如：
      "5*3+2"     → [5.0, 5.0, 5.0, 2.0]
      "5*3+2*2"   → [5.0, 5.0, 5.0, 2.0, 2.0]
      "7.26+0.2"   → [7.26, 0.2]
      "5*3"         → [5.0, 5.0, 5.0]
      "7.26"        → [7.26]
    """
    if not vol_str or not str(vol_str).strip():
        return []
    s = str(vol_str).strip()
    tube_volumes = []

    # 先按 + 分割
    parts = s.split('+')
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # 检查是否是乘法格式（A*B）
        m = re.match(r'^([\d.]+)\s*\*\s*(\d+)$', part)
        if m:
            unit_vol = float(m.group(1))
            cnt = int(m.group(2))
            tube_volumes.extend([unit_vol] * cnt)
        else:
            try:
                v = float(part)
                tube_volumes.append(v)
            except ValueError:
                continue
    return tube_volumes


def _deduct_volume(vol_str, deduct_amount):
    """
    从体积字符串中精确扣除出库体积。
    返回 (新总量, 剩余管体积列表)。
    支持格式：A*B, A+B, A*B+C, A*B+C*D 等。
    """
    if not vol_str or not str(vol_str).strip():
        return -1.0, []

    # 解析成管体积列表
    tube_volumes = _parse_to_tube_list(vol_str)

    if not tube_volumes:
        return 0.0, []

    total = sum(tube_volumes)
    if deduct_amount > total + 1e-6:
        return -1.0, tube_volumes  # 体积不足

    # 尝试精确匹配某管体积
    for i, v in enumerate(tube_volumes):
        if abs(v - deduct_amount) < 1e-6:
            remaining = tube_volumes[:i] + tube_volumes[i+1:]
            new_total = sum(remaining)
            return round(new_total, 6), remaining

    # 没有精确匹配，尝试从最大的管开始扣减
    sorted_indices = sorted(range(len(tube_volumes)),
                           key=lambda i: tube_volumes[i], reverse=True)
    remaining = list(tube_volumes)
    left_to_deduct = deduct_amount

    for idx in sorted_indices:
        if left_to_deduct <= 1e-10:
            break
        if remaining[idx] <= left_to_deduct + 1e-10:
            left_to_deduct -= remaining[idx]
            remaining[idx] = 0.0
        else:
            remaining[idx] = round(remaining[idx] - left_to_deduct, 6)
            left_to_deduct = 0.0

    # 移除为0的管
    remaining = [v for v in remaining if v > 1e-10]
    new_total = sum(remaining)

    if left_to_deduct > 1e-6:
        return -1.0, remaining

    return round(new_total, 6), remaining


def _rebuild_volume_from_parts(parts):
    """
    从剩余管体积列表重建体积字符串，连续相同体积自动合并为 A*N 格式。
    例：[7.26, 0.2]           → "7.26+0.2"
         [5.0, 5.0, 5.0]       → "5*3"
         [7.26, 7.26, 7.26, 0.2] → "7.26*3+0.2"
         [7.26]                → "7.26"
         []                    → "0"
    """
    if not parts:
        return "0"

    # 分组连续相同体积
    rounded = [round(v, 6) for v in parts]
    groups = []
    pos = 0
    for key, grp in itertools.groupby(rounded):
        count = sum(1 for _ in grp)
        groups.append((parts[pos], count))
        pos += count

    result_parts = []
    for val, count in groups:
        val_str = f"{val:.6g}" if val != int(val) else str(int(val))
        if count >= 2:
            result_parts.append(f"{val_str}*{count}")
        else:
            result_parts.append(val_str)
    return "+".join(result_parts)

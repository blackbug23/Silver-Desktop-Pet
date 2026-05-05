# -*- coding: utf-8 -*-
"""
pdf_import.py — PDF 智能识别录入

功能：
  - 解析 PDF 文档，自动提取并映射到仓库字段
  - 自动判断仓库类型（试剂 / 蛋白 / 细胞）
  - PDF 页面预览 + 拖拽选框提取文本
  - 缩放工具栏：滑块、按钮、鼠标滚轮
  - 模板功能：保存/套用选取位置，相似格式 PDF 自动提取
  - 拖拽/按钮触发导入流程
"""

import re
import os
import json
import pdfplumber
import pypdfium2

from PyQt5.QtCore import Qt, pyqtSignal, QSize, QRect, QPoint
from PyQt5.QtGui import QPixmap, QImage, QCursor, QIcon, QWheelEvent
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QFormLayout, QComboBox, QLabel, QScrollArea, QWidget,
    QMessageBox, QSplitter, QSpinBox, QDoubleSpinBox,
    QSizePolicy, QMenu, QAction, QRubberBand, QSlider,
    QFileDialog, QInputDialog,
)

from desktop_pet.config import ICON_PATH, LOCATION_MAP
from desktop_pet.reagents.manager import (
    ReagentManager, WAREHOUSE_REAGENT, WAREHOUSE_PROTEIN, WAREHOUSE_CELL,
    WAREHOUSE_LABELS, parse_volume_str, normalize_volume_str,
)


# ── 模板存储路径 ──────────────────────────────────────
_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "pdf_templates")


def _ensure_template_dir():
    """确保模板目录存在"""
    os.makedirs(_TEMPLATE_DIR, exist_ok=True)
    return _TEMPLATE_DIR


# ── PDF 文本提取与字段映射 ─────────────────────────────

# 已知厂家品牌名
_MANUFACTURER_PATTERNS = [
    "BioLegend", "Thermo[Fisher]?", "Abcam", "Cell Signaling",
    "R&D Systems", "Sigma[- ]Aldrich", "BD Biosciences", "BD",
    "eBioscience", "Invitrogen", "Miltenyi", "STEMCELL",
    "Santa Cruz", "Sino Biological", "Proteintech", "Novus",
    "LSBio", "GeneTex", "Watanabe", "和光", "同仁", "国药",
]

# 产品标题行关键词
_PRODUCT_NAME_KEYWORDS = [
    "Antibody", "Antibodies", "Reagent", "Protein", "Kit",
    "Serum", "Probe", "探针", "抗体", "试剂", "蛋白",
    "Medium", "培养基", "Supplement", "Buffer",
    "Conjugate", "Labeling", "Staining",
]


def auto_detect_warehouse(text):
    """
    根据 PDF 全文内容自动判断应录入哪个仓库。
    优先级：蛋白 > 细胞 > 试剂（默认）
    """
    upper = text.lower()
    # 蛋白库特征
    protein_kw = ["molecular weight", "分子量", "消光系数", "extinction coeff",
                  "等电点", "isoelectric point", "extinction coefficient",
                  "expression volume", "表达体积", "titer"]
    if any(kw in upper for kw in protein_kw):
        return WAREHOUSE_PROTEIN
    # 细胞库特征
    cell_kw = ["cell line", "细胞系", "culture medium", "培养基",
               "cryopreserv", "冻存", "passage", "代次", "mycoplasma", "支原体"]
    if any(kw in upper for kw in cell_kw):
        return WAREHOUSE_CELL
    # 默认试剂库
    return WAREHOUSE_REAGENT


def _extract_product_name(text):
    """从PDF全文中提取产品名称（通常是含关键词的标题行）"""
    lines = text.strip().split("\n")
    for line in lines[:10]:  # 只看前10行
        line = line.strip()
        if not line:
            continue
        # 跳过版本号行
        if line.lower().startswith("version:"):
            continue
        # 检查是否含产品关键词
        if any(kw.lower() in line.lower() for kw in _PRODUCT_NAME_KEYWORDS):
            return line
    # 如果没找到，取第一个非版本号非空行
    for line in lines[:5]:
        line = line.strip()
        if line and not line.lower().startswith("version:"):
            return line
    return ""


def _extract_manufacturer(text):
    """从PDF全文中识别厂家/品牌"""
    for pattern in _MANUFACTURER_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0)
    return ""


def _truncate_value(val, max_len=120):
    """截断过长值，加省略号"""
    if len(val) > max_len:
        return val[:max_len] + "…"
    return val


def parse_pdf(pdf_path):
    """
    解析 PDF 文件，提取文本并映射到仓库字段。

    返回:
        {
            "warehouse_type": "reagent"|"protein"|"cell",
            "fields": {"name": "...", "catalog_no": "...", ...},
            "full_text": "完整提取文本",
            "page_count": 页数,
        }
    """
    full_text = ""
    page_count = 0

    with pdfplumber.open(pdf_path) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"

    wh_type = auto_detect_warehouse(full_text)
    fields = {}

    # ── 通用提取（所有仓库类型都有） ──
    fields["name"] = _extract_product_name(full_text)

    # Catalog# / 货号
    m = re.search(r'Catalog[#\s]*[/\s]*Size\s+(\S+)', full_text)
    if m:
        fields["catalog_no"] = m.group(1).strip()

    # Clone
    m = re.search(r'Clone\s+(\S+)', full_text)
    if m:
        fields["clone"] = m.group(1).strip()

    # Isotype
    m = re.search(r'Isotype\s+(.+?)(?:\n|$)', full_text)
    if m:
        fields["isotype"] = m.group(1).strip()

    # 厂家
    mfg = _extract_manufacturer(full_text)
    if mfg:
        fields["manufacturer"] = mfg

    # ── 试剂库专属 ──
    if wh_type == WAREHOUSE_REAGENT:
        # Formulation → specification
        m = re.search(r'Formulation\s+(.+?)(?:\n[A-Z][a-z])', full_text, re.DOTALL)
        if m:
            fields["specification"] = _truncate_value(m.group(1).strip().replace("\n", " "))

        # Size → specification 追加
        m = re.search(r'Catalog[#\s]*[/\s]*Size\s+\S+\s*/\s*(.+)', full_text)
        if m and "specification" not in fields:
            fields["specification"] = m.group(1).strip()

        # Application
        m = re.search(r'Application\s+(.+?)(?:\n|$)', full_text)
        if m:
            fields["application"] = m.group(1).strip()

        # Storage
        m = re.search(r'Storage\s*&?\s*Handling\s+(.+?)(?:\n[A-Z][a-z])', full_text, re.DOTALL)
        if m:
            storage_text = m.group(1).strip().replace("\n", " ")
            fields["storage"] = _truncate_value(storage_text)

        # 拼接 notes
        notes_parts = []
        if "clone" in fields:
            notes_parts.append(f"Clone: {fields['clone']}")
        if "isotype" in fields:
            notes_parts.append(f"Isotype: {fields['isotype']}")
        if "application" in fields:
            notes_parts.append(f"Application: {fields['application']}")
        if "storage" in fields:
            notes_parts.append(f"Storage: {fields['storage']}")
        if notes_parts:
            fields["notes"] = "; ".join(notes_parts)

        # 清理中间字段（只保留最终字段）
        for k in ["clone", "isotype", "application", "storage"]:
            fields.pop(k, None)

    # ── 蛋白库专属 ──
    elif wh_type == WAREHOUSE_PROTEIN:
        # Concentration
        m = re.search(r'Concentration\s+(.+?)(?:\n|$)', full_text)
        if m:
            val = m.group(1).strip()
            # 去单位
            val = re.sub(r'\s*(mg/?m[lL]|m[gL]|m[lL])\s*$', '', val)
            fields["concentration"] = _truncate_value(val)

        # Purity
        m = re.search(r'Purity\s+(.+?)(?:\n|$)', full_text)
        if m:
            fields["purity"] = m.group(1).strip()

        # Buffer / Formulation
        m = re.search(r'(?:Buffer|Formulation)\s+(.+?)(?:\n[A-Z][a-z])', full_text, re.DOTALL)
        if m:
            fields["buffer_type"] = _truncate_value(m.group(1).strip().replace("\n", " "))

        # Molecular Weight
        m = re.search(r'Molecular\s+Weight[:\s]+(\S+)', full_text, re.IGNORECASE)
        if m:
            fields["molecular_weight"] = m.group(1).strip()

        # Isoelectric Point / pI
        m = re.search(r'(?:Isoelectric\s+Point|pI)[:\s]+(\S+)', full_text, re.IGNORECASE)
        if m:
            fields["isoelectric_point"] = m.group(1).strip()

        # Extinction Coefficient
        m = re.search(r'Extinction\s+(?:Coefficient|Coeff)[:\s]+(\S+)', full_text, re.IGNORECASE)
        if m:
            fields["extinction_coeff"] = m.group(1).strip()

    # ── 细胞库专属 ──
    elif wh_type == WAREHOUSE_CELL:
        # Cell Line / Reactivity
        m = re.search(r'(?:Cell\s+Line|Reactivity)\s+(.+?)(?:\n|$)', full_text)
        if m:
            fields["cell_line"] = m.group(1).strip()

        # Culture Medium
        m = re.search(r'Culture\s+Medium\s+(.+?)(?:\n|$)', full_text, re.IGNORECASE)
        if m:
            fields["culture_medium"] = m.group(1).strip()

        # Passage
        m = re.search(r'Passage[:\s]+(\S+)', full_text, re.IGNORECASE)
        if m:
            fields["passage_no"] = m.group(1).strip()

    return {
        "warehouse_type": wh_type,
        "fields": fields,
        "full_text": full_text,
        "page_count": page_count,
    }


def extract_text_from_pdf_rect(pdf_path, page_idx, x0, y0, x1, y1):
    """
    直接从 pdfplumber 坐标矩形区域提取文本。

    ⚠️ 坐标系说明（重要）：
    pdfplumber 的坐标系与屏幕/QLabel 完全一致：
      - 原点在左上角
      - Y 轴向下（越往下 y 越大）
    因此调用方不需要做任何 Y 轴翻转，直接传比例换算后的坐标即可。

    参数:
        pdf_path: PDF 文件路径
        page_idx: 页码（0-based）
        x0, y0: 矩形左上角（pdfplumber 点坐标）
        x1, y1: 矩形右下角（pdfplumber 点坐标）
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if page_idx >= len(pdf.pages):
                return ""
            page = pdf.pages[page_idx]
            # 确保在页面范围内
            x0 = max(0.0, min(float(x0), page.width))
            y0 = max(0.0, min(float(y0), page.height))
            x1 = max(0.0, min(float(x1), page.width))
            y1 = max(0.0, min(float(y1), page.height))
            if x1 <= x0 or y1 <= y0:
                return ""
            cropped = page.crop((x0, y0, x1, y1))
            text = cropped.extract_text()
            return text.strip() if text else ""
    except Exception:
        return ""


def extract_text_from_rect(pdf_path, page_idx, img_rect, img_size, page_size):
    """
    从 QLabel 上的选取矩形（像素坐标）转换为 pdfplumber 坐标，
    并提取矩形内文本。

    ⚠️ 坐标系说明（重要）：
    pdfplumber 坐标系与 QLabel 像素坐标系完全一致（左上角原点，Y 向下），
    因此只需做简单的比例缩放，不需要任何 Y 轴翻转。

    参数:
        pdf_path: PDF 文件路径
        page_idx: 页码索引（0-based）
        img_rect: QRect，选取矩形（相对于当前显示 pixmap 的像素坐标）
        img_size: (width, height) 当前显示 pixmap 的像素尺寸
        page_size: (width, height) PDF 页面尺寸（pdfplumber 点单位）
    """
    img_w, img_h = img_size
    page_w, page_h = page_size

    if img_w == 0 or img_h == 0:
        return ""

    # X/Y 方向：直接等比例映射（两套坐标系方向完全一致，无需翻转）
    scale_x = page_w / img_w
    scale_y = page_h / img_h

    pdf_x0 = img_rect.x() * scale_x
    pdf_y0 = img_rect.y() * scale_y
    pdf_x1 = (img_rect.x() + img_rect.width()) * scale_x
    pdf_y1 = (img_rect.y() + img_rect.height()) * scale_y

    return extract_text_from_pdf_rect(
        pdf_path, page_idx, pdf_x0, pdf_y0, pdf_x1, pdf_y1
    )


def extract_text_from_pdf_rect_normalized(pdf_path, page_idx, norm_rect):
    """
    从归一化矩形 (0~1 比例坐标) 提取 PDF 文本。
    模板存储用归一化坐标，不受缩放影响。

    参数:
        norm_rect: (x0, y0, x1, y1) 归一化坐标 (0~1)
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if page_idx >= len(pdf.pages):
                return ""
            page = pdf.pages[page_idx]
            page_w, page_h = page.width, page.height
            x0 = norm_rect[0] * page_w
            y0 = norm_rect[1] * page_h
            x1 = norm_rect[2] * page_w
            y1 = norm_rect[3] * page_h
            cropped = page.crop((x0, y0, x1, y1))
            text = cropped.extract_text()
            return text.strip() if text else ""
    except Exception:
        return ""


# ── 模板管理 ──────────────────────────────────────

def save_template(name, warehouse_type, field_rects):
    """
    保存模板到 JSON 文件。

    参数:
        name: 模板名称
        warehouse_type: 仓库类型
        field_rects: {field_key: {"page": int, "rect": (x0, y0, x1, y1)}}
                     rect 为归一化坐标 (0~1)
    """
    tpl_dir = _ensure_template_dir()
    # 安全文件名
    safe_name = re.sub(r'[^\w\u4e00-\u9fff\-]', '_', name)
    filepath = os.path.join(tpl_dir, f"{safe_name}.json")
    data = {
        "name": name,
        "warehouse_type": warehouse_type,
        "field_rects": field_rects,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return filepath


def load_template(filepath):
    """加载模板 JSON 文件"""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def list_templates():
    """列出所有可用模板"""
    tpl_dir = _ensure_template_dir()
    templates = []
    for fname in os.listdir(tpl_dir):
        if fname.endswith(".json"):
            try:
                data = load_template(os.path.join(tpl_dir, fname))
                templates.append({
                    "name": data.get("name", fname),
                    "file": fname,
                    "warehouse_type": data.get("warehouse_type", ""),
                    "field_rects": data.get("field_rects", {}),
                })
            except Exception:
                pass
    return templates


def delete_template(filepath):
    """删除模板文件"""
    if os.path.exists(filepath):
        os.remove(filepath)


# ── PDF 预览组件 ─────────────────────────────────────────

class PDFPreviewWidget(QLabel):
    """可拖拽选框的 PDF 预览组件，支持缩放"""

    region_selected = pyqtSignal(int, int, int, int, int)  # (page_idx, x, y, w, h) 像素坐标
    zoom_changed = pyqtSignal(float)  # 缩放因子变化信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pdf_path = None
        self._pdf_doc = None
        self._page_idx = 0
        self._page_count = 0
        self._render_scale = 2  # 渲染倍率
        self._pixmap = None
        self._page_width = 0   # PDF页面宽度（点）
        self._page_height = 0 # PDF页面高度（点）

        # 拖拽选框相关
        self._rubber_band = None
        self._drag_start = None
        self._is_dragging = False

        # 缩放相关
        self._zoom_factor = 1.0   # 当前缩放因子（相对于原始渲染图）
        self._min_zoom = 0.25
        self._max_zoom = 5.0

        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setMinimumWidth(200)
        self.setCursor(QCursor(Qt.CrossCursor))
        self.setStyleSheet("background-color: #e8e8e8; border: 1px solid #ccc;")
        self.setText("请打开 PDF 文件")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def load_pdf(self, pdf_path):
        """加载 PDF 文件"""
        self._pdf_path = pdf_path
        try:
            self._pdf_doc = pypdfium2.PdfDocument(pdf_path)
            self._page_count = len(self._pdf_doc)
            self._page_idx = 0
            self._render_page()
        except Exception as e:
            self.setText(f"无法加载 PDF：{e}")

    def _render_page(self):
        """渲染当前页为 QPixmap"""
        if not self._pdf_doc:
            return
        try:
            page = self._pdf_doc[self._page_idx]
            # 获取页面尺寸（PDF点）
            self._page_width = page.get_width()
            self._page_height = page.get_height()
            # 渲染
            bitmap = page.render(scale=self._render_scale)
            pil_img = bitmap.to_pil()
            # PIL Image → QPixmap
            if pil_img.mode == "RGBA":
                data = pil_img.tobytes("raw", "RGBA")
                qimg = QImage(data, pil_img.width, pil_img.height,
                              QImage.Format_RGBA8888)
            else:
                data = pil_img.tobytes("raw", "RGB")
                qimg = QImage(data, pil_img.width, pil_img.height,
                              QImage.Format_RGB888)
            self._pixmap = QPixmap.fromImage(qimg)
            # 根据缩放因子更新显示
            self._update_pixmap()
        except Exception as e:
            self.setText(f"渲染页面出错：{e}")

    def _update_pixmap(self):
        """根据当前缩放因子 _zoom_factor 更新显示的 pixmap"""
        if not self._pixmap:
            return
        if abs(self._zoom_factor - 1.0) < 0.01:
            scaled = self._pixmap
        else:
            new_w = int(self._pixmap.width() * self._zoom_factor)
            new_h = int(self._pixmap.height() * self._zoom_factor)
            scaled = self._pixmap.scaled(
                new_w, new_h,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
        self.setPixmap(scaled)
        # 更新 QLabel 大小以匹配 pixmap，让 QScrollArea 可以滚动
        self.resize(scaled.size())

    # ── 缩放方法 ──

    def set_zoom(self, factor):
        """设置缩放因子"""
        factor = max(self._min_zoom, min(self._max_zoom, factor))
        if abs(factor - self._zoom_factor) < 0.01:
            return
        self._zoom_factor = factor
        self._update_pixmap()
        self.zoom_changed.emit(factor)

    def zoom_in(self):
        """放大"""
        self.set_zoom(self._zoom_factor * 1.25)

    def zoom_out(self):
        """缩小"""
        self.set_zoom(self._zoom_factor / 1.25)

    def zoom_fit_width(self, viewport_width):
        """适合宽度"""
        if not self._pixmap:
            return
        # 减去边距
        available = viewport_width - 20
        if available <= 0:
            return
        factor = available / self._pixmap.width()
        self.set_zoom(factor)

    def zoom_fit_page(self, viewport_width, viewport_height):
        """适合整页"""
        if not self._pixmap:
            return
        available_w = viewport_width - 20
        available_h = viewport_height - 20
        if available_w <= 0 or available_h <= 0:
            return
        factor_w = available_w / self._pixmap.width()
        factor_h = available_h / self._pixmap.height()
        self.set_zoom(min(factor_w, factor_h))

    def zoom_reset(self):
        """重置为 100%"""
        self.set_zoom(1.0)

    @property
    def zoom_factor(self):
        return self._zoom_factor

    def wheelEvent(self, event):
        """鼠标滚轮缩放"""
        if event.modifiers() & Qt.ControlModifier:
            # Ctrl + 滚轮：缩放
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
        else:
            # 普通滚轮：交给 QScrollArea 滚动
            super().wheelEvent(event)

    # ── 鼠标事件：拖拽选框 ──

    def mousePressEvent(self, event):
        """左键拖拽开始 → 显示 rubber band"""
        if event.button() == Qt.LeftButton and self._pixmap and self._pdf_path:
            self._drag_start = event.pos()
            self._is_dragging = True
            if not self._rubber_band:
                self._rubber_band = QRubberBand(QRubberBand.Rectangle, self)
            self._rubber_band.setGeometry(QRect(self._drag_start, QSize()))
            self._rubber_band.show()
            event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """拖拽过程中更新 rubber band 几何"""
        if self._is_dragging and self._rubber_band:
            rect = QRect(self._drag_start, event.pos()).normalized()
            self._rubber_band.setGeometry(rect)
            event.accept()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """拖拽结束 → 发射 region_selected 信号"""
        if event.button() == Qt.LeftButton and self._is_dragging:
            self._is_dragging = False
            if self._rubber_band:
                self._rubber_band.hide()
            rect = QRect(self._drag_start, event.pos()).normalized()
            if rect.width() >= 5 and rect.height() >= 5:
                self.region_selected.emit(
                    self._page_idx,
                    rect.x(), rect.y(), rect.width(), rect.height()
                )
            event.accept()
        super().mouseReleaseEvent(event)

    # ── 公开接口 ──

    def page_index(self):
        return self._page_idx

    def page_count(self):
        return self._page_count

    def get_page_size(self):
        """返回 (page_width, page_height) PDF点"""
        return self._page_width, self._page_height

    def get_rendered_size(self):
        """返回当前显示的 pixmap 尺寸（缩放后的）"""
        pm = self.pixmap()
        if pm:
            return pm.width(), pm.height()
        return 0, 0

    def get_original_rendered_size(self):
        """返回原始渲染图尺寸（缩放前），用于坐标转换"""
        if self._pixmap:
            return self._pixmap.width(), self._pixmap.height()
        return 0, 0

    def next_page(self):
        if self._page_idx < self._page_count - 1:
            self._page_idx += 1
            self._render_page()
            return True
        return False

    def prev_page(self):
        if self._page_idx > 0:
            self._page_idx -= 1
            self._render_page()
            return True
        return False

    def cleanup(self):
        """释放资源"""
        if self._pdf_doc:
            self._pdf_doc.close()
            self._pdf_doc = None


# ── 各仓库类型的字段定义（用于动态表单） ──────────────────

# 格式：(字段名, 显示标签, 默认值, tooltip)
REAGENT_FORM_FIELDS = [
    ("name",          "名称",       "",  "试剂名称（必填）"),
    ("batch",         "批号",       "",  ""),
    ("expire",        "效期",       "2099-12-31", "格式：YYYY-MM-DD"),
    ("stock",         "库存",       "1", "数量"),
    ("threshold",     "阈值",       "1", "低库存报警阈值"),
    ("price",         "单价(¥)",    "0", ""),
    ("sample_volume", "体积(mL)",   "",  "按体积模式：7.26+0.2 或 5*3"),
    ("specification", "规格",       "",  "如：500U/管、100mL/瓶"),
    ("catalog_no",    "货号",       "",  ""),
    ("manufacturer",  "厂家",       "",  ""),
    ("notes",         "备注",       "",  "自动提取的信息会填充在此"),
    ("location",      "存放位置",   "",  "位置代码"),
]

PROTEIN_FORM_FIELDS = [
    ("name",             "蛋白名",      "",  "必填"),
    ("project_no",       "项目号",      "",  ""),
    ("molecular_weight", "分子量(kD)",   "",  ""),
    ("isoelectric_point","等电点",      "",  ""),
    ("extinction_coeff", "消光系数",    "",  ""),
    ("concentration",    "浓度(mg/mL)", "",  ""),
    ("sample_volume",    "体积(mL)",    "",  "7.26+0.2 或 5*3"),
    ("total_amount",     "总量(mg)",    "",  ""),
    ("batch",            "批号",        "",  ""),
    ("purity",           "纯度",        "",  ""),
    ("buffer_type",      "Buffer",      "",  ""),
    ("specification",    "规格",        "",  ""),
    ("catalog_no",       "货号",        "",  ""),
    ("manufacturer",     "厂家",        "",  ""),
    ("notes",            "备注",        "",  ""),
    ("expire",           "效期",        "2099-12-31", ""),
    ("location",         "存放位置",    "",  ""),
]

CELL_FORM_FIELDS = [
    ("name",           "名称",       "",  "必填"),
    ("cell_line",      "细胞系",     "",  ""),
    ("passage_no",     "代次",       "",  ""),
    ("culture_medium", "培养基",     "",  ""),
    ("stock",          "冻存管数",   "1",  ""),
    ("viability",      "存活率",     "",  "如：95%"),
    ("mycoplasma",     "支原体",     "未检测", ""),
    ("batch",          "批号",       "",  ""),
    ("specification",  "规格",       "",  ""),
    ("catalog_no",     "货号",       "",  ""),
    ("manufacturer",   "厂家",       "",  ""),
    ("notes",          "备注",       "",  ""),
    ("expire",         "效期",       "2099-12-31", ""),
    ("location",       "存放位置",   "",  ""),
]

# 仓库类型 → 字段列表
WAREHOUSE_FIELDS = {
    WAREHOUSE_REAGENT: REAGENT_FORM_FIELDS,
    WAREHOUSE_PROTEIN: PROTEIN_FORM_FIELDS,
    WAREHOUSE_CELL:    CELL_FORM_FIELDS,
}

# 仓库类型 → 可点选映射的字段列表（用于点选时下拉菜单）
WAREHOUSE_CLICKABLE_FIELDS = {
    WAREHOUSE_REAGENT: [
        ("name", "名称"), ("catalog_no", "货号"), ("specification", "规格"),
        ("manufacturer", "厂家"), ("notes", "备注"), ("batch", "批号"),
        ("sample_volume", "体积(mL)"), ("price", "单价"),
    ],
    WAREHOUSE_PROTEIN: [
        ("name", "蛋白名"), ("catalog_no", "货号"), ("concentration", "浓度"),
        ("molecular_weight", "分子量"), ("isoelectric_point", "等电点"),
        ("extinction_coeff", "消光系数"), ("purity", "纯度"),
        ("buffer_type", "Buffer"), ("batch", "批号"),
        ("sample_volume", "体积(mL)"), ("notes", "备注"),
    ],
    WAREHOUSE_CELL: [
        ("name", "名称"), ("catalog_no", "货号"), ("cell_line", "细胞系"),
        ("culture_medium", "培养基"), ("passage_no", "代次"),
        ("batch", "批号"), ("notes", "备注"),
    ],
}


# ── PDF 导入主对话框 ─────────────────────────────────────

class PDFImportDialog(QDialog):
    """PDF 智能识别录入对话框 — 左右分栏布局，含缩放工具栏和模板功能"""

    def __init__(self, pdf_path, parent=None):
        super().__init__(parent)
        self._pdf_path = pdf_path
        self._parse_result = None
        self._edits = {}  # 字段名 → QLineEdit/QComboBox/QSpinBox
        self._field_rects = {}  # 字段名 → {"page": int, "rect": (x0,y0,x1,y1)} 归一化坐标（模板用）

        self.setWindowTitle("📄 PDF 智能识别录入")
        self.setWindowIcon(QIcon(ICON_PATH))
        self.setMinimumSize(1050, 720)
        self.resize(1200, 800)

        # 先解析 PDF
        self._parse_result = parse_pdf(pdf_path)

        self._build_ui()
        self._fill_auto_extracted()

    def _build_ui(self):
        """构建左右分栏UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # ── 顶部：仓库类型选择 ──
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("仓库类型："))
        self._wh_combo = QComboBox()
        self._wh_combo.addItem(f"🧪 {WAREHOUSE_LABELS[WAREHOUSE_REAGENT]}", WAREHOUSE_REAGENT)
        self._wh_combo.addItem(f"🧬 {WAREHOUSE_LABELS[WAREHOUSE_PROTEIN]}", WAREHOUSE_PROTEIN)
        self._wh_combo.addItem(f"🧫 {WAREHOUSE_LABELS[WAREHOUSE_CELL]}", WAREHOUSE_CELL)
        # 设置自动判断的仓库类型
        detected = self._parse_result["warehouse_type"]
        for i in range(self._wh_combo.count()):
            if self._wh_combo.itemData(i) == detected:
                self._wh_combo.setCurrentIndex(i)
                break
        self._wh_combo.currentIndexChanged.connect(self._on_warehouse_changed)
        top_bar.addWidget(self._wh_combo)

        # 自动检测提示
        detected_label = WAREHOUSE_LABELS.get(detected, detected)
        top_bar.addWidget(QLabel(f"  (自动识别：{detected_label})"))
        top_bar.addStretch()

        # 文件名
        fname = os.path.basename(self._pdf_path)
        top_bar.addWidget(QLabel(f"📄 {fname}"))
        main_layout.addLayout(top_bar)

        # ── 分栏：左 PDF 预览 + 右表单 ──
        splitter = QSplitter(Qt.Horizontal)

        # ══════════════════════════════════════════════════
        # 左侧：PDF 预览区（含缩放工具栏 + 滚动区域）
        # ══════════════════════════════════════════════════
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        # ── 缩放工具栏 ──
        zoom_bar = QHBoxLayout()
        zoom_bar.setSpacing(4)

        # 缩小按钮
        self._zoom_out_btn = QPushButton("➖")
        self._zoom_out_btn.setFixedSize(28, 28)
        self._zoom_out_btn.setToolTip("缩小 (Ctrl+-)")
        self._zoom_out_btn.clicked.connect(lambda: self._preview.zoom_out())
        zoom_bar.addWidget(self._zoom_out_btn)

        # 缩放滑块
        self._zoom_slider = QSlider(Qt.Horizontal)
        self._zoom_slider.setRange(25, 500)  # 25% ~ 500%
        self._zoom_slider.setValue(100)
        self._zoom_slider.setFixedWidth(140)
        self._zoom_slider.setToolTip("缩放比例")
        self._zoom_slider.valueChanged.connect(self._on_zoom_slider_changed)
        zoom_bar.addWidget(self._zoom_slider)

        # 放大按钮
        self._zoom_in_btn = QPushButton("➕")
        self._zoom_in_btn.setFixedSize(28, 28)
        self._zoom_in_btn.setToolTip("放大 (Ctrl++)")
        self._zoom_in_btn.clicked.connect(lambda: self._preview.zoom_in())
        zoom_bar.addWidget(self._zoom_in_btn)

        # 缩放百分比标签
        self._zoom_label = QLabel("100%")
        self._zoom_label.setFixedWidth(48)
        self._zoom_label.setAlignment(Qt.AlignCenter)
        self._zoom_label.setStyleSheet("font-size: 12px; font-weight: bold;")
        zoom_bar.addWidget(self._zoom_label)

        zoom_bar.addSpacing(8)

        # 适合宽度按钮
        fit_w_btn = QPushButton("↔ 适合宽度")
        fit_w_btn.setToolTip("缩放至适合预览区宽度")
        fit_w_btn.clicked.connect(self._zoom_fit_width)
        zoom_bar.addWidget(fit_w_btn)

        # 适合页面按钮
        fit_p_btn = QPushButton("📐 适合页面")
        fit_p_btn.setToolTip("缩放至整页可见")
        fit_p_btn.clicked.connect(self._zoom_fit_page)
        zoom_bar.addWidget(fit_p_btn)

        # 重置按钮
        reset_btn = QPushButton("1:1")
        reset_btn.setToolTip("重置为原始大小")
        reset_btn.clicked.connect(lambda: self._preview.zoom_reset())
        zoom_bar.addWidget(reset_btn)

        zoom_bar.addStretch()

        # 提示
        hint_label = QLabel("💡 拖拽选区提取文字 | Ctrl+滚轮缩放")
        hint_label.setStyleSheet("color: #888; font-size: 11px;")
        zoom_bar.addWidget(hint_label)

        left_layout.addLayout(zoom_bar)

        # ── PDF 预览区（QScrollArea 包裹） ──
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(False)  # 手动控制 QLabel 大小
        self._scroll_area.setStyleSheet("QScrollArea { background-color: #e8e8e8; border: 1px solid #ccc; }")

        self._preview = PDFPreviewWidget()
        self._preview.load_pdf(self._pdf_path)
        self._preview.region_selected.connect(self._on_region_selected)
        self._preview.zoom_changed.connect(self._on_zoom_changed)

        self._scroll_area.setWidget(self._preview)
        left_layout.addWidget(self._scroll_area, 1)

        # ── 翻页控制 ──
        page_bar = QHBoxLayout()
        self._prev_btn = QPushButton("◀ 上一页")
        self._prev_btn.clicked.connect(self._prev_page)
        self._page_label = QLabel(f"1 / {self._preview.page_count()}")
        self._page_label.setAlignment(Qt.AlignCenter)
        self._next_btn = QPushButton("下一页 ▶")
        self._next_btn.clicked.connect(self._next_page)
        page_bar.addWidget(self._prev_btn)
        page_bar.addStretch()
        page_bar.addWidget(self._page_label)
        page_bar.addStretch()
        page_bar.addWidget(self._next_btn)
        left_layout.addLayout(page_bar)

        splitter.addWidget(left_widget)

        # ══════════════════════════════════════════════════
        # 右侧：入库表单 + 模板工具栏
        # ══════════════════════════════════════════════════
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 0, 4, 0)
        right_layout.setSpacing(4)

        # 提示标签
        hint = QLabel("📋 自动提取结果已预填，可手动修改\n   拖拽左侧 PDF 区域可补充提取")
        hint.setStyleSheet("color: #666; font-size: 12px; padding: 4px;")
        right_layout.addWidget(hint)

        # ── 模板工具栏 ──
        tpl_bar = QHBoxLayout()
        tpl_bar.setSpacing(4)

        save_tpl_btn = QPushButton("💾 保存模板")
        save_tpl_btn.setToolTip("将当前字段选取位置保存为模板，下次可套用")
        save_tpl_btn.setStyleSheet(
            "QPushButton { font-size: 12px; padding: 3px 10px; "
            "background: #2196F3; color: white; border-radius: 3px; }"
            "QPushButton:hover { background: #1976D2; }")
        save_tpl_btn.clicked.connect(self._save_template)
        tpl_bar.addWidget(save_tpl_btn)

        load_tpl_btn = QPushButton("📂 套用模板")
        load_tpl_btn.setToolTip("套用已有模板，自动提取各字段")
        load_tpl_btn.setStyleSheet(
            "QPushButton { font-size: 12px; padding: 3px 10px; "
            "background: #FF9800; color: white; border-radius: 3px; }"
            "QPushButton:hover { background: #F57C00; }")
        load_tpl_btn.clicked.connect(self._load_template)
        tpl_bar.addWidget(load_tpl_btn)

        manage_tpl_btn = QPushButton("🗂 管理模板")
        manage_tpl_btn.setToolTip("查看和删除已保存的模板")
        manage_tpl_btn.setStyleSheet(
            "QPushButton { font-size: 12px; padding: 3px 10px; }")
        manage_tpl_btn.clicked.connect(self._manage_templates)
        tpl_bar.addWidget(manage_tpl_btn)

        tpl_bar.addStretch()
        right_layout.addLayout(tpl_bar)

        # 表单滚动区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        self._form_widget = QWidget()
        self._form = QFormLayout(self._form_widget)
        self._form.setLabelAlignment(Qt.AlignRight)

        scroll.setWidget(self._form_widget)
        right_layout.addWidget(scroll, 1)

        # 按钮
        btn_row = QHBoxLayout()
        ok_btn = QPushButton("✅ 确认入库")
        ok_btn.setStyleSheet(
            "font-family:'Microsoft YaHei';font-size:14px;padding:6px 24px;"
            "background:#4CAF50;color:white;border-radius:4px;")
        ok_btn.clicked.connect(self._confirm_import)
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet(
            "font-family:'Microsoft YaHei';font-size:14px;padding:6px 24px;")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        right_layout.addLayout(btn_row)

        splitter.addWidget(right_widget)

        # 分栏比例：左60% 右40%
        splitter.setSizes([700, 450])
        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 4)

        main_layout.addWidget(splitter, 1)

        # 初始缩放：适合宽度
        QTimer_singleShot = False
        # 延迟一帧，等 QScrollArea 有了实际大小再 fit
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(100, self._zoom_fit_width)

    # ── 缩放相关 ──

    def _on_zoom_slider_changed(self, value):
        """滑块值变化 → 更新缩放"""
        factor = value / 100.0
        self._preview.set_zoom(factor)

    def _on_zoom_changed(self, factor):
        """缩放因子变化 → 更新滑块和标签"""
        slider_val = int(factor * 100)
        self._zoom_slider.blockSignals(True)
        self._zoom_slider.setValue(slider_val)
        self._zoom_slider.blockSignals(False)
        self._zoom_label.setText(f"{slider_val}%")

    def _zoom_fit_width(self):
        """适合宽度"""
        self._preview.zoom_fit_width(self._scroll_area.viewport().width())

    def _zoom_fit_page(self):
        """适合页面"""
        self._preview.zoom_fit_page(
            self._scroll_area.viewport().width(),
            self._scroll_area.viewport().height()
        )

    # ── 翻页 ──

    def _prev_page(self):
        if self._preview.prev_page():
            self._update_page_label()

    def _next_page(self):
        if self._preview.next_page():
            self._update_page_label()

    def _update_page_label(self):
        self._page_label.setText(
            f"{self._preview.page_index() + 1} / {self._preview.page_count()}")

    # ── 表单相关 ──

    def _build_form_fields(self, wh_type):
        """根据仓库类型动态构建表单字段"""
        # 清空旧字段
        while self._form.rowCount() > 0:
            self._form.removeRow(0)
        self._edits.clear()

        fields = WAREHOUSE_FIELDS.get(wh_type, REAGENT_FORM_FIELDS)

        # 存放位置选项
        loc_codes = [""] + list(LOCATION_MAP.keys())
        loc_labels = ["不指定"] + [
            f"{k} - {v[0]} {v[1]}" for k, v in LOCATION_MAP.items()
        ]

        for field_name, label, default, tooltip in fields:
            if field_name == "location":
                combo = QComboBox()
                combo.addItems(loc_labels)
                self._edits[field_name] = combo
                self._form.addRow(f"{label}：", combo)
            elif field_name == "mycoplasma":
                combo = QComboBox()
                combo.addItems(["未检测", "阴性", "阳性"])
                self._edits[field_name] = combo
                self._form.addRow(f"{label}：", combo)
            elif field_name in ("stock", "threshold"):
                spin = QSpinBox()
                spin.setRange(0, 999999)
                spin.setValue(int(default) if default.isdigit() else 1)
                self._edits[field_name] = spin
                self._form.addRow(f"{label}：", spin)
            else:
                edit = QLineEdit(default)
                if tooltip:
                    edit.setToolTip(tooltip)
                self._edits[field_name] = edit
                # 必填字段标红
                if field_name == "name":
                    edit.setStyleSheet("border: 2px solid #f44336; padding: 3px;")
                self._form.addRow(f"{label}：", edit)

    def _fill_auto_extracted(self):
        """将自动提取的结果预填到表单中"""
        wh_type = self._parse_result["warehouse_type"]
        self._build_form_fields(wh_type)

        fields = self._parse_result.get("fields", {})
        for field_name, value in fields.items():
            if field_name in self._edits:
                widget = self._edits[field_name]
                if isinstance(widget, QComboBox):
                    idx = widget.findText(value)
                    if idx >= 0:
                        widget.setCurrentIndex(idx)
                elif isinstance(widget, QLineEdit):
                    widget.setText(value)

    def _on_warehouse_changed(self, idx):
        """仓库类型切换时重建表单"""
        wh_type = self._wh_combo.currentData()
        self._build_form_fields(wh_type)
        # 重新填入已提取的数据
        fields = self._parse_result.get("fields", {})
        for field_name, value in fields.items():
            if field_name in self._edits:
                widget = self._edits[field_name]
                if isinstance(widget, QLineEdit):
                    widget.setText(value)

    # ── 区域选取 → 文本提取 → 字段映射 ──

    def _on_region_selected(self, page_idx, x, y, w, h):
        """PDF 预览区域被拖拽选取 → 提取矩形内文本 → 弹出映射菜单"""
        page_w, page_h = self._preview.get_page_size()
        img_w, img_h = self._preview.get_rendered_size()

        if page_w == 0 or page_h == 0:
            return

        # 构造选取矩形
        rect = QRect(x, y, w, h)

        # 提取矩形区域内的文本
        text = extract_text_from_rect(
            self._pdf_path, page_idx, rect, (img_w, img_h), (page_w, page_h)
        )

        if not text:
            QMessageBox.information(self, "提示", "未提取到文本，请尝试重新选取。")
            return

        # 记录归一化坐标（用于模板保存）
        # 把像素坐标转为归一化坐标 (0~1)
        # 注意：rect 的坐标是缩放后的像素坐标，所以要用缩放后的尺寸归一化
        norm_rect = (
            rect.x() / img_w,
            rect.y() / img_h,
            (rect.x() + rect.width()) / img_w,
            (rect.y() + rect.height()) / img_h,
        )
        self._current_selection = {"page": page_idx, "rect": norm_rect}

        # 弹出映射菜单（在鼠标位置）
        self._show_mapping_menu(text, QCursor.pos())

    def _show_mapping_menu(self, text, global_pos):
        """弹出字段映射右键菜单"""
        wh_type = self._wh_combo.currentData()
        clickable = WAREHOUSE_CLICKABLE_FIELDS.get(wh_type, [])

        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { font-family: 'Microsoft YaHei'; font-size: 13px; }"
            "QMenu::item { padding: 6px 20px; }")

        # 显示提取到的文本（标题）
        preview = text[:80] + ("…" if len(text) > 80 else "")
        title_action = menu.addAction(f"📝 提取文本：{preview}")
        title_action.setEnabled(False)
        menu.addSeparator()

        # 字段映射选项
        for field_key, field_label in clickable:
            action = menu.addAction(f"→ 填入「{field_label}」")
            action.setData((field_key, text))
            action.triggered.connect(self._apply_mapping)

        # 复制到剪贴板
        menu.addSeparator()
        copy_action = menu.addAction("📋 复制文本到剪贴板")
        copy_action.triggered.connect(lambda: self._copy_to_clipboard(text))

        menu.exec_(QCursor.pos())

    def _apply_mapping(self):
        """将提取的文本填入对应字段，同时记录归一化坐标"""
        action = self.sender()
        if action and action.data():
            field_key, text = action.data()
            if field_key in self._edits:
                widget = self._edits[field_key]
                if isinstance(widget, QLineEdit):
                    widget.setText(text)
                elif isinstance(widget, QComboBox):
                    idx = widget.findText(text)
                    if idx >= 0:
                        widget.setCurrentIndex(idx)

            # 记录归一化坐标（模板保存用）
            if hasattr(self, '_current_selection'):
                self._field_rects[field_key] = self._current_selection.copy()

    def _copy_to_clipboard(self, text):
        """复制文本到剪贴板"""
        from PyQt5.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(text)

    # ── 模板功能 ──

    def _save_template(self):
        """保存当前字段选取位置为模板"""
        if not self._field_rects:
            QMessageBox.information(self, "提示",
                "还没有选取任何区域映射到字段。\n"
                "请先在 PDF 上拖拽选区并映射到字段，然后再保存模板。")
            return

        # 让用户输入模板名称
        name, ok = QInputDialog.getText(
            self, "保存模板", "请输入模板名称：",
            text=os.path.basename(self._pdf_path).replace(".pdf", "")
        )
        if not ok or not name.strip():
            return

        wh_type = self._wh_combo.currentData()
        try:
            filepath = save_template(name.strip(), wh_type, self._field_rects)
            QMessageBox.information(self, "保存成功",
                f"模板「{name.strip()}」已保存！\n"
                f"包含 {len(self._field_rects)} 个字段区域映射。")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"模板保存出错：{e}")

    def _load_template(self):
        """套用已有模板"""
        templates = list_templates()
        if not templates:
            QMessageBox.information(self, "提示",
                "还没有已保存的模板。\n请先通过「保存模板」创建模板。")
            return

        # 弹出选择菜单
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { font-family: 'Microsoft YaHei'; font-size: 13px; }"
            "QMenu::item { padding: 6px 20px; }")

        for tpl in templates:
            wh_label = WAREHOUSE_LABELS.get(tpl["warehouse_type"], "")
            field_count = len(tpl.get("field_rects", {}))
            action = menu.addAction(
                f"📄 {tpl['name']}  ({wh_label}, {field_count}个字段)")
            action.setData(tpl)

        action = menu.exec_(QCursor.pos())
        if not action or not action.data():
            return

        tpl = action.data()
        self._apply_template(tpl)

    def _apply_template(self, tpl):
        """套用模板：按模板中的归一化坐标提取文本并填入字段"""
        wh_type = self._wh_combo.currentData()
        tpl_wh = tpl.get("warehouse_type", "")

        # 如果模板仓库类型不匹配，提示
        if tpl_wh and tpl_wh != wh_type:
            ret = QMessageBox.question(self, "仓库类型不匹配",
                f"模板仓库类型为「{WAREHOUSE_LABELS.get(tpl_wh, tpl_wh)}」，\n"
                f"当前仓库类型为「{WAREHOUSE_LABELS.get(wh_type, wh_type)}」。\n"
                f"是否仍要套用？",
                QMessageBox.Yes | QMessageBox.No)
            if ret != QMessageBox.Yes:
                return

        field_rects = tpl.get("field_rects", {})
        if not field_rects:
            QMessageBox.information(self, "提示", "模板中没有字段区域映射。")
            return

        # 逐字段提取
        applied_count = 0
        for field_key, sel_info in field_rects.items():
            page_idx = sel_info.get("page", 0)
            norm_rect = sel_info.get("rect", None)
            if norm_rect is None or len(norm_rect) != 4:
                continue

            # 用归一化坐标提取文本
            text = extract_text_from_pdf_rect_normalized(
                self._pdf_path, page_idx, norm_rect
            )

            if text and field_key in self._edits:
                widget = self._edits[field_key]
                if isinstance(widget, QLineEdit):
                    widget.setText(text)
                elif isinstance(widget, QComboBox):
                    idx = widget.findText(text)
                    if idx >= 0:
                        widget.setCurrentIndex(idx)
                    else:
                        widget.setCurrentText(text)
                # 记录到 _field_rects 以便后续再次保存
                self._field_rects[field_key] = sel_info
                applied_count += 1

        QMessageBox.information(self, "模板套用完成",
            f"已自动提取 {applied_count} / {len(field_rects)} 个字段。\n"
            f"请检查各字段是否正确，如有误可手动修改或重新拖拽选区。")

    def _manage_templates(self):
        """管理模板：查看和删除"""
        templates = list_templates()
        if not templates:
            QMessageBox.information(self, "提示", "还没有已保存的模板。")
            return

        # 弹出列表对话框
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { font-family: 'Microsoft YaHei'; font-size: 13px; }"
            "QMenu::item { padding: 6px 20px; }")

        for tpl in templates:
            wh_label = WAREHOUSE_LABELS.get(tpl["warehouse_type"], "")
            field_count = len(tpl.get("field_rects", {}))
            action = menu.addAction(
                f"🗑 删除「{tpl['name']}」({wh_label}, {field_count}个字段)")
            action.setData(tpl)

        action = menu.exec_(QCursor.pos())
        if not action or not action.data():
            return

        tpl = action.data()
        ret = QMessageBox.question(self, "确认删除",
            f"确定要删除模板「{tpl['name']}」吗？",
            QMessageBox.Yes | QMessageBox.No)
        if ret == QMessageBox.Yes:
            tpl_dir = _ensure_template_dir()
            filepath = os.path.join(tpl_dir, tpl["file"])
            delete_template(filepath)
            QMessageBox.information(self, "已删除", f"模板「{tpl['name']}」已删除。")

    # ── 入库 ──

    def _confirm_import(self):
        """确认入库"""
        wh_type = self._wh_combo.currentData()

        # 收集表单数据
        data = {}
        for field_name, widget in self._edits.items():
            if isinstance(widget, QLineEdit):
                data[field_name] = widget.text().strip()
            elif isinstance(widget, QComboBox):
                if field_name == "location":
                    loc_codes = [""] + list(LOCATION_MAP.keys())
                    idx = widget.currentIndex()
                    data[field_name] = loc_codes[idx] if 0 <= idx < len(loc_codes) else ""
                elif field_name == "mycoplasma":
                    data[field_name] = widget.currentText()
                else:
                    data[field_name] = widget.currentText()
            elif isinstance(widget, QSpinBox):
                data[field_name] = widget.value()

        # 验证
        if not data.get("name"):
            QMessageBox.warning(self, "输入有误", "名称不能为空！")
            return

        # 处理位置
        loc_code = data.get("location", "")

        try:
            if wh_type == WAREHOUSE_REAGENT:
                # 判断是按数量还是按体积
                sv = data.get("sample_volume", "")
                stock_mode = "volume" if sv else "quantity"
                try:
                    price = float(data.get("price", 0))
                except ValueError:
                    price = 0.0
                try:
                    stock = int(data.get("stock", 1))
                except ValueError:
                    stock = 1
                try:
                    threshold = int(data.get("threshold", 1))
                except ValueError:
                    threshold = 1

                ReagentManager.add_reagent(
                    name=data["name"],
                    batch=data.get("batch", ""),
                    expire_str=data.get("expire", "2099-12-31"),
                    amount=stock if stock_mode == "quantity" else 0,
                    price=price,
                    threshold=threshold if stock_mode == "quantity" else 1,
                    location=loc_code,
                    warehouse_type=WAREHOUSE_REAGENT,
                    specification=data.get("specification", ""),
                    catalog_no=data.get("catalog_no", ""),
                    manufacturer=data.get("manufacturer", ""),
                    notes=data.get("notes", ""),
                    stock_mode=stock_mode,
                    sample_volume=sv,
                )
            elif wh_type == WAREHOUSE_PROTEIN:
                ReagentManager.add_reagent(
                    name=data["name"],
                    batch=data.get("batch", ""),
                    expire_str=data.get("expire", "2099-12-31"),
                    amount=0,
                    price=0.0,
                    threshold=1,
                    location=loc_code,
                    warehouse_type=WAREHOUSE_PROTEIN,
                    project_no=data.get("project_no", ""),
                    molecular_weight=data.get("molecular_weight", ""),
                    isoelectric_point=data.get("isoelectric_point", ""),
                    extinction_coeff=data.get("extinction_coeff", ""),
                    concentration=data.get("concentration", ""),
                    sample_volume=data.get("sample_volume", ""),
                    total_amount=data.get("total_amount", ""),
                    purity=data.get("purity", ""),
                    buffer_type=data.get("buffer_type", ""),
                    specification=data.get("specification", ""),
                    catalog_no=data.get("catalog_no", ""),
                    manufacturer=data.get("manufacturer", ""),
                    notes=data.get("notes", ""),
                )
            elif wh_type == WAREHOUSE_CELL:
                try:
                    stock = int(data.get("stock", 1))
                except ValueError:
                    stock = 1
                ReagentManager.add_reagent(
                    name=data["name"],
                    batch=data.get("batch", ""),
                    expire_str=data.get("expire", "2099-12-31"),
                    amount=stock,
                    price=0.0,
                    threshold=1,
                    location=loc_code,
                    warehouse_type=WAREHOUSE_CELL,
                    cell_line=data.get("cell_line", ""),
                    passage_no=data.get("passage_no", ""),
                    culture_medium=data.get("culture_medium", ""),
                    viability=data.get("viability", ""),
                    mycoplasma=data.get("mycoplasma", "未检测"),
                    specification=data.get("specification", ""),
                    catalog_no=data.get("catalog_no", ""),
                    manufacturer=data.get("manufacturer", ""),
                    notes=data.get("notes", ""),
                )

            QMessageBox.information(self, "入库成功",
                f"「{data['name']}」已成功录入{WAREHOUSE_LABELS.get(wh_type, '')}！")
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "入库失败", f"录入出错：{e}")

    def closeEvent(self, event):
        """关闭时释放PDF资源"""
        self._preview.cleanup()
        super().closeEvent(event)

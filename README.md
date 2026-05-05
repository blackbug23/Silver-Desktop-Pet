# Silver Desktop Pet

AI 桌面宠物 Silver —— 一只碎嘴子银狐仓鼠博士，帮你看管实验室库存。

## 功能特性

### 🐹 桌面宠物
- 全屏透明窗口，Silver 自由溜达（正弦波速度，随机停留）
- 时段感知问候（早/午/晚/夜各有专属台词）
- 打字机效果对话，手滑防抖（0.5s 冷却）
- 被抓时挣扎动画（两帧交替）

### 🧪 三仓库管理
| 仓库类型 | 出入库单位 | 特色字段 |
|---------|-----------|---------|
| 试剂库 | 数量 | 效期提醒、最低库存预警、冻存标记 |
| 蛋白库 | 体积(mL) | 项目号、分子量、等电点、消光系数、浓度、buffer |
| 细胞库 | 管数 | 细胞系、代数、培养基、活率、支原体检测 |

- 蛋白体积格式支持：`7.26+0.2`（多管不同体积）、`5*3`（同体积分装 5 管各 3mL）
- 出入库记录自动写入鹰谷记录（模拟）
- 效期过期自动标红预警

### 📄 PDF 智能识别录入
- **拖拽选框**：在 PDF 预览图上拖拽选取区域，自动提取对应文本
- **坐标精准映射**：选框位置与提取文本 1:1 对应（pdfplumber 坐标系与 QLabel 一致）
- **模板保存**：将字段→区域映射存为 JSON 模板，同类 PDF 下次可套用
- **自动识别仓库类型**：根据关键词自动判断试剂/蛋白/细胞

### 💬 AI 对话
- 接入 DeepSeek API（openai SDK >= 1.0.0）
- 消息队列，多条消息顺序播放
- AI 状态枚举，防止重入

## 安装运行

### 依赖
```bash
pip install -r requirements.txt
```

### 配置 API Key
打开 `DesktopPetSilver/desktop_pet/config.py`，找到 `# api输入口` 注释处，填入你的 DeepSeek API Key：
```python
DEEPSEEK_API_KEY = "your-api-key-here"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
```

### 启动
```bash
cd DesktopPetSilver
python main.py
```

或直接双击 `run.bat`。

## 项目结构

```
Desktop-pet/
├── DesktopPetSilver/
│   ├── desktop_pet/
│   │   ├── __init__.py
│   │   ├── main.py              # 入口
│   │   ├── config.py            # 配置（API Key 等）
│   │   ├── pet_widget.py       # 宠物窗口（溜达/动画）
│   │   ├── dialogue_box.py     # 对话气泡（打字机效果）
│   │   ├── main_window.py      # 主窗口（全屏透明）
│   │   ├── menu.py             # 右键菜单
│   │   ├── ai_chat.py         # AI 对话模块
│   │   ├── utils.py           # 工具函数
│   │   └── reagents/          # 三仓库模块
│   │       ├── manager.py     # 库存管理器（CRUD + 持久化）
│   │       ├── stock_panel.py  # 库存面板 UI
│   │       ├── pdf_import.py  # PDF 智能识别录入
│   │       ├── record.py      # 鹰谷记录
│   │       └── location_map.py# 位置地图
│   ├── resources/             # Silver 图片资源
│   ├── pdf_templates/        # PDF 识别模板
│   ├── run.bat / install.bat / pack.bat
│   └── import_protein_excel.py  # 蛋白 Excel 导入
├── requirements.txt
└── README.md
```

## Silver 的角色设定

> 银狐仓鼠博士，严谨护试剂，碎嘴子。
> 核心口头禅：
> - "库存扣减成功，省着点用"
> - "效期还剩 X 天，赶紧安排"
> - "鹰谷记录已生成，别让我白写"

## 技术栈

- **Python 3.10+**
- **PyQt5** — GUI
- **pdfplumber** — PDF 文本提取
- **pypdfium2** — PDF 渲染（预览图）
- **Pillow** — 图像处理
- **openai SDK** — DeepSeek API 调用

## 已知问题 & 修复记录

| 日期 | 问题 | 修复 |
|------|------|------|
| 2026-05-04 | 选取 PDF 区域后程序崩溃退出 | `pyqtSignal` 参数数量不匹配，修复为 5 参数 |
| 2026-05-04 | 缩放后归一化坐标偏差 | 改为除以缩放后尺寸而非原始尺寸 |
| 2026-05-05 | 选框区域与提取文本不对应 | pdfplumber 坐标系 Y 向下，与 QLabel 一致，删除错误的 Y 轴翻转 |

## License

MIT

## 作者

blackbug23 — GitHub: [@blackbug23](https://github.com/blackbug23)

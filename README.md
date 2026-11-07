# 基于视觉图像识别的跨端自动化测试系统 (Visual-Test-System)

## 📖 项目简介

本项目是一个基于**视觉图像识别**的跨端（Android + Web）自动化测试系统。针对传统基于控件树（DOM / UIAutomator）的自动化测试脚本容易因 UI 结构变化、不同设备分辨率差异而频繁失效的问题，本系统采用 **"所见即所得"** 的测试理念，利用 OpenCV 和 PaddleOCR 替代传统控件定位，实现高度鲁棒的自动化测试。

系统通过统一的抽象接口封装了底层设备操作，业务测试用例完全由 YAML 文件驱动，支持图像匹配、文字识别、坐标换算、失败截图存证，并自动生成现代化的 HTML 可视化测试报告。

---

## 🛠️ 技术栈

- **开发语言**：Python 3.11.5
- **设备控制**：
  - Android: `uiautomator2`
  - Web: `playwright` (规划中)
- **视觉识别**：
  - 图像匹配: `OpenCV` (多尺度模板匹配、NMS 去重)
  - 文字识别: `PaddleOCR` (基于深度学习的中英文识别)
- **脚本驱动**：`PyYAML`
- **测试报告**：纯 HTML/CSS 前端渲染 (内联样式，无外部依赖)
- **工程架构**：面向对象、控制反转 (依赖注入)、单例模式

---

## 🧠 核心架构与设计思路

### 1. 三层架构设计
系统采用解耦设计，分为三层，每层只关心自己的职责：
- **Device 层 (设备底座)**：负责截图、点击等物理动作。屏蔽安卓和 Web 的底层差异，向上提供统一的 `BaseDevice` 抽象类。
- **Vision 层 (视觉识别)**：负责处理截图（BGR 格式），提供 `find_text` (OCR) 和 `find_image` (OpenCV) 能力，返回统一的 `MatchResult (x, y, w, h, score)` 结构。
- **Runner 层 (执行引擎)**：解析 YAML 脚本，维护测试上下文（变量池），调度 Device 和 Vision 执行具体动作，并捕获异常。

### 2. 核心技术点：多分辨率坐标映射算法
**痛点**：OpenCV 和 OCR 往往在缩放后的图像上识别（为了速度），但点击必须基于设备的真实物理像素，直接点击会导致严重偏移。
**解决方案**：在 `BaseDevice` 中引入 `work_size`（工作分辨率）概念。
- 截图时，记录真实分辨率与工作分辨率的缩放比例 `sx, sy`。
- 识别出的坐标默认为 `space="image"`。
- 点击时，系统自动通过公式 `真实坐标 = 图像坐标 ÷ 缩放因子` 换算。
- 支持三种坐标空间切换：`image` (图像坐标)、`real` (物理坐标)、`norm` (归一化坐标，如 0.5 代表屏幕中心，用于跨端复用)。

### 3. 性能与兼容性优化
- **PaddleOCR 单例模式**：OCR 引擎初始化（加载模型）耗时通常在 2~5 秒，系统使用类级缓存（单例模式）保证整个测试进程内只初始化一次。
- **版本自适应**：自动兼容 PaddleOCR 2.x 与 3.x 的 API 差异。同时针对 CPU 运行 PaddlePaddle 3.x 时的 `oneDNN` 崩溃 Bug，强制全局设置 `FLAGS_use_mkldnn = False` 以确保稳定运行。
- **荣耀/华为机型适配**：绕过 HDB 限制，且自动校验 `window_size` 与真实截图分辨率，防止因系统分辨率设置导致的点击偏移。

---

## 📁 项目目录结构

```text
visual-test-system/
│
├── core/                 # 核心代码目录
│   ├── __init__.py
│   ├── device.py         # 跨端设备抽象 (BaseDevice, AndroidDevice, WebDevice)
│   ├── vision.py         # 视觉识别层 (TemplateMatcher, OCRRecognizer)
│   ├── runner.py         # YAML 解析与测试执行引擎
│   └── report.py         # HTML 测试报告生成器
│
├── scripts/              # 测试脚本目录 (业务层)
│   └── test_android.yaml # 安卓端自动化测试用例
│
├── assets/               # 资源目录
│   ├── templates/        # 匹配用的小图 (素材库)
│   └── screenshots/      # 运行截图与失败现场存证
│
├── reports/              # 生成的 HTML 测试报告存放处
├── main.py               # 程序入口
├── requirements.txt      # 依赖清单
└── README.md             # 项目说明文档
```

# 🚀 快速开始

## 1. 环境安装

请确保已安装 Python 3.10+，建议在虚拟环境中运行：

```bash
# 创建并激活虚拟环境
python -m venv .venv
# Windows 激活:
.venv\Scripts\activate
# Mac/Linux 激活:
source .venv/bin/activate

# 安装依赖 (使用清华镜像加速)
pip install opencv-python paddlepaddle==3.3.0 paddleocr uiautomator2 pyyaml -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 2. 设备准备 (Android)

- 手机开启“开发者选项”和“USB 调试”。
- （针对荣耀/华为等机型）需开启“仅充电时允许 ADB 调试”或 HDB 相关开关。
- 连接电脑，终端执行 `adb devices` 确认设备已授权连接。

## 📝 使用指南：如何编写 YAML 测试脚本

测试用例存放于 `scripts/` 目录。系统支持上下文变量传递机制：`find` 步骤找到元素后，通过 `save_as` 存入变量池，后续步骤通过 `target` 引用它。

### YAML 脚本示例

```yaml
name: "荣耀 Magic5 自动化测试用例"
platform: "android"
config:
  work_size: [612, 1344]      # 识别分辨率，缩半可显著提升 OCR 速度
  auto_screenshot: true       # 步骤失败时自动截图
  continue_on_failure: false  # 遇到失败是否继续执行后续步骤

steps:
  # 1. 找文字
  - action: "find_text"
    target: "设置"
    save_as: "my_settings"    # 识别结果存入变量 my_settings
    desc: "在屏幕上寻找『设置』文字"

  # 2. 点击刚才找到的元素
  - action: "click"
    target: "my_settings"     # 引用上一步的变量
    desc: "点击进入设置页"

  # 3. 等待页面渲染
  - action: "wait"
    seconds: 2
    desc: "等待设置页加载"

  # 4. 找图像 (模板匹配)
  # 需要事先在 assets/templates/ 放入要寻找的小图标 (如 wifi.png)
  - action: "find_image"
    target: "assets/templates/wifi.png"
    save_as: "wifi_icon"
    threshold: 0.85           # 匹配度阈值，可选，默认0.8
    desc: "寻找 WLAN 图标"
```

## 🏃‍♂️ 运行测试与查看报告

确保手机亮屏并解锁，停留在测试脚本预期的起始页面。

在项目根目录运行以下命令：

```bash
python main.py
```

观察终端日志，系统会调度手机自动进行找图/找字与点击。

测试完成后，终端会打印报告路径。前往 `reports/` 目录，双击打开最新的 `.html` 文件。

报告特性：包含通过率统计、总耗时、每一步的执行详情。如果有失败的步骤，报告会自动展示手机当时的现场截图，方便快速定位 Bug。

## 🗺️ 路线图与进度状态

- [x] 阶段一：环境搭建与设备连接 (完成)
- [x] 阶段二：底层设备封装与多分辨率映射算法 (完成)
- [x] 阶段三：视觉识别双通道 (OCR + OpenCV) (完成)
- [x] 阶段四：YAML 测试引擎与 HTML 报告 (完成)
- [ ] 阶段五：Web 跨端适配 (Playwright 实现) (待开发)
- [ ] 阶段六：视觉自愈机制 (Self-Healing 智能降级) (待开发)
- [ ] 阶段七：自动化测试框架性能评估与对比实验 (待开发)

## 👨‍💻 作者

Lemon

毕业设计项目 - 基于视觉图像识别的跨端自动化测试系统
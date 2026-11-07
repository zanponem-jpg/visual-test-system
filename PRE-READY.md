# 项目准备
#### 项目支持
vs code，python，adb，git，pip，

#### vs code插件安装如下
1. Python (Microsoft官方)：提供代码高亮、补全、调试功能。

3. Pylance：Python 的语言服务器，提供极速的类型提示，能帮你少写很多 Bug。

5. Python Environment Manager：在侧边栏方便地切换你创建的虚拟环境（强烈建议你为这个项目建一个 conda 或 venv 虚拟环境）。

7. ADB Interface（可选但好用）：有些插件可以直接在 VS Code 侧边栏显示连接的安卓设备，一键截图。不装也没关系，直接在终端敲命令就行。

9. YAML (Red Hat提供)：因为你毕设要用 YAML 写测试脚本，这个插件提供 YAML 的语法高亮和格式校验。

11. Path Intellisense：自动补全文件路径（比如你写 cv2.imread("images/...") 时会有提示）。

13. Jupyter：你在调试 OpenCV 或 OCR 的时候，用 .ipynb 的 Jupyter Notebook 格式跑代码看图片效果，比纯 Python 脚本直观 100 倍！

为了不把电脑里的 Python 环境搞乱，一定要建一个独立的虚拟环境：

在 VS Code 终端（Ctrl+`）里输入：


#### VS code 环境配置
##### 内置的 venv
python -m venv .venv
##### Windows 激活：
.venv\Scripts\activate

在终端里一口气装好你需要的库：（使用清华源）
`pip install opencv-python paddleocr numpy uiautomator2 playwright pyyaml -i https://pypi.tuna.tsinghua.edu.cn/simple --default-timeout=1000
`

修改为，清华源
`pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
`
#### 项目结构
```
visual-test-system/
│
├── core/                 # 核心代码目录
│   ├── __init__.py
│   ├── device.py         # 封装 ADB 和 Playwright 的统一接口（截图、点击）
│   ├── vision.py         # OpenCV 图像匹配、多尺度缩放、OCR 识别
│   └── runner.py         # 解析 YAML，执行测试步骤，触发自愈机制
│
├── scripts/              # 测试脚本目录
│   ├── test_android.yaml # 安卓端的测试用例
│   └── test_web.yaml     # Web 端的测试用例
│
├── assets/               # 素材目录
│   ├── templates/        # 存放用于匹配的小图（如 login_btn.png）
│   └── screenshots/      # 存放运行过程中截的图（报错证据）
│
├── reports/              # 生成的 HTML 测试报告存放处
├── main.py               # 程序的入口文件
├── requirements.txt      # 依赖清单（用 pip freeze > requirements.txt 生成）
└── README.md             # 项目说明文档
```

通过USB连接到手机
执行ADB devices

【背景】
我正在做毕业设计《基于视觉图像识别的跨端自动化测试系统》。核心思路是用 OpenCV（找图）和 PaddleOCR（找字）替代传统的控件定位，结合 Python、uiautomator2（安卓）和 Playwright（Web），实现一套脚本跨端执行。

【当前进度：环境已全部搭建完毕】

开发环境：VS Code + Python 3.11.5（已建好 .venv 虚拟环境并激活）。

已装依赖：
opencv-python
, paddleocr, uiautomator2, playwright, pyyaml 等（已配置清华镜像源）。

硬件连接：使用荣耀 Magic 5（型号 PGT-AN00）真机调试。已解决 USB 模式（改为 MTP）、荣耀专属 HDB 开关、ADB 驱动等问题，手机已授权。

连通性测试：成功用 
uiautomator2
 连接手机并获取了设备信息（分辨率 1224x2688）。最后一次遇到 
FileNotFoundError
，已通过 os.makedirs("assets/screenshots", exist_ok=True) 解决。

【当前项目结构】
已经建好了标准目录：core/（核心代码）、scripts/（测试用例）、assets/（素材图）、reports/（测试报告）。

【下一步计划：阶段二 - 跨端底座开发】
现在我们要开始编写 core/device.py，封装一个统一的 BaseDevice 类，以及 AndroidDevice 和 WebDevice 子类。重点解决“截图”和“基于坐标的点击”，并攻克毕设难点：多分辨率下的坐标映射与缩放算法。

【我的问题】
请带我开始编写 core/device.py 的代码，先设计统一接口，并实现安卓端（基于 uiautomator2）的截图与点击，并带上坐标映射的换算逻辑。
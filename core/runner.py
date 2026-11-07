"""
core/runner.py
测试执行引擎：解析 YAML，调度 Device 和 Vision，处理异常并生成报告数据。
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List

import yaml

from core.device import AndroidDevice, BaseDevice
from core.vision import TemplateMatcher, OCRRecognizer, MatchResult
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.runner import StepResult

logger = logging.getLogger(__name__)


@dataclass
class StepResult:
    step_index: int
    action: str
    desc: str
    status: str          # "PASS" / "FAIL"
    duration: float
    error_msg: str = ""
    screenshot: str = ""


class TestRunner:
    def __init__(self, yaml_path: str, device: BaseDevice):
        self.yaml_path = Path(yaml_path)
        self.device = device
        self.context: Dict[str, Any] = {}  # 用于保存 find 的结果，比如 {"settings_btn": MatchResult(...)}
        self.results: List[StepResult] = []
        
        # 初始化视觉能力
        self.matcher = TemplateMatcher()
        self.ocr = OCRRecognizer(lang="ch")
        
        # 读取配置
        with open(self.yaml_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
            
        self.case_name = self.config.get("name", "未命名测试")

    def run(self) -> bool:
        logger.info(f"🚀 开始执行测试: {self.case_name}")
        self.device.connect()
        start_time = time.time()  # 记录全局开始时间
        
        all_passed = True
        steps = self.config.get("steps", [])
        
        for i, step in enumerate(steps):
            action = step.get("action")
            desc = step.get("desc", action)
            logger.info(f"👉 步骤 {i+1}/{len(steps)}: [{action}] {desc}")
            
            start_t = time.time()
            try:
                self._execute_step(step)
                duration = time.time() - start_t
                self.results.append(StepResult(i + 1, action, desc, "PASS", duration))
                
            except Exception as e:
                duration = time.time() - start_t
                logger.error(f"❌ 步骤失败: {e}")
                
                # 失败截图存证（自愈机制的一部分）
                shot_path = ""
                if self.config.get("config", {}).get("auto_screenshot", True):
                    shot_path = f"assets/screenshots/fail_step_{i+1}.png"
                    self.device.screenshot(save_path=shot_path)
                    logger.info(f"📸 已保存失败现场截图: {shot_path}")
                    
                self.results.append(StepResult(
                    i + 1, action, desc, "FAIL", duration, str(e), shot_path
                ))
                all_passed = False
                
                # 默认失败即停止，可在 yaml 里配 continue_on_failure: true
                if not self.config.get("config", {}).get("continue_on_failure", False):
                    logger.error("测试终止：遇到失败步骤。")
                    break

        self.device.disconnect()
        total_time = time.time() - start_time
        
        logger.info(f"🏁 测试结束。总计 {len(steps)} 步，通过 {sum(1 for r in self.results if r.status == 'PASS')} 步。")
        
        # ---- 延迟导入，避免循环依赖 ----
        from core.report import ReportGenerator
        reporter = ReportGenerator(self.case_name)
        report_path = reporter.generate(self.results, total_time)
        logger.info(f"📊 测试报告已生成，请在浏览器中打开: {report_path}")
        # --------------------------------

        return all_passed

    def _execute_step(self, step: dict):
        action = step.get("action")
        
        if action == "find_text":
            target = step["target"]
            save_as = step.get("save_as", target)
            # 拿到图像
            img = self.device.screenshot()
            # OCR 识别（支持 ROI）
            res = self.ocr.find(img, target, roi=step.get("roi"))
            if not res:
                raise RuntimeError(f"未在屏幕上找到文字: '{target}'")
            self.context[save_as] = res
            logger.info(f"   ✅ 找到文字，坐标: {res.box}，置信度: {res.score:.2f}")

        elif action == "find_image":
            target = step["target"]
            save_as = step.get("save_as", target)
            threshold = step.get("threshold", 0.8)
            # 加载模板
            import cv2
            tpl = cv2.imread(target, cv2.IMREAD_COLOR)
            if tpl is None:
                raise FileNotFoundError(f"无法加载模板图: {target}")
            img = self.device.screenshot()
            res = self.matcher.find(img, tpl, threshold=threshold, roi=step.get("roi"))
            if not res:
                raise RuntimeError(f"未在屏幕上找到图像: '{target}'")
            self.context[save_as] = res
            logger.info(f"   ✅ 找到图像，坐标: {res.box}，匹配度: {res.score:.3f}")

        elif action == "click":
            target = step["target"]
            if isinstance(target, str) and target in self.context:
                res: MatchResult = self.context[target]
                self.device.click_box(res.box)
                logger.info(f"   ✅ 点击元素中心点: {res.center}")
            elif isinstance(target, list) and len(target) == 2:
                self.device.click(target[0], target[1], space="image")
                logger.info(f"   ✅ 点击坐标: {target}")
            else:
                # 增强报错信息：告诉你目前有哪些变量可用
                available = list(self.context.keys())
                raise ValueError(
                    f"无效的点击目标: '{target}'。当前步骤找不到这个变量。"
                    f"当前可用的变量只有: {available}。请检查 YAML 里的 save_as 和 target 拼写是否一致。"
                )

        elif action == "wait":
            seconds = step.get("seconds", 1.0)
            time.sleep(seconds)
            logger.info(f"   ✅ 等待 {seconds} 秒")

        elif action == "assert_text":
            target = step["target"]
            img = self.device.screenshot()
            res = self.ocr.find(img, target)
            if not res:
                raise AssertionError(f"断言失败：屏幕上不存在文字 '{target}'")
            logger.info(f"   ✅ 断言通过：存在文字 '{target}'")

        else:
            raise ValueError(f"未知的 action: {action}")
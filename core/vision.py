"""
core/vision.py
视觉识别层：OpenCV 模板匹配 + PaddleOCR 文字识别，统一返回 MatchResult。

坐标系约定：
    所有 find_xxx() 的输入 image 都来自 device.screenshot()，
    返回的 MatchResult.box 就在该 image 的坐标系下，
    可直接传给 device.click_box(result.box, space="image")。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np
import os
os.environ["FLAGS_log_level"] = "3"         # 屏蔽 Paddle 底层的 INFO 日志刷屏
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE" # 防止部分 OpenMP 库冲突
logger = logging.getLogger(__name__)

Box = Tuple[int, int, int, int]      # (x, y, w, h)


# --------------------------------------------------------------------------- #
#                            统一返回结构
# --------------------------------------------------------------------------- #
@dataclass
class MatchResult:
    x: int
    y: int
    w: int
    h: int
    score: float
    kind: str                        # "template" | "ocr"
    text: Optional[str] = None

    @property
    def box(self) -> Box:
        return (self.x, self.y, self.w, self.h)

    @property
    def center(self) -> Tuple[float, float]:
        return (self.x + self.w / 2.0, self.y + self.h / 2.0)

    def __repr__(self) -> str:
        extra = f" text='{self.text}'" if self.text else ""
        return (f"<MatchResult {self.kind} box={self.box} "
                f"score={self.score:.3f}{extra}>")


# --------------------------------------------------------------------------- #
#                          OpenCV 模板匹配
# --------------------------------------------------------------------------- #
class TemplateMatcher:
    """多尺度模板匹配器。

    参数
    ----
    scales : 模板缩放比例序列。
        1.0 表示模板与屏幕同尺寸；若模板采自另一分辨率的设备，
        可传 (0.8, 0.9, 1.0, 1.1, 1.2) 让匹配器自动找最合适的尺度。
    default_threshold : 匹配分数阈值（TM_CCOEFF_NORMED，范围 [-1, 1]），
        工程上 0.8 是比较稳的默认值。
    """

    def __init__(
        self,
        scales: Sequence[float] = (1.0,),
        default_threshold: float = 0.8,
    ):
        self.scales = tuple(scales)
        self.default_threshold = default_threshold

    def find(
        self,
        screen: np.ndarray,
        template: np.ndarray,
        threshold: Optional[float] = None,
        roi: Optional[Box] = None,
    ) -> Optional[MatchResult]:
        """在 screen 中查找 template，返回最佳匹配；找不到返回 None。

        roi : 只在 screen 的某个区域内搜索 (x, y, w, h)，可大幅提速。
        """
        th = threshold if threshold is not None else self.default_threshold
        search_img, offset = self._apply_roi(screen, roi)
        if search_img is None:
            return None

        best: Optional[MatchResult] = None
        for s in self.scales:
            tpl = self._resize_template(template, s)
            if tpl is None:
                continue
            if tpl.shape[0] > search_img.shape[0] or tpl.shape[1] > search_img.shape[1]:
                continue  # 模板比搜索区还大，跳过该尺度

            res = cv2.matchTemplate(search_img, tpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val < th:
                continue

            candidate = MatchResult(
                x=offset[0] + max_loc[0],
                y=offset[1] + max_loc[1],
                w=tpl.shape[1],
                h=tpl.shape[0],
                score=float(max_val),
                kind="template",
            )
            if best is None or candidate.score > best.score:
                best = candidate

        if best:
            logger.debug("模板匹配成功: %s", best)
        else:
            logger.debug("模板匹配失败 (threshold=%.2f, scales=%s)", th, self.scales)
        return best

    def find_all(
        self,
        screen: np.ndarray,
        template: np.ndarray,
        threshold: Optional[float] = None,
        roi: Optional[Box] = None,
        max_results: int = 20,
    ) -> List[MatchResult]:
        """返回所有匹配（NMS 去重），用于"列表项"等重复元素场景。"""
        th = threshold if threshold is not None else self.default_threshold
        search_img, offset = self._apply_roi(screen, roi)
        if search_img is None:
            return []

        raw: List[MatchResult] = []
        for s in self.scales:
            tpl = self._resize_template(template, s)
            if tpl is None:
                continue
            if tpl.shape[0] > search_img.shape[0] or tpl.shape[1] > search_img.shape[1]:
                continue
            res = cv2.matchTemplate(search_img, tpl, cv2.TM_CCOEFF_NORMED)
            ys, xs = np.where(res >= th)
            for (yy, xx) in zip(ys, xs):
                raw.append(MatchResult(
                    x=offset[0] + int(xx),
                    y=offset[1] + int(yy),
                    w=tpl.shape[1],
                    h=tpl.shape[0],
                    score=float(res[yy, xx]),
                    kind="template",
                ))

        return self._nms(raw, iou_thr=0.3)[:max_results]

    # -------- 内部工具 -------- #
    @staticmethod
    def _apply_roi(screen, roi):
        if screen is None or screen.size == 0:
            return None, (0, 0)
        if roi is None:
            return screen, (0, 0)
        x, y, w, h = roi
        H, W = screen.shape[:2]
        x, y = max(0, x), max(0, y)
        w, h = min(w, W - x), min(h, H - y)
        if w <= 0 or h <= 0:
            return None, (0, 0)
        return screen[y:y + h, x:x + w], (x, y)

    @staticmethod
    def _resize_template(template: np.ndarray, scale: float) -> Optional[np.ndarray]:
        if template is None or template.size == 0:
            return None
        if abs(scale - 1.0) < 1e-6:
            return template
        new_w = max(1, int(round(template.shape[1] * scale)))
        new_h = max(1, int(round(template.shape[0] * scale)))
        return cv2.resize(template, (new_w, new_h), interpolation=cv2.INTER_AREA)

    @staticmethod
    def _nms(items: List[MatchResult], iou_thr: float = 0.3) -> List[MatchResult]:
        if not items:
            return []
        items = sorted(items, key=lambda r: r.score, reverse=True)
        kept: List[MatchResult] = []
        for it in items:
            if all(_iou(it.box, k.box) < iou_thr for k in kept):
                kept.append(it)
        return kept


def _iou(a: Box, b: Box) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ax2, ay2, bx2, by2 = ax + aw, ay + ah, bx + bw, by + bh
    ix = max(0, min(ax2, bx2) - max(ax, bx))
    iy = max(0, min(ay2, by2) - max(ay, by))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


# --------------------------------------------------------------------------- #
#                            PaddleOCR 封装
# --------------------------------------------------------------------------- #
class OCRRecognizer:
    """PaddleOCR 封装（单例，避免重复初始化）。

    参数
    ----
    lang : 语言，'ch'（中英文）、'en'、'japan' 等。
    use_gpu : 是否使用 GPU（本机无 CUDA 保持 False）。
    """

    _engines: dict = {}  # 类级缓存：{(lang, use_gpu): PaddleOCR 实例}

    def __init__(self, lang: str = "ch", use_gpu: bool = False):
        self.lang = lang
        self.use_gpu = use_gpu

    @property
    def engine(self):
        key = (self.lang, self.use_gpu)
        if key not in OCRRecognizer._engines:
            logger.info("初始化 PaddleOCR (lang=%s, gpu=%s)…", self.lang, self.use_gpu)
            from paddleocr import PaddleOCR
            import paddle

            # 双保险：关闭 oneDNN 加速 (解决之前的崩溃)
            paddle.set_flags({"FLAGS_use_mkldnn": False})

            device = "gpu" if self.use_gpu else "cpu"
            engine = None

            # 尝试 PaddleOCR 3.x 签名
            try:
                engine = PaddleOCR(
                    lang=self.lang,
                    use_textline_orientation=True,
                    use_doc_orientation_classify=False, # <--- 关键：关闭文档方向分类
                    use_doc_unwarping=False,            # <--- 关键：关闭文档矫正 (UVDoc)
                    device=device,
                    enable_mkldnn=False, 
                )
                logger.info("PaddleOCR 初始化完成（3.x API）")
            except (TypeError, ValueError) as e:
                logger.debug(f"3.x 初始化失败: {e}，回退 2.x 签名")

            if engine is None:
                # 回退 2.x 签名
                try:
                    engine = PaddleOCR(
                        use_angle_cls=True,
                        lang=self.lang,
                        use_gpu=self.use_gpu,
                    )
                    logger.info("PaddleOCR 初始化完成（2.x API）")
                except Exception as e:
                    raise RuntimeError(f"PaddleOCR 初始化失败: {e}") from e

            OCRRecognizer._engines[key] = engine
        return OCRRecognizer._engines[key]

    def recognize(self, image: np.ndarray) -> List[MatchResult]:
        """识别图中所有文本，返回 MatchResult 列表（kind='ocr'）。"""
        import time
        if image is None or image.size == 0:
            return []
            
        # --- 耗时打点 1：看看图片的尺寸到底多大 ---
        h, w = image.shape[:2]
        t0 = time.time()
        print(f"🔍 [OCR Debug] 接收到的图像尺寸: {w}x{h}")
        
        try:
            # 兼容 2.x / 3.x 的调用签名
            try:
                # 注意：这里加了 time 记录纯推理耗时
                raw = self.engine.ocr(image, cls=True)
            except TypeError:
                raw = self.engine.ocr(image)
        except Exception as e:
            logger.error("OCR 识别异常: %s", e)
            return []

        t1 = time.time()
        
        # --- 耗时打点 2：解析结果耗时 ---
        results: List[MatchResult] = []
        for poly, text, score in _parse_ocr_result(raw):
            if not text or not text.strip():
                continue
            x, y, w, h = _poly_to_box(poly)
            results.append(MatchResult(
                x=x, y=y, w=w, h=h, score=score, kind="ocr", text=text,
            ))
            
        t2 = time.time()
        
        # --- 打印结果 ---
        print(f"⏱️ [OCR Debug] PaddleOCR 推理耗时: {t1 - t0:.3f}s | 结果解析耗时: {t2 - t1:.3f}s | 识别出 {len(results)} 条")
        
        logger.debug("OCR 识别到 %d 条文本", len(results))
        return results

    def find(
        self,
        image: np.ndarray,
        keyword: str,
        exact: bool = False,
        threshold: float = 0.6,
        roi: Optional[Box] = None,
    ) -> Optional[MatchResult]:
        """在图中查找包含 keyword 的文本。

        参数
        ----
        exact : True 要求完全相等，False 为子串包含（默认）。
        threshold : OCR 置信度下限。
        roi : 只在该区域内识别（先裁剪再 OCR，显著提速）。
        """
        search_img, offset = TemplateMatcher._apply_roi(image, roi)  # 复用 ROI 工具
        if search_img is None:
            return None

        candidates = [r for r in self.recognize(search_img) if r.score >= threshold]
        for r in candidates:
            hit = (r.text == keyword) if exact else (keyword in r.text)
            if hit:
                r.x += offset[0]
                r.y += offset[1]
                logger.debug("OCR 命中关键字 %r: %s", keyword, r)
                return r
        logger.debug("OCR 未命中关键字 %r（候选 %d 条）", keyword, len(candidates))
        return None


# --------------------------------------------------------------------------- #
#                     PaddleOCR 结果格式兼容解析
# --------------------------------------------------------------------------- #
def _parse_ocr_result(raw) -> List[Tuple[np.ndarray, str, float]]:
    """把 PaddleOCR 2.x / 3.x 的返回统一解析为 [(poly, text, score), ...]。

    poly 为 4 点 numpy array，shape=(4,2)。
    """
    items: List[Tuple[np.ndarray, str, float]] = []
    if not raw:
        return items

    # ---- 3.x 格式：[{'rec_texts': [...], 'rec_scores': [...], 'rec_polys': [...]}, ...]
    if isinstance(raw[0], dict):
        for page in raw:
            texts = page.get("rec_texts") or []
            scores = page.get("rec_scores") or []
            polys = page.get("rec_polys") or page.get("dt_polys") or []
            for i, t in enumerate(texts):
                if i >= len(polys):
                    continue
                score = float(scores[i]) if i < len(scores) else 0.0
                items.append((np.asarray(polys[i]), t, score))
        return items

    # ---- 2.x 格式：[[[poly, (text, score)], ...]]
    for line in raw:
        if not line:
            continue
        for item in line:
            try:
                poly = np.asarray(item[0])
                text, score = item[1][0], float(item[1][1])
                items.append((poly, text, score))
            except Exception:
                continue
    return items


def _poly_to_box(poly: np.ndarray) -> Box:
    """4 点多边形 → 外接矩形 (x, y, w, h)。"""
    xs = poly[:, 0]
    ys = poly[:, 1]
    x0, x1 = float(xs.min()), float(xs.max())
    y0, y1 = float(ys.min()), float(ys.max())
    return int(x0), int(y0), int(x1 - x0), int(y1 - y0)


# --------------------------------------------------------------------------- #
#                              自测入口
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import logging
    from pathlib import Path

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    # 1. 获取截图
    from core.device import AndroidDevice
    with AndroidDevice(work_size=None) as dev:
        img = dev.screenshot(save_path="assets/screenshots/vision_input.png")
    
    print(f"\n待识别图像: {img.shape[1]}x{img.shape[0]}\n")

    # 2. 测试 OCR
    print("=== 测试 PaddleOCR ===")
    ocr = OCRRecognizer(lang="ch")
    results = ocr.recognize(img)
    print(f"识别到 {len(results)} 条文本：")
    
    # 复制原图用来画框
    vis_img = img.copy()
    for i, r in enumerate(results):
        print(f"  [{r.score:.2f}] {r.text!r}  box={r.box}")
        # 画出矩形框
        cv2.rectangle(vis_img, (r.x, r.y), (r.x + r.w, r.y + r.h), (0, 0, 255), 3)
        # 写上文本
        cv2.putText(vis_img, f"{i}: {r.text}", (r.x, max(r.y - 10, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
        
        # 顺便把每一个框单独裁下来保存，方便你观察
        cropped = img[r.y:r.y+r.h, r.x:r.x+r.w]
        cv2.imwrite(f"assets/screenshots/ocr_crop_{i}.png", cropped)
        
    # 保存画好框的图
    cv2.imwrite("assets/screenshots/ocr_vis.png", vis_img)
    print("\n已保存画框可视化图: assets/screenshots/ocr_vis.png")
    print("已保存各文本框切片: assets/screenshots/ocr_crop_0.png 等")
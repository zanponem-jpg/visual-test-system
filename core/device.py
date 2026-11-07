"""
core/device.py
跨端设备统一接口层。

设计要点：
1. BaseDevice 定义统一接口，子类只需实现 _screenshot_raw / _tap_raw；
2. 引入 work_size（工作分辨率）概念，实现"识别坐标系"与"设备物理坐标系"解耦；
3. click 支持 image / real / norm 三种坐标空间，自动完成缩放映射。
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Tuple, Union

import cv2
import numpy as np

logger = logging.getLogger(__name__)

Size = Tuple[int, int]          # (width, height)
Box = Tuple[int, int, int, int] # (x, y, w, h)


# --------------------------------------------------------------------------- #
#                                 基类
# --------------------------------------------------------------------------- #
class BaseDevice(ABC):
    """跨端设备抽象基类。

    参数
    ----
    work_size : (w, h) | None
        识别工作分辨率。screenshot() 会把原图缩放到该尺寸后返回，
        后续 vision/OCR 都在该坐标系下工作，点击时自动映射回真实分辨率。
        None 表示不做缩放（直接用设备原始分辨率识别）。
    name : str
        设备别名，用于日志。
    """

    def __init__(self, work_size: Optional[Size] = None, name: str = ""):
        self.name = name or self.__class__.__name__
        self.work_size = work_size

        # 运行时状态（由 screenshot() 维护）
        self._real_size: Optional[Size] = None    # 设备真实分辨率
        self._image_size: Optional[Size] = None   # 最近一次截图返回的尺寸
        self._scale: Tuple[float, float] = (1.0, 1.0)  # work / real

    # ---------------- 子类必须实现的"物理动作" ---------------- #
    @abstractmethod
    def connect(self) -> "BaseDevice":
        ...

    @abstractmethod
    def disconnect(self) -> None:
        ...

    @abstractmethod
    def _screenshot_raw(self) -> np.ndarray:
        """返回设备原始分辨率的 BGR 截图。"""

    @abstractmethod
    def _tap_raw(self, x: int, y: int) -> None:
        """在设备真实物理坐标 (x, y) 上执行单击。"""

    # ---------------- 运行时属性 ---------------- #
    @property
    def real_size(self) -> Size:
        if self._real_size is None:
            raise RuntimeError("尚未截图，无法获取真实分辨率，请先调用 screenshot()")
        return self._real_size

    @property
    def image_size(self) -> Size:
        if self._image_size is None:
            raise RuntimeError("尚未截图，请先调用 screenshot()")
        return self._image_size

    # ---------------- 截图（含缩放） ---------------- #
    def screenshot(self, save_path: Optional[Union[str, Path]] = None) -> np.ndarray:
        """获取截图（BGR ndarray），并按 work_size 缩放。

        Returns
        -------
        np.ndarray
            形状为 (Hw, Ww, 3) 的 BGR 图像，坐标对应 click(space="image")。
        """
        raw = self._screenshot_raw()
        if raw is None or raw.size == 0:
            raise RuntimeError(f"[{self.name}] 截图失败：返回空图像")

        rh, rw = raw.shape[:2]
        self._real_size = (rw, rh)

        if self.work_size is not None and self.work_size != (rw, rh):
            ww, wh = self.work_size
            img = cv2.resize(raw, (ww, wh), interpolation=cv2.INTER_AREA)
            self._scale = (ww / rw, wh / rh)
        else:
            img = raw
            self._scale = (1.0, 1.0)

        self._image_size = (img.shape[1], img.shape[0])

        if save_path:
            p = Path(save_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(p), img)
            logger.debug("[%s] 截图已保存: %s", self.name, p)

        return img

    # ---------------- 点击（核心映射逻辑） ---------------- #
    def click(
        self,
        x: float,
        y: float,
        space: str = "image",
        duration: float = 0.05,
    ) -> None:
        """点击指定坐标。

        参数
        ----
        x, y : float
            坐标值。
        space : {"image", "real", "norm"}
            - image: 最近一次 screenshot() 返回图像的坐标系（默认，识别结果直接传入）
            - real : 设备物理像素坐标
            - norm : 归一化 [0, 1] 比例坐标
        duration : float
            点击后等待时间（秒），避免操作过快导致丢帧。
        """
        rx, ry = self._map_to_real(x, y, space)
        self._tap_raw(rx, ry)
        logger.debug("[%s] click space=%-5s (%.1f, %.1f) -> real (%d, %d)",
                     self.name, space, x, y, rx, ry)
        if duration > 0:
            time.sleep(duration)

    def click_box(
        self,
        box: Box,
        space: str = "image",
        offset: Tuple[float, float] = (0, 0),
        duration: float = 0.05,
    ) -> None:
        """点击识别框 (x, y, w, h) 的中心点。"""
        x, y, w, h = box
        cx = x + w / 2 + offset[0]
        cy = y + h / 2 + offset[1]
        self.click(cx, cy, space=space, duration=duration)

    def _map_to_real(self, x: float, y: float, space: str) -> Tuple[int, int]:
        """把任意坐标空间映射为设备物理像素坐标（含越界裁剪）。"""
        rw, rh = self.real_size

        if space == "norm":
            rx, ry = x * rw, y * rh
        elif space == "real":
            rx, ry = x, y
        elif space == "image":
            sx, sy = self._scale
            rx, ry = x / sx, y / sy
        else:
            raise ValueError(f"未知坐标空间: {space!r}，应为 image / real / norm")

        # 越界裁剪到屏幕内
        rx = int(round(min(max(rx, 0), rw - 1)))
        ry = int(round(min(max(ry, 0), rh - 1)))
        return rx, ry

    # ---------------- 上下文管理 ---------------- #
    def __enter__(self) -> "BaseDevice":
        return self.connect()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.disconnect()


# --------------------------------------------------------------------------- #
#                                 安卓端
# --------------------------------------------------------------------------- #
class AndroidDevice(BaseDevice):
    """基于 uiautomator2 的安卓设备实现。

    参数
    ----
    serial : str | None
        adb 序列号，None 表示自动连接第一台设备。
    work_size : (w, h) | None
        识别工作分辨率，建议传入 (1080, 2400) 之类基准值以实现跨机型统一。
    package_name : str | None
        被测应用包名（预留，用于后续拉起/杀进程）。
    """

    def __init__(
        self,
        serial: Optional[str] = None,
        work_size: Optional[Size] = None,
        package_name: Optional[str] = None,
    ):
        super().__init__(work_size=work_size, name=f"Android[{serial or 'auto'}]")
        self.serial = serial
        self.package_name = package_name
        self.d = None  # type: ignore

    # ---------- 连接管理 ---------- #
    def connect(self) -> "AndroidDevice":
        import uiautomator2 as u2

        try:
            self.d = u2.connect(self.serial) if self.serial else u2.connect()
        except Exception as e:
            raise RuntimeError(f"连接安卓设备失败: {e}") from e

        info = getattr(self.d, "device_info", {}) or {}
        model = info.get("productName") or info.get("model") or "unknown"
        android_ver = info.get("version") or f"sdk{info.get('sdk', '?')}"

        # 分辨率优先用 window_size()，最可靠；失败再退回截图尺寸
        try:
            ww, wh = self.d.window_size()
            resolution_str = f"{ww}x{wh}"
        except Exception:
            resolution_str = "n/a"

        logger.info(
            "[%s] 已连接：model=%s, android=%s, resolution=%s",
            self.name, model, android_ver, resolution_str,
        )
        self._verify_window_size()
        return self

    def disconnect(self) -> None:
        # uiautomator2 不需要显式关闭连接，置空即可；如需彻底释放可停服务
        self.d = None
        logger.info("[%s] 已断开", self.name)

    def _verify_window_size(self) -> None:
        """校验 window_size 与截图分辨率是否一致（荣耀/华为常见坑）。"""
        try:
            ww, wh = self.d.window_size()
            shot = self.d.screenshot()
            sw, sh = shot.size if hasattr(shot, "size") else (0, 0)
            if (ww, wh) != (sw, sh):
                logger.warning(
                    "[%s] window_size=%s 与截图分辨率=%s 不一致，"
                    "本系统以截图分辨率作为点击基准，若出现偏移请检查系统分辨率设置",
                    self.name, (ww, wh), (sw, sh),
                )
        except Exception as e:
            logger.debug("[%s] window_size 校验跳过: %s", self.name, e)

    # ---------- 物理动作实现 ---------- #
    def _screenshot_raw(self) -> np.ndarray:
        if self.d is None:
            raise RuntimeError("设备未连接，请先调用 connect()")

        last_err = None
        for attempt in range(3):
            try:
                shot = self.d.screenshot()
                return self._to_bgr_ndarray(shot)
            except Exception as e:  # 偶发截图失败，重试
                last_err = e
                time.sleep(0.3)
        raise RuntimeError(f"截图连续失败 3 次: {last_err}")

    @staticmethod
    def _to_bgr_ndarray(shot) -> np.ndarray:
        """兼容 PIL.Image / ndarray / bytes 三种返回类型，统一转为 BGR ndarray。"""
        if isinstance(shot, np.ndarray):
            img = shot
            # 可能是 RGB，稳妥起见统一按 BGR 处理（OpenCV 生态）
            if img.ndim == 2:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            return img
        if hasattr(shot, "convert"):  # PIL.Image
            rgb = np.array(shot.convert("RGB"))
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        # bytes
        arr = np.frombuffer(shot, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("无法将截图字节流解码为图像")
        return img

    def _tap_raw(self, x: int, y: int) -> None:
        self.d.click(x, y)


# --------------------------------------------------------------------------- #
#                                 Web 端（占位）
# --------------------------------------------------------------------------- #
class WebDevice(BaseDevice):
    """基于 Playwright 的 Web 设备实现（阶段二后续补充）。"""

    def __init__(self, browser: str = "chromium", headless: bool = True,
                 work_size: Optional[Size] = None, url: str = "about:blank"):
        super().__init__(work_size=work_size, name=f"Web[{browser}]")
        self.browser_name = browser
        self.headless = headless
        self.url = url
        self._page = None
        self._pw = None

    def connect(self) -> "WebDevice":
        raise NotImplementedError("WebDevice 将在阶段二后续实现")

    def disconnect(self) -> None:
        raise NotImplementedError

    def _screenshot_raw(self) -> np.ndarray:
        raise NotImplementedError

    def _tap_raw(self, x: int, y: int) -> None:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
#                              自测入口
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    import time

    with AndroidDevice(work_size=(612, 1344)) as dev:
        before = dev.screenshot()                       # 612x1344
        tx, ty = 300, 672                               # 识别坐标系中心
        print(f"点击 image 坐标系 ({tx}, {ty}) → "
              f"应映射到 real ({tx/0.5:.0f}, {ty/0.5:.0f})")
        dev.click(tx, ty, space="image")
        time.sleep(0.5)

        after = dev.screenshot()                        # 再截一张
        vis = after.copy()
        cv2.circle(vis, (tx, ty), 40, (0, 0, 255), 4)   # 红圈标出点击位置
        cv2.putText(vis, f"click ({tx},{ty})", (tx - 80, ty - 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        out = "assets/screenshots/click_check.png"
        cv2.imwrite(out, vis)
        print(f"已保存可视化结果: {out}")
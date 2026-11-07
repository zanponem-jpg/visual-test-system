# main.py
import logging
from core.device import AndroidDevice
from core.runner import TestRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)

if __name__ == "__main__":
    # 实例化安卓设备，工作分辨率统一为 612x1344 (缩半加速)
    device = AndroidDevice(work_size=(612, 1344))
    
    # 加载 YAML 测试用例
    runner = TestRunner("scripts/test_android.yaml", device)
    
    # 执行测试
    success = runner.run()
    
    print(f"\n最终结果: {'✅ 全部通过' if success else '❌ 存在失败'}")
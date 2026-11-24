#!/usr/bin/env python3
"""
环境光自动暗黑模式监控器 (host 侧, 通过 adb 驱动)

原理:
  设备的环境光传感器 (TCS3720ALSPRX, type=light) 是 on-change 类型 ——
  只有数值变化时才会写入 sensorservice 事件缓冲, 数值稳定时时间戳会"冻结",
  但最新一条事件的数值始终代表当前环境光. 因此:
    - 用 `dumpsys sensorservice` 读取最新一条 light 事件的第一个值 (lux);
    - 不能用"事件时间戳是否过期"来判定数据有效性 (稳定值不会重发);
    - 去抖计时用本机单调时钟: lux 持续低于阈值 DEBOUNCE 秒 -> 切暗黑;
      lux 恢复并持续高于阈值 DEBOUNCE 秒 -> 切回浅色.

切换暗黑模式: `adb shell cmd uimode night yes|no` (全局, 无需 root/额外权限).

用法:
  python3 light_dark_monitor.py                 # 默认阈值 10 lux, 去抖 2s
  python3 light_dark_monitor.py --threshold 10 --debounce 2
  python3 light_dark_monitor.py --once-dark      # 触发一次暗黑切换后退出(自检用)
"""
import argparse
import re
import subprocess
import sys
import time

# 匹配 "(ts=..., wall=...) 621.75, 3930.68, 262.00,"  捕获第一个数值(lux)
EVENT_RE = re.compile(r"\(ts=[\d.]+,\s*wall=[\d:.]+\)\s*(-?[\d.]+)")


def adb_shell(cmd: str) -> str:
    return subprocess.run(
        ["adb", "shell", cmd], capture_output=True, text=True, timeout=10
    ).stdout


def read_lux() -> float | None:
    """返回当前环境光 lux (最新 on-change 事件的第一个值); 读不到返回 None。"""
    out = adb_shell(
        "dumpsys sensorservice | grep -A 55 "
        "'Ambient Light Sensor Non-wakeup: last' | grep '(ts='"
    )
    matches = EVENT_RE.findall(out)
    if not matches:
        return None
    return float(matches[-1])  # 最后一条 = 最新值


def set_night_mode(on: bool) -> None:
    adb_shell(f"cmd uimode night {'yes' if on else 'no'}")


def is_night_mode() -> bool:
    return "yes" in adb_shell("cmd uimode night")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--threshold", type=float, default=10.0, help="lux 阈值, 低于则视为暗环境")
    p.add_argument("--debounce", type=float, default=2.0, help="持续秒数 (去抖)")
    p.add_argument("--interval", type=float, default=0.4, help="轮询间隔秒")
    p.add_argument("--once-dark", action="store_true", help="触发一次暗黑切换后退出")
    args = p.parse_args()

    dark = is_night_mode()
    low_since = high_since = None
    print(
        f"[start] 阈值={args.threshold}lux 去抖={args.debounce}s "
        f"当前模式={'暗黑' if dark else '浅色'}",
        flush=True,
    )

    while True:
        lux = read_lux()
        now = time.monotonic()
        if lux is None:
            time.sleep(args.interval)
            continue

        if lux < args.threshold:
            high_since = None
            if low_since is None:
                low_since = now
                print(f"[detect] {lux:.1f} lux < {args.threshold}, 开始计时…", flush=True)
            elif not dark and (now - low_since) >= args.debounce:
                set_night_mode(True)
                dark = True
                print(f"[switch] 低光持续 {args.debounce}s -> 已切换【暗黑模式】 ({lux:.1f} lux)", flush=True)
                if args.once_dark:
                    return
        else:
            low_since = None
            if high_since is None:
                high_since = now
                if dark:
                    print(f"[detect] {lux:.1f} lux ≥ {args.threshold}, 开始计时…", flush=True)
            elif dark and (now - high_since) >= args.debounce:
                set_night_mode(False)
                dark = False
                print(f"[switch] 环境变亮 {args.debounce}s -> 已切回【浅色模式】 ({lux:.1f} lux)", flush=True)

        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)

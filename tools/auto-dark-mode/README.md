# auto-dark-mode — 环境光自动暗黑

一套「手机环境光变暗就切暗黑模式」的小工具，包含：

- `AutoDark/` — Android 工程（Kotlin，通过 Shizuku / `cmd uimode night` 切换夜间模式）；
- `light_dark_monitor.py` — 主机侧脚本，用 `adb` 读取 `dumpsys sensorservice` 里的
  环境光（lux）事件，带去抖（默认阈值 10 lux、去抖 2 秒）后切换暗黑模式。

## 主机侧监控脚本

```bash
adb devices                                  # 确认设备已授权
python3 light_dark_monitor.py                # 默认阈值 10 lux / 去抖 2s
python3 light_dark_monitor.py --threshold 10 --debounce 2
python3 light_dark_monitor.py --once-dark     # 只切一次，用于自检
```

原理：设备的环境光传感器是 on-change 类型，数值稳定时不重发事件，
所以脚本读「最新一条 light 事件」的数值，并用本机单调时钟做去抖计时；
切换命令是 `adb shell cmd uimode night yes|no`（无需 root）。

## Android 工程

```bash
cd AutoDark
# 需要本机已安装 Android SDK，并在 local.properties 里写 sdk.dir=/path/to/Android/Sdk
gradle assembleDebug        # 未附带 gradle wrapper，请使用本机 gradle
```

工程里没有提交 gradle 发行版、构建产物与 `local.properties`（见根目录 `.gitignore`），
首次构建请自行准备 SDK 与 gradle。若需要 Shizuku 授权，可自行从官方渠道安装 Shizuku（仓库不再附带 APK）。

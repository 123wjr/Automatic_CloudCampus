# legacy/ — 旧版命令行工具

Web 版（当前主线）已经覆盖了这里的两套 CLI 的能力，保留它们是因为：

1. `autocc-cli` 是 **抓包产样** 的唯一来源（`Raw/*.npy`），Web 端的重放依赖这些样本；
2. `cc-replayer` 适合在本地一次性处理大批账号，不依赖数据库与支付流程。

| 目录 | 版本 | 技术栈 | 用途 |
|---|---|---|---|
| `autocc-cli/` | v1 | Selenium + mitmproxy | 浏览器交互完成 H5P 任务，拦截并满分改包，落盘为 `Raw/<任务ID>.npy` |
| `cc-replayer/` | v1.5 | requests + rich | 读取 `Raw/` 样本，多账号并发重放；附带按进度计价的 `price_calculator.py` |

两套 CLI 都在**本机**运行，属于个人使用工具，不参与服务端部署。
它们与原 Web 版共享仓库根目录的 `Raw/`（可用环境变量 `AUTOCC_RAW_DIR` 覆盖）。

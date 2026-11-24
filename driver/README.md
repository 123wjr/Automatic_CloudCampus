# driver/ — 浏览器驱动（可选）

v2 后端已经改为纯 HTTP 请求，默认**不需要**浏览器驱动。

只有在使用 `legacy/autocc-cli`（Selenium + mitmproxy 的旧版 CLI）时才需要：

- 新版 Selenium 可以自动下载驱动，无需手动放置；
- 如需手动指定，把 `msedgedriver` 放到本目录，并用环境变量 `EDGEDRIVER_PATH` 指向它；
- 驱动二进制体积大（约 20MB）且与浏览器版本绑定，因此不纳入版本库（见 `.gitignore`）。

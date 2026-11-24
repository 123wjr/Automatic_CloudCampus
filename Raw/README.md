# Raw/ — H5P 任务发包样本目录

本目录存放 `任务ID.npy` 形式的抓包样本，重放器（`backend/app/services/replayer.py`、
`legacy/autocc-cli/mitm.py`、`legacy/cc-replayer/replayer.py`）都会从这里读取。

- 文件由浏览器扩展 / mitmproxy 抓包生成，属于**个人会话数据**，默认被 `.gitignore` 忽略；
- 仓库只保留本说明文件，克隆后需要自己生成或从可信来源拷贝；
- 每个 `.npy` 文件包含原始请求的 URL / headers / body，请勿公开分享。

生成方式见 `legacy/autocc-cli/README.md`（mitmproxy 抓包）或 web 端「首次完成」流程。

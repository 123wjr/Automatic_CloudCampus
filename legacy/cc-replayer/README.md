# cc-replayer — v1.5 多账号批量重放 CLI

读取仓库根目录 `Raw/` 下的 `.npy` 样本，用 requests 直接向云校园重放，
`rich` 提供实时多进度条界面，支持常驻监视队列文件、失败重试与按进度计价。

## 安装

```bash
pip install -r requirements.txt
```

## 用法

```bash
python replayer.py                          # 常驻模式：监视 queue.json，回车/Ctrl+C 退出
python replayer.py add -u 账号 -p 密码       # 往队列里追加一个账号
python replayer.py add -f accounts.json      # 从 JSON 批量追加
python replayer.py run -f accounts.json      # 一次性批量执行，跑完退出
python replayer.py retry                     # 按 failed.json 重试失败的账号
python price_calculator.py -u 账号 -p 密码   # 只查询进度并计算报价
```

常用参数：`-c/--course` 课程 ID（默认 11881）、`-t/--threads` 并发数、
`-r/--raw-dir` 样本目录（默认仓库根目录 `Raw/`，也可用 `AUTOCC_RAW_DIR`）。

账号文件格式（`accounts.json` 只是模板，真实账号请写在别处并确保已被忽略）：

```json
[
  {"username": "user@example.com", "password": "secret"}
]
```

运行时会在本目录生成 `queue.json` / `failed.json`（含明文账号，已被 `.gitignore` 忽略，
**不要提交**）。`price_calculator.py` 复用 `replayer.py` 的登录与进度查询逻辑，
按「未完成比例 × 基准价」报价。

# autocc-cli — v1 抓包 + 首次完成（Selenium + mitmproxy）

用 Selenium 驱动 Edge 打开云校园，手动/自动完成一遍 H5P 任务；
mitmproxy 在中间拦截 `info=core_xapi_statement_post` 请求，把答案改成标准答案、
分数改成满分、时长改成随机 15~20 秒，并把改好的请求存成 `Raw/<任务ID>.npy`，
之后就可以用 `legacy/cc-replayer` 或 Web 端批量重放。

## 安装

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

mitmproxy 需要信任其根证书才能解密 HTTPS。**首次运行** mitmproxy 后，
把 `~/.mitmproxy/mitmproxy-ca-cert.cer` 安装到系统/浏览器的「受信任的根证书颁发机构」。
（仓库不再附带别人生成的 CA 证书，请用自己机器生成的。）

## 配置账号

三种方式任选其一，源码里不保存任何账号：

1. **环境变量**（推荐，不留痕迹）
   ```bash
   AUTOCC_ACCOUNTS='user1@example.com:pass1;user2@example.com:pass2' python Start.py
   ```
2. **accounts.txt / userdata.txt**（每行 `账号:密码`）
   ```bash
   cp accounts.example.txt accounts.txt && vim accounts.txt
   ```
3. **user_information.ini**
   ```bash
   cp user_information.example.ini user_information.ini && vim user_information.ini
   ```

以上都没有时，程序会交互式询问并写入 `user_information.ini`。
`accounts.txt`、`userdata.txt`、`user_information.ini` 都已被 `.gitignore` 忽略。

## Edge 驱动

默认交给 **Selenium Manager** 自动下载匹配的 `msedgedriver`。
如需手动指定，设置环境变量 `EDGEDRIVER_PATH=/path/to/msedgedriver`。

## 运行

```bash
python Start.py
# 1 查询用户进度 / 2 首次完成（抓包产样）/ 3 重复发包
```

抓到的样本默认写到仓库根目录的 `Raw/`（`AUTOCC_RAW_DIR` 可改）。
样本属于个人会话数据，不要提交到版本库。

## 文件说明

| 文件 | 作用 |
|---|---|
| `Start.py` | 菜单入口 |
| `config.py` | 驱动、ini、共享状态、`RAW_DIR` |
| `login.py` | 登录并抓取 Cookie / `sesskey` / 昵称；账号来源见上 |
| `mitm.py` | mitmproxy 拦截、改包、落盘 `Raw/<ID>.npy` |
| `select_cell.py` / `select_assignment.py` | 选课、挑选待完成任务 |
| `finish_assignment.py` / `question_set/*` | 按题型（单选/判断/填空/摘要/找词）作答 |
| `resend.py` / `send_package.py` / `change.py` | 复用样本重新发包 |
| `query.py` | 查询进度 |
| `initialize.py` | 交互式写入账号配置 |

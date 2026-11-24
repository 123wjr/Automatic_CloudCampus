# Automatic CloudCampus · 云校园任务自动化

把云校园（CloudCampus / Moodle）里重复的 H5P 任务自动化：**登录 → 查询进度 → 按完成比例付费 → 自动阅读页面 + 重放发包**。
主线是一个 FastAPI + Vue 3 的 Web 服务，`legacy/` 与 `tools/` 下保留了两套旧版 CLI 和一个 Android 环境光小工具。

> 仅用于个人学习与技术研究。请遵守目标站点的服务条款，使用本项目的风险由使用者自行承担。

---

## ⚠️ 安全须知（请先读这一段）

本仓库的历史版本里**曾经**提交过真实凭据，包括但不限于：

- `user_information.ini`（云校园账号 + 明文密码）
- 硬编码在 `login.py` 里的第二组账号密码
- `failed.json`、调试 notebook 中的真实 Cookie / `sesskey`
- 服务器地址与管理员口令

当前仓库已经**重建 git 历史**（旧提交全部丢弃），上述文件与内容都不再存在，并且已加入 `.gitignore`。
但 git 历史一旦被公开过就无法收回，因此：

1. **如果你的账号曾出现在旧仓库里，请立刻修改云校园密码**；
2. 如曾使用过旧仓库里的管理员口令 / 支付密钥，也请一并轮换；
3. 提交前请确认 `git status` 里没有 `.env`、`Raw/*.npy`、`*.db`、`user_information.ini`、`failed.json`。

安全问题请参考 [SECURITY.md](SECURITY.md)。

---

## 功能概览

| 模块 | 说明 |
|---|---|
| 用户登录 | 用云校园账号登录，服务端换取 Cookie / `sesskey` / 昵称 |
| 进度查询 | 解析成绩页，列出未完成任务及占比，判断是否已有抓包样本 |
| 计费 | 按「未完成比例 × 基准单价」计算金额，支持易支付（zpayz）扫码与福利码 |
| 自动执行 | 后台线程分两阶段：先 `visit` 逐个访问任务页，再 `replay` 重放发包，WebSocket 实时推送双进度条 |
| 管理后台 | 统计、客户、访客、课程、排除任务、支付设置、福利码、日志 |
| 旧版 CLI | `legacy/autocc-cli`（Selenium + mitmproxy 抓包改包）、`legacy/cc-replayer`（rich TUI 多账号批量重放） |
| 附属工具 | `tools/auto-dark-mode`（Android 环境光自动暗黑） |

## 目录结构

```
.
├── backend/                  FastAPI 服务端
│   ├── app/
│   │   ├── main.py           应用入口、静态资源托管
│   │   ├── config.py         配置（pydantic-settings，读取根目录 .env）
│   │   ├── database.py       SQLite + SQLAlchemy
│   │   ├── models/           数据模型与 Pydantic schema
│   │   ├── routes/           auth / tasks / payment / ws / admin
│   │   ├── services/         cloudcampus / replayer / task_job / payment
│   │   └── middleware.py     登录限流
│   ├── requirements.txt
│   └── run.py                本地开发入口（uvicorn --reload）
├── frontend/                 Vue 3 + Vite
│   ├── src/{views,components,stores,services,router}
│   ├── package.json
│   └── vite.config.js
├── tests/                    测试脚本（离线 / 联网两类）
├── deploy/                   nginx.conf 与 systemd 单元示例
├── Raw/                      .npy 发包样本（不入库，仅保留说明）
├── driver/                   浏览器驱动目录（仅旧版 CLI 需要，不入库）
├── legacy/
│   ├── autocc-cli/           v1：Selenium + mitmproxy
│   └── cc-replayer/          v1.5：多账号批量重放 CLI
├── tools/
│   └── auto-dark-mode/       AutoDark Android 工程 + 主机侧监控脚本
├── ARCHITECTURE.md           架构与数据流说明
├── SECURITY.md               安全策略
├── Dockerfile                多阶段构建（前端 → 运行时）
├── docker-compose.yml
└── .env.example              环境变量模板
```

## 快速开始

### 方式一：Docker Compose（最简单）

```bash
cp .env.example .env     # 按需填写管理员、支付等配置；不填也能启动
docker compose up -d --build
# 打开 http://127.0.0.1:8000
```

`docker-compose.yml` 会把 `./Raw` 与 `./backend/data` 挂进容器，重建镜像不会丢数据和样本。

### 方式二：本地开发

后端（建议 Python 3.11 / 3.12）：

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
cd backend && python run.py          # http://127.0.0.1:8000
```

前端（Node 20+）：

```bash
cd frontend
npm install
npm run dev                          # http://127.0.0.1:5173，已配置 /api 与 /ws 代理
npm run build                        # 产物在 frontend/dist，后端启动时会自动托管
```

### 准备发包样本（Raw/）

`replay` 阶段依赖 `Raw/<任务ID>.npy`（原始请求的 URL / headers / body）。

- 样本由 `legacy/autocc-cli` 的 mitmproxy 抓包生成，或从可信来源拷贝；
- 样本是**个人会话数据**，默认被 `.gitignore` 忽略，不要提交；
- 没有样本时仍可登录与查询进度，只是无法自动完成。

## 配置

所有配置都在仓库根目录的 `.env` 中（已被忽略），字段与 `backend/app/config.py` 的 `Settings` 同名；
同时也兼容历史的 `AUTOCC_` 前缀写法（例如 `AUTOCC_ADMIN_PASSWORD` 等价于 `ADMIN_PASSWORD`）。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | 空 | 管理后台账号；`ADMIN_PASSWORD` 为空时后台登录校验关闭 |
| `CORS_ORIGINS` | 空 | 允许的前端来源，逗号分隔；空则仅本地开发地址 |
| `TRUSTED_HOST` | 空 | 允许的 Host 头；空表示不限制 |
| `RATE_LIMIT_LOGIN` / `RATE_LIMIT_WINDOW` | 5 / 60 | 登录限流次数 / 窗口（秒） |
| `PAYMENT_PID` / `PAYMENT_KEY` | 空 | 易支付商户号与密钥；为空则支付功能关闭 |
| `PAYMENT_SITENAME` / `PAYMENT_BASE_PRICE` | AutoCC / 20 | 站点名称、基准单价 |
| `PAYMENT_NOTIFY_PATH` / `PAYMENT_RETURN_URL` | 空 | 支付回调与跳转地址（必须是公网 HTTPS） |
| `CLOUDCAMPUS_BASE` | https://www.cloudcampus.com.cn | 目标站点 |
| `DEFAULT_COURSE_ID` | 11881 | 默认课程 ID |
| `DEFAULT_EXCLUDED_TASKS` | 空 | 默认排除的任务 ID，逗号分隔 |
| `CONTACT_EMAIL` | support@example.com | 前端展示的客服邮箱 |

运行时数据：

- `backend/data/app.db` — SQLite 数据库（订单 / 福利码 / 日志），不入库；
- `Raw/*.npy` — 发包样本，不入库。

## HTTP 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/login` | 用户登录云校园 |
| POST | `/api/auth/admin/login` | 管理后台登录 |
| GET | `/api/tasks/progress/{session_id}` | 查询进度与任务状态 |
| POST | `/api/tasks/retry/{session_id}` | 重试失败任务 |
| POST | `/api/payment/create` | 创建支付订单 |
| POST | `/api/payment/redeem` | 使用福利码 |
| GET/POST | `/api/payment/notify` | 支付回调 |
| WS | `/ws/progress/{session_id}` | 实时进度推送 |
| GET | `/api/admin/*` | 统计、客户、访客、课程、排除任务、支付设置、福利码、日志 |
| GET | `/api/health`、`/api/config/public` | 健康检查、公开配置 |

## 测试

```bash
pip install -r backend/requirements-dev.txt          # 含 pytest / httpx
python3 -m pytest tests -q --ignore=tests/test_e2e.py --ignore=tests/test_concurrent.py
python3 -m pytest tests/test_security.py -q          # 只跑敏感信息回归
```

离线用例共 21 个（含 `tests/conftest.py` 自动建表，不依赖 `backend/data/app.db` 是否已存在）。

联网集成脚本（`tests/test_e2e.py`、`tests/test_concurrent.py`）需要真实账号，凭据一律从环境变量读取，缺失时自动跳过：

```bash
TEST_ACCOUNT=you@example.com TEST_PASSWORD='your_password' \
AUTOCC_ADMIN_PASSWORD='admin_password' python3 tests/test_e2e.py
```

> 注意：请用一次性/测试账号运行联网脚本，不要把真实凭据写进任何文件。

## 部署（systemd + nginx）

```bash
git clone <your-repo> /opt/automatic-cloudcampus && cd /opt/automatic-cloudcampus
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
cp .env.example .env && vim .env          # 填写域名、管理员口令、支付参数
cd frontend && npm ci && npm run build && cd ..
mkdir -p logs

sudo cp deploy/autocc.service /etc/systemd/system/autocc.service   # 记得改 User/路径
sudo cp deploy/nginx.conf /etc/nginx/conf.d/automatic-cloudcampus.conf  # 记得改域名与证书
sudo systemctl daemon-reload && sudo systemctl enable --now autocc
sudo nginx -t && sudo systemctl reload nginx
```

## 旧版工具

| 目录 | 说明 |
|---|---|
| [`legacy/autocc-cli`](legacy/autocc-cli/README.md) | v1 CLI：Selenium 驱动 + mitmproxy 拦截改包，负责**首次完成**并产出 `Raw/*.npy` |
| [`legacy/cc-replayer`](legacy/cc-replayer/README.md) | v1.5 CLI：rich TUI，多账号并发重放，含计价器 |
| [`tools/auto-dark-mode`](tools/auto-dark-mode/README.md) | Android 环境光自动暗黑 + 主机侧 adb 监控脚本 |

## 常见问题

- **打开首页 503 / 只有 API**：前端未构建，执行 `cd frontend && npm run build`。
- **支付回调收不到**：`PAYMENT_NOTIFY_PATH` 必须是公网 HTTPS 地址，且 nginx 已正确转发 `/api/payment/notify`。
- **登录一直失败**：确认账号密码正确；站点改版会导致解析失效，需要更新 `services/cloudcampus.py`。
- **任务进度不动**：先确认 `Raw/` 里有对应任务的 `.npy` 样本。
- **管理后台进不去**：检查 `.env` 的 `ADMIN_PASSWORD`（为空时校验关闭，但生产环境请务必设置）。

## 许可证

[GPL-3.0](LICENSE)

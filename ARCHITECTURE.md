# 项目架构文档

> 本文档描述 **Web 版（当前主线）** 的架构。`legacy/` 下的两套旧版 CLI 与
> `tools/auto-dark-mode/` 是独立的辅助工具，不参与 Web 端的运行时链路，见各自的 README。

## 整体架构

```
┌──────────────────────────────────────────────────────────────────┐
│                          用户浏览器                               │
│  ┌──────────────────────┐     ┌────────────────────────────────┐ │
│  │   LoginView.vue       │     │   DashboardView.vue             │ │
│  │   登录表单             │     │   ┌──────────────────────┐     │ │
│  └──────────────────────┘     │   │  TaskList.vue          │     │ │
│                               │   │  任务列表（可滚动）     │     │ │
│                               │   └──────────────────────┘     │ │
│                               │   ┌──────────────────────┐     │ │
│                               │   │  ProgressPanel.vue     │     │ │
│                               │   │  双进度条 (visit/replay)│     │ │
│                               │   └──────────────────────┘     │ │
│                               │   ┌──────────────────────┐     │ │
│                               │   │  PaymentModal.vue      │     │ │
│                               │   │  二维码/福利码/确认支付│     │ │
│                               │   └──────────────────────┘     │ │
│                               └────────────────────────────────┘ │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  AdminPanel.vue  管理面板                                  │   │
│  │  统计 | 客户 | 访客 | 课程 | 排除任务 | 支付设置 | 福利码 | 日志│   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────┬───────────────────────────────────────┘
                           │ HTTP + WebSocket
┌──────────────────────────┴───────────────────────────────────────┐
│                      Nginx (80/443)                              │
│                  proxy_pass → localhost:8888                      │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────┴───────────────────────────────────────┐
│                   FastAPI + Uvicorn (:8888)                       │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Routes (API 层)                                             │ │
│  │                                                              │ │
│  │  auth.py     ─── POST /api/auth/login, /admin/login         │ │
│  │  tasks.py    ─── GET  /api/tasks/progress/{sid}             │ │
│  │  payment.py  ─── POST /api/payment/create, /redeem, /notify │ │
│  │                GET  /api/payment/status/{id}                 │ │
│  │  ws.py       ─── WS   /ws/progress/{sid}                    │ │
│  │  admin.py    ─── GET  /api/admin/stats, /customers,         │ │
│  │                       /visitors, /logs, /welfare-codes, ... │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Services (业务层)                                           │ │
│  │                                                              │ │
│  │  task_job.py     ─── 后台任务管理器 (visit → replay)          │ │
│  │  payment.py      ─── zpayz 支付 + 订单管理                    │ │
│  │  replayer.py     ─── 包回放引擎 (Raw/.npy → HTTP POST)       │ │
│  │  cloudcampus.py  ─── 云校园 HTTP 登录 + 进度查询              │ │
│  │  middleware.py    ─── 登录限流                                │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Models (数据层)                                             │ │
│  │  db_models.py   ─── PaymentOrder, WelfareCode, TaskLog, ... │ │
│  │  schemas.py     ─── Pydantic 请求/响应模型                   │ │
│  │  database.py    ─── SQLite + SQLAlchemy                      │ │
│  │  config.py      ─── 环境变量配置                              │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

## 核心数据流

### 用户完整流程
```
1. Login            POST /auth/login
   ↓                cloudcampus.login() → HTTP 登录云校园
   ↓                获取 cookie, sesskey, user_id → 存入 user_sessions

2. Query Progress   GET /tasks/progress/{sid}
   ↓                cloudcampus.query_progress() → 解析成绩页面
   ↓                replayer.check_packets_exist() → 查 Raw/*.npy

3. Payment/Welfare  POST /payment/create  → zpayz 生成二维码
   ↓                POST /payment/redeem  → 福利码验证

4. Auto Start       confirm_payment() → job_manager.mark_paid()
   ↓                → 创建 Job → 后台线程执行

5. Execute          线程中:
   ↓                Phase 1: visit_task_pages()  → HTTP GET 页面
   ↓                Phase 2: replay_all()        → HTTP POST 发包

6. Progress         WebSocket /ws/progress/{sid}
                    实时推送双进度条 (阅读/发包)
```

### 支付 → 执行 流程
```
createOrder()                confirm_payment()
     ↓                              ↓
 _pending_orders[oid]        order["paid"] = True
     ↓                              ↓
 _save_order_to_db()         _mark_order_paid_in_db()
                                  ↓
                             job_manager.mark_paid()
                                  ↓
                             create() → start() → _run_job()
```

### 断线恢复流程
```
刷新页面 → DashboardView.mounted()
  → fetchProgress() → GET /tasks/progress/{sid}
  → 返回 job: {visit_progress, replay_progress, status}
  → 前端检测 status=running → 自动连 WebSocket
  → WebSocket 检测已有 job → _stream_job_progress()
  → 每 0.5s 推送最新进度 → 前端更新双进度条
```

## 关键设计决策

| 决策 | 原因 |
|---|---|
| 移除了 Selenium | chromedriver 不稳定，HTTP 请求足以完成所有操作 |
| visit 在 replay 之前 | 云校园需要先 registered view 才能接受 grade |
| 日志批量写入 | 避免高频 SQLite write 锁竞争 + killall 导致 DB 损坏 |
| `_pending_orders` 内存 + DB 双写 | 服务器重启后从 DB 恢复，防止付钱不做 |
| `fulfilled` 字段 | 区分"已付待执行"和"已完成"，支撑管理员预警 |
| 双进度条 (visit/replay) | 访问阶段 cookie 可能过期，用户需要看到哪个阶段出了问题 |

## 数据库表 (SQLite)

| 表 | 用途 |
|---|---|
| `payment_orders` | 支付订单 (paid, fulfilled, is_welfare) |
| `payment_config` | key-value 配置 (pid, key, base_price, contact_email) |
| `welfare_codes` | 福利码 (code, used, used_by, used_at) |
| `task_logs` | 任务执行日志 (nickname, title, phase, status) |
| `visit_logs` | 独立访客 (visitor_id UNIQUE) |
| `excluded_tasks` | 排除任务 URL 前缀 |
| `course_config` | 课程配置 |

## 代码结构

```
Automatic_CloudCampus/
├── backend/          FastAPI 服务（app/、requirements.txt）
├── frontend/         Vue 3 + Vite 前端（src/、package.json）
├── tests/            离线/联网测试脚本
├── deploy/           systemd 单元与 nginx 反向代理示例
├── Raw/              .npy 发包样本（不入库，只保留 README）
├── driver/           浏览器驱动目录（仅旧版 CLI 需要，不入库）
├── legacy/
│   ├── autocc-cli/   v1 CLI：Selenium + mitmproxy 抓包改包
│   └── cc-replayer/  v1.5 CLI：rich TUI 多账号批量重放
└── tools/
    └── auto-dark-mode/  AutoDark Android 工程 + 主机侧环境光监控脚本
```

## 部署

```bash
# 示例部署路径（可按需修改 deploy/autocc.service 中的值）
/opt/automatic-cloudcampus/
├── backend/          FastAPI
├── frontend/dist/    Vue 构建产物
├── deploy/
│   ├── autocc.service   systemd 单元
│   └── nginx.conf       nginx 反向代理
├── .env              环境变量 (密钥不提交)
├── Raw/              .npy 发包数据 (不提交)
└── logs/
    └── uvicorn.log

# 管理命令
systemctl start|stop|restart|status autocc
tail -f /opt/automatic-cloudcampus/logs/uvicorn.log
```

## Session 结构

登录成功后写入内存的 session dict 字段：

```python
{
    "nickname": nickname,
    "user_id": user_id,
    "cookie": cookie_str,
    "sesskey": sesskey,
    "password": password,
    "_ts": timestamp,
}
```
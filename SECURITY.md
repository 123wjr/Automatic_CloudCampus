# 安全策略

## 报告问题

如果发现安全漏洞、或者发现仓库里仍然残留凭据，请**不要**直接开公开 issue，
用邮件联系维护者（见仓库首页的客服邮箱），或使用 GitHub 的 “Report a vulnerability” 私密通道。

## 本仓库的敏感信息边界

以下内容**永远不进入版本库**（均已写入 `.gitignore`）：

| 类型 | 路径示例 |
|---|---|
| 环境变量 / 密钥 | `.env`、`.env.local` |
| 云校园账号密码 | `user_information.ini`、`accounts.txt`、`userdata.txt` |
| 抓包与会话数据 | `Raw/*.npy`、`legacy/cc-replayer/queue.json`、`failed.json` |
| 运行时数据库 | `backend/data/*.db` |
| 体积过大的二进制 | `driver/msedgedriver`、`*.apk` |

`tests/test_security.py` 会静态扫描源码，确保历史泄露的密码字面量不会再次出现，
同时校验管理员登录与支付签名使用 `hmac.compare_digest` 做常量时间比较。

## 历史泄露说明

本仓库的历史曾经包含真实凭据，现已通过**重建 git 历史**清除。
git 历史一旦公开就无法真正撤回，因此**所有曾经出现在旧仓库里的账号密码、管理员口令、
支付密钥都应视为已泄露并立即轮换**。

## 部署建议

- 生产环境必须设置 `ADMIN_PASSWORD`（为空时后台登录校验是关闭的）；
- 通过 nginx 终结 TLS，只把 `127.0.0.1:8000` 暴露给反代；
- `.env` 权限设为 `600`，不要提交、不要放进镜像；
- 定期备份 `backend/data/app.db` 并限制其读权限（内含订单与日志）。

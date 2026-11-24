"""
包回放引擎 — 截获的 xAPI 满分包重放
═══════════════════════════════════════════════════════════

核心逻辑:
  Step 1: 读取 Raw/{task_id}.npy 文件（mitm.py 截获的原始 xAPI 请求）
  Step 2: _rewrite_packet() 替换包中的用户身份（name, account, cookie, sesskey）
  Step 3: requests.post() 发送到云校园服务器

发包流程 ──→ replay_all():
  for each task:
    ┌──────────────────────────────────────────────┐
    │  1. task_id = url.split("id=")[-1]            │  ← 提取任务ID
    │  2. np.load(f"Raw/{task_id}.npy")             │  ← 读取截获的请求包
    │  3. _rewrite_packet(packet, user_info)        │  ← 替换用户身份
    │     ├─ actor.name    → user_info["nickname"]  │
    │     ├─ actor.account → user_info["user_id"]   │
    │     ├─ Cookie header → user_info["cookie"]    │
    │     └─ sesskey param → user_info["sesskey"]   │
    │  4. requests.post(url, headers, json=body)    │  ← 发送篡改包
    │  5. 检查 response: 200 + "error":false        │  ← 成功标志
    │  6. progress_callback({current,total,...})    │  ← 推送进度
    └──────────────────────────────────────────────┘

页面访问 ──→ visit_task_pages():
  for each task:
    ┌──────────────────────────────────────────────┐
    │  1. requests.Session() 维持 cookie            │  ← 跨请求保持会话
    │  2. session.get(task_url)                     │  ← 模拟页面浏览
    │  3. 云校园 JS 检测到访问 → 标记 "viewed"       │
    │  4. progress_callback()                       │
    └──────────────────────────────────────────────┘

check_packets_exist():
  用于查询进度时检查哪些任务有对应的 Raw/.npy 文件
  返回的 has_packet 字段决定任务是否出现在可执行列表中
"""

import asyncio
import numpy as np
import requests
import json
import re
from pathlib import Path
from typing import Callable, List, Optional

from requests import Session, Response

from app.config import RAW_DIR, MANUAL_MARK_URL, USER_AGENT
from app.services.cloudcampus import login

# 注意: user_sessions 在 re_login() 内部按需 import，避免
# auth → task_job → replayer → auth 的模块级循环导入。


def _task_title_url(task) -> tuple[str, str]:
    """规范化任务条目: 既支持 dict {title,url} 也支持 (title, href) 元组。"""
    if isinstance(task, dict):
        return task.get("title", ""), task.get("url", "")
    if isinstance(task, (tuple, list)) and len(task) >= 2:
        return task[0], task[1]
    return "", ""


def _extract_task_id(task_url: str) -> str:
    """从 URL 提取任务 id，容忍 id= 后还跟有其它 query 参数。"""
    if "id=" not in task_url:
        return task_url
    tail = task_url.split("id=")[-1]
    return re.split(r"[&#]", tail)[0]


async def replay_single_packet(task_id: str, user_info: dict) -> bool:
    npy_path = Path(RAW_DIR) / f"{task_id}.npy"
    if not npy_path.exists():
        return False

    original = np.load(str(npy_path), allow_pickle=True).item()
    modified = _rewrite_packet(original, user_info)

    try:
        resp = requests.post(
            url=modified["url"],
            headers=modified["headers"],
            json=modified["body"],
            timeout=15,
        )
        if resp.status_code == 200 and '"error":false' in resp.text:
            return True
        return False
    except requests.exceptions.RequestException:
        return False


def _rewrite_packet(packet: dict, user_info: dict) -> dict:
    body = packet["body"]
    requesttext = body[0]["args"]["requestjson"]
    requestjson = json.loads(requesttext)

    for item in requestjson:
        item["actor"]["name"] = user_info["nickname"]
        item["actor"]["account"]["name"] = user_info["user_id"]

    updated_requesttext = json.dumps(requestjson)
    body[0]["args"]["requestjson"] = updated_requesttext
    packet["body"] = body

    packet["headers"]["Cookie"] = user_info["cookie"]

    sesskey_pattern = r"(sesskey=)[^&\s\r\n]*"
    if re.search(sesskey_pattern, packet["url"]):
        packet["url"] = re.sub(
            sesskey_pattern,
            f"\\g<1>{user_info['sesskey']}",
            packet["url"],
        )

    return packet


async def replay_all(
    tasks: list[dict],
    user_info: dict,
    progress_callback: Optional[Callable] = None,
) -> dict:
    total = len(tasks)
    success = 0
    failed = 0
    results = []

    # 构建 Session
    cookie_str = user_info.get("cookie", "")
    ses = build_ses(cookie_str)

    for i, task in enumerate(tasks):
        for retry in range(2):
            task_url = task["url"]
            task_id = task_url.split("id=")[-1]

            if progress_callback:
                progress_callback(
                    {
                        "current": i + 1,
                        "total": total,
                        "title": task["title"],
                        "status": "processing",
                        "message": f"正在处理 {task['title']}...",
                    }
                )

            # 我先访问一下
            resp = ses.get(task_url, allow_redirects=True, timeout=15)

            ok = (
                await replay_single_packet(task_id, user_info)
                and resp.status_code == 200
            )
            await asyncio.sleep(1.5)

            if ok:
                success += 1
                status = "success"
                message = f"{task['title']} 发包成功"
                results.append(
                    {
                        "title": task["title"],
                        "status": status,
                        "message": message,
                    }
                )

                # 退出尝试
                break

            # 如果失败了重新登录，并把新 cookie 同步到会话 jar 再重试
            user_info = await re_login(user_info)
            apply_cookies(ses, user_info.get("cookie", ""))

            if retry == 1:
                failed += 1
                status = "failed"
                message = f"{task['title']} 发包失败"
                results.append(
                    {
                        "title": task["title"],
                        "status": status,
                        "message": message,
                    }
                )
        if progress_callback:
            progress_callback(
                {
                    "current": i + 1,
                    "total": total,
                    "title": task["title"],
                    "status": results[-1]["status"],
                    "message": results[-1]["message"],
                }
            )

    return {
        "total": total,
        "success": success,
        "failed": failed,
        "results": results,
    }


async def re_login(user_info: dict) -> dict:
    """
    刷新登录态（任务/前端会话唯一的 cookie 刷新入口）。

    失败时返回原 user_info（不抛异常），让上层按发包失败处理，而不是把整个
    Job 打挂。成功时**原地更新** user_info（cookie/sesskey 等），因此调用方
    持有的同一份 dict —— 即 job.user_info —— 在后续阶段（mark 等）也会用上新
    cookie；并把同一引用写回全局 user_sessions，让前端 get_progress 使用的
    会话保持一致，不会出现任务刷新后前端仍拿旧 cookie 的情况。
    """
    import time

    account = user_info.get("account") or user_info.get("user_id", "")
    password = user_info.get("password", "")
    if not account or not password:
        return user_info

    try:
        fresh = login(account, password)
    except Exception:
        fresh = None

    if not fresh or not fresh.get("cookie"):
        return user_info

    # 原地合并新的 cookie/sesskey，保持与 job.user_info / user_sessions 同一引用
    user_info.update(fresh)
    user_info["account"] = account
    user_info["password"] = password
    user_info["_ts"] = time.time()

    # 同步全局登录会话（按邮箱 account 索引，与 auth 一致）
    # 延迟 import 打破模块级循环导入（见文件顶部说明）
    from app.routes.auth import user_sessions

    user_sessions[account] = user_info
    return user_info


def check_packets_exist(tasks: list[dict]) -> list[dict]:
    result = []
    for task in tasks:
        task_url = task["url"]
        task_id = task_url.split("id=")[-1]
        npy_path = Path(RAW_DIR) / f"{task_id}.npy"
        task["has_packet"] = npy_path.exists()
        result.append(task)
    return result


async def visit_task_pages(
    tasks: list[dict],
    user_info: dict,
    progress_callback: Optional[Callable] = None,
) -> dict:
    total = len(tasks)
    visited = 0
    failed = 0
    cookie_str = user_info.get("cookie", "")

    ses = build_ses(cookie_str)
    try:
        for i, task in enumerate(tasks):
            url = task["url"]
            title = task["title"]

            if progress_callback:
                progress_callback(
                    {
                        "current": i + 1,
                        "total": total,
                        "title": title,
                        "status": "visiting",
                        "message": f"正在访问 {title}...",
                    }
                )

            try:
                for retry in range(2):
                    resp = ses.get(url, allow_redirects=True, timeout=15)
                    if resp.status_code == 200:
                        visited += 1
                        status = "visited"
                        message = f"已访问 {title}"
                        break

                    # 重试前刷新登录态，并把新 cookie 同步到会话 jar
                    user_info = await re_login(user_info)
                    apply_cookies(ses, user_info.get("cookie", ""))

                    if retry == 1:
                        failed += 1
                        status = "visit_failed"
                        message = f"访问 {title} 失败"

            except requests.exceptions.RequestException:
                failed += 1
                status = "visit_failed"
                message = f"访问 {title} 网络错误"

            if progress_callback:
                progress_callback(
                    {
                        "current": i + 1,
                        "total": total,
                        "title": title,
                        "status": status,
                        "message": message,
                    }
                )

            await asyncio.sleep(0.3)
    finally:
        ses.close()

    return {
        "total": total,
        "visited": visited,
        "failed": failed,
    }


async def manual_set_done(
    tasks: List[dict],
    user_info: dict,
    progress_callback: Optional[Callable] = None,
) -> dict:
    total = len(tasks)
    visited = 0
    failed = 0

    cookie_str = user_info.get("cookie", "")
    ses = build_ses(cookie_str)
    try:
        for i, task in enumerate(tasks):
            title, task_url = _task_title_url(task)
            task_id = _extract_task_id(task_url)

            if progress_callback:
                progress_callback(
                    {
                        "current": i + 1,
                        "total": total,
                        "title": title,
                        "status": "setting",
                        "message": f"正在标记 {title} 为已完成...",
                    }
                )

            try:
                resp = mark_single_task(user_info, task_id, ses=ses)

                # Moodle service.php 失败也返回 200，错误信息在响应体里，
                # 必须看 "error":false 才算真正成功，否则会把失败误记为成功。
                if resp.status_code == 200 and '"error":false' in resp.text:
                    visited += 1
                    status = "set_done"
                    message = f"已标记 {title} 为已完成"
                else:
                    failed += 1
                    status = "set_failed"
                    message = f"标记 {title} 失败"
            except requests.exceptions.RequestException:
                failed += 1
                status = "set_failed"
                message = f"标记 {title} 网络错误"

            if progress_callback:
                progress_callback(
                    {
                        "current": i + 1,
                        "total": total,
                        "title": title,
                        "status": status,
                        "message": message,
                    }
                )

            await asyncio.sleep(0.3)
    finally:
        ses.close()

    return {
        "total": total,
        "visited": visited,
        "failed": failed,
        "success": visited,
    }


def mark_single_task(
    user_info: dict, task_id: str, ses: Optional[Session] = None
) -> Response:
    sesskey = user_info.get("sesskey", "")

    # 构建 POST 参数
    post_url = MANUAL_MARK_URL
    query_params = {
        "sesskey": sesskey,
        "info": "core_completion_update_activity_completion_status_manually",
    }

    # 复用调用方传入的 session（批量标记时只建一个连接池），
    # 没有则临时建一个并在用完后关闭，避免泄漏 socket。
    own_session = ses is None
    if own_session:
        ses = build_ses(user_info.get("cookie", ""))

    # Moodle 的 /lib/ajax/service.php 期望请求体是「方法调用数组」而非单个对象；
    # 传裸 dict 会让它按对象的 key 迭代，methodname 解析为空 → external_functions
    # 查不到记录(invalidrecord)。必须包成 list。
    content = [
        {
            "index": 0,
            "methodname": "core_completion_update_activity_completion_status_manually",
            "args": {"cmid": str(task_id), "completed": True},
        }
    ]

    try:
        resp = ses.post(
            post_url,
            params=query_params,
            json=content,
            allow_redirects=True,
            timeout=15,
        )
    finally:
        if own_session:
            ses.close()

    return resp


def apply_cookies(ses: Session, cookie_str: str) -> None:
    """
    用 cookie 字符串覆盖会话的 cookie jar。

    re_login() 刷新的是 user_info["cookie"] 字符串，而 requests.Session 自带
    独立的 cookie jar 不会随之更新；重试前必须调用本函数把新 cookie 同步到
    ses，否则 ses.get() 仍用旧 cookie，重试无意义。
    """
    ses.cookies.clear()
    for cookie_item in cookie_str.replace("; ", ";").split(";"):
        cookie_item = cookie_item.strip()
        if not cookie_item or "=" not in cookie_item:
            continue
        name, value = cookie_item.split("=", 1)
        ses.cookies.set(name.strip(), value.strip())


def build_ses(cookie_str: str) -> Session:
    ses = requests.Session()
    ses.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
    )
    apply_cookies(ses, cookie_str)
    return ses

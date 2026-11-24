"""
认证路由 — 用户登录、管理员登录
═══════════════════════════════════════════════════════════

数据结构:
  user_sessions: {email: {nickname, user_id, cookie, sesskey, password}}
  admin_tokens:  set of UUID strings

  user_sessions 是内存字典，服务器重启后清空
  前端通过 localStorage 持久化 session_id，刷新页面后重新请求

登录流程:
  POST /api/auth/login {account, password}
    → cloudcampus.login() HTTP 请求云校园
    → 成功: 存入 user_sessions[account]
    → 返回 {session_id:account, nickname, user_id}

管理员:
  POST /api/auth/admin/login {username, password}
        → 比对环境变量 ADMIN_USERNAME/ADMIN_PASSWORD
    → 生成 UUID token 加入 admin_tokens
"""

import time
import uuid
import hmac
import logging
from fastapi import APIRouter, HTTPException, Request
from app.models.schemas import LoginRequest, AdminLoginRequest
from app.services.cloudcampus import login, query_resend, get_course_list
from app.middleware import get_login_limiter, get_admin_limiter
from app.services.task_job import job_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])
user_sessions: dict[str, dict] = {}
SESSION_TTL_SECONDS = 2 * 3600


def _cleanup_expired_sessions():
    now = time.time()
    expired = [
        k
        for k, v in list(user_sessions.items())
        if now - v.get("_ts", 0) > SESSION_TTL_SECONDS
    ]
    for k in expired:
        user_sessions.pop(k, None)


def get_user_session(session_id: str) -> dict | None:
    _cleanup_expired_sessions()
    session = user_sessions.get(session_id)
    if session:
        if time.time() - session.get("_ts", 0) > SESSION_TTL_SECONDS:
            user_sessions.pop(session_id, None)
            return None
        session["_ts"] = time.time()
    return session


admin_tokens: dict[str, float] = {}

TOKEN_TTL_SECONDS = 24 * 3600


def _cleanup_expired_tokens():
    now = time.time()
    expired = [t for t, exp in list(admin_tokens.items()) if now > exp]
    for t in expired:
        admin_tokens.pop(t, None)


def is_admin_valid(token: str) -> bool:
    _cleanup_expired_tokens()
    exp = admin_tokens.get(token)
    if exp is None:
        return False
    if time.time() > exp:
        admin_tokens.pop(token, None)
        return False
    return True


@router.post("/login")
async def auth_login(req: LoginRequest, request: Request):
    await get_login_limiter()(request)
    session_id = req.account

    # 该账号已有进行中的任务时，复用任务持有的登录态而不重新登录：
    # 重新登录会让云校园颁发新会话、使任务正在使用的 cookie 失效，从而打断
    # 后台任务（参见 job_manager.get_active）。
    active_job = job_manager.get_active(session_id)
    if active_job:
        stored_pwd = active_job.user_info.get("password", "")
        # 用任务里保存的密码做常量时间比较，避免跳过登录后被任意复用会话
        if not stored_pwd or not hmac.compare_digest(req.password, stored_pwd):
            raise HTTPException(status_code=401, detail="账号或密码不正确，请重新输入")
        # 与任务共享同一份登录信息：任务内部 re_login() 原地刷新 cookie 时会话
        # 随之更新，前端不会拿到过期 cookie。刷新 _ts 防止被 TTL 清理。
        active_job.user_info["_ts"] = time.time()
        user_sessions[session_id] = active_job.user_info
        return {
            "success": True,
            "session_id": session_id,
            "nickname": active_job.user_info.get("nickname", req.account),
            "user_id": active_job.user_info.get("user_id", ""),
            "ws_token": str(uuid.uuid4())[:16],
        }

    # 常规登录：请求云校园校验账号密码并获取新 cookie
    try:
        result = login(req.account, req.password)
    except Exception as e:
        logger.error(f"Login request failed for {req.account}: {e}")
        raise HTTPException(status_code=502, detail="云校园暂时无法访问，请稍后再试")

    if not result or not result.get("user_id"):
        raise HTTPException(status_code=401, detail="账号或密码不正确，请重新输入")

    result["password"] = req.password
    result["account"] = req.account
    result["_ts"] = time.time()
    user_sessions[session_id] = result

    return {
        "success": True,
        "session_id": session_id,
        "nickname": result["nickname"],
        "user_id": result["user_id"],
        "ws_token": str(uuid.uuid4())[:16],
    }


@router.post("/admin/login")
async def admin_login(req: AdminLoginRequest, request: Request):
    await get_admin_limiter()(request)

    from app.config import ADMIN_USERNAME, ADMIN_PASSWORD

    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="管理员账号未配置")
    # 常量时间比较，避免通过响应时间侧信道猜测用户名/密码
    user_ok = hmac.compare_digest(req.username, ADMIN_USERNAME)
    pass_ok = hmac.compare_digest(req.password, ADMIN_PASSWORD)
    if not (user_ok and pass_ok):
        raise HTTPException(status_code=401, detail="管理员账号或密码错误")
    token = str(uuid.uuid4())[:16]
    admin_tokens[token] = time.time() + TOKEN_TTL_SECONDS
    return {"success": True, "token": token, "username": req.username}


@router.post("/admin/logout")
async def admin_logout(token: str = ""):
    admin_tokens.pop(token, None)
    return {"success": True}


@router.get("/courses/{session_id}")
async def get_courses(session_id: str):
    session = get_user_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="会话已过期，请重新登录")
    courses = get_course_list(session["cookie"])
    return {"courses": courses}


@router.get("/logout/{session_id}")
async def auth_logout(session_id: str):
    user_sessions.pop(session_id, None)
    return {"success": True}

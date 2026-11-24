#!/usr/bin/env python
"""
安全回归测试 — 纯静态/离线。

防止真实凭据再次被硬编码进源码，并验证敏感比较使用常量时间。

运行: cd backend && python3 -m pytest ../tests/test_security.py -q
"""
import glob
import hashlib
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

REPO = os.path.join(os.path.dirname(__file__), "..")

# 历史泄漏的真实密钥(密码 / 管理密码)，绝不允许出现在任何源码里。
# 这里只保存 SHA-256 摘要，避免测试文件本身又把明文公开一遍。
#
# 注意: 对外客服邮箱不算密钥，但它曾被当作测试登录账号写死，
# 故下方单独校验测试脚本不得再把它写死为登录账号。
FORBIDDEN_SHA256 = {
    "355d89ae07d444df053f7cccfe022e966e1ba6eb23176c5334e405ccb3533bac": "历史后台管理密码",
    "d9df9e4a01d9d3b7e58c09e782f5cd8b3fedcbbc0dbf88090e5973ad9effe32e": "历史后台管理密码(变体)",
}

# 仅在“测试脚本里被当作登录账号写死”这一语境下禁止的明文摘要
FORBIDDEN_IN_TESTS_SHA256 = {
    "530cd86bf21257f3d12d420fdd00f40c3d79fd4c93b894168a5eefcdb53d4aab": "客服邮箱",
}

# 源码里可能承载凭据的 token（标识符、引号内字符串、邮箱等）
_TOKEN_RE = re.compile(r"[A-Za-z0-9_!@.\-]{4,}")


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _find_forbidden_tokens(paths, digests):
    """逐 token 比对摘要，命中即返回可读报告（不回显明文）。"""
    hits = []
    for path in paths:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        for token in set(_TOKEN_RE.findall(text)):
            label = digests.get(_sha256(token))
            if label:
                hits.append(
                    f"{os.path.relpath(path, REPO)} 含 {label} 明文"
                    f"(sha256 前缀 {_sha256(token)[:8]})"
                )
    return hits


def _source_files():
    for base in ("backend/app", "tests"):
        for path in glob.glob(os.path.join(REPO, base, "**", "*.py"), recursive=True):
            if "__pycache__" in path:
                continue
            yield path


def test_no_hardcoded_known_credentials():
    """任何 .py 源码都不得包含历史泄漏的密码/管理密码明文。"""
    hits = _find_forbidden_tokens(_source_files(), FORBIDDEN_SHA256)
    assert not hits, "发现硬编码凭据:\n" + "\n".join(hits)


def test_test_scripts_do_not_hardcode_login_account():
    """测试脚本不得把客服邮箱当作登录账号写死(应从 env 读取)。"""
    paths = [
        p
        for p in glob.glob(os.path.join(REPO, "tests", "*.py"))
        if os.path.basename(p) != "test_security.py"
    ]
    hits = _find_forbidden_tokens(paths, FORBIDDEN_IN_TESTS_SHA256)
    assert not hits, "测试脚本硬编码登录账号:\n" + "\n".join(hits)


def test_integration_scripts_read_creds_from_env():
    """联网集成脚本必须从环境变量取凭据，且缺失时跳过(sys.exit(0))。"""
    for name in ("test_e2e.py", "test_concurrent.py"):
        path = os.path.join(REPO, "tests", name)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        assert "os.environ.get(\"TEST_ACCOUNT\"" in text, f"{name} 应从 env 读 TEST_ACCOUNT"
        assert "sys.exit(0)" in text, f"{name} 缺少凭据时应优雅跳过"


def test_admin_login_uses_constant_time_compare():
    """管理员登录应使用 hmac.compare_digest，而非 == 直接比较密码。"""
    path = os.path.join(REPO, "backend", "app", "routes", "auth.py")
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    assert "hmac.compare_digest" in text
    # 确认旧的明文 != 比较已移除
    assert "req.password != ADMIN_PASSWORD" not in text


def test_payment_sign_uses_constant_time_compare():
    """支付签名校验应使用 hmac.compare_digest。"""
    from app.services import payment as pay

    # 仍然 fail-closed：无 key 时返回 False
    orig = pay._get_key
    try:
        pay._get_key = lambda: ""
        assert pay.verify_notify_sign({"sign": "x"}) is False
    finally:
        pay._get_key = orig

    src_path = os.path.join(REPO, "backend", "app", "services", "payment.py")
    with open(src_path, "r", encoding="utf-8") as f:
        text = f.read()
    assert "hmac.compare_digest(expected, sign_param)" in text

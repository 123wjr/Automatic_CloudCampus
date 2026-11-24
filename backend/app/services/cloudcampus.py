"""
云校园 API 封装 — 登录、查询进度
═══════════════════════════════════════════════════════════

登录流程 ──→ login():
  ┌──────────────────────────────────────────────────────┐
  │  1. requests.get(cloudcampus.com.cn)                 │
  │     → 提取 <input name="logintoken">                 │
  │                                                     │
  │  2. requests.post(LOGIN_URL, {username,password,     │
  │                    logintoken})                       │
  │     → 检查响应中是否有 #loginerrormessage              │
  │                                                     │
  │  3. 成功 → 提取:                                     │
  │     ├─ nickname    ← #user-menu-toggle (清洗后缀)     │
  │     ├─ user_id     ← .d-inline-block href 中的 id=    │
  │     ├─ cookie      ← 所有 cookies 拼接为字符串        │
  │     └─ sesskey     ← 正则 \""sesskey\":\"...\"\""   │
  └──────────────────────────────────────────────────────┘

  注意: 仅使用 HTTP (requests) 登录，已移除 Selenium 后备

查询进度 ──→ query_progress():
  ┌──────────────────────────────────────────────────────┐
  │  1. 访问 /grade/report/user/index.php?id={course_id} │
  │  2. 解析 <tbody> 表格                                │
  │  3. 遍历所有行:                                      │
  │     ├─ 检查 span[title='H5P'] → 仅 H5P 任务          │
  │     ├─ 提取 title, url, percentage                   │
  │     ├─ 判断 completed (100.00%)                      │
  │     └─ 判断 excluded (黑名单匹配)                     │
  │  4. 返回 ALL 任务 (含已完成) + total_h5p_count        │
  └──────────────────────────────────────────────────────┘

  注意: 返回 ALL 任务而非仅未完成，因为计价总量需要包含已完成的
        有发包数据的那部分任务（不管已完成还是未完成）
"""

import re
import logging
import requests
from dataclasses import dataclass, field
import bs4
from bs4 import BeautifulSoup
from app.config import (
    CLOUDCAMPUS_BASE,
    LOGIN_URL,
    DEFAULT_COURSE_ID,
    GRADE_URL_TEMPLATE,
    USER_AGENT,
)

logger = logging.getLogger(__name__)


@dataclass
class CloudCampusSession:
    account: str
    password: str
    session: requests.Session = field(default_factory=requests.Session)
    nickname: str = ""
    user_id: str = ""
    cookie_str: str = ""
    sesskey: str = ""
    logged_in: bool = False

    @property
    def user_info(self) -> dict:
        return {
            "nickname": self.nickname,
            "user_id": self.user_id,
            "cookie": self.cookie_str,
            "sesskey": self.sesskey,
        }


def _clean_nickname(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"\s+", " ", raw)
    raw_clean = re.sub(r"\s*[A-Z]{2,3}$", "", raw).strip()
    return raw_clean if raw_clean else raw


def login_via_requests(account: str, password: str) -> dict | None:
    ses = requests.Session()
    ses.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
    )

    resp = ses.get(CLOUDCAMPUS_BASE, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    token_input = soup.find("input", {"name": "logintoken"})
    logintoken = token_input["value"] if token_input else ""

    login_data = {
        "username": account,
        "password": password,
        "logintoken": logintoken,
    }

    login_resp = ses.post(LOGIN_URL, data=login_data, timeout=15, allow_redirects=True)

    if (
        "loginerrormessage" in login_resp.text.lower()
        or "login/index.php" in login_resp.url
    ):
        return None

    soup = BeautifulSoup(login_resp.text, "lxml")
    user_menu = soup.find(id="user-menu-toggle")
    nickname = user_menu.get_text(strip=True) if user_menu else account
    nickname = _clean_nickname(nickname)

    profile_link = soup.select_one(".d-inline-block")
    user_id = ""
    if profile_link and profile_link.get("href"):
        href = profile_link["href"]
        id_match = re.search(r"id=(\d+)", href)
        if id_match:
            user_id = id_match.group(1)

    sesskey = ""
    sess_match = re.search(r'"sesskey":"([^"]+)"', login_resp.text)
    if sess_match:
        sesskey = sess_match.group(1)

    cookies = ses.cookies.get_dict()
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())

    return {
        "nickname": nickname,
        "user_id": user_id,
        "cookie": cookie_str,
        "sesskey": sesskey,
    }


def login(account: str, password: str) -> dict | None:
    result = login_via_requests(account, password)
    if result and result.get("user_id"):
        return result
    logger.warning(
        f"[login] requests login failed or incomplete for account: {account}"
    )
    return None


def _get_excluded_patterns() -> list[str]:
    try:
        from app.database import SessionLocal
        from app.models.db_models import ExcludedTask

        db = SessionLocal()
        try:
            records = db.query(ExcludedTask.url_pattern).all()
            return [r[0] for r in records]
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"_get_excluded_patterns failed: {e}")
        from app.config import DEFAULT_EXCLUDED_TASKS

        return list(DEFAULT_EXCLUDED_TASKS)


def _is_task_excluded(url: str, patterns: list[str]) -> bool:
    for p in patterns:
        if url.startswith(p):
            return True
    return False


def query_all(cookie_str: str, course_id: int = DEFAULT_COURSE_ID) -> dict:
    """
    :param cookie_str:
    :param course_id:
    :return: tasks;
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Cookie": cookie_str,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    COURSE_URL = f"{CLOUDCAMPUS_BASE}/course/view.php"
    params = {"id": course_id}
    resp = requests.get(
        COURSE_URL, headers=headers, params=params, timeout=15, allow_redirects=False
    )
    if resp.status_code in (301, 302, 303, 307, 308):
        location = resp.headers.get("Location", "")
        if "login" in location.lower() or resp.status_code == 302:
            return {"error": "cookie_expired", "tasks": [], "total_h5p_count": 0}

    if resp.status_code != 200:
        # Retry with redirects if first attempt was a non-login redirect
        resp = requests.get(
            COURSE_URL, headers=headers, timeout=15, allow_redirects=True
        )
        if resp.status_code != 200:
            return {
                "error": f"http_{resp.status_code}",
                "tasks": [],
                "total_h5p_count": 0,
            }

    soup = BeautifulSoup(resp.text, "lxml")
    if soup.find("input", {"name": "logintoken"}):
        return {"error": "cookie_expired", "tasks": [], "total_h5p_count": 0}

    total_todo_collection = soup.find_all(class_="futureNotCompleted")
    total_amount = len(soup.find_all(class_="progressBarCell"))
    if not total_todo_collection:
        return {"tasks": [], "total_h5p_count": 0}

    tasks = []
    for item in total_todo_collection:
        element_id: str = item.get("data-info-ref")
        task = soup.find(id=element_id)
        assert isinstance(
            task, bs4.element.Tag
        ), f"Expected BeautifulSoup Tag for task with id {element_id}"
        href_e = task.find("a")
        if not href_e or not href_e.get("href"):
            continue
        title = href_e.get_text(strip=True)
        href = href_e.get("href")
        assert isinstance(
            href, str
        ), f"Expected href to be a string for task with id {element_id}"
        tasks.append((title, href))
    return {"tasks": tasks, "total_h5p_count": total_amount}


def query_resend(cookie_str: str, course_id: int) -> dict:
    headers = {
        "User-Agent": USER_AGENT,
        "Cookie": cookie_str,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    grade_url = GRADE_URL_TEMPLATE.format(base=CLOUDCAMPUS_BASE, course_id=course_id)

    try:
        resp = requests.get(
            grade_url, headers=headers, timeout=15, allow_redirects=False
        )
    except requests.RequestException:
        return {"error": "network_error", "tasks": [], "total_h5p_count": 0}

    if resp.status_code in (301, 302, 303, 307, 308):
        location = resp.headers.get("Location", "")
        if "login" in location.lower():
            return {"error": "cookie_expired", "tasks": [], "total_h5p_count": 0}

    if resp.status_code != 200:
        resp = requests.get(
            grade_url, headers=headers, timeout=15, allow_redirects=True
        )
        if resp.status_code != 200:
            return {
                "error": f"http_{resp.status_code}",
                "tasks": [],
                "total_h5p_count": 0,
            }

    soup = BeautifulSoup(resp.text, "lxml")
    if soup.find("input", {"name": "logintoken"}):
        return {"error": "cookie_expired", "tasks": [], "total_h5p_count": 0}

    tbody = soup.find("tbody")
    if not tbody:
        return {"tasks": [], "total_h5p_count": 0}

    tasks = []
    rows = tbody.find_all("tr")

    for row in rows:
        if "lastrow" in (row.get("class") or []):
            break

        item_cell = row.select_one(".column-itemname")
        if not item_cell:
            continue

        h5p_span = item_cell.select_one("span[title='H5P']")
        if not h5p_span:
            continue

        link = item_cell.find("a")
        if not link:
            continue

        title = link.get_text(strip=True)
        href = link.get("href", "")

        pct_cell = row.select_one("td.column-percentage")
        pct_text = pct_cell.get_text(strip=True) if pct_cell else ""
        completed = "100.00" in pct_text

        if not completed:
            tasks.append((title, href))

    return {"tasks": tasks, "total_h5p_count": len(tasks)}


def get_course_list(cookie_str: str) -> list[dict]:
    headers = {
        "User-Agent": USER_AGENT,
        "Cookie": cookie_str,
    }

    resp = requests.get(f"{CLOUDCAMPUS_BASE}/my/", headers=headers, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    courses = []

    for card in soup.select(".coursebox, .course_listitem, .coc-course"):
        link = card.select_one("a")
        if link:
            href = link.get("href", "")
            name = link.get_text(strip=True)
            course_id = ""
            id_match = re.search(r"id=(\d+)", href)
            if id_match:
                course_id = id_match.group(1)
            courses.append({"course_id": course_id, "course_name": name})

    return courses

#!/usr/bin/env python3
"""
CC_Replayer — 轻量化多账号并行云校园刷课工具 (常驻版)
========================================================
用法:
    python replayer.py                          常驻模式,自动加载 queue.json
    python replayer.py -t 4 -c 11881            常驻模式,4线程

    python replayer.py add -u user -p pass       添加账号到队列
    python replayer.py add user:password         快捷添加 (冒号格式)
    python replayer.py add -f accounts.json      批量添加账号

    python replayer.py run -f accounts.json      一次性批量模式 (跑完退出)
    python replayer.py run -u user -p pass       单账号一次性模式

常驻模式:
    daemon 读取 queue.json 中的待处理账号,自动执行 view+replay
    使用 add 子命令 (可在另一个终端) 随时添加账号到队列
    Ctrl+C 退出

依赖:
    pip install rich requests beautifulsoup4 lxml numpy
"""

import argparse
import json
import os
import re
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import requests
import bs4
from bs4 import BeautifulSoup

try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeRemainingColumn,
    )
    from rich.table import Table
    from rich.text import Text
    from rich import box
    from rich.align import Align

    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    print("[!] pip install rich 以获得漂亮的终端进度条")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════
# 配置常量
# ═══════════════════════════════════════════════════════════════

CLOUDCAMPUS_BASE = "https://www.cloudcampus.com.cn"
LOGIN_URL = f"{CLOUDCAMPUS_BASE}/login/index.php"
GRADE_URL_TEMPLATE = "{base}/grade/report/user/index.php?id={course_id}"

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
# 抓包样本目录：默认使用仓库根目录的 Raw/，可用 AUTOCC_RAW_DIR 或 --raw-dir 覆盖
REPO_RAW_DIR = Path(os.environ.get("AUTOCC_RAW_DIR") or (REPO_ROOT / "Raw")).expanduser()

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
)

DEFAULT_COURSE_ID = 11881
DEFAULT_THREADS = 2
MAX_REPLAY_RETRIES = 3  # 发包失败自动重试次数
REPLAY_RETRY_DELAY = 2.0  # 重试间隔 (秒)

FAILED_LOG = SCRIPT_DIR / "failed.json"
QUEUE_FILE = SCRIPT_DIR / "queue.json"

_shutdown_flag = threading.Event()
console = Console()


# ═══════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════


@dataclass
class AccountState:
    username: str
    password: str = ""
    nickname: str = ""
    phase: str = "pending"  # pending / login / query / running / done / error
    sub_phase: str = ""  # 子阶段: visiting / replaying / marking_done (当前正在做的事)
    progress: int = 0  # 当前任务序号
    total: int = 0  # 总任务数
    success: int = 0  # 发包成功
    failed: int = 0  # 发包失败
    error_msg: str = ""
    start_time: float = 0.0

    user_info: dict = field(default_factory=dict)
    tasks: list = field(default_factory=list)

    @property
    def label(self) -> str:
        return self.nickname or self.username

    @property
    def pct(self) -> float:
        if self.total == 0:
            return 0.0
        return min(self.progress / self.total, 1.0)


# ═══════════════════════════════════════════════════════════════
# 云校园 API
# ═══════════════════════════════════════════════════════════════


def login(account: str, password: str) -> Optional[dict]:
    ses = requests.Session()
    ses.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
    )

    try:
        resp = ses.get(CLOUDCAMPUS_BASE, timeout=15)
        resp.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(resp.text, "lxml")
    token_input = soup.find("input", {"name": "logintoken"})
    logintoken = token_input["value"] if token_input else ""

    login_data = {"username": account, "password": password, "logintoken": logintoken}

    try:
        login_resp = ses.post(
            LOGIN_URL, data=login_data, timeout=15, allow_redirects=True
        )
    except requests.RequestException:
        return None

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
        id_match = re.search(r"id=(\d+)", profile_link["href"])
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


def _clean_nickname(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"\s+", " ", raw)
    raw_clean = re.sub(r"\s*[A-Z]{2,3}$", "", raw).strip()
    return raw_clean if raw_clean else raw


def query(cookie_str: str, course_id: int = DEFAULT_COURSE_ID) -> dict:
    """
    :param cookie_str:
    :param course_id:
    :return: tasks;
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
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
    return {"tasks": tasks}


def query_progress(cookie_str: str, course_id: int) -> dict:
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
    total_h5p = 0
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

        total_h5p += 1

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

    return {"tasks": tasks, "total_h5p_count": total_h5p}


# ═══════════════════════════════════════════════════════════════
# 发包引擎
# ═══════════════════════════════════════════════════════════════


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


def replay_single_packet(
    task_id: str,
    user_info: dict,
    raw_dir: Path,
    max_retries: int = MAX_REPLAY_RETRIES,
    retry_delay: float = REPLAY_RETRY_DELAY,
) -> tuple[bool, str]:
    """发包, 返回 (成功?, 错误原因). 失败自动重试"""
    npy_path = raw_dir / f"{task_id}.npy"
    if not npy_path.exists():
        return False, "no_packet"

    original = np.load(str(npy_path), allow_pickle=True).item()
    modified = _rewrite_packet(original, user_info)

    last_error = ""

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                url=modified["url"],
                headers=modified["headers"],
                json=modified["body"],
                timeout=15,
            )
            if resp.status_code == 200 and '"error":false' in resp.text:
                return True, ""
            if resp.status_code != 200:
                last_error = f"http_{resp.status_code}"
            else:
                last_error = f"resp_error"
        except requests.exceptions.Timeout:
            last_error = "timeout"
        except requests.exceptions.RequestException as e:
            last_error = str(e)[:60]

        if attempt < max_retries:
            time.sleep(retry_delay)

    return False, f"{last_error}(x{max_retries})"


# ═══════════════════════════════════════════════════════════════
# View + Replay 一体 (逐任务交替)
# ═══════════════════════════════════════════════════════════════


def view_and_replay(
    user_info: dict,
    state: AccountState,
    raw_dir: Path,
    username: str = "",
    password: str = "",
    fail_log_path: Path = FAILED_LOG,
    replay_set: set[tuple[str, str]] | None = None,
    view_set: set[tuple[str, str]] | None = None,
) -> dict:
    """逐任务: 先 view, 再 replay (仅 replay_set 中的), 交替进行"""

    if replay_set is None:
        replay_set = set()

    if view_set is None:
        view_set = set()

    total = len(replay_set) + len(view_set)

    cookie_str = user_info.get("cookie", "")
    ses = requests.Session()
    ses.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
    )
    for item in cookie_str.replace("; ", ";").split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        name, value = item.split("=", 1)
        ses.cookies.set(name.strip(), value.strip())

    success = 0
    failed = 0
    failed_entries = []

    for i, task in enumerate(replay_set):
        state.progress = i + 1

        task_url = task[1]
        task_title = task[0]
        task_id = task_url.split("id=")[-1]

        # —— View (全部任务都 view) ——
        state.sub_phase = "visiting"
        try:
            ses.get(task_url, allow_redirects=True, timeout=15)
        except requests.RequestException:
            pass

        # —— Replay (仅需发包的任务) ——
        state.sub_phase = "replaying"
        ok, err = replay_single_packet(task_id, user_info, raw_dir)
        time.sleep(1.5)

        if ok:
            success += 1
        else:
            failed += 1
            failed_entries.append(
                {
                    "username": username,
                    "password": password,
                    "task_id": task_id,
                    "task_title": task_title,
                    "task_url": task_url,
                    "error": err,
                    "time": time.time(),
                }
            )
        state.success = success
        state.failed = failed

        if i < total - 1:
            time.sleep(0.3)

    for i, task in enumerate(view_set):
        state.progress += 1
        state.sub_phase = "visiting"
        try:
            ses.get(task[1], allow_redirects=True, timeout=15)
        except requests.RequestException:
            pass

    remain_task = query(cookie_str, course_id=DEFAULT_COURSE_ID).get("tasks", [])
    state.progress -= len(remain_task)

    for i, t in enumerate(remain_task):
        state.sub_phase = "marking_done"
        state.progress += 1

        ses.headers.update(
            {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": "application/json",
                "Host": "www.cloudcampus.com.cn",
                "Origin": "https://www.cloudcampus.com.cn",
                "Referer": f"https://www.cloudcampus.com.cn/mod/folder/view.php?id={t[1].split('id=')[-1]}",
                "X-Requested-With": "XMLHttpRequest",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            }
        )

        param = {
            "sesskey": user_info.get("sesskey", ""),
            "info": "core_completion_update_activity_completion_status_manually",
        }
        json_data = [
            {
                "index": 0,
                "methodname": "core_completion_update_activity_completion_status_manually",
                "args": {"cmid": str(t[1].split("id=")[-1]), "completed": True},
            }
        ]
        resp = ses.post(
            "https://www.cloudcampus.com.cn/lib/ajax/service.php",
            json=json_data,
            params=param,
        )
        if resp.status_code == 200 and '"error":false' in resp.text:
            success += 1
        else:
            failed += 1

        state.success = success
        state.failed = failed

        time.sleep(1.5)

    if failed_entries:
        _append_failed_log(failed_entries, fail_log_path)

    return {"total": total, "success": success, "failed": failed}


# ═══════════════════════════════════════════════════════════════
# 单账号完整流程
# ═══════════════════════════════════════════════════════════════


def process_account(
    username: str,
    password: str,
    course_id: int,
    raw_dir: Path,
    state: AccountState,
    retry_count: int = 2,
) -> AccountState:
    state.start_time = time.time()

    state.phase = "login"
    for attempt in range(retry_count + 1):
        user_info = login(username, password)
        if user_info:
            state.nickname = user_info["nickname"]
            state.user_info = user_info
            break
        if attempt < retry_count:
            time.sleep(2)
    else:
        state.phase = "error"
        state.error_msg = "登录失败"
        return state

    state.phase = "query"

    result = query_progress(state.user_info["cookie"], course_id)
    all_result = query(state.user_info["cookie"], course_id)

    if result.get("error"):
        state.phase = "error"
        state.error_msg = f"查询失败: {result['error']}"
        return state

    all_tasks = all_result["tasks"]
    resend_tasks = result["tasks"]
    if not all_tasks:
        state.phase = "done"
        return state

    # 标记哪些需要发包 (未完成 + 有数据包)
    replay_set: set[tuple[str, str]] = set()
    for t in resend_tasks:
        task_id = t[1].split("id=")[-1]
        npy_path = raw_dir / f"{task_id}.npy"
        if npy_path.exists():
            replay_set.add(t)

    view_set = set(all_tasks) - replay_set

    state.tasks = all_tasks
    state.total = len(all_tasks)
    state.phase = "running"

    view_and_replay(
        state.user_info,
        state,
        raw_dir,
        username=username,
        password=password,
        replay_set=replay_set,
        view_set=view_set,
    )

    state.phase = "done"
    return state


# ═══════════════════════════════════════════════════════════════
# 终端 UI (Rich)
# ═══════════════════════════════════════════════════════════════

PHASE_EMOJI = {
    "pending": "⏳",
    "login": "🔑",
    "query": "🔍",
    "running": "🔄",
    "done": "✅",
    "error": "❌",
}

PHASE_COLOR = {
    "pending": "dim",
    "login": "yellow",
    "query": "cyan",
    "running": "magenta",
    "done": "green",
    "error": "red",
}

SUB_PHASE_LABEL = {
    "visiting": "📖 阅读中",
    "replaying": "🚀 发包中",
    "retrying": "🔄 重试中",
    "view_only": "📖 仅阅读",
    "marking_done": "✅ 标记完成",
}


def _pct_bar(pct: float, width: int = 8, color: str = "green") -> Text:
    filled = int(pct * width)
    empty = width - filled
    bar_str = "█" * filled + "░" * empty
    return Text(f"{bar_str} {pct*100:5.1f}%", style=color)


def build_table(states: list[AccountState]) -> Table:
    """构建账号进度表格"""
    table = Table(
        box=box.ROUNDED,
        expand=True,
        show_header=True,
        header_style="bold white",
        border_style="grey50",
    )
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("账号", style="cyan", no_wrap=True, width=14)
    table.add_column("阶段", width=10)
    table.add_column("进度", width=24)
    table.add_column("结果", width=12)
    table.add_column("耗时", width=8)

    for idx, st in enumerate(states, 1):
        label = f"{st.username} ({st.nickname})"

        emoji = PHASE_EMOJI.get(st.phase, "❓")
        phase_color = PHASE_COLOR.get(st.phase, "white")

        # 阶段文本
        if st.phase == "running" and st.sub_phase:
            sub_label = SUB_PHASE_LABEL.get(st.sub_phase, st.sub_phase)
            phase_text = Text(f"{sub_label}", style=phase_color)
        else:
            phase_text = Text(f"{emoji} {st.phase}", style=phase_color)

        # 进度条
        if st.total > 0 and st.phase in ("running", "done"):
            progress_bar = _pct_bar(
                st.pct, width=12, color="green" if st.phase == "done" else "magenta"
            )
        elif st.phase == "running":
            progress_bar = Text("—")
        else:
            progress_bar = Text("—")

        # 统计
        if st.phase == "error":
            stats = Text(st.error_msg[:10], style="red")
        elif st.phase == "done":
            if st.total > 0:
                stats = Text(f"{st.success}✅{st.failed}❌")
            else:
                stats = Text("全部完成", style="green")
        elif st.total > 0:
            stats = Text(f"{st.success}✅{st.failed}❌")
        elif st.phase == "pending":
            stats = Text("排队中", style="dim")
        else:
            stats = Text("—")

        # 耗时
        if st.start_time > 0 and st.phase not in ("done", "error"):
            elapsed = int(time.time() - st.start_time)
            m, s = divmod(elapsed, 60)
            elapsed_str = f"{m}m{s}s"
        elif st.phase in ("done", "error"):
            elapsed_str = "完成"
        else:
            elapsed_str = "—"

        table.add_row(str(idx), label, phase_text, progress_bar, stats, elapsed_str)

    return table


def build_full_view(states: list[AccountState], status_line: str) -> Layout:
    """构建完整的终端视图: 表格 + 底部输入栏"""
    layout = Layout()
    layout.split(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=4),
    )

    # 顶部标题
    active = sum(1 for s in states if s.phase not in ("done", "error", "pending"))
    done = sum(1 for s in states if s.phase == "done")
    err = sum(1 for s in states if s.phase == "error")
    total = len(states)

    header_text = Text()
    header_text.append(
        "╔══════════════════ CC Replayer ═══════════════════╗\n", style="bold cyan"
    )
    header_text.append(
        f"║  账号: {total}  |  运行中: {active}  |  完成: {done}  |  失败: {err}",
        style="white",
    )
    header_text.append(
        f"\n╚══════════════════════════════════════════════════╝", style="dim"
    )
    layout["header"].update(Align(header_text, align="center"))

    # 表格主体
    if states:
        layout["body"].update(build_table(states))
    else:
        layout["body"].update(
            Align(Text("等待输入账号...\n", style="dim"), align="center")
        )

    # 底部输入栏
    footer_text = Text()
    footer_text.append("━" * 50 + "\n", style="dim")
    if status_line:
        footer_text.append(f"  {status_line}\n", style="yellow")
    footer_text.append("  python replayer.py add user:password", style="dim")
    footer_text.append(" 添加账号  |  ", style="dim")
    footer_text.append("python replayer.py retry", style="dim")
    footer_text.append(" 重试失败  |  ", style="dim")
    footer_text.append("Ctrl+C", style="bold red")
    footer_text.append(" 退出", style="dim")
    layout["footer"].update(Panel(footer_text, border_style="grey50", padding=(0, 1)))

    return layout


# ═══════════════════════════════════════════════════════════════
# 任务队列管理器
# ═══════════════════════════════════════════════════════════════


class JobQueue:
    """管理账号状态、线程池、动态添加"""

    def __init__(self, course_id: int, raw_dir: Path, max_workers: int, retry: int):
        self.course_id = course_id
        self.raw_dir = raw_dir
        self.retry = retry
        self.states: dict[str, AccountState] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._futures: dict = {}
        self.status_line = ""

    def add(self, username: str, password: str) -> str | None:
        """添加账号,返回 None 成功,否则返回错误信息"""
        with self._lock:
            if username in self.states:
                existing = self.states[username]
                if existing.phase not in ("done", "error"):
                    return f"账号 {username} 已在队列中 (状态: {existing.phase})"
                del self.states[username]

            state = AccountState(username=username, password=password)
            self.states[username] = state
            future = self._executor.submit(
                process_account,
                username,
                password,
                self.course_id,
                self.raw_dir,
                state,
                self.retry,
            )
            self._futures[future] = username

        self._cleanup_completed()
        return None

    def _cleanup_completed(self):
        """清理已完成的 future"""
        done_futures = [f for f in self._futures if f.done()]
        for f in done_futures:
            self._futures.pop(f, None)

    def get_states(self) -> list[AccountState]:
        with self._lock:
            return list(self.states.values())

    def shutdown(self):
        self._executor.shutdown(wait=False, cancel_futures=True)


QUEUE_FILE = SCRIPT_DIR / "queue.json"


# ═══════════════════════════════════════════════════════════════
# 队列文件操作 (daemon ↔ add 子命令的桥梁)
# ═══════════════════════════════════════════════════════════════


def load_queue() -> list[dict]:
    """读取 queue.json, 返回待处理账号列表"""
    if not QUEUE_FILE.exists():
        return []
    try:
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("entries", data.get("accounts", []))
    return []


def save_queue(entries: list[dict]):
    """原子写入 queue.json"""
    tmp = str(QUEUE_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    os.replace(tmp, str(QUEUE_FILE))


def append_to_queue(username: str, password: str):
    entries = load_queue()
    entries.append({"username": username, "password": password})
    save_queue(entries)
    # touch 文件让 daemon 的 mtime 检测生效
    QUEUE_FILE.touch()


def mark_queue_processed(remaining: list[dict]):
    """将 remaining 写回队列文件 (已处理的被移除)"""
    save_queue(remaining)
    QUEUE_FILE.touch()


# ═══════════════════════════════════════════════════════════════
# 失败日志 (failed.json) — 用于重试
# ═══════════════════════════════════════════════════════════════


def _append_failed_log(entries: list[dict], fail_log_path: Path = FAILED_LOG):
    existing = load_failed_log(fail_log_path)
    existing.extend(entries)
    tmp = str(fail_log_path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    os.replace(tmp, str(fail_log_path))


def load_failed_log(fail_log_path: Path = FAILED_LOG) -> list[dict]:
    if not fail_log_path.exists():
        return []
    try:
        with open(fail_log_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, IOError):
        pass
    return []


def clear_failed_log(fail_log_path: Path = FAILED_LOG):
    if fail_log_path.exists():
        fail_log_path.unlink()


def retry_failed_accounts(
    raw_dir: Path,
    course_id: int,
    threads: int = DEFAULT_THREADS,
    fail_log_path: Path = FAILED_LOG,
    filter_username: str | None = None,
):
    """读取 failed.json, 按账号分组重新发包, 成功的从日志移除"""
    entries = load_failed_log(fail_log_path)
    if not entries:
        console.print("[dim]没有失败的记录需要重试[/dim]")
        return

    if filter_username:
        entries = [e for e in entries if e.get("username") == filter_username]
        if not entries:
            console.print(f"[dim]没有 {filter_username} 的失败记录[/dim]")
            return

    by_user: dict[str, dict] = {}
    for e in entries:
        u = e["username"]
        if u not in by_user:
            by_user[u] = {"password": e["password"], "tasks": []}
        by_user[u]["tasks"].append(e)

    console.print(
        f"[bold]重试 {len(entries)} 个失败任务 (来自 {len(by_user)} 个账号)...[/bold]\n"
    )

    total_success = 0
    total_failed = 0
    remaining_all = []

    for username, info in by_user.items():
        console.print(f"[cyan]登录 {username}...[/cyan]")
        user_info = login(username, info["password"])
        if not user_info:
            console.print(f"[red]  {username} 登录失败, 跳过[/red]")
            remaining_all.extend(
                {**t, "error": "relogin_failed"} for t in info["tasks"]
            )
            total_failed += len(info["tasks"])
            continue

        for task in info["tasks"]:
            task_id = task["task_id"]
            task_url = task.get("task_url", "")
            title = task.get("task_title", task_id)

            # View first
            if task_url:
                try:
                    requests.get(
                        task_url,
                        headers={
                            "User-Agent": USER_AGENT,
                            "Cookie": user_info["cookie"],
                        },
                        timeout=15,
                        allow_redirects=True,
                    )
                except requests.RequestException:
                    pass

            ok, err = replay_single_packet(task_id, user_info, raw_dir)
            time.sleep(1.5)
            if ok:
                console.print(f"  [green]✅[/green] {title}")
                total_success += 1
            else:
                console.print(f"  [red]❌[/red] {title} ({err})")
                total_failed += 1
                remaining_all.append(task)

    save_queue(remaining_all)
    # 更新失败日志
    if remaining_all:
        tmp = str(fail_log_path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(remaining_all, f, ensure_ascii=False, indent=2)
        os.replace(tmp, str(fail_log_path))
    else:
        clear_failed_log(fail_log_path)

    console.print(
        f"\n[bold green]成功: {total_success}[/bold green]  [bold red]仍失败: {total_failed}[/bold red]"
    )
    if remaining_all:
        console.print(f"[dim]剩余失败记录已保留在 {fail_log_path}, 可再次重试[/dim]")


# ═══════════════════════════════════════════════════════════════
# 模式: 一次性批量
# ═══════════════════════════════════════════════════════════════


def load_accounts_from_file(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get("accounts", [])
    accounts = []
    for item in data:
        if isinstance(item, str):
            if ":" in item:
                u, p = item.split(":", 1)
                accounts.append({"username": u.strip(), "password": p.strip()})
        elif isinstance(item, dict):
            accounts.append(item)
    return accounts


def parse_account_line(line: str) -> tuple[str, str] | None:
    """解析 'user:pass' 或 'user pass' 格式"""
    line = line.strip()
    if not line:
        return None
    if ":" in line:
        parts = line.split(":", 1)
    else:
        parts = line.split(None, 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return None


def run_batch(
    accounts: list[dict], course_id: int, raw_dir: Path, threads: int, retry: int
):
    """一次性批量模式"""
    npy_count = len(list(raw_dir.glob("*.npy")))
    console.print(
        f"[dim]Raw: {raw_dir} ({npy_count}包) | 课程: {course_id} | 线程: {threads}[/dim]\n"
    )

    queue = JobQueue(course_id, raw_dir, threads, retry)
    for acct in accounts:
        queue.add(acct["username"], acct["password"])

    live = Live(
        build_full_view(queue.get_states(), queue.status_line),
        console=console,
        refresh_per_second=6,
    )
    live.start()

    def refresh_ui():
        while True:
            time.sleep(0.2)
            live.update(build_full_view(queue.get_states(), queue.status_line))

    ui_thread = threading.Thread(target=refresh_ui, daemon=True)
    ui_thread.start()

    # 等待所有任务完成
    start_ts = time.time()
    while True:
        states = queue.get_states()
        pending = sum(1 for s in states if s.phase not in ("done", "error"))
        if pending == 0 and len(states) > 0:
            break
        time.sleep(0.5)

    total_elapsed = time.time() - start_ts
    m, s = divmod(int(total_elapsed), 60)
    live.stop()

    console.print(f"\n[bold]总耗时: {m}分{s}秒[/bold]")
    total_ok = sum(s.success for s in queue.get_states())
    total_fail = sum(s.failed for s in queue.get_states())
    errors = [s.label for s in queue.get_states() if s.phase == "error"]
    if total_ok + total_fail > 0:
        console.print(
            f"[bold green]成功: {total_ok}[/bold green]  [bold red]失败: {total_fail}[/bold red]"
        )
    if errors:
        console.print(f"[red]登录失败: {', '.join(errors)}[/red]")

    queue.shutdown()


def run_daemon(course_id: int, raw_dir: Path, threads: int, retry: int):
    """常驻模式: 监视 queue.json, 自动处理新账号"""
    _shutdown_flag.clear()
    npy_count = len(list(raw_dir.glob("*.npy")))
    queue = JobQueue(course_id, raw_dir, threads, retry)

    processed_usernames: set[str] = set()

    def load_new_accounts():
        """从 queue.json 加载尚未处理的账号"""
        entries = load_queue()
        added = 0
        new_entries = []
        for entry in entries:
            username = entry.get("username", "")
            password = entry.get("password", "")
            if not username or not password:
                continue
            if username in processed_usernames:
                new_entries.append(entry)
                continue
            err = queue.add(username, password)
            if err:
                queue.status_line = f"[跳过] {err}"
                new_entries.append(entry)
            else:
                processed_usernames.add(username)
                added += 1
        if added > 0:
            queue.status_line = f"[添加] 从队列加载了 {added} 个账号"
        # 清理已处理的条目
        remaining = [
            e for e in entries if e.get("username", "") not in processed_usernames
        ]
        if len(remaining) != len(entries):
            save_queue(remaining)
        return added

    # 加载初始队列
    load_new_accounts()

    live = Live(
        build_full_view(queue.get_states(), queue.status_line),
        console=console,
        refresh_per_second=6,
        screen=False,
    )
    live.start()

    console.print(
        f"[dim]Raw: {raw_dir} ({npy_count}包) | 课程: {course_id} | 线程: {threads}[/dim]"
    )
    console.print("[dim]用另一个终端执行: python replayer.py add user:password[/dim]")
    console.print("[dim]或编辑 queue.json 添加账号, 回车后 Ctrl+C 退出[/dim]\n")

    def refresh_ui():
        while not _shutdown_flag.is_set():
            time.sleep(0.2)
            try:
                live.update(build_full_view(queue.get_states(), queue.status_line))
            except Exception:
                break

    ui_thread = threading.Thread(target=refresh_ui, daemon=True)
    ui_thread.start()

    # 监视 queue.json 文件变化
    last_mtime = QUEUE_FILE.stat().st_mtime if QUEUE_FILE.exists() else 0

    def file_watcher():
        nonlocal last_mtime
        while not _shutdown_flag.is_set():
            time.sleep(1)
            try:
                if QUEUE_FILE.exists():
                    mtime = QUEUE_FILE.stat().st_mtime
                    if mtime > last_mtime:
                        last_mtime = mtime
                        load_new_accounts()
                else:
                    last_mtime = 0
            except Exception:
                pass

    watcher_thread = threading.Thread(target=file_watcher, daemon=True)
    watcher_thread.start()

    try:
        while not _shutdown_flag.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        _shutdown_flag.set()
        live.stop()
        queue.shutdown()

    console.print("\n[bold]已退出[/bold]")
    states = queue.get_states()
    if states:
        total_ok = sum(s.success for s in states)
        total_fail = sum(s.failed for s in states)
        console.print(
            f"[bold green]成功发包: {total_ok}[/bold green]  [bold red]失败: {total_fail}[/bold red]"
        )


def main():
    parser = argparse.ArgumentParser(
        description="CC_Replayer — 轻量化多账号并行云校园刷课工具 (常驻版)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python replayer.py                          常驻模式 (监视 queue.json)
  python replayer.py -t 4 -c 11881            常驻模式,4线程
  python replayer.py add user:password         快捷添加账号
  python replayer.py add -u user -p pass       添加账号到队列
  python replayer.py add -f accounts.json      批量添加账号
  python replayer.py run -f accounts.json      一次性批量模式
  python replayer.py retry                     重试所有失败任务
  python replayer.py retry -u user             只重试某账号的失败任务
        """,
    )
    parser.add_argument(
        "-c", "--course", type=int, default=DEFAULT_COURSE_ID, help="课程ID"
    )
    parser.add_argument(
        "-t", "--threads", type=int, default=DEFAULT_THREADS, help="并行线程数"
    )
    parser.add_argument(
        "-r", "--raw-dir", default=str(REPO_RAW_DIR), help="Raw 数据包目录"
    )
    parser.add_argument("--retry", type=int, default=2, help="登录重试次数")

    sub = parser.add_subparsers(dest="command", help="子命令")

    # —— add 子命令 ——
    add_parser = sub.add_parser("add", help="添加账号到队列 (daemon 自动拾取)")
    add_parser.add_argument("quick", nargs="?", help="快捷格式: user:password")
    add_parser.add_argument("-u", "--username", action="append", help="账号用户名")
    add_parser.add_argument("-p", "--password", action="append", help="账号密码")
    add_parser.add_argument("-f", "--file", help="从 JSON 文件批量添加")

    # —— run 子命令 ——
    run_parser = sub.add_parser("run", help="一次性批量模式 (跑完退出)")
    run_parser.add_argument("-f", "--file", help="账号配置文件 (JSON)")
    run_parser.add_argument("-u", "--username", action="append", help="账号用户名")
    run_parser.add_argument("-p", "--password", action="append", help="账号密码")

    # —— retry 子命令 ——
    retry_parser = sub.add_parser("retry", help="重试失败的发包任务 (读取 failed.json)")
    retry_parser.add_argument("-u", "--username", help="只重试指定账号的失败任务")
    retry_parser.add_argument(
        "-t", "--threads", type=int, default=DEFAULT_THREADS, help="并行线程数"
    )

    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    if not raw_dir.exists():
        console.print(f"[red]错误: Raw 目录不存在: {raw_dir}[/red]")
        sys.exit(1)

    if args.command == "add":
        accounts = []
        if args.quick:
            parsed = parse_account_line(args.quick)
            if parsed:
                accounts.append({"username": parsed[0], "password": parsed[1]})
            else:
                console.print(
                    f"[red]格式错误: 应为 user:password, 收到: {args.quick}[/red]"
                )
                sys.exit(1)
        if args.file:
            accounts.extend(load_accounts_from_file(args.file))
        if args.username:
            if not args.password or len(args.username) != len(args.password):
                console.print("[red]错误: -u 和 -p 数量必须一致[/red]")
                sys.exit(1)
            for u, p in zip(args.username, args.password):
                accounts.append({"username": u, "password": p})

        if not accounts:
            console.print("[red]错误: 请通过参数提供账号[/red]")
            console.print("[dim]示例: python replayer.py add user:password[/dim]")
            console.print("[dim]       python replayer.py add -u user -p pass[/dim]")
            sys.exit(1)

        for acct in accounts:
            append_to_queue(acct["username"], acct["password"])
            console.print(f"[green]已添加:[/green] {acct['username']}")
        console.print(
            f"[dim]共 {len(accounts)} 个账号已加入队列, daemon 将自动处理[/dim]"
        )

    elif args.command == "run":
        accounts = []
        if args.file:
            accounts = load_accounts_from_file(args.file)
        if args.username:
            if not args.password or len(args.username) != len(args.password):
                console.print("[red]错误: -u 和 -p 数量必须一致[/red]")
                sys.exit(1)
            for u, p in zip(args.username, args.password):
                accounts.append({"username": u, "password": p})
        if not accounts:
            console.print("[red]错误: 请通过 -f 或 -u/-p 提供账号[/red]")
            sys.exit(1)
        run_batch(accounts, args.course, raw_dir, args.threads, args.retry)

    elif args.command == "retry":
        retry_failed_accounts(
            raw_dir=raw_dir,
            course_id=args.course,
            threads=args.threads,
            filter_username=args.username,
        )

    else:
        # 默认: 常驻模式
        run_daemon(args.course, raw_dir, args.threads, args.retry)


if __name__ == "__main__":
    main()

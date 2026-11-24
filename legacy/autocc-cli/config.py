"""
配置管理模块 - 集中管理全局资源

所有路径都相对本文件定位，因此可以从任意工作目录启动；
敏感路径可用环境变量覆盖（EDGEDRIVER_PATH / AUTOCC_RAW_DIR）。
"""
import os
from configparser import ConfigParser
from pathlib import Path
from typing import Optional
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.webdriver import WebDriver

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parents[1]

# 账号 / 课程配置文件（已加入 .gitignore，仓库只提供 user_information.example.ini）
INI_PATH = BASE_DIR / "user_information.ini"

# 抓包样本目录：默认复用仓库根目录的 Raw/
RAW_DIR = Path(os.environ.get("AUTOCC_RAW_DIR") or (REPO_ROOT / "Raw")).expanduser()
RAW_DIR.mkdir(parents=True, exist_ok=True)

# 全局实例
_drive: Optional[WebDriver] = None
_conf = None
_current_qs = None
_total_cells = 0
_current_index = None
_shared_namespace = None
_shared_state = {}


def initialize_driver() -> WebDriver:
	"""初始化浏览器驱动"""
	global _drive
	if _drive is None:
		opt = Options()
		opt.add_argument("--proxy-server=http://127.0.0.1:8800")
		opt.add_argument("--ignore-certificate-errors")
		# 设置 SELENIUM_HEADLESS=1 可启用无头模式
		if os.environ.get("SELENIUM_HEADLESS", "").lower() in ("1", "true", "yes"):
			opt.add_argument("--headless=new")
		opt.add_argument("--mute-audio")
		opt.add_argument("--disable-infobars")
		opt.add_argument("--disable-extensions")
		opt.add_argument("--disable-gpu")
		opt.add_argument("--disable-software-rasterizer")
		opt.add_argument('--no-sandbox')
		opt.add_argument('--blink-settings=imagesEnabled=false')
		# 驱动路径可选：不设置时交给 Selenium Manager 自动匹配并下载
		driver_path = os.environ.get("EDGEDRIVER_PATH", "").strip()
		ser = Service(executable_path=driver_path) if driver_path else Service()
		_drive = webdriver.Edge(service=ser, options=opt)
		_drive.maximize_window()
	assert _drive is not None, "浏览器驱动未初始化"
	return _drive


def initialize_config():
	"""初始化配置文件"""
	global _conf
	if _conf is None:
		_conf = ConfigParser()
		_conf.read(str(INI_PATH), encoding='utf-8')
	return _conf


def save_config():
	"""把内存中的配置写回 user_information.ini"""
	with open(INI_PATH, 'w', encoding='utf-8') as configfile:
		get_config().write(configfile)


def get_driver() -> WebDriver:
	"""获取驱动实例"""
	if _drive is None:
		initialize_driver()
	assert _drive is not None, "浏览器驱动未初始化"
	return _drive


def set_driver(driver):
	"""设置驱动实例"""
	global _drive
	_drive = driver


def get_config():
	"""获取配置实例"""
	if _conf is None:
		initialize_config()
	return _conf


def close_driver():
	"""关闭浏览器驱动"""
	global _drive
	if _drive is not None:
		_drive.quit()
		_drive = None


def get_current_qs():
	"""获取当前问题元素"""
	return _current_qs


def set_current_qs(qs):
	"""设置当前问题元素"""
	global _current_qs
	_current_qs = qs


def attach_shared_namespace(namespace):
	"""绑定跨进程共享的 Namespace（如 multiprocessing.Manager().Namespace）。"""
	global _shared_namespace
	_shared_namespace = namespace
	# 确保存在 state 字典容器
	if not hasattr(_shared_namespace, 'state'):
		_shared_namespace.state = {}


def shared_write(data: dict, *, merge: bool = True):
	"""写共享字典：默认合并，merge=False 则整体覆盖。"""
	if data is None:
		return
	if _shared_namespace is not None:
		current = getattr(_shared_namespace, 'state', {}) or {}
		_shared_namespace.state = {**current, **data} if merge else dict(data)
	else:
		global _shared_state
		_shared_state = {**_shared_state, **data} if merge else dict(data)


def shared_read() -> dict:
	"""读共享字典的浅拷贝。未绑定时返回本地缓存。"""
	if _shared_namespace is not None:
		return dict(getattr(_shared_namespace, 'state', {}) or {})
	return dict(_shared_state)


def set_total_count(total_cells):
	"""设置任务总数"""
	global _total_cells
	_total_cells = total_cells


def get_total_count():
	"""获取任务总数"""
	return _total_cells

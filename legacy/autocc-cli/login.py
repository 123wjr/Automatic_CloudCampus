import os
from pathlib import Path

from selenium.common import NoSuchElementException
from selenium.webdriver import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from config import BASE_DIR, get_config, get_driver
from initialize import initialize

DEFAULT_ACCOUNTS_FILE = BASE_DIR / "accounts.txt"
LEGACY_ACCOUNTS_FILE = BASE_DIR / "userdata.txt"


def _parse_accounts_text(text: str) -> list[dict]:
	"""解析 "账号:密码" 形式的文本（每行一个账号，保留首尾空格）。"""
	accounts: list[dict] = []
	for line_num, line in enumerate(text.splitlines(), 1):
		original_line = line.rstrip("\r\n")
		if not original_line.strip() or original_line.lstrip().startswith("#"):
			continue
		if ":" not in original_line:
			continue
		# 只按第一个冒号切分，密码里允许出现冒号
		account, _, password = original_line.partition(":")
		accounts.append({"account": account, "password": password, "line": line_num})
	return accounts


def _accounts_from_file(path: Path) -> list[dict]:
	if not path.is_absolute():
		path = BASE_DIR / path
	if not path.is_file():
		return []
	try:
		return _parse_accounts_text(path.read_text(encoding="utf-8"))
	except OSError:
		return []


def _accounts_from_ini() -> list[dict]:
	conf = get_config()
	account = (conf.get("user", "username", fallback="") or "").strip()
	password = conf.get("user", "password", fallback="") or ""
	if account and password:
		return [{"account": account, "password": password, "line": 1}]
	return []


def get_user_info(file_path=None) -> list[dict]:
	"""获取用户信息。

	优先级（全部靠外部文件 / 环境变量，源码里不保存任何凭据）：
	 1. 环境变量 AUTOCC_ACCOUNTS（多个账号用 ";" 或换行分隔，格式 账号:密码）
	 2. 命令行传入的 file_path
	 3. 本目录的 accounts.txt / userdata.txt
	 4. user_information.ini 中的 [user] 段
	 5. 以上都没有时，交互式询问并写入 user_information.ini
	"""
	text = os.environ.get("AUTOCC_ACCOUNTS", "")
	if text.strip():
		accounts = _parse_accounts_text(text.replace(";", "\n"))
		if accounts:
			return accounts

	candidates = []
	if file_path:
		candidates.append(Path(file_path))
	candidates.extend([DEFAULT_ACCOUNTS_FILE, LEGACY_ACCOUNTS_FILE])
	for candidate in candidates:
		accounts = _accounts_from_file(candidate)
		if accounts:
			return accounts

	accounts = _accounts_from_ini()
	if accounts:
		return accounts

	print("未找到任何账号配置，将引导你输入一次（保存到 user_information.ini）。")
	initialize()
	return _accounts_from_ini()


def try_login(user, pwd) -> dict:
	"""尝试登录"""
	driver = get_driver()
	# get information
	username, password = user, pwd
	# to official website
	driver.get("https://www.cloudcampus.com.cn/")
	# locate element
	wait = WebDriverWait(driver, 10)
	main_form = wait.until(
		EC.presence_of_element_located((By.CSS_SELECTOR, "form[class='login-form']"))
	)
	# fill the blank
	element_username = main_form.find_element(By.ID, "username")
	driver.execute_script("arguments[0].value = arguments[1];", element_username, username)
	element_password = main_form.find_element(By.ID, "password")
	driver.execute_script("arguments[0].value = arguments[1];", element_password, password)
	element_password.send_keys(Keys.RETURN)
	try:
		driver.find_element(By.ID, "loginerrormessage")
		print("登录失败，重新输入账号密码")
	except NoSuchElementException:
		# 登陆成功后，获取所有的 验证信息 以及 修改
		print("Login successfully")
		cookies = driver.get_cookies()  # 获取所有Cookie
		print(f"获取到 {len(cookies)} 个Cookie")
		cookie_str = ""
		for cookie in reversed(cookies):
			cookie_str += f"{cookie['name']}={cookie['value']}; "

		# 去掉最后的空格和分号
		cookie_str = cookie_str.rstrip('; ')

		link = driver.find_element(By.CSS_SELECTOR, ".d-inline-block")
		href = link.get_attribute("href")
		id_part = href.split('id=')[1]
		# 去掉可能的后缀参数
		user_id = id_part.split('&')[0] if '&' in id_part else id_part
		print(f"用户ID: {user_id}")
		# 找到用户菜单
		user_menu = driver.find_element(By.ID, "user-menu-toggle")
		# 获取文本

		nickname = user_menu.get_attribute("innerText")
		print(nickname)

		sesskey = None
		try:
			page_source = driver.page_source
			import re
			pattern = r'"sesskey":"([^"]+)"'
			match = re.search(pattern, page_source)
			if match:
				sesskey = match.group(1)
				print(f"sesskey: {sesskey}")
		except Exception as e:
			print(f"正则提取失败: {e}")

		return {"nickname": nickname, "user_id": user_id, "Cookie": cookie_str, "sesskey": sesskey}

	else:
		initialize()
		return try_login(user, pwd)

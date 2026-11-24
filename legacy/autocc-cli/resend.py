import time
import numpy as np
from selenium.webdriver.edge.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
import login
import send_package
from change import change_content
from config import RAW_DIR, get_driver
from login import get_user_info
from mitm import start_mitmproxy, stop_mitmproxy
from select_assignment import find_todo_pages
from select_cell import select_cell
from send_package import send_request


def find_and_go_through_all_view_pages(driver: WebDriver) -> None:
	todo_pages = {}

	table = driver.find_element(By.CSS_SELECTOR, "tbody")
	cells = table.find_elements(By.CSS_SELECTOR, "td.column-percentage")

	for cell in cells:
		parent_cell:WebElement = cell.find_element(By.XPATH, "..")

		if "lastrow" in str(parent_cell.get_attribute("class")):
			break

		# 获取任务标题和链接
		item_cell = parent_cell.find_element(By.CSS_SELECTOR, ".column-itemname")
		item_element = item_cell.find_element(By.CSS_SELECTOR, "a")
		herf = item_element.get_attribute("href")
		title = item_element.text

		todo_pages[len(todo_pages) + 1] = [title, herf]

	for index, (_, herf) in todo_pages.items():
		driver.get(herf)
		print(f"正在访问任务页面 {index}/{len(todo_pages)}: {herf}")


def modify_resend(todo_dict: dict[int, list[str]], user_data: dict):
	print(f"正在为用户 {user_data['nickname']} 重复发包...")
	for index, (title, herf) in todo_dict.items():
		ID = herf.split("id=")[-1]
		npy_path = RAW_DIR / f"{ID}.npy"
		try:
			ori_dict: dict = np.load(str(npy_path), allow_pickle=True).item()
		except Exception as e:
			print(
				f"未找到原始数据文件 {npy_path}，跳过用户 {user_data['nickname']} 的任务 {title}。错误: {e}"
			)
			continue
		else:
			new_dict: dict = change_content(ori_dict, user_data)
			result: bool = send_request(new_dict)
			time.sleep(2)
			if result:
				print(f"成功为用户 {user_data['nickname']} 的任务 {title} 重复发包。")
			else:
				print(f"为用户 {user_data['nickname']} 的任务 {title} 重复发包失败。")


def resend_package():
	import time
	import random
	import requests
	import json
	import datetime

	# 读取用户信息
	mitm_process = start_mitmproxy("127.0.0.1", 8800)  # 启动 mitmproxy
	time.sleep(2)
	driver: WebDriver = get_driver()
	accounts = get_user_info()
	cnt = 0

	for acc in accounts:
		cnt = cnt + 1
		print("正在处理第", cnt, "个用户")
		user_data: dict = login.try_login(acc["account"], acc["password"])
		select_cell()
		todo_dict = find_todo_pages()
		find_and_go_through_all_view_pages(driver)
		modify_resend(todo_dict, user_data)
		driver.delete_all_cookies()
		time.sleep(2)
	stop_mitmproxy(mitm_process)

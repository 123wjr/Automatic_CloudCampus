from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By

import time


CSS = By.CSS_SELECTOR
from config import get_current_qs, get_driver


def solve_true_false():
	"""完成判断题"""
	# 获取所有选项
	driver = get_driver()
	current_qs = get_current_qs()
	driver.execute_script("arguments[0].scrollIntoView(true);", current_qs)
	current_qs_content = current_qs.find_element(CSS, ".h5p-question-content")
	option = current_qs_content.find_element(CSS, ".h5p-true-false-answer")

	# 点击第一个选项以激活题目
	option.click()

	# 获取按钮区域
	current_qs_btns = current_qs.find_element(CSS, ".h5p-question-buttons")

	# 提交答案
	current_qs_btns.find_element(CSS, "button.h5p-question-check-answer").click()
	time.sleep(0.3)  # 等待检查答案加载
	return
	# 不必要全对，尝试一次即可

	# # 检查是否有重试按钮
	# try:
	# 	current_qs_btns.find_element(CSS, ".h5p-question-try-again").click()
	# 	time.sleep(1)  # 等待重试加载
	# except NoSuchElementException:
	# 	return
	# else:
	# 	option = current_qs_content.find_element(By.XPATH, "//div[@class='h5p-true-false-answer' and text()='False']")
	# 	option.click()  # 点击第一个选项以激活题目
	# 	time.sleep(1)  # 等待选项激活
	# 	# 提交答案
	# 	current_qs_btns.find_element(CSS, "button.h5p-question-check-answer").click()
	# 	time.sleep(1)  # 等待检查答案加载
	# 	return
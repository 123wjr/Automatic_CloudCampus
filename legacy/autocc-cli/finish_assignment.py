import time
from typing import Any

from lxml.html.diff import href_token
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# from select_assignment import not_h5p_pages

# 重定义CSS_SELECTOR以简化代码
CSS = By.CSS_SELECTOR

from config import get_driver, set_current_qs, shared_write, get_current_qs, shared_read, get_total_count

"""
框架包括：
h5p-course-presentation（多页的）
h5p-interactive-book（多页的）
h5p-column（h5p-single-choice-set为多页，其余为单页）
None（多页的）

题目类型包括：
h5p-single-choice-set
h5p-drag-text
h5p-true-false
h5p-dragquestion
h5p-multichoice
h5p-blanks
h5p-find-the-words
"""

# 支持的题目类型列表
qs_templates = ["h5p-drag-text",
                "h5p-true-false",
                "h5p-dragquestion",
                "h5p-multichoice",
                "h5p-blanks",
                "h5p-find-the-words",
                "h5p-single-choice-set",
                "h5p-summary"]
frames = ["h5p-course-presentation",
          "h5p-interactive-book",
          "h5p-column"]


# 主函数，完成所有任务
def finish_assignments(todo_dict):
	global driver, wait
	driver = get_driver()
	wait = WebDriverWait(driver, 4)
	first_failures, final_failures = {}, {}
	solve_qs_dict(first_failures, todo_dict)

	if first_failures != {}:
		print(f"有{len(first_failures)}个任务未能完成，即将重试:")
		manual_finish_qs_dict(first_failures)

	# if not_h5p_pages != {}:
	# 	print(f"有{len(not_h5p_pages)}个任务无法自动完成:")
	# 	for index, (title, herf) in not_h5p_pages.items():
	# 		print(f'{index}. 任务 "{title}" 无法自动完成，请手动完成。链接: {herf}')


def solve_qs_dict(failure_dict: dict[Any, Any], todo_dict):
	for index, (title, herf) in todo_dict.items():
		print(f"正在完成第{index}/{len(todo_dict)}个任务: {title}")
		shared_write({'current_index': index, 'current_title': title, 'current_herf': herf, 'succeed': False})
		driver.get(herf)
		main = enter_single_assignment()
		solve_questions(main, herf)
		judge_qs_state(failure_dict)


def manual_finish_qs_dict(todo_dict):
	for index, (title, herf) in todo_dict.items():
		print(f"请手动完成第{index}/{len(todo_dict)}个任务: {title} - {herf}")
		shared_write({'current_index': index, 'current_title': title, 'current_herf': herf, 'succeed': False})
		driver.get(herf)
		input("完成后按回车继续...")
		if shared_read().get('succeed') == True:
			print(f"任务 {title} 已标记为完成。")
		else:
			print(f"任务 {title} 仍未完成，请检查后续处理。")


def judge_qs_state(failures_dict: dict[Any, Any]):
	last_state = shared_read().get('succeed')
	if last_state == False:
		index = len(failures_dict) + 1
		failures_dict[index] = (shared_read().get('current_title'), shared_read().get('current_herf'))
		print(f"任务 {shared_read().get('current_title')} 未完成，已保存失败信息")


def enter_single_assignment():
	# 切换到H5P iframe
	h5p_site = wait.until(EC.presence_of_element_located((CSS, "iframe"))).get_attribute("src")

	# 访问H5P内容页面
	driver.get(h5p_site)

	# 再次切换到H5P iframe
	iframe = wait.until(EC.presence_of_element_located((CSS, "iframe")))
	driver.switch_to.frame(iframe)
	main = wait.until(EC.presence_of_element_located((CSS, "div.h5p-container.h5p-standalone")))

	return main


# 核心答题函数
def solve_questions(main, href):
	# 开始答题流程
	try:
		# 选择当前框架类型
		frame_type = select_frame()

		# 如果有开始页面，先点击开始，通用的手段
		start(main, frame_type)

		if frame_type == "h5p-interactive-book":
			previous_page(main, frame_type)
			while True:
				if not next_page(main, frame_type):
					break
			# 点击提交按钮
			match_case = ".h5p-interactive-book-summary-button.h5p-interactive-book-summary-submit"
			submit_btn = WebDriverWait(driver, 10).until(EC.presence_of_element_located((CSS, match_case)))
			wait_until_clickable_click(submit_btn)
			wait_for_submit()
			return

		if frame_type == "h5p-course-presentation":
			# 特判course-presentation的封面页
			while True:
				if not next_page(main, frame_type):
					break
			# time.sleep(0.5)
			try:
				finish_btn = main.find_element(CSS, "button.h5p-question-finish")
				wait_until_clickable_click(finish_btn)
			except NoSuchElementException:
				pass
			finally:
				wait_for_submit()
				return

		# 对single_choice_set进行特判
		try:
			current_qs_set = main.find_elements(CSS, ".h5p-single-choice-set")
		except NoSuchElementException:
			pass
		else:
			for current_qs in current_qs_set:
				set_current_qs(current_qs)
				distribute_to_qs_module("h5p-single-choice-set")
			return

		# 寻找所有题目，统计题目数量
		questions = main.find_elements(CSS, ".h5p-question")
		if len(questions) == 0:
			questions = [main]

		# 对普通框架的题目进行补充的隐藏判断
		is_problem_hid = False
		for current_qs in questions:
			style_value = current_qs.get_attribute("style")
			if style_value == "":
				continue
			if style_value is None:
				continue
			if "display: none" in style_value:
				is_problem_hid = True
				break

		if is_problem_hid:
			# 防止有人自己先做了，先回到第一页
			# while True and frame_type != "h5p-course-presentation":
			while True:
				current_qs = main.find_element(CSS, ".h5p-question[style='']")
				set_current_qs(current_qs)
				# 回到第一页
				if not previous_page(main, frame_type):
					break
			set_current_qs(None)
			# 逐题作答
			while True:
				# 定位当前题目，由于course-presentation的已返回，此处不再处理
				# find_question = True
				# if frame_type != "h5p-course-presentation":
				current_qs = main.find_element(CSS, ".h5p-question[style='']")
				# else:
				# 	find_question = False
				# 	current_page = main.find_element(CSS, ".h5p-current")
				# 	try:
				# 		current_qs = current_page.find_element(CSS, ".h5p-question")
				# 	except NoSuchElementException:
				# 		pass
				# 	else:
				# 		find_question = True
				# # 确定题目类型
				# if find_question:
				qs_type = select_qs_type(current_qs.get_attribute('class'))
				set_current_qs(current_qs)
				distribute_to_qs_module(qs_type)
				# 点击下一题按钮
				if not next_page(main, frame_type):
					break
			# 题目做完以后，尝试点击完成按钮
			finish(main)

		else:
			# 如果题目都在一页上，直接全部作答
			for current_qs in questions:
				current_qs_class = current_qs.get_attribute("class")
				qs_type = select_qs_type(current_qs_class)
				set_current_qs(current_qs)
				distribute_to_qs_module(qs_type)
			# 尝试结束按钮
			try:
				finish_btn = main.find_element(CSS, "button.h5p-question-finish")
				wait_until_clickable_click(finish_btn)
			except NoSuchElementException:
				pass
			finally:
				wait_for_submit()

	except Exception as e:
		print(f"任务 {href} 无法完成，出现错误: {e}")

	# 最后把mark-as-done点了
	else:
		click_mark_as_done(href)


def start(main, frame_type):
	if frame_type == "h5p-interactive-book":
		try:
			start_btn = main.find_element(CSS, ".h5p-interactive-book-cover-readbutton")
		except NoSuchElementException:
			return
		else:
			wait_until_clickable_click(start_btn)
			return

	try:
		start_page = main.find_element(CSS, "[class*='intro-page']:not([style*='display'])")
	except NoSuchElementException:
		return
	else:
		start_button = start_page.find_element(CSS, "a.qs-startbutton")  # 开始按钮，此处可能有匹配不完全的问题
		wait_until_clickable_click(start_button)


def previous_page(main, frame_type):
	# 如果是h5p-course-presentation类型，点击右下角的上一页按钮
	if frame_type == "h5p-course-presentation":
		try:
			prev_btn = main.find_element(CSS, ".h5p-footer-previous-slide.h5p-footer-button[aria-disabled='false']")
		except NoSuchElementException:
			pass
		else:
			wait_until_clickable_click(prev_btn)
			return True

	# 如果是h5p-interactive-book类型，不需要点击上一页，直接返回False
	elif frame_type == "h5p-interactive-book":
		try:
			prev_btn = main.find_element(CSS, "[aria-label='Previous page']:not([disabled='disabled'])")
		except NoSuchElementException:
			pass
		else:
			wait_until_clickable_click(prev_btn)
			return True

	else:
		try:
			# 定位当前题目
			current_qs = get_current_qs()
			# 定位按钮集
			current_qs_btns = current_qs.find_element(CSS, ".h5p-question-buttons")
			prev_btn = current_qs_btns.find_element(CSS, ".h5p-question-prev")
		except NoSuchElementException:
			pass
		else:
			wait_until_clickable_click(prev_btn)
			return True

	return False


def next_page(main, frame_type):
	# 如果是h5p-course-presentation类型，点击右下角的下一页按钮
	if frame_type == "h5p-course-presentation":
		try:
			next_btn = main.find_element(CSS, ".h5p-footer-next-slide.h5p-footer-button[aria-disabled='false']")
		except NoSuchElementException:
			pass
		else:
			wait_until_clickable_click(next_btn)
			return True

	# 如果是h5p-interactive-book类型，点击右上角的下一页按钮
	elif frame_type == "h5p-interactive-book":
		try:
			next_btn = main.find_element(CSS, "[aria-label='Next page']:not([disabled='disabled'])")
		except NoSuchElementException:
			pass
		else:
			wait_until_clickable_click(next_btn)
			return True

	# 尝试点击下一题按钮，如果没有则说明是最后一题或者是都在一页上（针对除了h5p-course-presentation的类型）
	else:
		try:
			# 定位当前题目
			current_qs = get_current_qs()
			# 定位按钮集
			current_qs_btns = current_qs.find_element(CSS, ".h5p-question-buttons")
			next_btn = current_qs_btns.find_element(CSS, ".h5p-question-next")
		except NoSuchElementException:
			pass
		else:
			wait_until_clickable_click(next_btn)
			return True

	return False


def distribute_to_qs_module(qs_type):
	if qs_type == "h5p-single-choice-set":
		import question_set.single_choice_set
		question_set.single_choice_set.solve_single_choice_set()
	elif qs_type == "h5p-find-the-words":
		import question_set.find_the_words
		question_set.find_the_words.solve_find_the_words()
	elif qs_type == "h5p-true-false":
		import question_set.true_false
		question_set.true_false.solve_true_false()
	elif qs_type == "h5p-summary":
		import question_set.summary
		question_set.summary.solve_summary()
	else:
		import question_set.general
		question_set.general.solve_general_qs()


def finish(main):
	try:
		finish_btn = main.find_element(CSS, "button.h5p-question-finish")
		wait_until_clickable_click(finish_btn)

	except NoSuchElementException:
		pass

	finally:
		wait_for_submit()


def select_qs_type(current_qs_classes):
	type_of_qs = None
	for qs_template in qs_templates:
		if qs_template in current_qs_classes:
			type_of_qs = qs_template
			break
	return type_of_qs


def select_frame():
	frame_type = None
	for frame in frames:
		try:
			driver.find_element(CSS, f".{frame}")
		except NoSuchElementException:
			continue
		else:
			frame_type = frame
			break
	return frame_type


def wait_until_clickable_click(element):
	wait.until(EC.element_to_be_clickable(element))
	element.click()


def wait_for_submit():
	retry_count = 1
	while shared_read().get("succeed") is False:
		time.sleep(0.2)
		retry_count += 1
		if retry_count >= 5:
			break


def click_mark_as_done(herf):
	try:
		driver.get(herf)
		# 先把所有标记点击完成的单元格点掉
		mark_as_done_btn = driver.find_element(By.CSS_SELECTOR, "button.btn.text-nowrap")
	except NoSuchElementException:
		pass
	else:
		if "Mark as done" in mark_as_done_btn.get_attribute("innerText"):
			mark_as_done_btn.click()

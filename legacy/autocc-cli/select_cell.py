"""
选择单元格模块 - 查找并打印页面链接
"""
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import get_driver, get_config, save_config

def select_cell():
	conf = get_config()
	course_link = conf.get('target', 'course_shell', fallback='') if conf.has_section('target') else ''
	if course_link == "":
		print("未找到课程链接记录，即将重新选择课程")
		find_select_new_links()
	else:
		print(f"找到已保存的课程链接: {course_link}，即将跳转")
		drive = get_driver()
		drive.get(course_link)
		print(f"已跳转到课程链接: {course_link}")

def find_select_new_links():
	"""查找并打印页面中的链接"""
	drive = get_driver()
	try:
		wait = WebDriverWait(drive, 10)
		main_div = wait.until(
			EC.presence_of_element_located((By.CLASS_NAME, "frontpage-course-list-enrolled"))
		)

		# 在main div中查找所有a标签
		courses = {}

		infos = main_div.find_elements(By.CLASS_NAME, "info")
		for i,info in enumerate(infos,1):
			course = info.find_element(By.TAG_NAME, "a")
			coursename = course.get_attribute("innerText")
			href = course.get_attribute("href")
			courses[i]=[coursename,href]

		print(f"找到 {len(courses)} 个链接:")
		for index, course in courses.items():
			print(f"{index}. {course[0]}")

		select = input("请输入想要学习的课程：")
		save_links_to_file(courses[int(select)][1])
		print(f"已选择课程: {courses[int(select)][0]}，链接已保存。")
		drive.get(courses[int(select)][1])


	except Exception as e:
		print(f"查找链接时出错: {e}")

def save_links_to_file(link):
	"""将链接保存到文件"""
	conf = get_config()
	if 'target' not in conf:
		conf.add_section('target')
	conf['target']['course_shell'] = link
	save_config()
from selenium.common import NoSuchElementException
from selenium.webdriver.common.by import By

from config import get_driver, set_total_count

# not_h5p_pages = {}
unsupported_h5p_pages = ["https://www.cloudcampus.com.cn/mod/h5pactivity/view.php?id=591330",
                         "https://www.cloudcampus.com.cn/mod/h5pactivity/view.php?id=591270",
                         "https://www.cloudcampus.com.cn/mod/h5pactivity/view.php?id=625359" #video
                         ]


def find_todo_pages()->dict[int,list[str]]:
	# 延迟获取驱动，避免在模块导入时初始化浏览器
	driver = get_driver()
	todo_pages = {}
	current_url = driver.current_url
	target_url = current_url.replace("course/view", "grade/report/user/index")
	driver.get(target_url)

	table = driver.find_element(By.CSS_SELECTOR, "tbody")
	cells = table.find_elements(By.CSS_SELECTOR, "td.column-percentage")
	to_do_index = 1
	unable_index = 1
	for cell in cells:
		if "100.00 %" not in cell.text:
			parent_cell = cell.find_element(By.XPATH, "..")

			if "lastrow" in parent_cell.get_attribute("class"):
				break

			# 获取任务标题和链接
			item_cell = parent_cell.find_element(By.CSS_SELECTOR, ".column-itemname")
			item_element = item_cell.find_element(By.CSS_SELECTOR, "a")
			herf = item_element.get_attribute("href")
			title = item_element.text

			# 看看是不是h5p任务
			try:
				item_cell.find_element(By.XPATH, ".//span[@title='H5P']")
			except NoSuchElementException:
				# not_h5p_pages[unable_index] = [title, herf]
				unable_index += 1
				pass
			else:
				if whether_h5p_supported(herf):
					todo_pages[to_do_index] = [title, herf]
					to_do_index += 1

	set_total_count(len(cells) - unable_index - 1)  # 减去表尾行

	print(f"找到 {len(todo_pages)} 个待完成的任务。")
	for index, (title, herf) in todo_pages.items():
		print(f"{index}. {title} - {herf}")
	print(f"应付{len(todo_pages) / (len(cells) - unable_index - 1) * 100:.2f}%。")

	deal_or_not = input("是否继续完成这些任务？(y/n): ")

	if deal_or_not.lower() != 'y':
		print("用户选择不继续，程序结束。")
		exit(0)
	else:
		return todo_pages


def whether_h5p_supported(url: str) -> bool:
	for unsupported_url in unsupported_h5p_pages:
		if url.startswith(unsupported_url):
			return False
	return True

"""
query程序 -
"""
import time

from selenium.webdriver.edge.webdriver import WebDriver
from selenium.webdriver.common.by import By
from config import close_driver, get_driver
import login
from login import get_user_info
from mitm import start_mitmproxy, stop_mitmproxy

def query():
	"""主程序入口"""
	mitmproxy_process = None
	try:
		mitmproxy_process = start_mitmproxy("127.0.0.1", 8800)  # 启动 mitmproxy
		driver:WebDriver = get_driver() # 获取驱动实例，放在循环外面，避免重复初始化浏览器
		time.sleep(2)
		accounts = get_user_info()
		print(accounts)
		cnt = 0

		for acc in accounts:
			cnt += 1
			try:
				# 登录
				login.try_login(acc['account'], acc['password'])
				driver.get("https://www.cloudcampus.com.cn/grade/report/user/index.php?id=11881")
				print(f"正在处理第{cnt}个用户: {acc['account']}")

				# 等待页面加载
				time.sleep(3)

				# 查找成绩
				try:
					# 使用更精准的CSS选择器
					grade_element = driver.find_element(By.CSS_SELECTOR,
														"td.level1.d1.baggt.b2b.itemcenter.column-grade.cell.c2")
					grade = grade_element.text.strip()
					print(f"成绩: {grade}")

					# 或者使用包含所有类的选择器
					# grade_element = driver.find_element(By.CSS_SELECTOR, "td[class*='level1'][class*='d1'][class*='baggt'][class*='b2b'][class*='itemcenter'][class*='column-grade'][class*='cell'][class*='c2']")

				except:
					print("未找到成绩")

			except Exception as e:
				print(f"程序执行出错: {e}")
			finally:
				driver.delete_all_cookies() # 清除cookie，准备下一个账号登录
				time.sleep(3)

	except Exception as e:
		print(f"主程序出错: {e}")
	finally:
		# 确保无论是否出错都停止mitmproxy
		if mitmproxy_process:
			stop_mitmproxy(mitmproxy_process)
		print("程序执行完毕")

if __name__ == "__main__":
	query()
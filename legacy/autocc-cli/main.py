"""
主程序 - 自动化云校园登录和链接查找
"""
import time
from config import close_driver
import login
import select_cell
import select_assignment
import finish_assignment
from login import get_user_info
from mitm import start_mitmproxy, stop_mitmproxy

def main():
	"""主程序入口"""
	mitmproxy_process = start_mitmproxy("127.0.0.1", 8800)  # 启动 mitmproxy
	time.sleep(2)
	accounts=get_user_info()
	cnt=0
	for acc in accounts:
		try:
			# 登录
			login.try_login(acc['account'], acc['password'])
			cnt=cnt+1
			print("正在处理第",cnt,"个用户")
			# 查找链接

			select_cell.select_cell()

			# 挑选任务
			todo_dict = select_assignment.find_todo_pages()

			# 完成任务
			finish_assignment.finish_assignments(todo_dict)

		except Exception as e:
			print(f"程序执行出错: {e}")
		finally:
			# 关闭浏览器
			time.sleep(0.5)
			close_driver()
			stop_mitmproxy(mitmproxy_process)
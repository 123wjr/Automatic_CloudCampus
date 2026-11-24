import time

from selenium.webdriver.common.by import By

from config import get_current_qs, get_driver
from finish_assignment import wait_for_submit


def solve_find_the_words():
	current_qs = get_current_qs()
	driver = get_driver()
	check_btn = current_qs.find_element(By.TAG_NAME, "button")  # 很弱的定位
	driver.execute_script("arguments[0].scrollIntoView(true);", check_btn)
	time.sleep(0.4)
	driver.execute_script("arguments[0].click();", check_btn)
	wait_for_submit()
	return

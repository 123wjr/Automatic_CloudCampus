import time

from selenium.common import NoSuchElementException
from selenium.webdriver.common.by import By

from config import get_current_qs, get_driver, shared_read
from finish_assignment import wait_for_submit

CSS = By.CSS_SELECTOR


def solve_general_qs():
	driver = get_driver()
	current_qs = get_current_qs()
	try:
		check_btn = current_qs.find_element(CSS, ".h5p-question-check-answer")
	except NoSuchElementException:
		check_btn = current_qs.find_element(CSS, ".h5p-joubelui-button")
	driver.execute_script("arguments[0].scrollIntoView(true);", check_btn)
	time.sleep(0.7)
	driver.execute_script("arguments[0].click();", check_btn)
	wait_for_submit()
	return

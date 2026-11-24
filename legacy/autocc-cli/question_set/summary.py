from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

from config import get_driver, get_current_qs


def solve_summary():
	driver = get_driver()
	current_qs:WebElement = get_current_qs()
	target_element = current_qs.find_element(By.CLASS_NAME,"summary-claim-unclicked")
	driver.execute_script("arguments[0].click();", target_element)
	return
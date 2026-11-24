import time

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By

from finish_assignment import wait_for_submit, wait_until_clickable_click

CSS = By.CSS_SELECTOR
from config import get_current_qs


def solve_single_choice_set():
	current_qs = get_current_qs()
	qs_content = current_qs.find_element(CSS, ".h5p-question-content")
	while True:
		try:
			current_slide = qs_content.find_element(CSS, ".h5p-sc-current-slide")
			wait_until_clickable_click(current_slide.find_element(CSS, "li.h5p-sc-is-correct"))
			time.sleep(2)
		except NoSuchElementException:
			break
	wait_for_submit()
	return

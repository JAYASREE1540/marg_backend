import os
import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException

@pytest.fixture(scope="function")
def driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=chrome_options)
    driver.implicitly_wait(10)
    driver.base_url = os.getenv("BASE_URL", "http://127.0.0.1:5000")
    yield driver
    driver.quit()

def test_web_login_success(driver):
    """SELENIUM‑001 – verify successful web login."""
    driver.get(f"{driver.base_url}/login")
    try:
        driver.find_element(By.NAME, "email").send_keys("testuser@example.com")
        driver.find_element(By.NAME, "password").send_keys("Secret123!")
        driver.find_element(By.XPATH, "//button[contains(text(),'Login')]").click()
        driver.find_element(By.ID, "dashboard")
    except NoSuchElementException as e:
        pytest.fail(f"Login flow broken: {e}")

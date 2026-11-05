import os
import pytest
from appium import webdriver
from selenium.common.exceptions import NoSuchElementException

@pytest.fixture(scope="function")
def driver():
    caps = {
        "platformName": "Android",
        "platformVersion": "13",
        "deviceName": "Android Emulator",
        "automationName": "UiAutomator2",
        "appPackage": "com.example.marg",       # ← change to your package
        "appActivity": ".MainActivity",         # ← change to your activity
        "noReset": True,
    }
    host = os.getenv("APPIUM_HOST", "localhost")
    port = os.getenv("APPIUM_PORT", "4723")
    driver = webdriver.Remote(f"http://{host}:{port}/wd/hub", caps)
    driver.implicitly_wait(10)
    yield driver
    driver.quit()

def test_login_success(driver):
    """APPIUM‑001 – verify successful login."""
    try:
        driver.find_element_by_accessibility_id("login_button").click()
    except NoSuchElementException:
        pytest.fail("Login button missing")
    driver.find_element_by_accessibility_id("email_input").send_keys("testuser@example.com")
    driver.find_element_by_accessibility_id("password_input").send_keys("Secret123!")
    driver.find_element_by_accessibility_id("submit_button").click()
    try:
        driver.find_element_by_accessibility_id("home_screen")
    except NoSuchElementException:
        pytest.fail("Home screen not shown after login")

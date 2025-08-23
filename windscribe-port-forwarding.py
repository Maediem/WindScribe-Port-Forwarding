#########################################################################################################################
# WARNING: Running this script repeatedly or in rapid succession may result in your account being temporarily disabled. #
#########################################################################################################################

# pip install requests selenium selenium-stealth python-dotenv qbittorrent-api

# --- Standard libraries ---
import os
import pickle
import datetime
import time
import subprocess
import random
import email.utils # Needed for parsing cookie expiry dates

# --- Third-Party Packages ---
import requests # Needed for FlareSolverr

# Selenium-related imports
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium_stealth import stealth

# Environment variable handling
from dotenv import load_dotenv, set_key

# qBittorrent API
from qbittorrentapi import Client, LoginFailed



#############
# VARIABLES #
#############

# --- Login Configuration ---
# Choose the login method: "selenium" or "flaresolverr"
# "selenium": Uses browser automation only. Faster, but likely to be blocked by CAPTCHA. Uses cookies to persist sessions.
# "flaresolverr": Hybrid method. Uses FlareSolverr to bypass CAPTCHA, then Selenium to interact. Most robust option.
LOGIN_METHOD = "flaresolverr"  # <-- CHANGE THIS TO "selenium" OR "flaresolverr"

# A list of realistic user-agents to be used when LOGIN_METHOD is "selenium".
# This helps mimic different browsers and operating systems to reduce blocking likelihood.
USER_AGENTS = [
    # Windows 10/11
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",

    # macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:126.0) Gecko/20100101 Firefox/126.0"
]

# --- FlareSolverr Configuration ---
# Only used if LOGIN_METHOD is "flaresolverr"
FLARESOLVERR_URL = "http://localhost:8191/v1"

# --- Configuration Flags ---
ENABLE_QBITTORRENT_UPDATE = False     # Enable or disable qBittorrent port update
ENABLE_DOCKER_RESTART = True          # Enable or disable Docker container restart

# --- Docker Configuration ---
# Change the path to the proper directory
ROOT_DIR = "/path/to/root/directory"
DOCKER_COMPOSE_FILE = os.path.join(ROOT_DIR, "master-docker-compose.yml")
DOCKER_VPN_INSTANCE = "gluetun-openvpn"
DOCKER_QBIT_INSTANCE = "qb-private"

# Command used to restart the dockers if enabled
DOCKER_RESTART_CMD = [
            "docker-compose", "-f", DOCKER_COMPOSE_FILE,
            "up", "-d", "--force-recreate",
            DOCKER_VPN_INSTANCE, DOCKER_QBIT_INSTANCE
]

# --- File Configuration ---
# Change the path to the proper directories
LOG_FILE = "/var/log/windscribe-port-forwarding.log"                        # File to store logging if enabled
LOG_TO_FILE = True                                                          # True = Enable logging
COOKIES_FILE = os.path.join(ROOT_DIR, "scripts", "windscribe.cookies")      # File to store cookies for Windscribe login
CREDENTIALS_ENV_FILE = os.path.join(ROOT_DIR, "scripts", "credentials.env") # File with Windscribe & qBittorrent credentials
ENV_FILE = os.path.join(ROOT_DIR, ".env")                                   # Docker .env file to store the forwarded port
SCREENSHOT_DIR = os.path.join(ROOT_DIR, "scripts", "screenshots")           # Directory to save screenshots on failure (useful for troubleshooting)

# --- Load environment variables ---
load_dotenv(CREDENTIALS_ENV_FILE)
load_dotenv(ENV_FILE)

# --- Extract credentials and settings from environment ---
ENV_KEY_PORT_FORWARDED  = "VPN_PORT_FORWARDED"
VPN_PORT_FORWARDED = os.getenv(ENV_KEY_PORT_FORWARDED)
WS_USERNAME = os.getenv("WS_USERNAME")
WS_PASSWORD = os.getenv("WS_PASSWORD")
QBIT_HOST = os.getenv("QBIT_HOST")
QBIT_USERNAME = os.getenv("QBIT_USERNAME")
QBIT_PASSWORD = os.getenv("QBIT_PASSWORD")



#############
# FUNCTIONS #
#############

def print_message(log_level: str, msg: str, print_only: bool = False):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{log_level}] {msg}"
    print(log_entry)
    
    if LOG_TO_FILE and not print_only:
        with open(LOG_FILE, "a") as f:
            f.write(log_entry + "\n")

# --- Selenium-Only Method Functions ---
def save_cookies():
    with open(COOKIES_FILE, "wb") as f:
        pickle.dump(driver.get_cookies(), f)
    
    print_message("INFO", "Selenium login cookies saved.")

def load_cookies():
    if os.path.exists(COOKIES_FILE):
        driver.get("https://windscribe.com")
        
        with open(COOKIES_FILE, "rb") as f:
            cookies = pickle.load(f)
            for cookie in cookies:
                driver.add_cookie(cookie)
        
        print_message("INFO", "Selenium login cookies loaded.")
        return True
    
    return False

def is_logged_in():
    print_message("INFO", "Checking Windscribe login status...")
    driver.get("https://windscribe.com/myaccount")
    
    try:
        wait.until(EC.url_to_be("https://windscribe.com/myaccount"))
        print_message("INFO", "Windscribe login confirmed via cookies.")
        return True
    
    except TimeoutException:
        return False

# --- Hybrid & Selenium Method Functions ---
def get_flaresolverr_clean_session(url):
    print_message("INFO", "Using FlareSolverr to get a clean session for Selenium...")
    get_challenge_payload = {"cmd": "request.get", "url": url, "maxTimeout": 120000}
    
    try:
        response = requests.post(FLARESOLVERR_URL, json=get_challenge_payload)
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") == "ok":
            print_message("INFO", "FlareSolverr successfully bypassed initial challenge.")
            return data["solution"]
        else:
            print_message("ERROR", f"FlareSolverr failed to solve challenge. Message: {data.get('message')}")
            return None
    
    except requests.exceptions.RequestException as e:
        print_message("ERROR", f"Failed to connect to FlareSolverr at {FLARESOLVERR_URL}. Error: {e}")
        return None

def human_like_typing(element, text):
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.05, 0.2))

# Perform a robust JavaScript click
def click_with_javascript(element):
    driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", element)
    driver.execute_script("arguments[0].click();", element)

# Waits for an element to be clickable, adds a human-like delay, then clicks it robustly
def wait_and_click(by_locator, locator_value, timeout=20):
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((by_locator, locator_value))
        )
        time.sleep(random.uniform(0.7, 1.8))  # Simulate human pause
        click_with_javascript(element)
        
        print_message("DEBUG", f"Successfully clicked element: {locator_value}", print_only=True)
    
    except TimeoutException:
        print_message("ERROR", f"Timeout while waiting to click element: {locator_value}")
        raise  # Re-raise the exception to be caught by the main try/except block

def perform_selenium_login():
    try:
        print_message("INFO", "Performing login actions with Selenium...")
        
        username_field = wait.until(EC.visibility_of_element_located((By.ID, "username")))
        human_like_typing(username_field, WS_USERNAME)
        
        password_field = driver.find_element(By.ID, "pass")
        human_like_typing(password_field, WS_PASSWORD)
        
        driver.find_element(By.ID, "login_button").click()
        wait.until(EC.url_to_be("https://windscribe.com/myaccount"))
        
        print_message("INFO", "Selenium login successful.")
        save_cookies()
    
    except TimeoutException:
        print_message("ERROR", "Selenium login failed. This could be due to wrong credentials, a CAPTCHA, or a website change.")
        
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        screenshot_path = os.path.join(SCREENSHOT_DIR, f"selenium_login_failure_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        driver.save_screenshot(screenshot_path)
        print_message("INFO", f"Screenshot saved to: {screenshot_path}")
        
        driver.quit()
        exit(1)

# --- Post-Login Action Functions ---
def update_env_file(new_port, timeout=5):
    if set_key(ENV_FILE, ENV_KEY_PORT_FORWARDED, new_port):
        start = time.time()
        
        while time.time() - start < timeout:
            load_dotenv(ENV_FILE, override=True)
            if os.getenv(ENV_KEY_PORT_FORWARDED) == new_port:
                print_message("INFO", f"Updated '{ENV_FILE}' with '{ENV_KEY_PORT_FORWARDED}={new_port}'")
                return
            
            time.sleep(1)
        
        print_message("WARN", f"{ENV_FILE} was not updated as expected within {timeout} seconds.")
    
    else:
        print_message("ERROR", f"Could not update {ENV_FILE}. Please check file permissions.")

def update_qbittorrent_port(new_port):
    if not all([QBIT_HOST, QBIT_USERNAME, QBIT_PASSWORD]):
        print_message("WARN", "qBittorrent credentials not found. Skipping update.")
        return
    
    print_message("INFO", f"Updating qBittorrent port to {new_port}...")
    
    try:
        qbt_client = Client(host=QBIT_HOST, username=QBIT_USERNAME, password=QBIT_PASSWORD)
        qbt_client.auth_log_in()
        
        current_port = qbt_client.app.preferences().get("listen_port")
        
        if str(current_port) == str(new_port):
            print_message("INFO", f"qBittorrent port is already set to {new_port}. No action needed.")
        else:
            qbt_client.app.set_preferences(prefs={'listen_port': new_port})
            print_message("INFO", f"qBittorrent listening port updated to {new_port}.")
    
    except LoginFailed:
        print_message("ERROR", "qBittorrent login failed. Check credentials.")
    
    except Exception as e:
        print_message("ERROR", f"An error occurred while updating qBittorrent: {e}")

def restart_docker_containers(new_port=None):
    if not DOCKER_COMPOSE_FILE or not os.path.exists(DOCKER_COMPOSE_FILE):
        print_message("WARNING", f"Docker compose file not found: {DOCKER_COMPOSE_FILE}")
        return
    
    if not new_port:
        print_message("WARNING", "New port is either None or empty.")
        return

    if new_port != VPN_PORT_FORWARDED:
        update_env_file(new_port)
        print_message("INFO", "Restarting Docker containers...")
        
        try:
            result = subprocess.run(DOCKER_RESTART_CMD, capture_output=True, text=True, check=True)
            print_message("INFO", "Docker containers restarted successfully.")
            
            if result.stdout:
                print_message("DEBUG", f"[DOCKER STDOUT]: {result.stdout}", print_only=True)
        
        except FileNotFoundError:
            print_message("ERROR", "'docker-compose' not found. Please install it or check your path.")
        
        except subprocess.CalledProcessError as e:
            print_message("ERROR", "Docker-compose failed.")
            
            if e.stderr:
                print_message("DEBUG", f"[DOCKER STDERR]: {e.stderr}", print_only=True)
        
        except Exception as e:
            print_message("ERROR", f"Unexpected error during Docker restart: {e}")
    else:
        print_message("INFO", f"Port unchanged ({VPN_PORT_FORWARDED}). Skipping restart.")



###############
# MAIN SCRIPT #
###############
print_message("INFO", "Script started.")

driver = None
wait = None

# Configure Chrome Options
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--window-size=1920,1000") # More "human" default to simulate a maximized browser on a 1080p screen

if LOGIN_METHOD == "flaresolverr":
    print_message("INFO", "Using login method: Hybrid (FlareSolverr + Selenium)")
    fs_solution = get_flaresolverr_clean_session("https://windscribe.com/login")
    
    if not fs_solution:
        print_message("CRITICAL", "Failed to obtain clean session from FlareSolverr. Exiting.")
        exit(1)
        
    windscribe_cookies = fs_solution.get("cookies", [])
    fs_user_agent = fs_solution.get("userAgent")
    
    # Use the exact user agent from FlareSolverr for consistency
    chrome_options.add_argument(f"user-agent={fs_user_agent}")

    print_message("INFO", "Launching browser and injecting trusted session...")
    driver = webdriver.Chrome(options=chrome_options)
    
    stealth(driver, languages=["en-US", "en"], vendor="Google Inc.", platform="Win32",
            webgl_vendor="Intel Inc.", renderer="Intel Iris OpenGL Engine", fix_hairline=True)
    
    wait = WebDriverWait(driver, 20)
    
    driver.get("https://windscribe.com")
    for cookie in windscribe_cookies:
        selenium_cookie = {k: v for k, v in cookie.items() if k != 'expires'}
        
        if cookie.get('expires'):
            expiry_datetime = email.utils.parsedate_to_datetime(cookie['expires'])
            selenium_cookie['expiry'] = int(expiry_datetime.timestamp())
        
        driver.add_cookie(selenium_cookie)
    
    print_message("INFO", "Navigating to login page with trusted session...")
    driver.get("https://windscribe.com/login")
    perform_selenium_login()

elif LOGIN_METHOD == "selenium":
    print_message("INFO", "Using login method: Selenium Only")
    chrome_options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")
    driver = webdriver.Chrome(options=chrome_options)
    
    stealth(driver, languages=["en-US", "en"], vendor="Google Inc.", platform="Win32",
            webgl_vendor="Intel Inc.", renderer="Intel Iris OpenGL Engine", fix_hairline=True)
    
    wait = WebDriverWait(driver, 20)
    
    if load_cookies() and is_logged_in():
        print_message("INFO", "Successfully logged in using existing session cookies.")
    else:
        print_message("INFO", "No valid session found. Performing fresh login.")
        driver.get("https://windscribe.com/login")
        perform_selenium_login()
else:
    print_message("ERROR", f"Invalid LOGIN_METHOD: '{LOGIN_METHOD}'. Please choose 'selenium' or 'flaresolverr'.")
    exit(1)

# Requesting Port Forwarding after successful login
new_port = None
try:
    print_message("INFO", "Navigating to Windscribe's port forwarding page...")
    wait_and_click(By.ID, "menu-ports")
    
    print_message("INFO", "Switching to ephemeral port section...")
    wait_and_click(By.ID, "pf-eph-btn")

    try:
        print_message("INFO", "Checking for existing port to delete...")
        
        # A short wait to ensure the button appears after the previous click
        time.sleep(random.uniform(1.6, 3.2))
        
        delete_button = driver.find_element(By.XPATH, "//button[normalize-space()='Delete Port']")
        
        wait_and_click(By.XPATH, "//button[normalize-space()='Delete Port']")
        wait.until(EC.invisibility_of_element_located((By.XPATH, "//button[normalize-space()='Delete Port']")))
        
        print_message("INFO", "Existing port deleted.")
    except (NoSuchElementException, TimeoutException):
        print_message("INFO", "No existing port found to delete.")

    print_message("INFO", "Requesting new matching port...")
    wait_and_click(By.XPATH, "//button[normalize-space()='Request Matching Port']")

    port_element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "#epf-port-info > span")))
    new_port_str = port_element.text
    
    if new_port_str and new_port_str.isdigit():
        new_port = int(new_port_str)
        print_message("INFO", f"Acquired new port from Windscribe: {new_port}")
    else:
        raise ValueError(f"Could not extract a valid port. Found: '{new_port_str}'")

except (Exception) as e: # Catch any exception during this critical block
    print_message("ERROR", f"A critical step failed while getting port from Windscribe: {e}")
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    
    screenshot_path = os.path.join(SCREENSHOT_DIR, f"interaction_failure_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    driver.save_screenshot(screenshot_path)
    
    print_message("INFO", f"Screenshot saved to: {screenshot_path}")
    
    if driver:
        driver.quit()
    exit(1)

finally:
    if driver:
        driver.quit()

# Post-Requesting Port Forwarding
if new_port:
    if ENABLE_QBITTORRENT_UPDATE:
        update_qbittorrent_port(new_port)

    if ENABLE_DOCKER_RESTART:
        restart_docker_containers(str(new_port))

print_message("INFO", "Script finished.")

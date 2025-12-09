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

#--------------------------
# USER CUSTOM CONFIGURATION
#--------------------------

# --- Paths ---
ROOT_DIR = "/data/docker" # If empty, defaults to directory of this script.
DOCKER_COMPOSE_FILE = os.path.join(ROOT_DIR, "master-docker-compose.yml") # Can change the docker compose file name if using docker
ENV_FILE = os.path.join(ROOT_DIR, ".env")
COOKIES_FILE = os.path.join(ROOT_DIR, "scripts", "windscribe.cookies") # This will write the cookie data in the following file: /data/docker/scripts/windscribe.cookies
SCREENSHOT_DIR = os.path.join(ROOT_DIR, "scripts", "screenshots")

# --- Core Settings ---
LOGIN_METHOD = "flaresolverr"                 # "selenium" or "flaresolverr"
FLARESOLVERR_URL = "http://localhost:8191/v1" # Only used if LOGIN_METHOD is "flaresolverr"

# --- Feature Flags ---
ENABLE_QBITTORRENT_UPDATE = False  # Enable or disable qBittorrent port update
ENABLE_DOCKER_RESTART = True       # Enable or disable Docker container restart

# --- Docker Settings ---
DOCKER_VPN_INSTANCE  = "gluetun-openvpn"
DOCKER_QBIT_INSTANCE = "qb-private"

# --- Logging ---
LOG_FILE = "/var/log/windscribe-port-forwarding.log"
LOG_TO_FILE = True

# --- Manual Credentials (optional) ---
# If left empty (""), script will fall back to environment variables.
WS_USERNAME   = ""           # Windscribe username
WS_PASSWORD   = ""           # Windscribe password

QBIT_HOST     = ""           # Example: "http://localhost:8080"
QBIT_USERNAME = ""
QBIT_PASSWORD = ""


#---------------------------------------
# INTERNAL CONFIGURATION (DO NOT MODIFY)
#---------------------------------------

# Set default ROOT_DIR if empty
if ROOT_DIR == "":
    ROOT_DIR = os.path.normpath(os.path.dirname(os.path.abspath(__file__)))

# Ensure credentials.env fallback
CREDENTIALS_ENV_FILE = os.path.join(ROOT_DIR, "scripts", "credentials.env")
if not os.path.isfile(CREDENTIALS_ENV_FILE):
    CREDENTIALS_ENV_FILE = os.path.join(ROOT_DIR, "credentials.env")

# Load environment variables
load_dotenv(CREDENTIALS_ENV_FILE)
load_dotenv(ENV_FILE)
ENV_KEY_PORT_FORWARDED  = "VPN_PORT_FORWARDED"
VPN_PORT_FORWARDED = os.getenv(ENV_KEY_PORT_FORWARDED)

# --- Fill values from environment if user left them empty ---
WS_USERNAME   = WS_USERNAME   or os.getenv("WS_USERNAME", "")
WS_PASSWORD   = WS_PASSWORD   or os.getenv("WS_PASSWORD", "")
QBIT_HOST     = QBIT_HOST     or os.getenv("QBIT_HOST", "")
QBIT_USERNAME = QBIT_USERNAME or os.getenv("QBIT_USERNAME", "")
QBIT_PASSWORD = QBIT_PASSWORD or os.getenv("QBIT_PASSWORD", "")


# Docker restart command
DOCKER_RESTART_CMD = [
    "docker-compose", "-f", DOCKER_COMPOSE_FILE,
    "up", "-d", "--force-recreate",
    DOCKER_VPN_INSTANCE, DOCKER_QBIT_INSTANCE
]


##########################
# VALIDATION (SAFE EXIT) #
##########################

# --- Windscribe credentials are ALWAYS required ---
if not WS_USERNAME or not WS_PASSWORD:
    print("[ERROR] Missing Windscribe credentials: WS_USERNAME / WS_PASSWORD")
    print("        Provide them manually OR set them in credentials.env")
    sys.exit(1)

# --- FlareSolverr must exist for flaresolverr login ---
if LOGIN_METHOD == "flaresolverr":
    if not FLARESOLVERR_URL:
        print("[ERROR] LOGIN_METHOD is 'flaresolverr', but FLARESOLVERR_URL is empty.")
        sys.exit(1)

# --- Docker validation ---
if ENABLE_DOCKER_RESTART:
    if not os.path.isfile(DOCKER_COMPOSE_FILE):
        print(f"[ERROR] Docker restart enabled, but docker-compose file missing:\n{DOCKER_COMPOSE_FILE}")
        sys.exit(1)

# --- qBittorrent validation ---
if ENABLE_QBITTORRENT_UPDATE:
    if not (QBIT_HOST and QBIT_USERNAME and QBIT_PASSWORD):
        print("[ERROR] qBittorrent update enabled, but required credentials are missing.")
        sys.exit(1)



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

# --- Configure Chrome Options ---
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--window-size=1920,1000") # More "human" default to simulate a maximized browser on a 1080p screen

# --- Login ---
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

# --- Getting the Ephemeral Port ---
new_port = None
try:
    print_message("INFO", "Navigating to Windscribe's port forwarding page...")
    wait_and_click(By.ID, "menu-ports")
    wait.until(EC.presence_of_element_located((By.ID, "ports-main-tab")))

    print_message("INFO", "Looking for existing Ephemeral Port (fully dynamic)...")

    # Dynamic, case-insensitive match for "Ephemeral Port" anywhere within a pf-item
    eph_item_xpath = (
        "//div[contains(@class,'pf-item') and "
        "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'ephemeral port')]"
    )

    try:
        eph_item = wait.until(EC.presence_of_element_located((By.XPATH, eph_item_xpath)))
        print_message("INFO", "Ephemeral Port entry found.")

        # Find the toggle button inside this pf-item
        toggle_btn = eph_item.find_element(By.CSS_SELECTOR, "button.pf-info-toggle")
        toggle_btn.click()
        print_message("INFO", "Opened EPF menu.")

        # Click "Delete" from the dropdown (dynamic text match)
        delete_xpath = ".//li[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'delete')]"
        delete_option = wait.until(EC.element_to_be_clickable((By.XPATH, delete_xpath)))
        delete_option.click()

        # Wait for deletion to finish
        wait.until(EC.invisibility_of_element_located((By.XPATH, eph_item_xpath)))
        print_message("INFO", "Old Ephemeral Port deleted.")

    except TimeoutException:
        print_message("INFO", "No existing Ephemeral Port found. Continuing...")

    # Request a new port
    print_message("INFO", "Requesting a new ephemeral port...")
    try:
        wait_and_click(By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'request') and contains(., 'Port')]")
    except Exception:
        print_message("WARNING", "Request button not found; proceeding to read existing port if present.")

    # Extract port (pf-ext takes priority)
    print_message("INFO", "Extracting ephemeral port value...")

    port_xpath = (eph_item_xpath + "//span[contains(@class,'pf-ext') or contains(@class,'pf-int')]")
    port_elem = wait.until(EC.visibility_of_element_located((By.XPATH, port_xpath)))
    new_port_str = port_elem.text.strip()

    if new_port_str.isdigit():
        new_port = int(new_port_str)
        print_message("INFO", f"Acquired ephemeral port: {new_port}")
    else:
        raise ValueError(f"Windscribe returned invalid port: '{new_port_str}'")

except Exception as e:
    print_message("ERROR", f"Critical error in port-forward automation: {e}")

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    screenshot_path = os.path.join(
        SCREENSHOT_DIR,
        f"failure_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    )
    driver.save_screenshot(screenshot_path)
    print_message("INFO", f"Screenshot saved at {screenshot_path}")

    if driver:
        driver.quit()
    exit(1)

finally:
    if driver:
        driver.quit()

# --- Post-Requesting Port Forwarding ---
if new_port:
    if ENABLE_QBITTORRENT_UPDATE:
        update_qbittorrent_port(new_port)

    if ENABLE_DOCKER_RESTART:
        restart_docker_containers(str(new_port))

print_message("INFO", "Script finished.")

import os
import pickle
import datetime
import subprocess
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from dotenv import load_dotenv, set_key
from qbittorrentapi import Client, LoginFailed

#############
# VARIABLES #
#############

# --- Configuration Flags ---
# Set these to True or False to enable/disable actions
ENABLE_QBITTORRENT_UPDATE = False
ENABLE_DOCKER_RESTART = True

# Docker Configuration
DOCKER_COMPOSE_FILE_PATH = "/path/to/compose.yml"
DOCKER_VPN_INSTANCE = "gluetun"
DOCKER_QBIT_INSTANCE = "qbittorrent"

# --- File Configuration ---
COOKIES_FILE = "/path/to/windscribe.cookies"
ENV_FILE = "/path/to/docker/compose/.env"
CREDENTIALS_ENV_FILE = "/path/to/scripts/credentials.env"

# --- Load credentials and environment variables ---
print("[INFO] Loading configuration from .env files...")
load_dotenv(CREDENTIALS_ENV_FILE)
load_dotenv(ENV_FILE)

# Current port - Docker
VPN_PORT_FORWARDED = os.getenv("VPN_PORT_FORWARDED")

# Windscribe Credentials
WS_USERNAME = os.getenv("WS_USERNAME")
WS_PASSWORD = os.getenv("WS_PASSWORD")

# qBittorrent Credentials
QBIT_HOST = os.getenv("QBIT_HOST")
QBIT_USERNAME = os.getenv("QBIT_USERNAME")
QBIT_PASSWORD = os.getenv("QBIT_PASSWORD")

# --- Selenium Setup ---
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")

#############
# FUNCTIONS #
#############

def save_cookies():
    with open(COOKIES_FILE, "wb") as f:
        pickle.dump(driver.get_cookies(), f)
    print("[INFO] Windscribe cookies saved.")

def load_cookies():
    if os.path.exists(COOKIES_FILE):
        driver.get("https://windscribe.com")
        with open(COOKIES_FILE, "rb") as f:
            cookies = pickle.load(f)
            for cookie in cookies:
                driver.add_cookie(cookie)
        print("[INFO] Windscribe cookies loaded.")
        return True
    return False

def is_logged_in():
    print("[INFO] Checking Windscribe login status...")
    driver.get("https://windscribe.com/myaccount")
    try:
        wait.until(EC.url_to_be("https://windscribe.com/myaccount"))
        print("[INFO] Windscribe login confirmed.")
        return True
    except TimeoutException:
        return False

def login_windscribe():
    print("[ACTION] Logging into Windscribe...")
    driver.get("https://windscribe.com/login")
    try:
        wait.until(EC.visibility_of_element_located((By.ID, "username"))).send_keys(WS_USERNAME)
        driver.find_element(By.ID, "pass").send_keys(WS_PASSWORD)
        driver.find_element(By.ID, "login_button").click()
        wait.until(EC.url_to_be("https://windscribe.com/myaccount"))
        print("[SUCCESS] Windscribe login successful.")
        save_cookies()
    except TimeoutException:
        print("[ERROR] Windscribe login failed. Check credentials.")
        driver.quit()
        exit(1)

def update_env_file(new_port):
    if set_key(ENV_FILE, "VPN_PORT_FORWARDED", new_port):
        print(f"[SUCCESS] Updated {ENV_FILE} with VPN_PORT_FORWARDED={new_port}")
    else:
        print(f"[ERROR] Could not update {ENV_FILE}. Please check file permissions.")

# --- qBittorrent Update Function ---
def update_qbittorrent_port(new_port):
    if not all([QBIT_HOST, QBIT_USERNAME, QBIT_PASSWORD]):
        print("[WARNING] qBittorrent credentials not found in environment file. Skipping update.")
        return

    print(f"[ACTION] Updating qBittorrent port to {new_port}...")
    try:
        qbt_client = Client(host=QBIT_HOST, username=QBIT_USERNAME, password=QBIT_PASSWORD)
        qbt_client.auth_log_in()

        current_port = qbt_client.app.preferences().get("listen_port")
        if str(current_port) == str(new_port):
            print(f"[INFO] qBittorrent port is already set to {new_port}. No action needed.")
        else:
            qbt_client.app.set_preferences(prefs={'listen_port': new_port})
            print(f"[SUCCESS] qBittorrent listening port updated to {new_port}.")

    except LoginFailed:
        print("[ERROR] qBittorrent login failed. Please check credentials in credentials.env.")
    except Exception as e:
        print(f"[ERROR] An error occurred while updating qBittorrent: {e}")

# --- Docker Restart Function ---
def restart_docker_containers(new_port=None):
    if not DOCKER_COMPOSE_FILE_PATH or not os.path.exists(DOCKER_COMPOSE_FILE_PATH):
        print(f"[WARNING] DOCKER_COMPOSE_FILE_PATH '{DOCKER_COMPOSE_FILE_PATH}' not found or not set. Skipping Docker restart.")
        return

    if new_port != VPN_PORT_FORWARDED:
        # Updating the .env file with the new port
        update_env_file(new_port)

        print("[ACTION] Restarting Docker containers via docker-compose...")
        command = [
            "docker-compose", "-f", DOCKER_COMPOSE_FILE_PATH,
            "up", "-d", "--force-recreate",
            DOCKER_VPN_INSTANCE, DOCKER_QBIT_INSTANCE
        ]

        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            print("[SUCCESS] Docker containers restarted successfully.")
            print("[DOCKER STDOUT]:", result.stdout)
        except FileNotFoundError:
            print("[ERROR] 'docker-compose' command not found. Is it installed and in your PATH?")
        except subprocess.CalledProcessError as e:
            print("[ERROR] Docker-compose command failed.")
            print("[DOCKER STDERR]:", e.stderr)
        except Exception as e:
            print(f"[ERROR] An unexpected error occurred during Docker restart: {e}")
    else:
        print(f"[INFO] The current port ({VPN_PORT_FORWARDED}) is the same as the new port ({new_port}). No restart needed.")


###############
# MAIN SCRIPT #
###############

print("[INFO] Launching headless browser...")
driver = webdriver.Chrome(options=chrome_options)
wait = WebDriverWait(driver, 20)

print(f"\n[INFO] Script started at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# --- Windscribe Port Forwarding ---
load_cookies()
if not is_logged_in():
    login_windscribe()

new_port = None
try:
    print("[ACTION] Navigating to Windscribe's port forwarding page...")
    port_forwarding_tab = wait.until(EC.element_to_be_clickable((By.ID, "menu-ports")))
    port_forwarding_tab.click()
    ephemeral_tab = wait.until(EC.element_to_be_clickable((By.ID, "pf-eph-btn")))
    ephemeral_tab.click()

    try:
        print("[INFO] Checking for existing port to delete...")
        delete_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Delete Port']")))
        delete_button.click()
        wait.until(EC.invisibility_of_element_located((By.XPATH, "//button[normalize-space()='Delete Port']")))
        print("[INFO] Existing port deleted.")
    except (NoSuchElementException, TimeoutException):
        print("[INFO] No existing port found to delete.")

    print("[ACTION] Requesting new matching port...")
    request_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Request Matching Port']")))
    request_button.click()

    port_element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "#epf-port-info > span")))
    new_port_str = port_element.text
    
    if new_port_str and new_port_str.isdigit():
        new_port = int(new_port_str)
        print(f"[SUCCESS] Acquired new port from Windscribe: {new_port}")
    else:
        raise ValueError(f"Could not extract a valid port. Found: '{new_port_str}'")

except (TimeoutException, NoSuchElementException, ValueError) as e:
    print(f"[ERROR] A critical step failed while getting port from Windscribe: {e}")
    driver.quit()
    exit(1)
finally:
    driver.quit()

# --- Post-Windscribe Actions ---
if new_port:
    # Update qBittorrent if enabled
    if ENABLE_QBITTORRENT_UPDATE:
        update_qbittorrent_port(new_port)

    # Restart Docker containers if enabled
    if ENABLE_DOCKER_RESTART:
        restart_docker_containers(str(new_port))

print("[INFO] Script finished.")

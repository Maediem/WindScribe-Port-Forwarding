# Import standard and third-party libraries
import os
import pickle
import datetime
import time
import subprocess

# Selenium-related imports
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Environment variable handling
from dotenv import load_dotenv, set_key

# qBittorrent API
from qbittorrentapi import Client, LoginFailed



#############
# VARIABLES #
#############

# --- Configuration Flags ---
# Toggle these as needed for debugging or disabling certain features
ENABLE_QBITTORRENT_UPDATE = False     # Enable or disable qBittorrent port update
ENABLE_DOCKER_RESTART = True          # Enable or disable Docker container restart

# --- Docker Configuration ---
DOCKER_COMPOSE_FILE_PATH = "/path/to/compose.yml"     # Path to your docker-compose YAML file
DOCKER_VPN_INSTANCE = "gluetun"                       # Name of the VPN container
DOCKER_QBIT_INSTANCE = "qbittorrent"                  # Name of the qBittorrent container

# --- File Configuration ---
COOKIES_FILE = "/path/to/windscribe.cookies"          # File to store cookies for Windscribe login
ENV_FILE = "/path/to/docker/compose/.env"             # Docker .env file to store the forwarded port
CREDENTIALS_ENV_FILE = "/path/to/scripts/credentials.env"  # File with Windscribe and qBittorrent credentials

# --- Load environment variables ---
print("[INFO] Loading configuration from .env files...")
load_dotenv(CREDENTIALS_ENV_FILE)
load_dotenv(ENV_FILE)

# --- Extract credentials and settings from environment ---
VPN_PORT_FORWARDED = os.getenv("VPN_PORT_FORWARDED")

WS_USERNAME = os.getenv("WS_USERNAME")
WS_PASSWORD = os.getenv("WS_PASSWORD")

QBIT_HOST = os.getenv("QBIT_HOST")
QBIT_USERNAME = os.getenv("QBIT_USERNAME")
QBIT_PASSWORD = os.getenv("QBIT_PASSWORD")

# --- Selenium WebDriver Options ---
# Configure Chrome to run headlessly and minimize resource usage
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)



#############
# FUNCTIONS #
#############

# Save the current session's cookies to a file for future login reuse.
def save_cookies():
    with open(COOKIES_FILE, "wb") as f:
        pickle.dump(driver.get_cookies(), f)
    print("[INFO] Windscribe cookies saved.")


# Load previously saved cookies into the browser session if available.
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

# Check if the Windscribe user is currently logged in.
def is_logged_in():
    print("[INFO] Checking Windscribe login status...")
    driver.get("https://windscribe.com/myaccount")
    try:
        wait.until(EC.url_to_be("https://windscribe.com/myaccount"))
        print("[INFO] Windscribe login confirmed.")
        return True
    except TimeoutException:
        return False

# Perform login to Windscribe using credentials from environment variables.
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

# Update the Docker .env file with the new forwarded port.
def update_env_file(new_port):
    if set_key(ENV_FILE, "VPN_PORT_FORWARDED", new_port):
        print(f"[SUCCESS] Updated {ENV_FILE} with VPN_PORT_FORWARDED={new_port}")
    else:
        print(f"[ERROR] Could not update {ENV_FILE}. Please check file permissions.")
    
    time.sleep(1) # Add 1 sec. sleep to ensure the file is saved and can be used by the docker restart

# Update qBittorrent's listening port using the qBittorrent Web API.
def update_qbittorrent_port(new_port):
    if not all([QBIT_HOST, QBIT_USERNAME, QBIT_PASSWORD]):
        print("[WARNING] qBittorrent credentials not found. Skipping update.")
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
        print("[ERROR] qBittorrent login failed. Check credentials.")
    except Exception as e:
        print(f"[ERROR] An error occurred while updating qBittorrent: {e}")

# Restart VPN and qBittorrent Docker containers after updating .env.
def restart_docker_containers(new_port=None):
    if not DOCKER_COMPOSE_FILE_PATH or not os.path.exists(DOCKER_COMPOSE_FILE_PATH):
        print(f"[WARNING] Docker compose file not found: {DOCKER_COMPOSE_FILE_PATH}")
        return

    # Proceed only if the port has changed
    if new_port != VPN_PORT_FORWARDED:
        update_env_file(new_port)

        print("[ACTION] Restarting Docker containers...")
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
            print("[ERROR] 'docker-compose' not found. Install it or check your PATH.")
        except subprocess.CalledProcessError as e:
            print("[ERROR] Docker-compose failed.")
            print("[DOCKER STDERR]:", e.stderr)
        except Exception as e:
            print(f"[ERROR] Unexpected error during Docker restart: {e}")
    else:
        print(f"[INFO] Port unchanged ({VPN_PORT_FORWARDED}). Skipping restart.")



###############
# MAIN SCRIPT #
###############

print("[INFO] Launching headless browser...")
driver = webdriver.Chrome(options=chrome_options)
wait = WebDriverWait(driver, 20)

print(f"\n[INFO] Script started at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# --- Attempt Windscribe Login ---
load_cookies()
if not is_logged_in():
    login_windscribe()

new_port = None
try:
    # Navigate to the Port Forwarding section in Windscribe
    print("[ACTION] Navigating to Windscribe's port forwarding page...")
    port_forwarding_tab = wait.until(EC.element_to_be_clickable((By.ID, "menu-ports")))
    port_forwarding_tab.click()

    # Switch to ephemeral port section
    ephemeral_tab = wait.until(EC.element_to_be_clickable((By.ID, "pf-eph-btn")))
    ephemeral_tab.click()

    # Check if there's an existing port to delete
    try:
        print("[INFO] Checking for existing port to delete...")
        delete_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Delete Port']")))
        delete_button.click()
        wait.until(EC.invisibility_of_element_located((By.XPATH, "//button[normalize-space()='Delete Port']")))
        print("[INFO] Existing port deleted.")
    except (NoSuchElementException, TimeoutException):
        print("[INFO] No existing port found to delete.")

    # Request a new matching port
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
    # Ensure browser is closed properly
    driver.quit()

# --- Post-login Actions ---
if new_port:
    if ENABLE_QBITTORRENT_UPDATE:
        update_qbittorrent_port(new_port)

    if ENABLE_DOCKER_RESTART:
        restart_docker_containers(str(new_port))

print("[INFO] Script finished.")

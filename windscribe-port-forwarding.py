#########################################################################################################################
# WARNING: Running this script repeatedly or in rapid succession may result in your account being temporarily disabled. #
#########################################################################################################################

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
from dotenv import load_dotenv, set_key, get_key

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
# Change the path to the proper directory
ROOT_DIR = "/data/docker"
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
CREDENTIALS_ENV_FILE = os.path.join(ROOT_DIR, "scripts", "credentials.env") # File with Windscribe and qBittorrent credentials
ENV_FILE = os.path.join(ROOT_DIR, ".env")                                   # Docker .env file to store the forwarded port


# --- Load environment variables ---
load_dotenv(CREDENTIALS_ENV_FILE)
load_dotenv(ENV_FILE)

# --- Extract credentials and settings from environment ---
ENV_KEY_PORT_FORWARDED  = "VPN_PORT_FORWARDED"          # # Variable used because it is used in the script for updating .env file.
VPN_PORT_FORWARDED = os.getenv(ENV_KEY_PORT_FORWARDED)

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

# Print & log message if enabled
def print_message(log_level: str, msg: str, print_only: bool = False):
    # Get current timestamp
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Format log entry
    log_entry = f"[{timestamp}] [{log_level}] {msg}"
    
    # Print to console
    print(log_entry)
    
    # Write to log file if enabled in variables
    if LOG_TO_FILE and not print_only:
        with open(LOG_FILE, "a") as f:
            f.write(log_entry + "\n")

# Save the current session's cookies to a file for future login reuse.
def save_cookies():
    with open(COOKIES_FILE, "wb") as f:
        pickle.dump(driver.get_cookies(), f)
        
    print_message("INFO", "Windscribe cookies saved.")


# Load previously saved cookies into the browser session if available.
def load_cookies():
    if os.path.exists(COOKIES_FILE):
        driver.get("https://windscribe.com")
        
        with open(COOKIES_FILE, "rb") as f:
            cookies = pickle.load(f)
            for cookie in cookies:
                driver.add_cookie(cookie)
                
        print_message("INFO", "Windscribe cookies loaded.")
        return True
    return False

# Check if the Windscribe user is currently logged in.
def is_logged_in():
    print_message("INFO", "Checking Windscribe login status...")
    driver.get("https://windscribe.com/myaccount")
    
    try:
        wait.until(EC.url_to_be("https://windscribe.com/myaccount"))
        print_message("INFO", "Windscribe login confirmed.")
        return True
    except TimeoutException:
        return False

# Perform login to Windscribe using credentials from environment variables.
def login_windscribe():
    print_message("INFO", "Logging into Windscribe...")
    driver.get("https://windscribe.com/login")
    
    try:
        wait.until(EC.visibility_of_element_located((By.ID, "username"))).send_keys(WS_USERNAME)
        driver.find_element(By.ID, "pass").send_keys(WS_PASSWORD)
        driver.find_element(By.ID, "login_button").click()
        wait.until(EC.url_to_be("https://windscribe.com/myaccount"))
        
        print_message("INFO", "Windscribe login successful.")
        save_cookies()
    except TimeoutException:
        print_message("ERROR", "Windscribe login failed. Check credentials.")
        driver.quit()
        exit(1)

# Update the Docker .env file with the new forwarded port.
def update_env_file(new_port, timeout=5):
    if set_key(ENV_FILE, ENV_KEY_PORT_FORWARDED, new_port):
        # Poll until the environment reflects the change
        start = time.time()
        
        while time.time() - start < timeout:
            load_dotenv(ENV_FILE, override=True)
            tmp = os.getenv(ENV_KEY_PORT_FORWARDED)
            
            if tmp == new_port:
                print_message("INFO", f"Updated '{ENV_FILE}' with '{ENV_KEY_PORT_FORWARDED}={new_port}'")
                break
            
            time.sleep(1)
        else:
            print_message("WARN", f"{ENV_FILE} was not updated as expected within {timeout} seconds.")
    else:
        print_message("ERROR", f"Could not update {ENV_FILE}. Please check file permissions.")

# Update qBittorrent's listening port using the qBittorrent Web API.
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

# Restart VPN and qBittorrent Docker containers after updating .env.
def restart_docker_containers(new_port=None):
    if not DOCKER_COMPOSE_FILE or not os.path.exists(DOCKER_COMPOSE_FILE):
        print_message("WARNING", f"Docker compose file not found: {DOCKER_COMPOSE_FILE}")
        return

    # Proceed only if the port has changed
    if new_port != VPN_PORT_FORWARDED:
        update_env_file(new_port)

        print_message("INFO", "Restarting Docker containers...")

        try:
            result = subprocess.run(DOCKER_RESTART_CMD, capture_output=True, text=True, check=True)
            print_message("INFO", "Docker containers restarted successfully.")

            # True is to print only. If required, it can be added in log file by removing "True".
            if result.stdout:
                print_message("DEBUG", f"[DOCKER STDOUT]: {result.stdout}", print_only=True)
        except FileNotFoundError:
            print_message("ERROR", "'docker-compose' not found. Please install it or check your path.")
        except subprocess.CalledProcessError as e:
            print_message("ERROR", "Docker-compose failed.")

            # True is to print only. If required it can be added in log file by removing "True".
            if e.stderr:
                print_message("DEBUG" f"[DOCKER STDERR]: {e.stderr}")
        except Exception as e:
            print_message("ERROR", f"Unexpected error during Docker restart: {e}")
    else:
        print_message("INFO", f"Port unchanged ({VPN_PORT_FORWARDED}). Skipping restart.")



###############
# MAIN SCRIPT #
###############
print_message("INFO", "Script started.")

print_message("INFO", "Launching headless browser...")
driver = webdriver.Chrome(options=chrome_options)
wait = WebDriverWait(driver, 20)

# --- Attempt Windscribe Login ---
load_cookies()
if not is_logged_in():
    login_windscribe()

new_port = None
try:
    # Navigate to the Port Forwarding section in Windscribe
    print_message("INFO", "Navigating to Windscribe's port forwarding page...")
    port_forwarding_tab = wait.until(EC.element_to_be_clickable((By.ID, "menu-ports")))
    port_forwarding_tab.click()

    # Switch to ephemeral port section
    ephemeral_tab = wait.until(EC.element_to_be_clickable((By.ID, "pf-eph-btn")))
    ephemeral_tab.click()

    # Check if there's an existing port to delete
    try:
        print_message("INFO", "Checking for existing port to delete...")
        
        delete_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Delete Port']")))
        delete_button.click()
        wait.until(EC.invisibility_of_element_located((By.XPATH, "//button[normalize-space()='Delete Port']")))
        
        print_message("INFO", "Existing port deleted.")
    except (NoSuchElementException, TimeoutException):
        print_message("INFO", "No existing port found to delete.")

    # Request a new matching port
    print_message("INFO", "Requesting new matching port...")
    request_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Request Matching Port']")))
    request_button.click()

    port_element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "#epf-port-info > span")))
    new_port_str = port_element.text
    
    if new_port_str and new_port_str.isdigit():
        new_port = int(new_port_str)
        print_message("INFO", f"Acquired new port from Windscribe: {new_port}")
    else:
        raise ValueError(f"Could not extract a valid port. Found: '{new_port_str}'")

except (TimeoutException, NoSuchElementException, ValueError) as e:
    print_message("ERROR", f"A critical step failed while getting port from Windscribe: {e}")
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

print_message("INFO", "Script finished.")

# Windscribe Port Forwarding Automation

This script automates the process of renewing an ephemeral port on Windscribe and applying the new port to services like qBittorrent and/or Docker containers. This script was made for Linux by using .env files.

> **⚠️ Important note on your connection**
> 
> For the highest chance of success, run this script from a machine with a standard internet connection (e.g., your home network), **not** from behind another VPN. VPN IP addresses are often flagged by websites, which triggers aggressive CAPTCHAs and security challenges that can cause the script to fail.

## Features

-   **Automated Login**: Logs into Windscribe using credentials (via .env file), saving session cookies to speed up subsequent runs.
-   **Port Renewal**: Navigates the Windscribe account page to delete the existing ephemeral port and request a new one.
-   **qBittorrent Integration**: (Optional) Updates the listening port in a running qBittorrent instance via its Web API.
-   **Docker Integration**: (Optional) Automatically updates a `.env` file with the new port number. Restarts specified docker-compose (e.g. gluetun & qbittorrent) services to apply the new port forwarding settings.

## Requirements

This section details everything you need to run the script successfully.

### System & Software

- Python 3.8+: The script uses modern Python syntax.
- Google Chrome / Chromium: The script uses Selenium to drive a Chrome-based browser.
- Docker & Docker Compose: Required only if ENABLE_DOCKER_RESTART is set to True. The docker-compose command must be accessible in your system's PATH.
- (Optional but Recommended) FlareSolverr: Required only if using the flaresolverr login method. You must have a running instance of FlareSolverr (can run on a docker). The script is pre-configured to connect to it at http://localhost:8191.

    Note on chromedriver: Modern versions of Selenium (which this script uses) include Selenium Manager, which automatically downloads and manages the correct chromedriver for you. You do not need to manually install chromedriver or add it to your PATH.

### Python Packages

All required Python packages can be installed with a single command:

```bash
pip install requests selenium selenium-stealth python-dotenv qbittorrent-api
```
  

## Configuration & File Permissions

The script requires a specific file structure and permissions to function correctly. All paths are relative to the ROOT_DIR variable you set in the script.

You need to create environment file(s) to store your credentials and configuration. Since the docker should not use the same credentials, one envronment file is use for this script and one for the dockers.

**Please ensure access based on the principle of least privilege.**


### Credentials File

Create a file named credentials.env in the location you specify in the script (/path/to/scripts/credentials.env by default). This file stores your sensitive login information for the VPN. If you are using qBittorrent directly on your machine, you can add those info as well.

Template for credentials.env:

```bash
# Windscribe Credentials
WS_USERNAME="your_windscribe_username"
WS_PASSWORD="your_windscribe_password"

# qBittorrent Web UI Credentials (only needed if ENABLE_QBITTORRENT_UPDATE is True)
QBIT_HOST="http://localhost:8080"
QBIT_USERNAME="your_qbit_username"
QBIT_PASSWORD="your_qbit_password"
```

### Docker Environment File

If enabled, this script reads and writes to the .env file used by your docker-compose setup. Make sure the path is correct in the script.

Example .env file:

```bash
# This variable will be managed by the script
VPN_PORT_FORWARDED='12345'
```

### You must edit the main Python script to match your setup.
Open the script and modify the variables below the section:
```python
#############
# VARIABLES #
#############
```

A. Enable or Disable Features

These flags control the script's major actions after fetching the new port.

```python
# Set to True to enable updating qBittorrent, False to disable.
ENABLE_QBITTORRENT_UPDATE = False

# Set to True to enable restarting Docker containers, False to disable.
ENABLE_DOCKER_RESTART = True
```
    
B. Docker Settings

If ENABLE_DOCKER_RESTART is True, you must specify your Docker Compose file path and the names of the services you want to restart.
```python
      
# The full, absolute path to your docker-compose file.
DOCKER_COMPOSE_FILE_PATH = "/path/to/your/docker-compose.yml"

# The name of your VPN container service in the compose file.
DOCKER_VPN_INSTANCE = "gluetun"

# The name of your qBittorrent (or other) service that depends on the VPN.
DOCKER_QBIT_INSTANCE = "qbittorrent"
```

C. File Paths

Update these paths to reflect where you are storing your configuration and cookie files. Use absolute paths to ensure the script can be run from anywhere (e.g., via a cron job).
```python      
# Path to store the Windscribe session cookie.
COOKIES_FILE = "/path/to/project/windscribe.cookies"

# Path to your Docker .env file that contains VPN_PORT_FORWARDED.
ENV_FILE = "/path/to/docker/.env"

# Path to your credentials file.
CREDENTIALS_ENV_FILE = "/path/to/project/credentials.env"
```

D. Login method and Flaresolverr URL
Update these variables to reflect the login method you want to use.

```python
# --- Login Configuration ---
# Choose "flaresolverr" (recommended) or "selenium".
LOGIN_METHOD = "flaresolverr"

# --- FlareSolverr Configuration ---
# URL of your running FlareSolverr instance.
FLARESOLVERR_URL = "http://localhost:8191/v1"
```

## Usage

Once everything is configured, you can run the script from your terminal:
```bash      
python3 /path/to/your/script.py
```


The script will print its progress to the console. The first run will be slower as it needs to perform a full login. Subsequent runs will use the saved windscribe.cookies file for faster authentication.

You can also set this up as a scheduled task (e.g., a cron job) to automatically refresh your port periodically.

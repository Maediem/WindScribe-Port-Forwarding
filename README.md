# Windscribe Port Forwarding Automation

This script automates the process of renewing an ephemeral port on Windscribe and applying the new port to services like qBittorrent and/or Docker containers. This script was made for Linux by using .env files.

## Features

-   **Automated Login**: Logs into Windscribe using credentials (via .env file), saving session cookies to speed up subsequent runs.
-   **Port Renewal**: Navigates the Windscribe account page to delete the existing ephemeral port and request a new one.
-   **qBittorrent Integration**: (Optional) Updates the listening port in a running qBittorrent instance via its Web API.
-   **Docker Integration**: (Optional) Automatically updates a `.env` file with the new port number. Restarts specified docker-compose (e.g. gluetun & qbittorrent) services to apply the new port forwarding settings.

## Requirements

-   Python 3.8+
-   `pip` (Python package installer)
-   `docker-compose` installed and accessible in the system's PATH.
-   A running instance of Google Chrome/Chromium.
-   `chromedriver` matching your Chrome version, installed and accessible in your system's PATH.
-   - Reading access to the .env variables

## Setup and Configuration

Follow these steps carefully to set up the script for your environment.

### 1. Install Python Dependencies

Install the required Python libraries using `pip`:

```bash
pip install selenium python-dotenv qbittorrent-api
```


## Configure Environment Files

You need to create environment file(s) to store your credentials and configuration. Since the docker should not use the same credentials, one envronment file is use for this script and one for the dockers.

**Please ensure access based on the principle of least privilege.**


## Credentials File

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

B. Docker Environment File

If enabled, this script reads and writes to the .env file used by your docker-compose setup. Make sure the path is correct in the script.

Example .env file:

```bash
# This variable will be managed by the script
VPN_PORT_FORWARDED='12345'
```

## You must edit the main Python script to match your setup.
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

## Usage

Once everything is configured, you can run the script from your terminal:
```bash      
python3 /path/to/your/script.py
```


The script will print its progress to the console. The first run will be slower as it needs to perform a full login. Subsequent runs will use the saved windscribe.cookies file for faster authentication.

You can also set this up as a scheduled task (e.g., a cron job) to automatically refresh your port periodically.

## Troubleshooting

> **selenium.common.exceptions.SessionNotCreatedException**  
> This usually means your chromedriver version does not match your Google Chrome  
> version, or there are permission issues. Ensure both are up-to-date.  
>
> **FileNotFoundError: [Errno 2] No such file or directory: 'docker-compose'**  
> The docker-compose executable is not in your system's PATH.  
>
> **Permission Denied**  
> The script may not have permission to read/write the specified file paths  
> (e.g., `COOKIES_FILE`, `ENV_FILE`). Ensure the user running the script has  
> the correct permissions.


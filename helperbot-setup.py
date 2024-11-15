import os
import sys
import shutil
import subprocess
import logging
from utils.config_utils import initialize_file_if_missing, load_config, save_config, setup_logging

config = load_config()
setup_logging(config)

def sanitize_path(user_path):
    """Clean the user-provided path by normalizing slashes, removing quotes, and ensuring a single trailing slash if needed."""
    user_path = user_path.strip("'\"")  # Remove surrounding quotes if present
    normalized_path = os.path.normpath(user_path)  # Normalize slashes
    if os.path.isdir(normalized_path) and not normalized_path.endswith(os.path.sep):
        normalized_path += os.path.sep
    return normalized_path

# YAML content template for docker-compose.override.yml
OVERRIDE_FILE_CONTENT = """
services:
  rsassistant:
    build:
      context: "{rsassistant_path}"
      dockerfile: Dockerfile
    container_name: rsassistant_container
    volumes:
      - "{rsassistant_path}/logs:/app/logs"
      - "{rsassistant_path}/logs/orders-log.csv:/app/logs/orders-log.csv"
      - "{rsassistant_path}/logs/holdings_log.csv:/app/logs/holdings_log.csv"
      - "{rsassistant_path}/excel/ReverseSplitLog.xlsx:/app/excel/ReverseSplitLog"
      - "{rsassistant_path}/excel/archive:/app/excel/archive"
    env_file:
      - "{rsassistant_path}/.env"
    networks:
      - app-network

networks:
  app-network:
    external: true
"""

def generate_override_file(rsassistant_path, auto_rsa_path):
    """Generate the docker-compose.override.yml file in the auto-rsa directory."""
    override_content = OVERRIDE_FILE_CONTENT.format(rsassistant_path=rsassistant_path.replace("\\", "/"))
    override_file_path = os.path.join(auto_rsa_path, "docker-compose.override.yml")
    with open(override_file_path, "w") as f:
        f.write(override_content)
    logging.info(f'Docker-compose.override.yml has been created at "{override_file_path}"')

def validate_auto_rsa_path(path):
    """Check if the given path contains docker-compose.yml, entrypoint.sh, and autoRSA.py to confirm it as the correct auto-rsa directory."""
    required_files = ["docker-compose.yml", "autoRSA.py", "entrypoint.sh"]
    missing_files = [file for file in required_files if not os.path.isfile(os.path.join(path, file))]
    
    if missing_files:
        logging.warning(f"The following required files are missing in '{path}': {', '.join(missing_files)}")
        return False
    return True

def add_to_git_exclude(file_path):
    """Add a file or directory to .git/info/exclude to prevent it from being tracked in version control."""
    exclude_file = os.path.join(".git", "info", "exclude")
    if os.path.exists(exclude_file):
        with open(exclude_file, "a") as f:
            f.write(f"\n{file_path}\n")
        logging.info(f'Added "{file_path}" to .git/info/exclude.')

def run_docker_compose(auto_rsa_path):
    """Navigate to the auto-rsa directory and run docker-compose up -d."""
    try:
        subprocess.run(["docker-compose", "up", "-d"], cwd=auto_rsa_path, check=True)
        logging.info("Docker containers started successfully.")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to start Docker containers: {e}")

def main():

    # Get paths from configuration or prompt user if not found
    auto_rsa_path = config.get("auto_rsa_path")
    rsassistant_path = config.get("rsassistant_path", os.path.abspath("."))

    # Initialize necessary files if they are missing
    logging.info("Checking for files and initializing...")
    initialize_file_if_missing(
        log_path_example=os.path.join(rsassistant_path, "excel", "example-ReverseSplitLog.xlsx"),
        log_path_working=os.path.join(rsassistant_path, "excel", "ReverseSplitLog.xlsx"),
        filename='ReverseSplitLog'
    )
    initialize_file_if_missing(
        log_path_example=os.path.join(rsassistant_path, "config", "example-settings.yaml"),
        log_path_working=os.path.join(rsassistant_path, "config", "settings.yaml"),
        filename='settings.yaml'
    )
    initialize_file_if_missing(
        log_path_example=os.path.join(rsassistant_path, "config", "account_mapping-example.json"),
        log_path_working=os.path.join(rsassistant_path, "config", "account_mapping.json"),
        filename='account_mapping.json'
    )
    
    # Ensure paths are valid or prompt the user
    if not auto_rsa_path or not os.path.isdir(auto_rsa_path) or not validate_auto_rsa_path(auto_rsa_path):
        logging.warning("Could not find a valid auto-rsa directory.")
        logging.info(f"Expected path of auto-rsa directory: '{rsassistant_path}'")
        user_path = input("Please enter the full path to the auto-rsa directory wrapped in single quotes: ").strip()

        # Sanitize the user input path
        user_path = sanitize_path(user_path)

        # Validate user-provided path
        logging.info(f"Checking path: '{user_path}'")
        if os.path.isdir(user_path) and validate_auto_rsa_path(user_path):
            auto_rsa_path = user_path  # Update to the user-provided path
            # Save the updated path in the configuration
            config["auto_rsa_path"] = auto_rsa_path
            save_config(config)
        else:
            logging.error("The provided path is not valid or does not contain required files. Exiting.")
            sys.exit(1)  # Exit the script if validation fails

    # Generate the docker-compose.override.yml file
    generate_override_file(rsassistant_path, auto_rsa_path)

    # Prompt user to optionally start Docker containers
    run_docker = input("\nWould you like to start both Docker containers now? (y/n): ").strip().lower()
    if run_docker == 'y':
        run_docker_compose(auto_rsa_path)
    else:
        # Final message for the user to proceed with regular docker-compose instructions
        logging.info("All setup checks are complete. To start the auto-rsa bot manually, follow the standard instructions:")
        logging.info("1. Navigate to your cloned auto-rsa directory.")
        logging.info("2. Run `docker-compose up -d` to start both of the Discord bots.")

if __name__ == "__main__":
    main()

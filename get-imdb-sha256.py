import os
import re
import time
from datetime import datetime
import logging
import logging.handlers
from urllib.parse import unquote
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

def setup_logger2(run_id):
    # Create a logger named 'my_logger'
    logger = logging.getLogger('my_logger')
    logger.setLevel(logging.INFO)  # Set the logging level to INFO

    # Define a formatter for the log messages
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # Create a timed rotating file handler for individual log files per run
    log_filename = f'get-imdb-sha256-{run_id}.log'
    file_handler = logging.handlers.TimedRotatingFileHandler(log_filename, when='D', interval=1, backupCount=10)
    file_handler.setLevel(logging.INFO)  # Set the logging level for the file handler
    file_handler.setFormatter(formatter)  # Apply the formatter to the file handler

    # Create a stream handler to output log messages to the console (stdout)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)  # Set the logging level for the console handler
    console_handler.setFormatter(formatter)  # Apply the formatter to the console handler

    # Add the file handler and console handler to the logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def setup_logger(run_id):
    # Define the log file name with the run_id
    log_filename = f'get-imdb-sha256-{run_id}.log'

    # Configure logging to both a file and the console
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename),  # File handler for writing to log file
            logging.StreamHandler()  # Console handler for displaying formatted log messages on the console
        ]
    )

    # Get the root logger
    logger = logging.getLogger()

    return logger

def generate_run_id():
    # Generate a timestamp-based unique identifier with millisecond precision
    return datetime.now().strftime('%Y%m%d%H%M%S%f')[:-3]  # Truncate microseconds to milliseconds


def cleanup_old_logs(max_logs_to_keep):
    log_pattern = r'get-imdb-sha256-\d{17}\.log'  # Timestamp format with milliseconds (YYYYMMDDHHMMSSfff)
    log_files = sorted([f for f in os.listdir('.') if re.match(log_pattern, f)])

    if len(log_files) > max_logs_to_keep:
        files_to_delete = log_files[:len(log_files) - max_logs_to_keep]
        for file in files_to_delete:
            try:
                logging.info(f"Removing log file: {file}")
                os.remove(file)
            except Exception as e:
                logging.error(f"Error while deleting log file {file}: {e}")


# Set up the logger for this run
run_id = generate_run_id()
logger = setup_logger(run_id)
logger.info("===================START===================")

# Install ChromeDriver
chrome_driver_path = ChromeDriverManager().install()
logger.info(f"chrome_driver_path: {chrome_driver_path}")

service = Service(chrome_driver_path)

options = Options()
options.add_argument("--headless")
options.add_argument("--window-size=1920,1600")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36")

# Initialize WebDriver with Service
driver = webdriver.Chrome(service=service, options=options)


def get_sha256_from_network_tab(url, keyword):
    try:
        # Log Chrome version
        browser_version = driver.capabilities['browserVersion']
        logger.info(f"Chrome Browser Version: {browser_version}")

        # Log ChromeDriver version
        chrome_driver_version = driver.capabilities['chrome']['chromedriverVersion']
        logger.info(f"ChromeDriver Version: {chrome_driver_version}")

        logger.info(f"Current URL: {url}")
        logger.info(f"Keyword: {keyword}")
        driver.get(url)
        time.sleep(5)
        driver.save_screenshot('./01_current_url.png')

        # Click on "Expand all" to reveal all advanced filter boxes
        expand_all_button = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, '//span[@class="ipc-btn__text" and text()="Expand all"]'))
        )
        expand_all_button.click()
        driver.save_screenshot('./02_after_expand_all_click.png')

        # Locate and interact with the search box
        search_box = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, '//input[@aria-label="Title name"]'))
        )

        # Send the keyword to the search box
        search_box.send_keys(keyword)
        driver.save_screenshot('./03_after_sending_keyword.png')

        # Click on the "Movie" button
        movie_button = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, '//button[@data-testid="test-chip-id-movie"]'))
        )
        movie_button.click()
        driver.save_screenshot('./04_after_movie_button_click.png')

        # Simulate pressing the Enter key
        search_box.send_keys(Keys.ENTER)
        time.sleep(5)

        # Wait for the search results to load
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'h3.ipc-title__text'))
        )
        logging.info(f"Current URL after first search results found: {driver.current_url}")
        driver.save_screenshot('./05_after_search_results_found.png')

        # Retrieve performance data
        network_requests = driver.execute_script("""
                var performanceEntries = [];
                var entries = window.performance.getEntries();
                if (entries && entries.length > 0) {
                    for (var i = 0; i < entries.length; i++) {
                        var entry = entries[i];
                        var url = entry.name || entry.initiatorType;
                        if (url) {
                            performanceEntries.push(url);
                        }
                    }
                }
                return performanceEntries;
            """)

        # Filter and process performance entries
        if network_requests:
            target_strings = ["persistedQuery", "sha256Hash", "caching.graphql.imdb.com", keyword]
            found_urls = set()

            for url in network_requests:
                if all(target_string in url for target_string in target_strings):
                    found_urls.add(url)

            if found_urls:
                for url in found_urls:
                    logger.info(f"Network request URL containing SHA-256 hash (ENCODED): {url}")
                    decoded_url = unquote(url)
                    logger.info(f"Network request URL containing SHA-256 hash (DECODED): {decoded_url}")
                    sha256_hash = re.search(r'sha256Hash":"([^"]+)', decoded_url).group(1)
                    logger.info(f"Extracted SHA-256 hash: {sha256_hash}")
                    return sha256_hash
            else:
                logger.info(f"No URLs matching the criteria were found.")
        else:
            logger.info(f"No performance entries found.")

    except Exception as e:
        logger.error(f"An error occurred: {e}")

    finally:
        # Quit the WebDriver session
        driver.quit()


if __name__ == "__main__":
    url = "https://www.imdb.com/search/title/"
    keyword = "Shrek"

    # Cleanup old log files to keep only the last 10
    cleanup_old_logs(max_logs_to_keep=10)

    # Read the existing content from the "HASH" file if it exists
    try:
        with open("HASH", "r") as f:
            stored_hash = f.read().strip()
    except FileNotFoundError:
        stored_hash = None

    # Simulate getting the SHA-256 hash value
    sha256_hash = get_sha256_from_network_tab(url, keyword)

    if sha256_hash:
        logger.info(f"SHA-256 hash from network tab: {sha256_hash}")

        # Compare the stored hash with the retrieved sha256_hash (if stored_hash exists)
        if stored_hash is not None:
            if stored_hash == sha256_hash:
                logger.info("Hash in file and hash retrieved match.")
            else:
                logger.info("Hash in file and hash retrieved DO NOT match.")
        else:
            logger.info("No existing hash found in the HASH file.")

        # Write the retrieved SHA-256 hash to the "HASH" file
        with open("HASH", "w") as f:
            f.write(sha256_hash)

        # Log the final write action
        logger.info("SHA-256 hash written to HASH file.")
    else:
        logger.info("Failed to retrieve SHA-256 hash.")

logger.info("====================END====================")

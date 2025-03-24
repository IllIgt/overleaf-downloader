import json
import os
import time
import logging
import traceback
from pathlib import Path

import selenium
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    StaleElementReferenceException,
    WebDriverException
)

CONFIG_FILE = 'config.json'
PROGRESS_FILE = '/app/shared/progress.json'
OUTPUT_DIR = 'downloads'
LOG_DIR = 'logs'

MAX_BACKOFF_SECONDS = 86400  # 24 hours

Path(OUTPUT_DIR).mkdir(exist_ok=True)
Path(LOG_DIR).mkdir(exist_ok=True)


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    cookie = os.getenv("OVERLEAF_COOKIE") or config.get("cookie")
    if not cookie:
        raise ValueError("Cookie не указан ни в .env, ни в config.json")

    projects = config.get("projects", [])
    if not projects:
        raise ValueError("Список проектов пуст или отсутствует в config.json")

    return cookie, projects


def ensure_progress_file():
    if not os.path.exists(PROGRESS_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
        initial_progress = {proj["name"]: 0 for proj in config.get("projects", [])}
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(initial_progress, f, indent=2)
        logging.info("Создан новый файл прогресса progress.json")


def load_progress():
    if Path(PROGRESS_FILE).exists():
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_progress(progress):
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)


def setup_logger(project_name):
    logger = logging.getLogger(project_name)
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(f'{LOG_DIR}/{project_name}.log')
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    return logger


def setup_driver(cookie):
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=chrome_options)
    driver.get("https://www.overleaf.com")
    driver.add_cookie({
        'name': 'overleaf_session2',
        'value': cookie,
        'domain': '.overleaf.com',
        'path': '/',
        'secure': True
    })
    return driver


def wait_and_click(driver, by, value, timeout=10):
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))
        el.click()
        return el
    except Exception as e:
        raise e


def extract_version_links(driver):
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-testid="history-version"]'))
        )
        versions = driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="history-version"]')
        return versions
    except Exception as e:
        raise e


def safe_click(driver, element, max_retries=5, scroll=True):
    for attempt in range(max_retries):
        try:
            if scroll:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(0.4)
            element.click()
            return
        except selenium.common.exceptions.ElementClickInterceptedException:
            time.sleep(0.5)
        except selenium.common.exceptions.StaleElementReferenceException:
            time.sleep(0.5)
        except Exception as e:
            logging.warning(f"❌ Ошибка при попытке клика: {e}")
            time.sleep(0.5)
    try:
        driver.execute_script("arguments[0].click();", element)
    except Exception as e:
        raise Exception("❌ Не удалось кликнуть по элементу ни обычным, ни js способом") from e


def download_version(driver, version_el, project_name, version_num):
    try:
        dropdown_button = version_el.find_element(By.CSS_SELECTOR, '.history-version-dropdown-menu-btn')
        safe_click(driver, dropdown_button)

        download_link_el = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'a[download]'))
        )
        download_url = download_link_el.get_attribute("href")

        content = driver.execute_script("""
            return fetch(arguments[0])
                .then(r => r.blob())
                .then(b => b.arrayBuffer())
                .then(buf => Array.from(new Uint8Array(buf)))
        """, download_url)

        if not content:
            raise Exception("Пустой контент из fetch")

        # Сохранить как zip
        with open(f"{OUTPUT_DIR}/{project_name}_v{version_num}.zip", "wb") as f:
            f.write(bytearray(content))

        return True

    except Exception as e:
        logging.warning(f"Ошибка при скачивании версии {version_num} проекта {project_name}: {e}")
        raise


def run_for_project(project, progress, cookie):
    name = project['name']
    url = project['url']
    logger = setup_logger(name)
    logger.info(f"== Запуск проекта {name} ==")

    backoff = 60
    done = False

    while not done:
        try:
            driver = setup_driver(cookie)
            driver.get(url)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "toolbar-label")))
            wait_and_click(driver, By.XPATH, '//span[text()="history"]/ancestor::button')

            version_elements = extract_version_links(driver)
            logger.info(f"Найдено {len(version_elements)} версий")

            last = progress.get(name, -1)
            for i in range(last + 1, len(version_elements)-1):
                logger.info(f"Обрабатываем версию {i}...")
                try:
                    download_version(driver, version_elements[i], name, i)
                    progress[name] = i
                    save_progress(progress)
                except (StaleElementReferenceException, ElementClickInterceptedException) as e:
                    logger.warning(f"Проблема с DOM: {e}. Повторный запуск")
                    break  # пересоздаем драйвер на следующем проходе
                except WebDriverException as e:
                    if '429' in str(e):
                        logger.warning(f"Лимит превышен, ждем {backoff} секунд")
                        time.sleep(backoff)
                        backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
                        break
                    else:
                        logger.error(f"Ошибка при обработке версии {i}: {e}")
                        logger.error(traceback.format_exc())
                except Exception as e:
                    logger.error(f"❌ Ошибка при обработке версии {i}: {e}")
                    logger.error(traceback.format_exc())
            else:
                done = True

            driver.quit()
        except Exception as e:
            logger.error(f"Общая ошибка: {e}")
            logger.error(traceback.format_exc())
            time.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)


if __name__ == '__main__':
    LOG_DIR = "logs"
    os.makedirs(LOG_DIR, exist_ok=True)
    logging.basicConfig(
        filename=os.path.join(LOG_DIR, "log.txt"),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    cookie, projects = load_config()
    ensure_progress_file()
    progress = load_progress()

    for project in projects:
        run_for_project(project, progress, cookie)

    print("✅ Все проекты завершены")

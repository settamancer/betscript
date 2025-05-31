from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import os
import time
import pandas as pd
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime
from config import PASSWORD, USERNAME

BRAVE_PATH = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
EXCEL_FILE = "pari_bets_history.xlsx"
LOGIN_URL = "https://pari.ru/authProcess/login"
BETS_URL = "https://pari.ru/account/history/bets"

TIMEOUT = 10

class PariParser:
    def __init__(self):
        self.driver = self.setup_driver()
        self.wait = WebDriverWait(self.driver, TIMEOUT)

    def setup_driver(self):
        if not os.path.exists(BRAVE_PATH):
            raise FileNotFoundError(f"Brave browser не найден по пути: {BRAVE_PATH}")
        options = Options()
        options.binary_location = BRAVE_PATH
        options.add_argument("--start-maximized")
        service = Service(ChromeDriverManager(driver_version="136.0.7103.94").install())
        driver = webdriver.Chrome(service=service, options=options)
        return driver

    def load_existing_data(self):
        if os.path.exists(EXCEL_FILE):
            try:
                return pd.read_excel(EXCEL_FILE)
            except Exception as e:
                print(f"Ошибка загрузки файла: {e}")
        return pd.DataFrame()

    def login(self):
        print("🔐 Авторизация на сайте...")
        self.driver.get(LOGIN_URL)
        try:
            login_field = self.wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, 'input[data-testid="input"][name="login"]')))
            login_field.clear()
            login_field.send_keys(USERNAME)
            time.sleep(1)

            password_field = self.driver.find_element(By.CSS_SELECTOR, 'input[data-testid="input"][type="password"]')
            password_field.clear()
            password_field.send_keys(PASSWORD)
            time.sleep(1)

            login_span = self.wait.until(EC.element_to_be_clickable(
                (By.XPATH, '//span[text()="Войти" and contains(@class, "button--_ckCX")]')))
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", login_span)
            time.sleep(0.5)
            self.driver.execute_script("arguments[0].click();", login_span)

            self.wait.until(EC.url_contains("/account/"))
            print("✅ Авторизация успешна")
            return True

        except Exception as e:
            print("❌ Ошибка авторизации:", str(e)[:300])
            print("Текущий URL:", self.driver.current_url)
            return False

    def parse_bets(self):
        print("📊 Сбор информации о ставках...")
        self.driver.get(BETS_URL)
        time.sleep(5)

        scroll_container = self.driver.find_element(By.CSS_SELECTOR, 'div.scroll-area__view-port__default--J1yYl')
        last_height = 0

        for i in range(100):
            self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scroll_container)
            time.sleep(1.5)
            new_height = self.driver.execute_script("return arguments[0].scrollTop", scroll_container)
            if new_height == last_height:
                print(f"🔽 Прокрутка остановлена на {i + 1} шаге — достигнут конец")
                break
            last_height = new_height

        bets = []
        current_date = None
        rows = self.driver.find_elements(By.CSS_SELECTOR, 'div[class^="row"]')

        for i, row in enumerate(rows):
            try:
                try:
                    date_cell = row.find_element(By.CSS_SELECTOR, '[class*="cellDate"]')
                    date_text = date_cell.text.strip()
                    if date_text:
                        current_date = date_text
                except:
                    pass

                try:
                    time_cell = row.find_element(By.CSS_SELECTOR, '[class*="cellDateTime"]')
                    time_text = time_cell.text.strip().lower()
                    if "время" in time_text or not time_text:
                        print(f"⏭ Пропущена строка #{i+1} — это заголовок или пустая строка")
                        continue
                    time_str = time_text
                except Exception as e:
                    print(f"⚠ Не удалось получить время в строке #{i+1}: {e}")
                    continue

                if not current_date or not time_str:
                    print(f"⚠ Пропущена строка #{i+1} — отсутствует дата или время")
                    continue

                full_datetime = f"{current_date} {time_str}"

                def safe_get(selector, inside=row, default=""):
                    try:
                        return inside.find_element(By.CSS_SELECTOR, selector).text.strip()
                    except:
                        return default

                def safe_get_float(selector, inside=row, default=0.0):
                    try:
                        return float(inside.find_element(By.CSS_SELECTOR, selector).text.strip()
                                     .replace(',', '.').replace('₽', '').replace('\xa0', ''))
                    except:
                        return default

                bet_data = {
                    "время": full_datetime,
                    "тип_пари": safe_get('div[class*="cellPariType"] .text--Y2SFL'),
                    "событие": safe_get('div[class*="cellDescription"] .text--Y2SFL'),
                    "описание": safe_get('div[class*="cellDescription"] .text--Y2SFL'),
                    "коэффициент": safe_get_float('div[class*="cellFactor"] span'),
                    "сумма": safe_get_float('div[class*="cellSum"] span'),
                    "результат": safe_get('div[class*="cellResult"]'),
                    "прибыль": self.calculate_profit(row)
                }
                bets.append(bet_data)
                print(f"✅ Успешно обработана ставка #{i + 1}")
            except Exception as e:
                print(f"⚠ Ошибка при разборе ставки #{i+1}: {str(e)}")
                print("HTML строки:\n", row.get_attribute("innerHTML"))
        return bets

    def calculate_profit(self, item):
        try:
            result = item.find_element(By.CSS_SELECTOR, 'div[class*="cellResult"]').text.lower()
            if "выигрыш" in result:
                coefficient = float(item.find_element(By.CSS_SELECTOR, 'div[class*="cellFactor"] span').text.replace(',', '.'))
                amount = float(item.find_element(By.CSS_SELECTOR, 'div[class*="cellSum"] span').text.replace('₽','').replace('\xa0', '').replace(',', '.'))
                return round(coefficient * amount - amount, 2)
        except:
            pass
        return 0.0

    def save_data(self, existing_data, new_bets):
        if not new_bets:
            print("🔄 Нет новых ставок для сохранения")
            return

        new_df = pd.DataFrame(new_bets)
        new_df = new_df[new_df['время'].notna()]
        new_df = new_df[~new_df['время'].str.contains("None|ДАТА", na=False)]

        current_year = datetime.now().year

        def add_year_if_missing(dt_str):
            if dt_str.count('.') == 1:
                return f"{dt_str.split()[0]}.{current_year} {dt_str.split()[1]}"
            return dt_str

        new_df['время'] = new_df['время'].apply(add_year_if_missing)

        try:
            new_df['время'] = pd.to_datetime(new_df['время'], dayfirst=True)
        except Exception as e:
            print("❌ Ошибка преобразования времени:", e)
            return

        if not existing_data.empty:
            existing_data['время'] = pd.to_datetime(existing_data['время'], dayfirst=True, errors='coerce')
            combined_df = pd.concat([existing_data, new_df], ignore_index=True)

            # Удаляем полные дубликаты по всем основным полям
            combined_df.drop_duplicates(subset=['время', 'тип_пари', 'событие', 'описание', 'коэффициент', 'сумма'], inplace=True)
        else:
            combined_df = new_df

        combined_df.sort_values('время', ascending=False, inplace=True)
        combined_df['время'] = combined_df['время'].dt.strftime('%d.%m.%Y %H:%M')

        try:
            combined_df.to_excel(EXCEL_FILE, index=False)
            print(f"💾 Сохранено {len(combined_df)} ставок в {EXCEL_FILE}")
        except Exception as e:
            print(f"⛔ Ошибка при сохранении: {e}")


    def run(self):
        try:
            existing_data = self.load_existing_data()
            if not self.login():
                print("⚠ Требуется ручной ввод капчи! Ожидание 30 секунд...")
                time.sleep(30)
                if "bets" not in self.driver.current_url:
                    print("❌ Не удалось авторизоваться")
                    return
            new_bets = self.parse_bets()
            if new_bets:
                self.save_data(existing_data, new_bets)
            else:
                print("⛔ Не удалось получить данные о ставках")
        finally:
            self.driver.quit()

if __name__ == "__main__":
    parser = PariParser()
    parser.run()
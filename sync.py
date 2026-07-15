#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FIXTURE_ROM Sync Automation Script
Скрипт для автоматического парсинга, скачивания и синхронизации прошивок
и DMX-карт для гаффер-флешки (FIXTURE_ROM).
"""

import os
import re
import sys
import shutil
import urllib.parse
import time
import json

# Попытка импортировать библиотеку requests.
try:
    import requests
except ImportError:
    import subprocess
    print("⏳ Библиотека 'requests' не найдена. Устанавливаем её автоматически...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
        import requests
        print("✅ Библиотека 'requests' успешно установлена!")
    except Exception as e:
        print(f"❌ Не удалось установить 'requests' автоматически: {e}")
        print("Пожалуйста, установите её вручную: pip install requests")
        sys.exit(1)

# --- Константы ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LINKS_FILE = os.path.join(SCRIPT_DIR, "links.md")
LOCAL_DOWNLOADS_ROOT = os.path.expanduser("~/Documents/FixtureROM/Downloads")

def get_usb_root():
    """
    Определяет путь к флешке FIXTURE_ROM на macOS и Windows.
    """
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            volumeNameBuffer = ctypes.create_unicode_buffer(1024)
            for letter in "EFGHIJKLMNOPQRSTUVWXYZD":
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    res = kernel32.GetVolumeInformationW(
                        drive, volumeNameBuffer, 1024, None, None, None, None, 0
                    )
                    if res and volumeNameBuffer.value == "FIXTURE_ROM":
                        return drive
        except Exception:
            pass
        return None
    else:
        mac_path = "/Volumes/FIXTURE_ROM"
        if os.path.exists(mac_path) and os.path.isdir(mac_path):
            return mac_path
        return None

# Фейковый User-Agent для обхода блокировок на сайтах производителей
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# ANSI-коды для красивого форматирования вывода в консоль
BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

def clean_filename(url):
    """
    Извлекает имя файла из URL, декодирует его и заменяет '+' на пробелы.
    """
    parsed_url = urllib.parse.urlparse(url)
    raw_filename = os.path.basename(parsed_url.path)
    decoded_filename = urllib.parse.unquote(raw_filename).replace("+", " ")
    return decoded_filename

def classify_brand(header_brand, url, description):
    """
    Определяет точный бренд на основе заголовка в MD и контекста (URL/описания).
    """
    header_lower = header_brand.lower()
    url_lower = url.lower()
    desc_lower = description.lower()
    
    if "aputure" in header_lower:
        return "Aputure"
        
    if "nanlux" in header_lower or "nanlite" in header_lower:
        if "nanlite" in url_lower or "nanlite" in desc_lower:
            return "Nanlite"
        if "nanlux" in url_lower or "nanlux" in desc_lower:
            return "Nanlux"
        return "Nanlux"
        
    if "godox" in header_lower or "knowled" in header_lower:
        if "knowled" in url_lower or "knowled" in desc_lower:
            return "Knowled"
        if "godox" in url_lower or "godox" in desc_lower:
            return "Godox"
        return "Godox"
        
    return header_brand.split('/')[0].strip()

def classify_category(filename, description):
    """
    Определяет категорию файла:
    - '01_Firmware' для прошивок.
    - '02_DMX_Charts' для DMX-карт (только если содержат слово 'dmx' в названии/описании).
    - None для прочих PDF (руководства, рекламные листы), которые нужно отфильтровать.
    """
    fn_lower = filename.lower()
    desc_lower = description.lower()
    
    is_dmx = "dmx" in fn_lower or "dmx" in desc_lower
    
    if fn_lower.endswith(".pdf"):
        if is_dmx:
            return "02_DMX_Charts"
        else:
            return None # Отфильтровываем обычные PDF-инструкции без DMX
            
    return "01_Firmware"

def parse_links_file(filepath):
    """
    Парсит links.md для извлечения брендов, названий моделей и ссылок на файлы.
    """
    if not os.path.exists(filepath):
        print(f"{RED}❌ Ошибка: Файл {filepath} не найден!{RESET}")
        return []
        
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    items = []
    current_brand_header = "General"
    
    header_pattern = re.compile(r"^##\s+(.+)$")
    item_pattern = re.compile(r"^\s*-\s*\*\*([^*]+)\*\*\s*\[([^\]]+)\]\(([^)]+)\)")
    host_file_pattern = re.compile(r"host:\s*([^,\s]+),\s*filename:\s*(\S+)")
    
    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue
            
        header_match = header_pattern.match(line_str)
        if header_match:
            current_brand_header = header_match.group(1).strip()
            continue
            
        item_match = item_pattern.match(line_str)
        if item_match:
            description = item_match.group(1).rstrip(':').strip()
            btn_text = item_match.group(2).strip()
            link_target = item_match.group(3).strip()
            
            desc_lower = description.lower()
            if "раздел" in desc_lower or "официальный" in desc_lower:
                continue
                
            host_match = host_file_pattern.search(link_target)
            if host_match:
                host = host_match.group(1).strip()
                filename_part = host_match.group(2).strip()
                url = f"https://{host}{filename_part}"
            else:
                url = link_target
                
            if not url.startswith("http"):
                continue
                
            parsed_url = urllib.parse.urlparse(url)
            url_path = parsed_url.path.lower()
            _, ext = os.path.splitext(url_path)
            
            if ext not in [".zip", ".bin", ".pdf", ".hex", ".dfu", ".tar", ".rar"]:
                continue
                
            filename = clean_filename(url)
            brand = classify_brand(current_brand_header, url, description)
            category = classify_category(filename, description)
            
            if category: # Пропускаем, если категория None
                items.append({
                    "url": url,
                    "description": description,
                    "brand": brand,
                    "category": category
                })
            
    return items

# --- Модули автоматического сканирования сайтов ---

def scrape_aputure_links():
    """
    Сканирует страницу загрузок Aputure и Amaran.
    """
    url = "https://aputure.com/en-US/pages/downloads"
    headers = {"User-Agent": USER_AGENT}
    scraped = []
    try:
        response = requests.get(url, headers=headers, timeout=25)
        response.raise_for_status()
        
        url_pattern = re.compile(
            r'https?://[^\s"\'<>\\(\)]+?\.(?:zip|bin|pdf|hex|dfu)', 
            re.IGNORECASE
        )
        matches = url_pattern.findall(response.text)
        
        for file_url in set(matches):
            file_url = file_url.replace('&amp;', '&').replace('&AMP;', '&')
            filename = clean_filename(file_url)
            
            if any(filename.lower().endswith(img_ext) for img_ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.woff', '.woff2']):
                continue
                
            brand = "Amaran" if "amaran" in file_url.lower() or "amaran" in filename.lower() else "Aputure"
            category = classify_category(filename, "")
            
            if category: # Сохраняем только валидные категории
                scraped.append({
                    "url": file_url,
                    "description": f"Автоматически найденный файл ({filename})",
                    "brand": brand,
                    "category": category
                })
    except Exception as e:
        print(f"    {RED}⚠️ Ошибка при сканировании Aputure: {e}{RESET}")
    return scraped

def scrape_nanlink_api(brand_path, brand_name):
    """
    Сканирует внутреннее API Nanlink для Nanlite и Nanlux.
    """
    index_url = f"https://serv.nanlink.com/{brand_path}/front/v1/download/index"
    detail_url = f"https://serv.nanlink.com/{brand_path}/front/v1/firmwareManual/queryDetail"
    headers = {
        "User-Agent": USER_AGENT,
        "lang": "2"
    }
    scraped = []
    try:
        response = requests.get(index_url, headers=headers, timeout=20)
        response.raise_for_status()
        index_data = response.json()
        
        if index_data.get("code") != 200:
            return scraped
            
        series_product = index_data.get("data", {}).get("seriesProduct", [])
        product_ids = set()
        for series in series_product:
            for child in series.get("children", []):
                p_id = child.get("productId")
                if p_id:
                    product_ids.add(p_id)
                    
        for idx, p_id in enumerate(product_ids, 1):
            sys.stdout.write(f"\r    Сканирование моделей {brand_name}: {idx}/{len(product_ids)}")
            sys.stdout.flush()
            
            try:
                detail_resp = requests.get(
                    detail_url, 
                    params={"productId": str(p_id), "accessoryId": ""}, 
                    headers=headers, 
                    timeout=15
                )
                detail_resp.raise_for_status()
                detail_data = detail_resp.json()
                
                if detail_data.get("code") == 200:
                    prod_data = detail_data.get("data", {})
                    
                    # Прошивки
                    for fw in prod_data.get("firmware", []):
                        file_url = fw.get("file")
                        if file_url:
                            scraped.append({
                                "url": file_url,
                                "description": fw.get("name", "Firmware"),
                                "brand": brand_name,
                                "category": "01_Firmware"
                            })
                            
                    # Руководства / DMX-карты
                    for man in prod_data.get("manual", []):
                        file_url = man.get("file")
                        if file_url:
                            name = man.get("name", "Manual")
                            category = classify_category(clean_filename(file_url), name)
                            if category: # Фильтруем ненужные PDF
                                scraped.append({
                                    "url": file_url,
                                    "description": name,
                                    "brand": brand_name,
                                    "category": category
                                })
            except Exception:
                pass
                
        sys.stdout.write("\r" + " " * 80 + "\r")
        sys.stdout.flush()
    except Exception as e:
        print(f"    {RED}⚠️ Ошибка при сканировании API {brand_name}: {e}{RESET}")
    return scraped

def scrape_godox_style_pages(base_url, pages, brand_name):
    """
    Парсит веб-страницы Godox или Knowled с пагинацией.
    """
    headers = {"User-Agent": USER_AGENT}
    scraped = []
    
    pattern = re.compile(
        r'([^<>]+?)\s*(?:<span>([^<>]+)</span>)?\s*<a[^>]+href=["\']([^"\']+)["\'][^>]*class="download"', 
        re.IGNORECASE
    )
    
    for page_path in pages:
        url = urllib.parse.urljoin(base_url, page_path)
        try:
            response = requests.get(url, headers=headers, timeout=20)
            response.raise_for_status()
            
            matches = pattern.findall(response.text)
            for title, version, href in matches:
                title = title.strip()
                version = version.strip() if version else ""
                href = href.strip()
                
                if href.startswith("/"):
                    href = urllib.parse.urljoin(base_url, href)
                    
                if not href.startswith("http"):
                    continue
                    
                filename = clean_filename(href)
                _, ext = os.path.splitext(filename.lower())
                if ext not in [".zip", ".bin", ".pdf", ".hex", ".dfu", ".tar", ".rar"]:
                    continue
                    
                description = f"{title} {version}".strip()
                category = classify_category(filename, description)
                
                if category: # Фильтруем ненужные PDF
                    scraped.append({
                        "url": href,
                        "description": description,
                        "brand": brand_name,
                        "category": category
                    })
        except Exception as e:
            print(f"    {RED}⚠️ Ошибка при сканировании страницы {url}: {e}{RESET}")
    return scraped

def download_file(url, local_path):
    """
    Скачивает файл по ссылке с отображением красивого прогресс-бара.
    """
    temp_path = local_path + ".tmp"
    headers = {"User-Agent": USER_AGENT}
    
    try:
        response = requests.get(url, headers=headers, stream=True, timeout=30)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        block_size = 8192
        downloaded = 0
        
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        
        with open(temp_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=block_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = int(40 * downloaded / total_size)
                        bar = '█' * percent + '░' * (40 - percent)
                        pct_text = f"{int(100 * downloaded / total_size)}%"
                        sys.stdout.write(f"\r    📥 [{bar}] {pct_text} ({downloaded // 1024} KB)")
                        sys.stdout.flush()
                    else:
                        sys.stdout.write(f"\r    📥 Скачано: {downloaded // 1024} KB")
                        sys.stdout.flush()
                        
        if os.path.exists(local_path):
            os.remove(local_path)
        os.rename(temp_path, local_path)
        sys.stdout.write("\r" + " " * 80 + "\r")
        sys.stdout.flush()
        return True
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        sys.stdout.write("\r" + " " * 80 + "\r")
        sys.stdout.flush()
        print(f"    {RED}❌ Ошибка при скачивании {url}: {e}{RESET}")
        return False

def sync_file_to_usb(local_path, usb_path):
    """
    Копирует файл на флешку, если он отсутствует или отличается по размеру/времени изменения.
    """
    os.makedirs(os.path.dirname(usb_path), exist_ok=True)
    
    copy_needed = False
    if not os.path.exists(usb_path):
        copy_needed = True
    else:
        local_stat = os.stat(local_path)
        usb_stat = os.stat(usb_path)
        if local_stat.st_size != usb_stat.st_size or local_stat.st_mtime > usb_stat.st_mtime:
            copy_needed = True
            
    if copy_needed:
        shutil.copy2(local_path, usb_path)
        return True
    return False

def clean_model_and_version(description, brand):
    """
    Извлекает имя модели и версию из описания.
    """
    desc = description.strip()
    
    # 0. Удаляем технические префиксы автопоиска (для Aputure/Amaran)
    desc = re.sub(r'^автоматически\s+найденный\s+файл\s*\(', '', desc, flags=re.IGNORECASE).strip()
    if desc.endswith(')'):
        desc = desc[:-1].strip()

    # 1. Извлекаем версию (например, V1.6, V2.01.22, 1.04)
    # Позволяем версии начинаться на границе слова или после подчеркивания (_)
    version = ""
    v_match = re.search(r'(?:\b|_)(v?\d+(?:\.\d+)+)\b', desc, re.IGNORECASE)
    if v_match:
        version = v_match.group(1)
        # Вырезаем версию из описания модели
        start_idx = v_match.start(1)
        if start_idx > 0 and desc[start_idx-1] in ['_', '-', ' ']:
            start_idx -= 1
        desc = desc[:start_idx] + desc[v_match.end():]
        
    # 2. Удаляем упоминание бренда
    desc = re.sub(rf'\b{brand}\b', '', desc, flags=re.IGNORECASE).strip()
    
    # 3. Удаляем ключевые слова типов файлов на конце описания
    desc = re.sub(r'\b(firmware|user\s+manual|manual|dmx\s+charts|dmx\s+chart|dmx\s+profile|dmx\s+specification|dmx|practical\s+table|table|specification|profile)\b.*$', '', desc, flags=re.IGNORECASE).strip()
    
    # 4. Очищаем висящие знаки препинания и разделители
    desc = re.sub(r'[\s\-_\/]+$', '', desc).strip()
    desc = re.sub(r'^[\s\-_\/]+', '', desc).strip()
    
    # 5. Приводим модель к верхнему регистру
    model = desc.upper()
    
    # Заменяем подчеркивания на пробелы для человекочитаемости модели
    model = model.replace('_', ' ').replace('  ', ' ').strip()
    
    # Стандартизируем формат версии (всегда с большой 'V')
    if version:
        version_upper = version.upper()
        if not version_upper.startswith('V'):
            version = "V" + version
        else:
            version = "V" + version[1:]
            
    return model, version

def get_new_filename(raw_fn, metadata):
    """
    Генерирует новое имя файла на основе метаданных.
    """
    desc = metadata.get("description", "")
    brand = metadata.get("brand", "")
    category = metadata.get("category", "01_Firmware")
    _, ext = os.path.splitext(raw_fn)
    
    model, version = clean_model_and_version(desc, brand)
    
    # Если не удалось вытащить модель, используем очищенное оригинальное имя
    if not model:
        model = os.path.splitext(raw_fn)[0].upper()
        model = re.sub(rf'\b{brand.upper()}\b', '', model).strip()
        model = re.sub(r'[\s\-_]+$', '', model).strip()
        
    if category == "01_Firmware":
        # Слияние вариантов 1 и 3 для прошивок (машинночитаемый CAPS с подчеркиваниями)
        # Например: EVOKE_1200B_V1.04.02.zip
        model_part = model.replace(' ', '_').replace('-', '_')
        model_part = re.sub(r'_+', '_', model_part).strip('_')
        
        if version:
            new_name = f"{model_part}_{version}{ext}"
        else:
            new_name = f"{model_part}{ext}"
    else:
        # Для DMX-карт и мануалов (человекочитаемый CAPS с пробелами и дефисами)
        # Например: EVOKE 1200B - DMX CHART.pdf
        
        # Определяем тип документа
        desc_lower = desc.lower()
        if any(kw in desc_lower for kw in ["dmx", "profile", "specification", "table", "chart", "map"]):
            doc_type = "DMX CHART"
        elif "manual" in desc_lower:
            doc_type = "USER MANUAL"
        elif "one sheet" in desc_lower or "onesheet" in desc_lower:
            doc_type = "ONE SHEET"
        elif "data book" in desc_lower:
            doc_type = "DATA BOOK"
        else:
            doc_type = "GUIDE"
            
        # Извлекаем язык, чтобы избежать коллизий имен файлов на разных языках
        lang = ""
        lang_match = re.search(
            r'\((English|French|Italian|Japanese|Spanish|German|Chinese|Traditional\s+Chinese|Russian|Korean|Dutch|Portuguese)\)', 
            desc, 
            re.IGNORECASE
        )
        if lang_match:
            lang = f" ({lang_match.group(1).upper()})"
            
        # Добавляем версию, если она есть
        version_part = f" {version}" if version else ""
        new_name = f"{model} - {doc_type}{version_part}{lang}{ext}"
        
    # Удаляем запрещенные в именах файлов символы
    new_name = re.sub(r'[\\/*?:"<>|]', '', new_name)
    return new_name

def notify_user_macos(new_files):
    """
    Отправляет нативное уведомление в macOS Sequoia.
    """
    import subprocess
    if not new_files:
        title = "FIXTURE_ROM Sync"
        subtitle = "Проверка обновлений"
        message = "Новых прошивок и DMX-карт не обнаружено."
        script = f'display notification "{message}" with title "{title}" subtitle "{subtitle}"'
        try:
            subprocess.run(["osascript", "-e", script])
        except Exception:
            pass
        return

    title = "FIXTURE_ROM"
    summary = {}
    for item in new_files:
        brand = item["brand"]
        desc = item["description"]
        summary.setdefault(brand, []).append(desc)
        
    lines = []
    for brand, descs in summary.items():
        lines.append(f"• {brand}:")
        for d in descs[:3]:
            lines.append(f"  - {d}")
        if len(descs) > 3:
            lines.append(f"  - и еще {len(descs) - 3}...")
            
    message_text = f"🔥 Найдено обновлений: {len(new_files)} шт.\\n\\n" + "\\n".join(lines)
    
    apple_script = f'''
    tell application "System Events"
        set dialogResult to display dialog "{message_text}" with title "FIXTURE_ROM Обновления" buttons {{"ОК", "Открыть папку"}} default button "ОК" with icon note
        if button returned of dialogResult is "Открыть папку" then
            do shell script "open '{LOCAL_DOWNLOADS_ROOT}'"
        end if
    end tell
    '''
    try:
        subprocess.run(["osascript", "-e", apple_script])
    except Exception as e:
        print(f"Ошибка вызова уведомления: {e}")

def scrape_custom_sources():
    """
    Сканирует пользовательские сайты автопоиска из файла custom_scrapers.json
    """
    scrapers_file = os.path.join(SCRIPT_DIR, "custom_scrapers.json")
    if not os.path.exists(scrapers_file):
        return []
        
    try:
        with open(scrapers_file, "r", encoding="utf-8") as f:
            scrapers = json.load(f)
    except Exception as e:
        print(f"⚠️ Ошибка чтения custom_scrapers.json: {e}")
        return []
        
    all_items = []
    for s in scrapers:
        brand = s.get("brand")
        url = s.get("url")
        file_types = s.get("file_types", [".zip", ".bin", ".pdf"])
        keywords = [k.strip().lower() for k in s.get("keyword_filter", "").split(",") if k.strip()]
        
        print(f"\n   - Автопоиск {brand} на {url}...")
        try:
            headers = {"User-Agent": USER_AGENT}
            response = requests.get(url, headers=headers, timeout=20)
            if response.status_code != 200:
                print(f"     ❌ Код ответа: {response.status_code}")
                continue
                
            try:
                from bs4 import BeautifulSoup
            except ImportError:
                print("     ❌ Требуется библиотека beautifulsoup4. Установите: pip install beautifulsoup4")
                continue
                
            soup = BeautifulSoup(response.text, "html.parser")
            found_count = 0
            
            for link in soup.find_all("a", href=True):
                href = link["href"]
                full_url = urllib.parse.urljoin(url, href)
                
                # Проверяем тип файла
                parsed_path = urllib.parse.urlparse(full_url).path
                ext = os.path.splitext(parsed_path)[1].lower()
                if ext not in file_types:
                    continue
                    
                # Получаем текст ссылки или описание
                text = link.get_text().strip()
                title_attr = link.get("title", "").strip()
                desc = text if len(text) > 3 else (title_attr if title_attr else os.path.basename(parsed_path))
                
                # Фильтруем по ключевым словам
                if keywords:
                    matches_keywords = any(k in desc.lower() or k in full_url.lower() for k in keywords)
                    if not matches_keywords:
                        continue
                        
                # Классифицируем категорию
                category = classify_category(full_url, desc)
                if not category:
                    continue
                    
                all_items.append({
                    "url": full_url,
                    "description": desc,
                    "brand": brand,
                    "category": category
                })
                found_count += 1
                
            print(f"     ✅ Завершено! Найдено новых файлов: {found_count}")
        except Exception as e:
            print(f"     ❌ Ошибка автопоиска: {e}")
            
    return all_items

def main():
    print(f"\n{BOLD}{CYAN}================================================================{RESET}")
    print(f"{BOLD}{CYAN}⚡  FIXTURE_ROM | Автоматическая синхронизация прошивок и DMX  ⚡{RESET}")
    print(f"{BOLD}{CYAN}================================================================{RESET}\n")
    
    # 1. Чтение links.md
    print(f"🔍 Чтение файла ресурсов: {BLUE}{LINKS_FILE}{RESET}...")
    manual_items = parse_links_file(LINKS_FILE)
    print(f"✅ Из links.md успешно получено ссылок: {GREEN}{len(manual_items)}{RESET}\n")
    
    # 2. Автоматическое сканирование сайтов
    print(f"🌐 {BOLD}Сканирование сайтов производителей (поиск всех моделей)...{RESET}")
    
    # Aputure & Amaran
    sys.stdout.write("    - Сканирование Aputure / Amaran...")
    sys.stdout.flush()
    aputure_items = scrape_aputure_links()
    print(f"\r    - Aputure / Amaran: найдено {GREEN}{len(aputure_items)}{RESET} файлов.")
    
    # Nanlite
    sys.stdout.write("    - Сканирование Nanlite...")
    sys.stdout.flush()
    nanlite_items = scrape_nanlink_api("nanlite", "Nanlite")
    print(f"\r    - Nanlite: найдено {GREEN}{len(nanlite_items)}{RESET} файлов.")
    
    # Nanlux
    sys.stdout.write("    - Сканирование Nanlux...")
    sys.stdout.flush()
    nanlux_items = scrape_nanlink_api("nanlux", "Nanlux")
    print(f"\r    - Nanlux: найдено {GREEN}{len(nanlux_items)}{RESET} файлов.")
    
    # Godox
    sys.stdout.write("    - Сканирование Godox...")
    sys.stdout.flush()
    godox_pages = [
        "/firmware-continuous-light/",
        "/firmware-continuous-light_2/",
        "/firmware-continuous-light_3/",
        "/firmware-control-system/",
        "/firmware-launcher-installers/"
    ]
    godox_items = scrape_godox_style_pages("https://www.godox.com", godox_pages, "Godox")
    print(f"\r    - Godox: найдено {GREEN}{len(godox_items)}{RESET} файлов.")
    
    # Knowled
    sys.stdout.write("    - Сканирование Knowled...")
    sys.stdout.flush()
    knowled_pages = [
        "/firmware-knowled/",
        "/firmware-knowled_2/",
        "/firmware-knowled_3/",
        "/firmware-knowled_4/",
        "/firmware-knowled_5/"
    ]
    knowled_items = scrape_godox_style_pages("https://www.knowled.com", knowled_pages, "Knowled")
    print(f"\r    - Knowled: найдено {GREEN}{len(knowled_items)}{RESET} файлов.")
    
    # Пользовательские источники
    sys.stdout.write("    - Сканирование пользовательских источников...")
    sys.stdout.flush()
    custom_items = scrape_custom_sources()
    print(f"\r    - Пользовательские источники: найдено {GREEN}{len(custom_items)}{RESET} файлов.")
    
    # Слияние всех списков с исключением дубликатов по URL и фильтрацией пустых категорий
    all_scraped = aputure_items + nanlite_items + nanlux_items + godox_items + knowled_items + custom_items
    
    seen_urls = {}
    for item in manual_items:
        if item.get("category"):
            seen_urls[item["url"]] = item
    for item in all_scraped:
        url = item["url"]
        if url not in seen_urls and item.get("category"):
            seen_urls[url] = item
            
    final_items = list(seen_urls.values())
    print(f"\n{GREEN}✅ Сканирование завершено!{RESET} Итого уникальных файлов для синхронизации: {BOLD}{len(final_items)}{RESET}\n")
    
    # Автоматически генерируем/обновляем metadata.json для rename.py
    db = {}
    for item in final_items:
        url = item["url"]
        raw_fn = clean_filename(url)
        db[raw_fn] = {
            "url": url,
            "description": item["description"],
            "brand": item["brand"],
            "category": item["category"]
        }
    db_path = os.path.join(LOCAL_DOWNLOADS_ROOT, "metadata.json")
    try:
        with open(db_path, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        print(f"📦 База метаданных для переименования записана в {BLUE}metadata.json{RESET} ({len(db)} записей).")
    except Exception as e:
        print(f"⚠️ Предупреждение: Не удалось записать metadata.json: {e}")
    
    # 3. Проверка подключения флешки
    usb_root = get_usb_root()
    usb_mounted = usb_root is not None
    if usb_mounted:
        print(f"💾 {GREEN}Обнаружен накопитель FIXTURE_ROM по пути {usb_root}{RESET}")
        print(f"   Включена односторонняя синхронизация (Mac -> USB).\n")
    else:
        print(f"ℹ️ {YELLOW}Накопитель FIXTURE_ROM не примонтирован.{RESET}")
        print(f"   Работаем в режиме локального кэширования на Mac.\n")
        
    print(f"{BOLD}🚀 Начинаем процесс синхронизации...{RESET}\n")
    
    download_count = 0
    skip_count = 0
    usb_copy_count = 0
    usb_skip_count = 0
    downloaded_files_info = []
    
    # 4. Обработка каждого файла
    allocated_names = {}
    for idx, item in enumerate(final_items, 1):
        url = item["url"]
        desc = item["description"]
        brand = item["brand"]
        category = item["category"]
        
        raw_filename = clean_filename(url)
        
        # Генерируем стандартное имя файла
        meta = {
            "url": url,
            "description": desc,
            "brand": brand,
            "category": category
        }
        new_filename = get_new_filename(raw_filename, meta)
        
        # Разрешаем коллизии имен для текущего прогона
        key = (category, brand)
        if key not in allocated_names:
            allocated_names[key] = set()
            
        if new_filename in allocated_names[key]:
            base, ext = os.path.splitext(new_filename)
            counter = 1
            while f"{base}_{counter}{ext}" in allocated_names[key]:
                counter += 1
            new_filename = f"{base}_{counter}{ext}"
            
        allocated_names[key].add(new_filename)
        
        local_path = os.path.join(LOCAL_DOWNLOADS_ROOT, category, brand, new_filename)
        usb_path = os.path.join(usb_root, category, brand, new_filename) if usb_mounted else None
        
        print(f"{BOLD}[{idx}/{len(final_items)}] {brand} | {desc}{RESET}")
        
        # А) Локальное скачивание
        if os.path.exists(local_path):
            print(f"   Skip: {GREEN}актуален на Mac{RESET} ({new_filename})")
            skip_count += 1
        else:
            print(f"   📥 На диске: {YELLOW}отсутствует{RESET}, скачиваем...")
            success = download_file(url, local_path)
            if success:
                print(f"   ✅ На диске: {GREEN}успешно скачан{RESET}")
                download_count += 1
                downloaded_files_info.append(item)
            else:
                continue
                
        # Б) Синхронизация с USB (если подключен)
        if usb_mounted:
            copied = sync_file_to_usb(local_path, usb_path)
            if copied:
                print(f"   💾 USB: {CYAN}скопирован новый/измененный файл{RESET}")
                usb_copy_count += 1
            else:
                print(f"   Skip: {GREEN}актуален на USB{RESET}")
                usb_skip_count += 1
                
        print()
        
    # 5. Итоговая статистика
    print(f"{BOLD}{CYAN}================================================================{RESET}")
    print(f"{BOLD}{GREEN}🎉 Синхронизация успешно завершена!{RESET}")
    print(f"{BOLD}{CYAN}----------------------------------------------------------------{RESET}")
    print(f"📂 Локальный кэш: {LOCAL_DOWNLOADS_ROOT}")
    print(f"   - Скачано новых файлов: {GREEN}{download_count}{RESET}")
    print(f"   - Пропущено (уже были): {skip_count}")
    
    if usb_mounted:
        print(f"💾 Накопитель: {usb_root}")
        print(f"   - Скопировано на USB: {CYAN}{usb_copy_count}{RESET}")
        print(f"   - Пропущено на USB: {usb_skip_count}")
    else:
        print(f"💾 Накопитель: {RED}Не подключен{RESET}")
    print(f"{BOLD}{CYAN}================================================================{RESET}\n")
    
    # Отправляем нативное уведомление macOS
    notify_user_macos(downloaded_files_info)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{RED}🛑 Процесс прерван пользователем.{RESET}\n")
        sys.exit(1)

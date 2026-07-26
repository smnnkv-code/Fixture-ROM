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
from html.parser import HTMLParser

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

from rom_common import GREEN, YELLOW, RED, CYAN, BOLD, RESET, get_usb_root, get_file_sha256, clean_model_and_version

# --- Константы ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LINKS_FILE = os.path.join(SCRIPT_DIR, "links.md")
LOCAL_DOWNLOADS_ROOT = os.path.join(SCRIPT_DIR, "Downloads")
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
SNAPSHOTS_DIR = os.path.join(SCRIPT_DIR, "Snapshots")
BLACKLIST_FILE = os.path.join(SNAPSHOTS_DIR, "blacklist.json")
RULES_FILE = os.path.join(SNAPSHOTS_DIR, "rules.json")

# Глобальные наборы черного списка и правил
BLACKLIST = set()
RULES = {}

def cleanup_empty_directories(path, preserve_path=None):
    """
    Рекурсивно удаляет все пустые папки в указанной директории,
    игнорируя скрытые файлы и сам корневой путь preserve_path.
    """
    if not os.path.isdir(path):
        return
        
    try:
        entries = os.listdir(path)
    except Exception:
        return
        
    for entry in entries:
        entry_path = os.path.join(path, entry)
        if os.path.isdir(entry_path):
            cleanup_empty_directories(entry_path, preserve_path)
            
    if preserve_path is None:
        preserve_path = LOCAL_DOWNLOADS_ROOT
        
    if path != preserve_path:
        try:
            current_entries = os.listdir(path)
            visible_contents = [e for e in current_entries if not e.startswith('.')]
            if not visible_contents:
                for e in current_entries:
                    try:
                        os.remove(os.path.join(path, e))
                    except Exception:
                        pass
                os.rmdir(path)
                print(f"   🧹 Удалена пустая папка: {os.path.relpath(path, LOCAL_DOWNLOADS_ROOT)}")
        except Exception:
            pass

def load_blacklist():
    """Загружает список заблокированных имен/хэшей."""
    if os.path.exists(BLACKLIST_FILE):
        try:
            with open(BLACKLIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return set(data)
        except Exception:
            pass
    return set()

def load_rules():
    """Загружает правила переименования."""
    if os.path.exists(RULES_FILE):
        try:
            with open(RULES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}

def normalize_key(k):
    """
    Нормализует имя файла для надежного сопоставления (без учета регистра, пробелов и дефисов).
    """
    return k.lower().replace(" ", "_").replace("-", "_")

def load_config():
    """
    Загружает настройки из config.json. Если файла нет, возвращает дефолтные.
    """
    default_config = {
        "enabled_categories": {"firmware": True, "dmx": True},
        "enabled_brands": {
            "Aputure": True, "Amaran": True, "Nanlite": True, 
            "Nanlux": True, "Godox": True, "Knowled": True, "ARRI": True,
            "Astera": True, "Creamsource": True, "GVM": True, "LiteGear": True,
            "Lightstar": True, "Litepanels": True, "Quasar Science": True,
            "Kino Flo": True, "Pipe Lighting": True, "Pheon Lux": True
        },
        "enabled_models": {}
    }
    if not os.path.exists(CONFIG_FILE):
        return default_config
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            user_config = json.load(f)
        for k, v in default_config.items():
            if k not in user_config:
                user_config[k] = v
            elif isinstance(v, dict):
                for sub_k, sub_v in v.items():
                    if sub_k not in user_config[k]:
                        user_config[k][sub_k] = sub_v
        return user_config
    except Exception:
        return default_config



# Фейковый User-Agent для обхода блокировок на сайтах производителей
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

BLUE = "\033[94m"

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
    
    if "arri" in header_lower:
        return "ARRI"
        
    if "astera" in header_lower:
        return "Astera"
        
    if "creamsource" in header_lower:
        return "Creamsource"
        
    if "gvm" in header_lower:
        return "GVM"
        
    if "litegear" in header_lower:
        return "LiteGear"
        
    if "lightstar" in header_lower:
        return "Lightstar"
        
    if "litepanels" in header_lower:
        return "Litepanels"
        
    if "quasar" in header_lower:
        return "Quasar Science"
        
    if "kino" in header_lower:
        return "Kino Flo"
        
    if "pipe" in header_lower:
        return "Pipe Lighting"
        
    if "pheon" in header_lower:
        return "Pheon Lux"
        
    if "aputure" in header_lower or "amaran" in header_lower:
        if "amaran" in url_lower or "amaran" in desc_lower:
            return "Amaran"
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

def classify_category(filename, description, brand=None):
    """
    Определяет категорию файла:
    - '01_Firmware' для прошивок.
    - '02_DMX_Charts' для DMX-карт (для Godox/Knowled руководства пользователя также считаются DMX-картами).
    - None для прочих PDF (руководства, рекламные листы), которые нужно отфильтровать.
    """
    fn_lower = filename.lower()
    desc_lower = description.lower()
    
    # Исключаем рекламные материалы, пресс-релизы, тендерные тексты и т.д.
    exclusions = [
        "press-release", "press_release", "pressrelease", 
        "whitepaper", "white-paper", 
        "tender-text", "tender_text", "tendertext", "ausschreibung",
        "brochure", "flyer", "leaflet", "folder",
        "price-list", "pricelist", "preisliste",
        "academy", "seminar", "workshop", "news"
    ]
    if fn_lower.endswith(".pdf") and any(ex in fn_lower or ex in desc_lower for ex in exclusions):
        return None

    is_dmx = "dmx" in fn_lower or "dmx" in desc_lower or "rdm" in fn_lower or "rdm" in desc_lower
    
    # Для Godox и Knowled руководства пользователя (PDF) содержат встроенные DMX-карты,
    # поэтому мы классифицируем их как 02_DMX_Charts, даже если в названии нет слова "dmx".
    is_godox_or_knowled = (brand in ["Godox", "Knowled"]) or ("godox" in fn_lower) or ("knowled" in fn_lower)
    
    if fn_lower.endswith(".pdf") or (fn_lower.endswith(".zip") and is_dmx):
        if is_dmx or is_godox_or_knowled:
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
            
            if ext not in [".zip", ".bin", ".pdf", ".hex", ".dfu", ".tar", ".rar", ".sfb", ".upg", ".exe", ".dmg"]:
                continue
                
            filename = clean_filename(url)
            brand = classify_brand(current_brand_header, url, description)
            category = classify_category(filename, description, brand)
            
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
            category = classify_category(filename, "", brand)
            
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
                            category = classify_category(clean_filename(file_url), name, brand_name)
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
    
    # Pattern 1: Original firmware style
    pattern_fw = re.compile(
        r'([^<>]+?)\s*(?:<span>([^<>]+)</span>)?\s*<a[^>]+href=["\']([^"\']+)["\'][^>]*class="download"', 
        re.IGNORECASE
    )
    # Pattern 2: Manuals style
    pattern_man = re.compile(
        r'<span>(?:<strong[^>]*>)?\s*([^<>]+?)\s*(?:</strong[^>]*>)?</span>\s*<a[^>]+href=["\']([^"\']+)["\'][^>]*class="download"', 
        re.IGNORECASE
    )
    
    for page_path in pages:
        url = urllib.parse.urljoin(base_url, page_path)
        try:
            response = requests.get(url, headers=headers, timeout=20)
            response.raise_for_status()
            
            page_results = []
            matches_fw = pattern_fw.findall(response.text)
            for title, version, href in matches_fw:
                title = title.strip()
                version = version.strip() if version else ""
                href = href.strip()
                if title:
                    page_results.append((title, version, href))
                    
            matches_man = pattern_man.findall(response.text)
            for title, href in matches_man:
                title = title.strip()
                href = href.strip()
                if not any(r[2] == href for r in page_results):
                    page_results.append((title, "", href))
            
            for title, version, href in page_results:
                if href.startswith("/"):
                    href = urllib.parse.urljoin(base_url, href)
                    
                if not href.startswith("http"):
                    continue
                    
                filename = clean_filename(href)
                _, ext = os.path.splitext(filename.lower())
                if ext not in [".zip", ".bin", ".pdf", ".hex", ".dfu", ".tar", ".rar"]:
                    continue
                    
                description = f"{title} {version}".strip()
                category = classify_category(filename, description, brand_name)
                
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

def resolve_canto_link(short_name):
    """
    Преобразует публичную ссылку Canto (short_name) в ID презентации.
    """
    headers = {"User-Agent": USER_AGENT}
    try:
        r = requests.get(f"https://arri.canto.de/rest/share/protected/{short_name}", headers=headers, timeout=15)
        if r.status_code == 200 and r.text.startswith("/v/"):
            return r.text[3:]
    except Exception:
        pass
    return None

def extract_canto_assets(presentation_id):
    """
    Рекурсивно обходит структуру Canto презентации и извлекает прямые ссылки на скачивание всех файлов.
    """
    headers = {"User-Agent": USER_AGENT}
    assets = []
    lib_url = f"https://arri.canto.de/rest/v/{presentation_id}/library"
    try:
        r = requests.get(lib_url, headers=headers, timeout=15)
        if r.status_code != 200:
            return assets
        lib_data = r.json()
        hits = lib_data.get("hits", {}).get("hit", [])
        
        queue = list(hits)
        visited = set()
        
        while queue:
            item = queue.pop(0)
            scheme = item.get("scheme")
            path = item.get("path")
            if not path or path in visited:
                continue
            visited.add(path)
            
            if scheme == "folder":
                folder_url = f"https://arri.canto.de/rest/v/{presentation_id}/search/folder/{path}"
                try:
                    fr = requests.get(folder_url, headers=headers, timeout=15)
                    if fr.status_code == 200:
                        fdata = fr.json()
                        queue.extend(fdata.get("hits", {}).get("hit", []))
                except Exception:
                    pass
            elif scheme == "album":
                album_url = f"https://arri.canto.de/rest/v/{presentation_id}/search/album/{path}"
                try:
                    ar = requests.get(album_url, headers=headers, timeout=15)
                    if ar.status_code == 200:
                        adata = ar.json()
                        queue.extend(adata.get("hits", {}).get("hit", []))
                except Exception:
                    pass
            elif scheme in ["document", "other", "image", "video", "audio"]:
                display_name = item.get("displayName") or f"{path}.bin"
                # Добавляем реальное имя файла в конец пути скачивания, т.к. Tomcat игнорирует этот суффикс
                dl_url = f"https://arri.canto.de/rest/v/{presentation_id}/binary/{scheme}/{path}/download/{display_name}"
                assets.append({
                    "url": dl_url,
                    "filename": display_name,
                    "description": display_name
                })
    except Exception:
        pass
    return assets

def scrape_arri_links():
    """
    Сканирует официальные страницы ARRI и Canto-порталы для поиска прошивок и DMX-карт.
    """
    headers = {"User-Agent": USER_AGENT}
    scraped = []
    
    fw_subpages = [
        "https://www.arri.com/en/technical-service/firmware/firmware-updates-for-lighting-products",
        "https://www.arri.com/en/lighting/apps-tools/software/lios",
        "https://www.arri.com/en/technical-service/firmware/firmware-updates-for-lighting-products/software-update-omnibar",
        "https://www.arri.com/en/technical-service/firmware/firmware-updates-for-lighting-products/l-series-firmware-2-5",
        "https://www.arri.com/en/technical-service/firmware/firmware-updates-for-lighting-products/firmware-for-l-series-plus-skypanel-classic"
    ]
    
    raw_urls = set()
    canto_keys = set()
    
    arri_blob_pattern = re.compile(r'/resource/blob/[a-zA-Z0-9_/.-]+', re.IGNORECASE)
    canto_pattern = re.compile(r'https?://arri\.canto\.de/b/([a-zA-Z0-9_-]+)', re.IGNORECASE)
    
    # 1. Сканирование страниц прошивок
    for page in fw_subpages:
        try:
            r = requests.get(page, headers=headers, timeout=20)
            if r.status_code == 200:
                blobs = arri_blob_pattern.findall(r.text)
                for b in blobs:
                    full_url = urllib.parse.urljoin("https://www.arri.com", b)
                    raw_urls.add((full_url, "ARRI Firmware"))
                cantos = canto_pattern.findall(r.text)
                for c in cantos:
                    canto_keys.add(c)
        except Exception:
            pass
            
    # 2. Сканирование результатов поиска DMX
    for page_num in range(3):
        search_url = f"https://www.arri.com/service/search/en/49664?pageNum={page_num}&query=DMX"
        try:
            r = requests.get(search_url, headers=headers, timeout=20)
            if r.status_code == 200:
                blobs = arri_blob_pattern.findall(r.text)
                for b in blobs:
                    full_url = urllib.parse.urljoin("https://www.arri.com", b)
                    raw_urls.add((full_url, "ARRI DMX Spec"))
                cantos = canto_pattern.findall(r.text)
                for c in cantos:
                    canto_keys.add(c)
        except Exception:
            pass
            
    # 3. Обход найденных Canto-порталов
    for short_name in canto_keys:
        pres_id = resolve_canto_link(short_name)
        if pres_id:
            canto_assets = extract_canto_assets(pres_id)
            for asset in canto_assets:
                raw_urls.add((asset["url"], asset["description"]))
                
    # 4. Классификация собранного
    for url, desc in raw_urls:
        filename = clean_filename(url)
        _, ext = os.path.splitext(filename.lower())
        if ext in [".zip", ".bin", ".pdf", ".hex", ".dfu", ".tar", ".rar"]:
            category = classify_category(filename, desc, "ARRI")
            if category:
                scraped.append({
                    "url": url,
                    "description": desc,
                    "brand": "ARRI",
                    "category": category
                })
                
    return scraped

class AsteraHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current_link = None
        self.current_attrs = None
        self.current_text = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            attrs_dict = dict(attrs)
            href = attrs_dict.get('href')
            if href:
                self.current_link = href
                self.current_attrs = attrs_dict
                self.current_text = []

    def handle_data(self, data):
        if self.current_link is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self.current_link is not None:
            text = "".join(self.current_text).strip()
            self.links.append((self.current_link, text, self.current_attrs))
            self.current_link = None
            self.current_attrs = None

def scrape_astera_links():
    """
    Сканирует страницу загрузок Astera для поиска DMX-карт и прошивок/софта.
    """
    url = "https://astera-led.com/downloads/"
    headers = {"User-Agent": USER_AGENT}
    scraped = []
    try:
        response = requests.get(url, headers=headers, timeout=25)
        response.raise_for_status()
        
        parser = AsteraHTMLParser()
        parser.feed(response.text)
        
        seen_urls = set()
        for href, text, attrs in parser.links:
            full_url = urllib.parse.urljoin("https://astera-led.com", href)
            if full_url in seen_urls:
                continue
                
            filename = clean_filename(full_url)
            fn_lower = filename.lower()
            text_lower = text.lower()
            url_lower = full_url.lower()
            
            # Получаем детальное описание из дата-атрибутов
            prod_title = attrs.get('data-download-product-title', '').strip() if attrs else ''
            doc_title = attrs.get('data-mn', '').strip() if attrs else ''
            desc = doc_title if doc_title else (prod_title if prod_title else text)
            if not desc:
                desc = f"Astera File ({filename})"
                
            # Проверяем DMX-карты
            is_dmx_keyword = any(k in url_lower or k in text_lower for k in ["dmx", "dmx_sheet", "dmx_table", "dmx_profiles"])
            if fn_lower.endswith(".pdf") and is_dmx_keyword:
                seen_urls.add(full_url)
                scraped.append({
                    "url": full_url,
                    "description": desc,
                    "brand": "Astera",
                    "category": "02_DMX_Charts"
                })
                continue
                
            # Проверяем прошивки / софт
            is_fw_ext = any(fn_lower.endswith(ext) for ext in [".zip", ".exe", ".dmg", ".bin"])
            is_fw_keyword = any(k in url_lower or k in text_lower for k in ["firmware", "update", "asteraapp", "app"])
            if is_fw_ext and is_fw_keyword:
                seen_urls.add(full_url)
                scraped.append({
                    "url": full_url,
                    "description": desc,
                    "brand": "Astera",
                    "category": "01_Firmware"
                })
    except Exception as e:
        print(f"    {RED}⚠️ Ошибка при сканировании Astera: {e}{RESET}")
    return scraped

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current_link = None
        self.current_text = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            attrs_dict = dict(attrs)
            href = attrs_dict.get('href')
            if href:
                self.current_link = href
                self.current_text = []

    def handle_data(self, data):
        if self.current_link is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self.current_link is not None:
            text = "".join(self.current_text).strip()
            self.links.append((self.current_link, text))
            self.current_link = None

def scrape_creamsource_links():
    """
    Сканирует базу знаний Creamsource для поиска DMX-карт, прошивок (.sfb, .upg) и софта (.exe, .dmg).
    """
    start_url = "https://knowledge.creamsource.com/"
    headers = {"User-Agent": USER_AGENT}
    scraped = []
    
    # Рекурсивный обход страниц
    urls_to_visit = [start_url]
    visited_urls = set()
    files_found = []
    max_pages = 60
    pages_crawled = 0
    
    try:
        while urls_to_visit and pages_crawled < max_pages:
            curr_url = urls_to_visit.pop(0)
            if curr_url in visited_urls:
                continue
                
            visited_urls.add(curr_url)
            pages_crawled += 1
            
            try:
                response = requests.get(curr_url, headers=headers, timeout=10)
                if response.status_code != 200:
                    continue
            except Exception:
                continue
                
            parser = LinkParser()
            parser.feed(response.text)
            
            for href, text in parser.links:
                full_url = urllib.parse.urljoin(curr_url, href)
                parsed = urllib.parse.urlparse(full_url)
                
                # Очищаем URL от параметров и фрагментов для проверки расширения
                url_clean = full_url.split("?")[0].split("#")[0]
                url_clean_lower = url_clean.lower()
                text_lower = text.lower()
                full_url_lower = full_url.lower()
                
                # Проверяем на прошивку / утилиту
                is_fw_ext = any(url_clean_lower.endswith(ext) for ext in [".sfb", ".upg", ".exe", ".dmg"])
                is_hubfs = "knowledge.creamsource.com/hubfs/" in full_url_lower
                if is_fw_ext and is_hubfs:
                    files_found.append((full_url, text, "01_Firmware"))
                    continue
                    
                # Проверяем на DMX-карту
                is_pdf = url_clean_lower.endswith(".pdf")
                is_dmx_kw = any(kw in url_clean_lower or kw in text_lower for kw in ["dmx", "dmx-tables", "dmx_specs", "dmx_profiles"])
                if is_pdf and is_dmx_kw:
                    files_found.append((full_url, text, "02_DMX_Charts"))
                    continue
                    
                # Добавляем в очередь для обхода
                if parsed.netloc == "knowledge.creamsource.com":
                    is_ignored = any(p in url_clean_lower for p in ["/login", "/tickets-view", "/kb-tickets/new", "#", "/_hcms/"])
                    is_static = any(url_clean_lower.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".css", ".js", ".svg", ".zip", ".pdf", ".sfb", ".upg", ".exe", ".dmg"])
                    
                    if not is_ignored and not is_static:
                        if full_url not in visited_urls and full_url not in urls_to_visit:
                            urls_to_visit.append(full_url)
                            
        # Преобразуем найденные файлы в стандартные словари скрапинга
        seen_urls = set()
        for url, text, category in files_found:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            
            filename = clean_filename(url)
            desc = text.strip() if text.strip() else f"Creamsource File ({filename})"
            desc_lower = desc.lower()
            fn_lower = filename.lower()
            if not any(k in desc_lower for k in ["vortex", "spacex", "sky", "micro"]):
                for k in ["vortex", "spacex", "sky", "micro"]:
                    if k in fn_lower:
                        desc = f"{k.capitalize()} {desc}"
                        break
            
            scraped.append({
                "url": url,
                "description": desc,
                "brand": "Creamsource",
                "category": category
            })
            
    except Exception as e:
        print(f"    {RED}⚠️ Ошибка при сканировании Creamsource: {e}{RESET}")
        
    return scraped

def scrape_gvm_links():
    """
    Сканирует страницу мануалов GVM и собирает ссылки на DMX-карт.
    """
    url = "https://gvmled.com/product-manuals/"
    headers = {"User-Agent": USER_AGENT}
    scraped = []
    try:
        response = requests.get(url, headers=headers, timeout=25)
        response.raise_for_status()
        
        parser = LinkParser()
        parser.feed(response.text)
        
        seen_urls = set()
        for href, text in parser.links:
            full_url = urllib.parse.urljoin(url, href)
            parsed_url = urllib.parse.urlparse(full_url)
            
            # Очищаем URL от параметров и фрагментов
            url_clean = full_url.split("?")[0].split("#")[0]
            url_clean_lower = url_clean.lower()
            text_lower = text.lower()
            
            # Ссылки должны вести на их медиа-хранилище и быть PDF
            is_pdf = url_clean_lower.endswith(".pdf")
            is_uploads = "gvmled.com/wp-content/uploads/" in url_clean_lower
            
            if is_pdf and is_uploads:
                keywords = ["dmx", "dmx channel", "dmx_channel", "dmx table", "dmx-pro"]
                is_dmx = any(kw in url_clean_lower or kw in text_lower for kw in keywords)
                
                if is_dmx:
                    if full_url in seen_urls:
                        continue
                    seen_urls.add(full_url)
                    
                    filename = clean_filename(full_url)
                    desc = text.strip() if text.strip() else f"GVM File ({filename})"
                    
                    # Если в описании нет префикса GVM, но он есть в имени файла - добавляем!
                    desc_lower = desc.lower()
                    fn_lower = filename.lower()
                    if "gvm-" not in desc_lower and "gvm-" in fn_lower:
                        match = re.search(r'(gvm-[a-z0-9\-]+)', fn_lower)
                        if match:
                            desc = f"{match.group(1).upper()} {desc}"
                            
                    scraped.append({
                        "url": full_url,
                        "description": desc,
                        "brand": "GVM",
                        "category": "02_DMX_Charts"
                    })
    except Exception as e:
        print(f"    {RED}⚠️ Ошибка при сканировании GVM: {e}{RESET}")
    return scraped

def scrape_litegear_links():
    """
    Сканирует ресурсы LiteGear и собирает ссылки на прошивки и DMX-карты.
    """
    headers = {"User-Agent": USER_AGENT}
    scraped = []
    
    # 1. Сканируем Spectrum OS downloads
    url_os = "https://www.litegear.com/spectrum-os/downloads/"
    try:
        response = requests.get(url_os, headers=headers, timeout=20)
        if response.status_code == 200:
            parser = LinkParser()
            parser.feed(response.text)
            for href, text in parser.links:
                if not href:
                    continue
                full_url = urllib.parse.urljoin(url_os, href)
                url_clean = full_url.split("?")[0].split("#")[0]
                url_clean_lower = url_clean.lower()
                text_lower = text.lower()
                
                # Ищем прошивки
                is_fw_ext = any(url_clean_lower.endswith(ext) for ext in [".zip", ".bin", ".exe", ".dmg"])
                is_fw_kw = any(k in url_clean_lower or k in text_lower for k in ["spectrum", "os", "update", "updater", "firmware"])
                if is_fw_ext and is_fw_kw:
                    filename = clean_filename(full_url)
                    desc = text.strip() if text.strip() else f"LiteGear OS File ({filename})"
                    
                    # Обогащаем описание продуктовыми ключевыми словами
                    desc_lower = desc.lower()
                    fn_lower = filename.lower()
                    product_keywords = ["litedimmer", "litemat", "litetile", "literibbon", "litestix", "litepower", "auroris", "spectrum"]
                    if not any(k in desc_lower for k in product_keywords):
                        for k in product_keywords:
                            if k in fn_lower:
                                desc = f"{k.capitalize()} {desc}"
                                break
                                
                    scraped.append({
                        "url": full_url,
                        "description": desc,
                        "brand": "LiteGear",
                        "category": "01_Firmware"
                    })
                    continue
                    
                # Ищем DMX-карты
                is_pdf = url_clean_lower.endswith(".pdf")
                is_dmx_kw = any(k in url_clean_lower or k in text_lower for k in ["dmx", "dmx profiles", "rdm-dmx", "dmx user guide", "protocol"])
                if is_pdf and is_dmx_kw:
                    filename = clean_filename(full_url)
                    desc = text.strip() if text.strip() else f"LiteGear DMX File ({filename})"
                    
                    # Обогащаем описание
                    desc_lower = desc.lower()
                    fn_lower = filename.lower()
                    product_keywords = ["litedimmer", "litemat", "litetile", "literibbon", "litestix", "litepower", "auroris", "spectrum"]
                    if not any(k in desc_lower for k in product_keywords):
                        for k in product_keywords:
                            if k in fn_lower:
                                desc = f"{k.capitalize()} {desc}"
                                break
                                
                    scraped.append({
                        "url": full_url,
                        "description": desc,
                        "brand": "LiteGear",
                        "category": "02_DMX_Charts"
                    })
    except Exception as e:
        print(f"    {RED}⚠️ Ошибка при сканировании Spectrum OS LiteGear: {e}{RESET}")

    # 2. Сканируем Document Center (WPFD ссылки)
    url_doc = "https://www.litegear.com/document-center/"
    try:
        response = requests.get(url_doc, headers=headers, timeout=20)
        if response.status_code == 200:
            parser = LinkParser()
            parser.feed(response.text)
            seen_ids = set()
            for attrs, text in parser.links_with_attrs() if hasattr(parser, 'links_with_attrs') else []:
                # Если у LinkParser нет links_with_attrs, соберем с помощью regex
                pass
                
            # Альтернативный сбор WPFD ссылок регуляркой (более надежно и просто)
            wpfd_pattern = re.compile(
                r'href=["\']#["\'][^>]*data-category_id=["\'](\d+)["\'][^>]*data-id=["\'](\d+)["\'][^>]*title=["\']([^"\']+)["\']',
                re.IGNORECASE
            )
            wpfd_matches = wpfd_pattern.findall(response.text)
            
            # Также проверим обратный порядок атрибутов data-id и data-category_id
            wpfd_pattern2 = re.compile(
                r'href=["\']#["\'][^>]*data-id=["\'](\d+)["\'][^>]*data-category_id=["\'](\d+)["\'][^>]*title=["\']([^"\']+)["\']',
                re.IGNORECASE
            )
            wpfd_matches2 = wpfd_pattern2.findall(response.text)
            
            all_wpfd = []
            for cat_id, file_id, title in wpfd_matches:
                all_wpfd.append((file_id, cat_id, title))
            for file_id, cat_id, title in wpfd_matches2:
                all_wpfd.append((file_id, cat_id, title))
                
            seen_urls = set()
            for file_id, cat_id, title in all_wpfd:
                title_lower = title.lower()
                is_dmx_kw = any(k in title_lower for k in ["dmx", "dmx profiles", "rdm-dmx", "dmx user guide", "protocol"])
                if is_dmx_kw:
                    dl_url = f"https://www.litegear.com/?wpfd_action=wpfd_download_file&wpfd_file_id={file_id}&wpfd_category_id={cat_id}"
                    if dl_url in seen_urls:
                        continue
                    seen_urls.add(dl_url)
                    scraped.append({
                        "url": dl_url,
                        "description": title.strip(),
                        "brand": "LiteGear",
                        "category": "02_DMX_Charts"
                    })
    except Exception as e:
        print(f"    {RED}⚠️ Ошибка при сканировании Document Center LiteGear: {e}{RESET}")
        
    return scraped

def scrape_lightstar_links():
    """
    Сканирует страницу поддержки Lightstar и собирает прошивки и DMX-карты.
    """
    url = "https://www.lightstarusa.com/support/"
    headers = {"User-Agent": USER_AGENT}
    scraped = []
    try:
        response = requests.get(url, headers=headers, timeout=25)
        if response.status_code == 200:
            parser = LinkParser()
            parser.feed(response.text)
            for href, text in parser.links:
                if not href:
                    continue
                full_url = urllib.parse.urljoin(url, href)
                url_clean = full_url.split("?")[0].split("#")[0]
                url_clean_lower = url_clean.lower()
                text_lower = text.lower()
                
                # Ищем прошивки
                is_fw_ext = any(url_clean_lower.endswith(ext) for ext in [".zip", ".bin", ".hex", ".exe", ".dmg"])
                is_fw_kw = any(k in url_clean_lower or k in text_lower for k in ["firmware", "update", "software", "luxed", "controller"])
                if is_fw_ext and is_fw_kw:
                    filename = clean_filename(full_url)
                    desc = text.strip() if text.strip() else f"Lightstar FW File ({filename})"
                    
                    # Обогащаем описание из имени файла, если оно generic
                    if desc.lower() in ["download", "download file", "download pdf"]:
                        match = re.search(r'(luxed[-_ ]*p?[-_ ]*\d+)', filename, re.IGNORECASE)
                        if match:
                            desc = f"Lightstar {match.group(1).upper()} Firmware"
                        else:
                            desc = f"Lightstar Firmware ({filename})"
                            
                    scraped.append({
                        "url": full_url,
                        "description": desc,
                        "brand": "Lightstar",
                        "category": "01_Firmware"
                    })
                    continue
                    
                # Ищем DMX-карты
                is_pdf = url_clean_lower.endswith(".pdf")
                is_xlsx = url_clean_lower.endswith(".xlsx") or url_clean_lower.endswith(".xls")
                is_dmx_kw = any(k in url_clean_lower or k in text_lower for k in ["dmx"])
                if (is_pdf or is_xlsx) and is_dmx_kw:
                    filename = clean_filename(full_url)
                    desc = text.strip() if text.strip() else f"Lightstar DMX File ({filename})"
                    
                    if desc.lower() in ["download", "download file", "download pdf"]:
                        desc = f"Lightstar DMX Chart ({filename})"
                        
                    scraped.append({
                        "url": full_url,
                        "description": desc,
                        "brand": "Lightstar",
                        "category": "02_DMX_Charts"
                    })
    except Exception as e:
        print(f"    {RED}⚠️ Ошибка при сканировании Lightstar: {e}{RESET}")
    return scraped

def scrape_litepanels_links():
    """
    Сканирует разделы Litepanels и собирает ссылки на прошивки и DMX.
    """
    scraped = []
    # Прошивки
    fw_url = "https://www.litepanels.com/en/product-support/firmware-updates/download/"
    # DMX
    dmx_url = "https://www.litepanels.com/en/product-support/download/"
    
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.litepanels.com/"
    }
    
    # 1. Скрапинг прошивок
    try:
        r = requests.get(fw_url, headers=headers, timeout=20)
        if r.status_code == 403:
            print(f"    {YELLOW}Litepanels (FW): Доступ временно ограничен защитой Cloudflare (403). Ссылка будет получена из резервных.{RESET}")
        elif r.status_code == 200:
            parser = LinkParser()
            parser.feed(r.text)
            for href, text in parser.links:
                full_url = urllib.parse.urljoin(fw_url, href)
                url_clean = full_url.split("?")[0].split("#")[0]
                url_clean_lower = url_clean.lower()
                text_lower = text.lower()
                
                if any(url_clean_lower.endswith(ext) for ext in [".hex", ".zip"]):
                    if any(kw in url_clean_lower or kw in text_lower for kw in ["firmware", "gemini", "astra"]):
                        desc = text.strip() if text.strip() else f"Litepanels FW ({clean_filename(full_url)})"
                        scraped.append({
                            "url": full_url,
                            "description": desc,
                            "brand": "Litepanels",
                            "category": "01_Firmware"
                        })
    except Exception as e:
        print(f"    {RED}⚠️ Ошибка скрапинга Litepanels FW: {e}{RESET}")

    # 2. Скрапинг DMX-карт
    try:
        r = requests.get(dmx_url, headers=headers, timeout=20)
        if r.status_code == 403:
            print(f"    {YELLOW}Litepanels (DMX): Доступ временно ограничен защитой Cloudflare (403). Ссылка будет получена из резервных.{RESET}")
        elif r.status_code == 200:
            parser = LinkParser()
            parser.feed(r.text)
            for href, text in parser.links:
                full_url = urllib.parse.urljoin(dmx_url, href)
                url_clean = full_url.split("?")[0].split("#")[0]
                url_clean_lower = url_clean.lower()
                text_lower = text.lower()
                
                if url_clean_lower.endswith(".pdf"):
                    if any(kw in url_clean_lower or kw in text_lower for kw in ["dmx", "rdm chart", "dmx function chart"]):
                        desc = text.strip() if text.strip() else f"Litepanels DMX ({clean_filename(full_url)})"
                        scraped.append({
                            "url": full_url,
                            "description": desc,
                            "brand": "Litepanels",
                            "category": "02_DMX_Charts"
                        })
    except Exception as e:
        print(f"    {RED}⚠️ Ошибка скрапинга Litepanels DMX: {e}{RESET}")
        
    return scraped

def scrape_quasar_links():
    """
    Сканирует страницу Quasar Science.
    """
    url = "https://www.quasarscience.com/pages/firmware"
    headers = {"User-Agent": USER_AGENT}
    scraped = []
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code == 200:
            parser = LinkParser()
            parser.feed(r.text)
            for href, text in parser.links:
                full_url = urllib.parse.urljoin(url, href)
                url_clean = full_url.split("?")[0].split("#")[0]
                url_clean_lower = url_clean.lower()
                text_lower = text.lower()
                
                # Прошивки
                if any(url_clean_lower.endswith(ext) for ext in [".dmg", ".exe", ".bin", ".hex", ".zip"]):
                    if any(kw in url_clean_lower or kw in text_lower for kw in ["rainbow 2", "double rainbow", "q-lion", "utility", "firmware", "qs_pc_fw", "wifi"]):
                        desc = text.strip() if text.strip() else f"Quasar Science FW ({clean_filename(full_url)})"
                        scraped.append({
                            "url": full_url,
                            "description": desc,
                            "brand": "Quasar Science",
                            "category": "01_Firmware"
                        })
                        continue
                        
                # DMX
                if url_clean_lower.endswith(".pdf"):
                    if any(kw in url_clean_lower or kw in text_lower for kw in ["dmx chart", "dmx_profiles", "table", "dmx"]):
                        desc = text.strip() if text.strip() else f"Quasar Science DMX ({clean_filename(full_url)})"
                        scraped.append({
                            "url": full_url,
                            "description": desc,
                            "brand": "Quasar Science",
                            "category": "02_DMX_Charts"
                        })
    except Exception as e:
        print(f"    {RED}⚠️ Ошибка скрапинга Quasar Science: {e}{RESET}")
    return scraped

def scrape_kinoflo_links():
    """
    Сканирует страницы Kino Flo.
    """
    urls = [
        "https://kinoflo.com/downloads/",
        "https://kinoflo.com/manuals-archive/",
        "https://kinoflo.com/true-match/"
    ]
    headers = {"User-Agent": USER_AGENT}
    scraped = []
    seen_urls = set()
    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=20)
            if r.status_code == 200:
                parser = LinkParser()
                parser.feed(r.text)
                for href, text in parser.links:
                    full_url = urllib.parse.urljoin(url, href)
                    url_clean = full_url.split("?")[0].split("#")[0]
                    url_clean_lower = url_clean.lower()
                    text_lower = text.lower()
                    
                    if full_url in seen_urls:
                        continue
                    
                    # Прошивки
                    if any(url_clean_lower.endswith(ext) for ext in [".zip", ".exe", ".dmg", ".bin", ".hex", ".dfs"]):
                        if any(kw in url_clean_lower or kw in text_lower for kw in ["firmware", "update", "software", "flash programmer", "rfp", "truematch"]):
                            seen_urls.add(full_url)
                            desc = text.strip() if text.strip() else f"Kino Flo FW ({clean_filename(full_url)})"
                            scraped.append({
                                "url": full_url,
                                "description": desc,
                                "brand": "Kino Flo",
                                "category": "01_Firmware"
                            })
                            continue
                            
                    # DMX
                    if url_clean_lower.endswith(".pdf"):
                        if any(kw in url_clean_lower or kw in text_lower for kw in ["dmx personalities", "dmx chart", "dmx"]):
                            seen_urls.add(full_url)
                            desc = text.strip() if text.strip() else f"Kino Flo DMX ({clean_filename(full_url)})"
                            scraped.append({
                                "url": full_url,
                                "description": desc,
                                "brand": "Kino Flo",
                                "category": "02_DMX_Charts"
                            })
        except Exception as e:
            print(f"    {RED}⚠️ Ошибка скрапинга Kino Flo ({url}): {e}{RESET}")
    return scraped

def scrape_pipelighting_links():
    """
    Сканирует страницу Pipe Lighting.
    """
    url = "https://www.pipelighting.com/downloads"
    headers = {"User-Agent": USER_AGENT}
    scraped = []
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code == 200:
            parser = LinkParser()
            parser.feed(r.text)
            for href, text in parser.links:
                full_url = urllib.parse.urljoin(url, href)
                url_clean = full_url.split("?")[0].split("#")[0]
                url_clean_lower = url_clean.lower()
                text_lower = text.lower()
                
                # Прошивки без расширения в ColorPipe
                # Ищем по ключевым словам и пути /s/
                is_s_path = "/s/" in url_clean_lower
                is_fw_kw = any(kw in url_clean_lower or kw in text_lower for kw in ["pipecolor_", "pc_"])
                has_ext = any(url_clean_lower.endswith(ext) for ext in [".pdf", ".zip", ".exe", ".dmg", ".bin", ".hex", ".xml"])
                
                if is_s_path and is_fw_kw and not has_ext:
                    desc = text.strip() if text.strip() else f"ColorPipe Firmware ({clean_filename(full_url)})"
                    if "colorpipe" not in desc.lower() and "pc_" not in desc.lower() and "pipecolor" not in desc.lower():
                        desc = f"ColorPipe {desc}"
                    scraped.append({
                        "url": full_url,
                        "description": desc,
                        "brand": "Pipe Lighting",
                        "category": "01_Firmware"
                    })
                    continue
                    
                # DMX
                if url_clean_lower.endswith(".pdf"):
                    desc = text.strip() if text.strip() else f"Pipe Lighting Document ({clean_filename(full_url)})"
                    scraped.append({
                        "url": full_url,
                        "description": desc,
                        "brand": "Pipe Lighting",
                        "category": "02_DMX_Charts"
                    })
    except Exception as e:
        print(f"    {RED}⚠️ Ошибка скрапинга Pipe Lighting: {e}{RESET}")
    return scraped

def scrape_pheonlux_links():
    """
    Сканирует Pheon Lux.
    """
    url = "https://www.pheonlux.com/download_center/"
    headers = {"User-Agent": USER_AGENT}
    scraped = []
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code == 200:
            parser = LinkParser()
            parser.feed(r.text)
            for href, text in parser.links:
                full_url = urllib.parse.urljoin(url, href)
                url_clean = full_url.split("?")[0].split("#")[0]
                url_clean_lower = url_clean.lower()
                text_lower = text.lower()
                
                if url_clean_lower.endswith(".pdf"):
                    if any(kw in url_clean_lower or kw in text_lower for kw in ["dmx profiles", "user manual", "dmx_sheet", "dmx", "brochure", "manual"]):
                        desc = text.strip() if text.strip() else f"Pheon Lux Document ({clean_filename(full_url)})"
                        scraped.append({
                            "url": full_url,
                            "description": desc,
                            "brand": "Pheon Lux",
                            "category": "02_DMX_Charts"
                        })
    except Exception as e:
        print(f"    {RED}⚠️ Ошибка скрапинга Pheon Lux: {e}{RESET}")
    return scraped

def download_file(url, local_path, attempts=3):
    """
    Скачивает файл по ссылке с отображением красивого прогресс-бара.
    С ретраями и проверкой целостности (downloaded == content-length).
    """
    import time
    temp_path = local_path + ".tmp"
    headers = {"User-Agent": USER_AGENT}

    for attempt in range(1, attempts + 1):
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

            # Проверка целостности: если знаем размер — файл должен совпадать
            if total_size > 0 and downloaded != total_size:
                raise IOError(f"обрыв: скачано {downloaded}/{total_size} байт")

            if os.path.exists(local_path):
                os.remove(local_path)
            os.replace(temp_path, local_path)  # атомично вместо rename
            sys.stdout.write("\r" + " " * 80 + "\r")
            sys.stdout.flush()
            return True
        except (requests.RequestException, IOError) as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if attempt < attempts:
                wait = 2 ** attempt
                sys.stdout.write("\r" + " " * 80 + "\r")
                print(f"    {YELLOW}⚠️ Попытка {attempt}/{attempts} не удалась: {e}. Повтор через {wait}с...{RESET}")
                time.sleep(wait)
                continue
            sys.stdout.write("\r" + " " * 80 + "\r")
            sys.stdout.flush()
            print(f"    {RED}❌ Ошибка при скачивании {url} после {attempts} попыток: {e}{RESET}")
            return False

def sync_file_to_usb(local_path, usb_path):
    """
    Копирует файл на флешку, если он отсутствует или отличается по размеру/времени изменения.
    Атомарно: пишет в .part, затем os.replace — не оставляет обрезанный файл при обрыве.
    Возвращает True если скопировано, False если пропущено или ошибка.
    """
    try:
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
            tmp_path = usb_path + ".part"
            shutil.copy2(local_path, tmp_path)
            os.replace(tmp_path, usb_path)   # не оставляем недописанный файл
            return True
        return False
    except OSError as e:
        print(f"   {RED}⚠️ USB: не удалось скопировать ({e}). Флешка отключена?{RESET}")
        return False

def get_clean_fallback_model(raw_filename, brand):
    """
    Извлекает чистое имя модели из имени файла, если нет описания.
    """
    base = os.path.splitext(raw_filename)[0]
    model, _ = clean_model_and_version(base, brand)
    if not model:
        model = base.upper()
        model = re.sub(rf'\b{brand.upper()}\b', '', model).strip()
        model = re.sub(r'[\s\-_]+$', '', model).strip()
    return model

def get_new_filename(raw_fn, metadata):
    """
    Генерирует новое имя файла на основе метаданных.
    """
    desc = metadata.get("description", "")
    brand = metadata.get("brand", "")
    category = metadata.get("category", "01_Firmware")
    _, ext = os.path.splitext(raw_fn)
    if not ext or '?' in ext:
        url = metadata.get("url", "")
        parsed_url = urllib.parse.urlparse(url)
        _, url_ext = os.path.splitext(parsed_url.path)
        if url_ext:
            ext = url_ext
        else:
            if brand == "Pipe Lighting" and category == "01_Firmware":
                ext = ""
            else:
                ext = ".pdf" if category == "02_DMX_Charts" else ".zip"
    
    model, version = clean_model_and_version(desc, brand)
    
    # Если не удалось вытащить модель, используем очищенное оригинальное имя
    if not model:
        model = get_clean_fallback_model(raw_fn, brand)
        
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

def _as_escape(text):
    """Экранирует строку для безопасной вставки в AppleScript."""
    return text.replace("\\", "\\\\").replace('"', '\\"')

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
        lines.append(f"• {_as_escape(brand)}:")
        for d in descs[:3]:
            lines.append(f"  - {_as_escape(d)}")
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



def main():
    import time
    start_time = time.time()
    
    # Проверяем, пуста ли папка Downloads
    is_empty_run = True
    if os.path.exists(LOCAL_DOWNLOADS_ROOT):
        for root, _, files in os.walk(LOCAL_DOWNLOADS_ROOT):
            for file in files:
                if not file.startswith('.') and file != "metadata.json":
                    is_empty_run = False
                    break
            if not is_empty_run:
                break
                
    global BLACKLIST, RULES
    BLACKLIST = load_blacklist()
    RULES = load_rules()
    
    print(f"\n{BOLD}{CYAN}================================================================{RESET}")
    print(f"{BOLD}{CYAN}⚡  FIXTURE_ROM | Автоматическая синхронизация прошивок и DMX  ⚡{RESET}")
    print(f"{BOLD}{CYAN}================================================================{RESET}\n")
    
    # 1. Чтение links.md
    print(f"🔍 Чтение файла ресурсов: {BLUE}{LINKS_FILE}{RESET}...")
    manual_items = parse_links_file(LINKS_FILE)
    print(f"✅ Из links.md успешно получено ссылок: {GREEN}{len(manual_items)}{RESET}\n")
    
    # Загружаем существующие метаданные для сохранения ручной структуры папок пользователя
    raw_db = {}
    existing_db = {}
    db_path = os.path.join(LOCAL_DOWNLOADS_ROOT, "metadata.json")
    if os.path.exists(db_path):
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                raw_db = json.load(f)
                existing_db = {normalize_key(k): v for k, v in raw_db.items()}
        except Exception:
            pass
    
    # 2. Загрузка конфигурации и сканирование сайтов
    config = load_config()
    print(f"🌐 {BOLD}Сканирование сайтов производителей (поиск моделей)...{RESET}")
    
    enabled_brands = config.get("enabled_brands", {})
    
    # Aputure & Amaran
    aputure_items = []
    run_aputure = enabled_brands.get("Aputure", True) or enabled_brands.get("Amaran", True)
    if run_aputure:
        sys.stdout.write("    - Сканирование Aputure / Amaran...")
        sys.stdout.flush()
        aputure_items = scrape_aputure_links()
        print(f"\r    - Aputure / Amaran: найдено {GREEN}{len(aputure_items)}{RESET} файлов.")
    else:
        print("    - Сканирование Aputure / Amaran: пропущено (отключено в настройках).")
        
    # Nanlite
    nanlite_items = []
    if enabled_brands.get("Nanlite", True):
        sys.stdout.write("    - Сканирование Nanlite...")
        sys.stdout.flush()
        nanlite_items = scrape_nanlink_api("nanlite", "Nanlite")
        print(f"\r    - Nanlite: найдено {GREEN}{len(nanlite_items)}{RESET} файлов.")
    else:
        print("    - Сканирование Nanlite: пропущено (отключено в настройках).")
        
    # Nanlux
    nanlux_items = []
    if enabled_brands.get("Nanlux", True):
        sys.stdout.write("    - Сканирование Nanlux...")
        sys.stdout.flush()
        nanlux_items = scrape_nanlink_api("nanlux", "Nanlux")
        print(f"\r    - Nanlux: найдено {GREEN}{len(nanlux_items)}{RESET} файлов.")
    else:
        print("    - Сканирование Nanlux: пропущено (отключено в настройках).")
        
    # Godox
    godox_items = []
    if enabled_brands.get("Godox", True):
        sys.stdout.write("    - Сканирование Godox...")
        sys.stdout.flush()
        godox_pages = [
            "/firmware-continuous-light/",
            "/firmware-continuous-light_2/",
            "/firmware-continuous-light_3/",
            "/firmware-control-system/",
            "/firmware-launcher-installers/",
            "/user-guides-continuous-light/",
            "/user-guides-continuous-light_2/",
            "/user-guides-continuous-light_3/",
            "/user-guides-control-system/"
        ]
        godox_items = scrape_godox_style_pages("https://www.godox.com", godox_pages, "Godox")
        print(f"\r    - Godox: найдено {GREEN}{len(godox_items)}{RESET} файлов.")
    else:
        print("    - Сканирование Godox: пропущено (отключено в настройках).")
        
    # Knowled
    knowled_items = []
    if enabled_brands.get("Knowled", True):
        sys.stdout.write("    - Сканирование Knowled...")
        sys.stdout.flush()
        knowled_pages = [
            "/firmware-knowled/",
            "/firmware-knowled_2/",
            "/firmware-knowled_3/",
            "/firmware-knowled_4/",
            "/firmware-knowled_5/",
            "/user-guides-knowled/",
            "/user-guides-knowled_2/",
            "/user-guides-knowled_3/",
            "/user-guides-knowled_4/",
            "/user-guides-knowled_5/"
        ]
        knowled_items = scrape_godox_style_pages("https://www.knowled.com", knowled_pages, "Knowled")
        print(f"\r    - Knowled: найдено {GREEN}{len(knowled_items)}{RESET} файлов.")
    else:
        print("    - Сканирование Knowled: пропущено (отключено в настройках).")
        
    # ARRI
    arri_items = []
    if enabled_brands.get("ARRI", True):
        sys.stdout.write("    - Сканирование ARRI...")
        sys.stdout.flush()
        arri_items = scrape_arri_links()
        print(f"\r    - ARRI: найдено {GREEN}{len(arri_items)}{RESET} файлов.")
    else:
        print("    - Сканирование ARRI: пропущено (отключено в настройках).")
        
    # Astera
    astera_items = []
    if enabled_brands.get("Astera", True):
        sys.stdout.write("    - Сканирование Astera...")
        sys.stdout.flush()
        astera_items = scrape_astera_links()
        print(f"\r    - Astera: найдено {GREEN}{len(astera_items)}{RESET} файлов.")
    else:
        print("    - Сканирование Astera: пропущено (отключено в настройках).")
        
    # Creamsource
    creamsource_items = []
    if enabled_brands.get("Creamsource", True):
        sys.stdout.write("    - Сканирование Creamsource...")
        sys.stdout.flush()
        creamsource_items = scrape_creamsource_links()
        print(f"\r    - Creamsource: найдено {GREEN}{len(creamsource_items)}{RESET} файлов.")
    else:
        print("    - Сканирование Creamsource: пропущено (отключено в настройках).")
        
    # GVM
    gvm_items = []
    if enabled_brands.get("GVM", True):
        sys.stdout.write("    - Сканирование GVM...")
        sys.stdout.flush()
        gvm_items = scrape_gvm_links()
        print(f"\r    - GVM: найдено {GREEN}{len(gvm_items)}{RESET} DMX-карт.")
    else:
        print("    - Сканирование GVM: пропущено (отключено в настройках).")
        
    # LiteGear
    litegear_items = []
    if enabled_brands.get("LiteGear", True):
        sys.stdout.write("    - Сканирование LiteGear...")
        sys.stdout.flush()
        litegear_items = scrape_litegear_links()
        print(f"\r    - LiteGear: найдено {GREEN}{len(litegear_items)}{RESET} файлов.")
    else:
        print("    - Сканирование LiteGear: пропущено (отключено в настройках).")
        
    # Lightstar
    lightstar_items = []
    if enabled_brands.get("Lightstar", True):
        sys.stdout.write("    - Сканирование Lightstar...")
        sys.stdout.flush()
        lightstar_items = scrape_lightstar_links()
        print(f"\r    - Lightstar: найдено {GREEN}{len(lightstar_items)}{RESET} файлов.")
    else:
        print("    - Сканирование Lightstar: пропущено (отключено в настройках).")
        
    # Litepanels
    litepanels_items = []
    if enabled_brands.get("Litepanels", True):
        sys.stdout.write("    - Сканирование Litepanels...")
        sys.stdout.flush()
        litepanels_items = scrape_litepanels_links()
        print(f"\r    - Litepanels: найдено {GREEN}{len(litepanels_items)}{RESET} файлов.")
    else:
        print("    - Сканирование Litepanels: пропущено (отключено в настройках).")

    # Quasar Science
    quasar_items = []
    if enabled_brands.get("Quasar Science", True):
        sys.stdout.write("    - Сканирование Quasar Science...")
        sys.stdout.flush()
        quasar_items = scrape_quasar_links()
        print(f"\r    - Quasar Science: найдено {GREEN}{len(quasar_items)}{RESET} файлов.")
    else:
        print("    - Сканирование Quasar Science: пропущено (отключено в настройках).")

    # Kino Flo
    kinoflo_items = []
    if enabled_brands.get("Kino Flo", True):
        sys.stdout.write("    - Сканирование Kino Flo...")
        sys.stdout.flush()
        kinoflo_items = scrape_kinoflo_links()
        print(f"\r    - Kino Flo: найдено {GREEN}{len(kinoflo_items)}{RESET} файлов.")
    else:
        print("    - Сканирование Kino Flo: пропущено (отключено в настройках).")

    # Pipe Lighting
    pipelighting_items = []
    if enabled_brands.get("Pipe Lighting", True):
        sys.stdout.write("    - Сканирование Pipe Lighting...")
        sys.stdout.flush()
        pipelighting_items = scrape_pipelighting_links()
        print(f"\r    - Pipe Lighting: найдено {GREEN}{len(pipelighting_items)}{RESET} файлов.")
    else:
        print("    - Сканирование Pipe Lighting: пропущено (отключено в настройках).")

    # Pheon Lux
    pheonlux_items = []
    if enabled_brands.get("Pheon Lux", True):
        sys.stdout.write("    - Сканирование Pheon Lux...")
        sys.stdout.flush()
        pheonlux_items = scrape_pheonlux_links()
        print(f"\r    - Pheon Lux: найдено {GREEN}{len(pheonlux_items)}{RESET} файлов.")
    else:
        print("    - Сканирование Pheon Lux: пропущено (отключено в настройках).")
        
    # Слияние всех списков с исключением дубликатов по URL и фильтрацией пустых категорий
    all_scraped = (aputure_items + nanlite_items + nanlux_items + 
                   godox_items + knowled_items + arri_items + astera_items + 
                   creamsource_items + gvm_items + litegear_items + lightstar_items + 
                   litepanels_items + quasar_items + kinoflo_items + pipelighting_items + 
                   pheonlux_items)
    
    seen_urls = {}
    for item in manual_items:
        if item.get("category"):
            seen_urls[item["url"]] = item
    for item in all_scraped:
        url = item["url"]
        if url not in seen_urls and item.get("category"):
            seen_urls[url] = item
            
    raw_final_items = list(seen_urls.values())
    
    # Фильтрация по категориям, брендам и моделям
    filtered_items = []
    enabled_categories = config.get("enabled_categories", {"firmware": True, "dmx": True})
    enabled_models = config.get("enabled_models", {})
    seen_models = {}  # brand -> set моделей, реально попавших в фильтр

    for item in raw_final_items:
        brand = item["brand"]
        category = item["category"]
        url = item["url"]
        desc = item["description"]

        # 1. Фильтр брендов
        if not enabled_brands.get(brand, True):
            continue

        # 2. Фильтр категорий
        if category == "01_Firmware" and not enabled_categories.get("firmware", True):
            continue
        if category == "02_DMX_Charts" and not enabled_categories.get("dmx", True):
            continue

        # 3. Фильтр моделей
        raw_filename = clean_filename(url)
        model, version = clean_model_and_version(desc, brand)
        if not model:
            model = get_clean_fallback_model(raw_filename, brand)

        brand_models = enabled_models.get(brand, [])
        if brand_models:
            if model not in brand_models:
                continue
            seen_models.setdefault(brand, set()).add(model)

        filtered_items.append(item)

    # Предупреждение: фильтр моделей не совпал ни с чем
    for brand, models in enabled_models.items():
        if models and not any(m in seen_models.get(brand, set()) for m in models):
            print(f"{YELLOW}⚠️ Для бренда {brand} ни одна сохранённая модель не совпала "
                  f"с найденными — проверьте фильтр в настройках.{RESET}")

    final_items = filtered_items
    link_checking_time = time.time() - start_time
    download_start_time = time.time()
    
    print(f"\n{GREEN}✅ Сканирование завершено!{RESET} Итого уникальных файлов для синхронизации (с учетом фильтров): {BOLD}{len(final_items)}{RESET} (всего найдено: {len(raw_final_items)})\n")
    
    # Автоматически генерируем/обновляем metadata.json для rename.py, сохраняя пользовательские пути
    db = {}
    for item in final_items:
        url = item["url"]
        raw_fn = clean_filename(url)
        norm_raw_fn = normalize_key(raw_fn)
        custom_meta = existing_db.get(norm_raw_fn, {})
        db[raw_fn] = {
            "url": url,
            "description": item["description"],
            "brand": item["brand"],
            "category": item["category"]
        }
        if "model_folder" in custom_meta:
            db[raw_fn]["model_folder"] = custom_meta["model_folder"]
        if "target_filename" in custom_meta:
            db[raw_fn]["target_filename"] = custom_meta["target_filename"]
            
    # Сохраняем все локальные ручные добавления из старой базы
    for raw_fn, meta in raw_db.items():
        if meta.get("url") == "":
            db[raw_fn] = meta
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
        
        # 0. Проверка черного списка до скачивания
        if raw_filename in BLACKLIST or url in BLACKLIST:
            print(f"{BOLD}[{idx}/{len(final_items)}] {brand} | {desc}{RESET}")
            print(f"   Skip: {RED}файл находится в черном списке blacklist.json{RESET}")
            skip_count += 1
            print()
            continue
            
        # 1. Проверяем правила переименования из rules.json по имени файла или URL до скачивания
        rule_target_rel_path = None
        if raw_filename in RULES:
            rule_target_rel_path = RULES[raw_filename]
        elif url in RULES:
            rule_target_rel_path = RULES[url]
        
        # Проверяем пользовательские переопределения папки и имени из базы метаданных
        norm_raw_fn = normalize_key(raw_filename)
        custom_meta = existing_db.get(norm_raw_fn, {})
        custom_filename = custom_meta.get("target_filename")
        custom_folder = custom_meta.get("model_folder")
        
        # Генерируем стандартное имя файла, если нет кастомного
        meta = {
            "url": url,
            "description": desc,
            "brand": brand,
            "category": category
        }
        
        if rule_target_rel_path:
            path_parts = rule_target_rel_path.replace("\\", "/").split("/")
            if len(path_parts) >= 3:
                category = path_parts[0]
                brand_folder_name = path_parts[1]
                model_folder = "/".join(path_parts[2:-1])
                new_filename = path_parts[-1]
        else:
            new_filename = custom_filename if custom_filename else get_new_filename(raw_filename, meta)

            # 0b. Проверка черного списка по стандартизированному имени (до скачивания)
            if new_filename in BLACKLIST:
                print(f"{BOLD}[{idx}/{len(final_items)}] {brand} | {desc}{RESET}")
                print(f"   Skip: {RED}в черном списке (по целевому имени){RESET}")
                skip_count += 1
                print()
                continue

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
            
            # Вычисляем имя модели для папки прибора
            if custom_folder is not None:
                model_folder = custom_folder
            else:
                model, _ = clean_model_and_version(desc, brand)
                if not model:
                    model = get_clean_fallback_model(raw_filename, brand)
                    
                model_folder = model.replace(" ", "_").strip()
                model_folder = re.sub(r'[\\/*?:"<>|]', "", model_folder) # убираем запрещенные символы для Windows
                if not model_folder:
                    model_folder = "UNKNOWN"
    
            # Определяем специфические пути сохранения для новых брендов
            brand_folder_name = brand
            if brand == "Quasar Science":
                brand_folder_name = "Quasar_Science" if category == "01_Firmware" else "Quasar"
            elif brand == "Kino Flo":
                brand_folder_name = "Kino_Flo" if category == "01_Firmware" else "KinoFlo"
            elif brand == "Pipe Lighting":
                brand_folder_name = "PipeLighting"
            elif brand == "Pheon Lux":
                brand_folder_name = "PheonLux"

        legacy_local_path = os.path.join(LOCAL_DOWNLOADS_ROOT, category, brand_folder_name, new_filename)
        local_dir = os.path.join(LOCAL_DOWNLOADS_ROOT, category, brand_folder_name, model_folder)
        local_path = os.path.join(local_dir, new_filename)
        
        legacy_usb_path = os.path.join(usb_root, category, brand_folder_name, new_filename) if usb_mounted else None
        usb_dir = os.path.join(usb_root, category, brand_folder_name, model_folder) if usb_mounted else None
        usb_path = os.path.join(usb_dir, new_filename) if usb_mounted else None
        
        # Автоматическая миграция файлов из старого плоского расположения в папки моделей
        if os.path.exists(legacy_local_path) and not os.path.exists(local_path):
            os.makedirs(local_dir, exist_ok=True)
            try:
                shutil.move(legacy_local_path, local_path)
            except Exception:
                pass
                
        if usb_mounted and os.path.exists(legacy_usb_path) and not os.path.exists(usb_path):
            os.makedirs(usb_dir, exist_ok=True)
            try:
                shutil.move(legacy_usb_path, usb_path)
            except Exception:
                pass
        
        print(f"{BOLD}[{idx}/{len(final_items)}] {brand} | {desc}{RESET}")
        
        # А) Локальное скачивание
        if os.path.exists(local_path):
            print(f"   Skip: {GREEN}актуален на Mac{RESET} ({new_filename})")
            skip_count += 1
        else:
            print(f"   📥 На диске: {YELLOW}отсутствует{RESET}, скачиваем...")
            success = download_file(url, local_path)
            if success:
                # ВЫЧИСЛЯЕМ SHA-256 ДЛЯ ПОСТ-ПРОВЕРКИ
                sha = get_file_sha256(local_path)
                
                # 2. Проверка по черному списку по хэшу
                if sha in BLACKLIST:
                    print(f"   🗑️ Файл пропущен: {RED}найден в черном списке по хэшу SHA-256{RESET}")
                    try:
                        os.remove(local_path)
                    except Exception:
                        pass
                    skip_count += 1
                    print()
                    continue
                
                # 3. Проверка правил переименования по хэшу (если не сработало текстовое правило до скачивания)
                if sha in RULES and not rule_target_rel_path:
                    rule_target_rel_path = RULES[sha]
                    path_parts = rule_target_rel_path.replace("\\", "/").split("/")
                    if len(path_parts) >= 3:
                        category = path_parts[0]
                        brand_folder_name = path_parts[1]
                        model_folder = "/".join(path_parts[2:-1])
                        new_filename = path_parts[-1]
                        
                        new_local_dir = os.path.join(LOCAL_DOWNLOADS_ROOT, category, brand_folder_name, model_folder)
                        new_local_path = os.path.join(new_local_dir, new_filename)
                        
                        os.makedirs(new_local_dir, exist_ok=True)
                        if os.path.exists(new_local_path):
                            os.remove(new_local_path)
                        shutil.move(local_path, new_local_path)
                        local_path = new_local_path
                        print(f"   🔄 Переименован по хэш-правилу в: {CYAN}{new_filename}{RESET}")
                        
                        # Обновляем usb_path для последующей синхронизации
                        if usb_mounted:
                            usb_dir = os.path.join(usb_root, category, brand_folder_name, model_folder)
                            usb_path = os.path.join(usb_dir, new_filename)
                            
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
    
    # Очищаем пустые папки в локальном кэше и на USB
    print(f"🧹 Очистка пустых папок...")
    cleanup_empty_directories(LOCAL_DOWNLOADS_ROOT, LOCAL_DOWNLOADS_ROOT)
    if usb_mounted:
        cleanup_empty_directories(os.path.join(usb_root, "01_Firmware"), os.path.join(usb_root, "01_Firmware"))
        cleanup_empty_directories(os.path.join(usb_root, "02_DMX_Charts"), os.path.join(usb_root, "02_DMX_Charts"))
    print()

    # Отправляем нативное уведомление macOS
    notify_user_macos(downloaded_files_info)

    download_verification_time = time.time() - download_start_time
    total_time = time.time() - start_time
    
    # Выводим показатели в лог для GUI
    print(f"[TIME_STATS] Link checking: {link_checking_time:.2f} seconds")
    print(f"[TIME_STATS] Downloading and hashing: {download_verification_time:.2f} seconds")
    print(f"[TIME_STATS] Empty run: {'true' if is_empty_run else 'false'}")
    print(f"[TIME_STATS] Downloaded files: {download_count}")
    print(f"[TIME_STATS] Total: {total_time:.2f} seconds")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{RED}🛑 Процесс прерван пользователем.{RESET}\n")
        sys.exit(1)

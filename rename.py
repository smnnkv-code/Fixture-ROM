#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FIXTURE_ROM Filename Standardization Script
Скрипт для безопасного переименования скачанных файлов на основе базы метаданных.
"""

import os
import sys
import re
import json
import argparse

# --- Константы ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_DOWNLOADS_ROOT = os.path.expanduser("~/Documents/FixtureROM/Downloads")
METADATA_FILE = os.path.join(LOCAL_DOWNLOADS_ROOT, "metadata.json")

# ANSI-коды для красивого вывода
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

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

def main():
    parser = argparse.ArgumentParser(description="Стандартизация имен файлов FIXTURE_ROM")
    parser.add_argument(
        "--commit", 
        action="store_true", 
        help="Применить изменения (по умолчанию скрипт работает в режиме превью)"
    )
    args = parser.parse_args()
    
    # 1. Проверяем наличие базы метаданных
    if not os.path.exists(METADATA_FILE):
        print(f"{RED}❌ Ошибка: Файл базы данных метаданных не найден по пути:{RESET}")
        print(f"   {METADATA_FILE}")
        print(f"   Пожалуйста, запустите `sync.py` или дождитесь создания базы в фоне.")
        sys.exit(1)
        
    with open(METADATA_FILE, "r", encoding="utf-8") as f:
        metadata_db = json.load(f)
        
    print(f"\n{BOLD}{CYAN}================================================================{RESET}")
    print(f"{BOLD}{CYAN}🔄  FIXTURE_ROM | Стандартизация и переименование файлов  🔄{RESET}")
    print(f"{BOLD}{CYAN}================================================================{RESET}\n")
    
    if not args.commit:
        print(f"{YELLOW}ℹ️  РЕЖИМ ПРЕВЬЮ (DRY RUN). Ни один файл не будет изменен.{RESET}")
        print(f"   Для применения изменений запустите: {BOLD}python3 rename.py --commit{RESET}\n")
    else:
        print(f"{RED}⚠️  ВНИМАНИЕ: Запущен режим применения изменений (COMMIT).{RESET}\n")
        
    rename_count = 0
    skip_count = 0
    not_found_count = 0
    collision_count = 0
    
    # Проходим по категориям в папке загрузок
    categories = ["01_Firmware", "02_DMX_Charts"]
    for cat in categories:
        cat_dir = os.path.join(LOCAL_DOWNLOADS_ROOT, cat)
        if not os.path.exists(cat_dir):
            continue
            
        # Проходим по папкам брендов
        for brand in os.listdir(cat_dir):
            brand_dir = os.path.join(cat_dir, brand)
            if not os.path.isdir(brand_dir) or brand.startswith('.'):
                continue
                
            print(f"{BOLD}📂 Раздел: {brand} | Категория: {cat}{RESET}")
            
            # Сканируем файлы в папке бренда
            files = [f for f in os.listdir(brand_dir) if os.path.isfile(os.path.join(brand_dir, f)) and not f.startswith('.')]
            
            # Список новых имен для предотвращения коллизий в текущей сессии
            allocated_names = set()
            
            for fn in sorted(files):
                source_path = os.path.join(brand_dir, fn)
                
                # Ищем метаданные для файла
                meta = metadata_db.get(fn)
                if not meta:
                    # Попробуем найти по URL/описанию (на случай если имя уже частично изменено)
                    not_found_count += 1
                    continue
                    
                new_fn = get_new_filename(fn, meta)
                
                # Защита от коллизий имен внутри папки
                if new_fn in allocated_names:
                    base, ext = os.path.splitext(new_fn)
                    counter = 1
                    while f"{base}_{counter}{ext}" in allocated_names or os.path.exists(os.path.join(brand_dir, f"{base}_{counter}{ext}")):
                        counter += 1
                    new_fn = f"{base}_{counter}{ext}"
                    collision_count += 1
                    
                allocated_names.add(new_fn)
                
                if fn == new_fn:
                    print(f"   ⏭️  {GREEN}Уже стандартизирован:{RESET} {fn}")
                    skip_count += 1
                    continue
                    
                dest_path = os.path.join(brand_dir, new_fn)
                
                if not args.commit:
                    print(f"   🔄  {YELLOW}[Превью]{RESET} {fn}\n       ↳ {GREEN}{new_fn}{RESET}")
                else:
                    try:
                        os.rename(source_path, dest_path)
                        print(f"   ✅  {GREEN}Переименован:{RESET} {fn}\n       ↳ {CYAN}{new_fn}{RESET}")
                        rename_count += 1
                    except Exception as e:
                        print(f"   ❌  {RED}Ошибка переименования {fn}: {e}{RESET}")
                        
            print() # пустая строка
            
    # Статистика
    print(f"{BOLD}{CYAN}================================================================{RESET}")
    print(f"{BOLD}{GREEN}📊 Итоги обработки:{RESET}")
    print(f"   - Переименовано/готово к переименованию: {GREEN}{rename_count if args.commit else (len(metadata_db) - skip_count - not_found_count)}{RESET}")
    print(f"   - Уже имеют верное имя: {skip_count}")
    print(f"   - Не найдено в базе метаданных: {not_found_count}")
    if collision_count > 0:
        print(f"   - Предотвращено конфликтов имен: {YELLOW}{collision_count}{RESET}")
    print(f"{BOLD}{CYAN}================================================================{RESET}\n")

if __name__ == "__main__":
    main()

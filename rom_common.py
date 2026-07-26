#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FIXTURE_ROM — общие утилиты и константы.
Вынесено из sync.py, gui.py, rename.py для устранения дублирования.
"""

import os
import sys
import re
import hashlib

# --- ANSI-коды для красивого вывода ---
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def get_usb_root():
    """
    Определяет путь к флешке FIXTURE_ROM на macOS и Windows.
    """
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            volumeNameBuffer = ctypes.create_unicode_buffer(1024)
            for letter in "EFGHIJKLMNOPQRSTUVWXYZD":  # D в конце — системный диск ищем последним
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


def get_file_sha256(filepath):
    """Вычисляет контрольную сумму SHA-256 для файла."""
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(65536), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception:
        return None


def clean_model_and_version(description, brand):
    """
    Извлекает имя модели и версию из описания.
    """
    desc_clean = description.strip().lower()
    if desc_clean in [
        "download", "download file", "download pdf", "download zip",
        "view more", "link", "click here", "read more", "view full",
        "view", "downloading", "view full change log"
    ] or desc_clean.startswith("download ") or desc_clean.startswith("view "):
        if not any(model_kw in desc_clean for model_kw in ["gemini", "astra", "rainbow", "q-lion", "celeb", "diva", "select", "freestyle", "image", "mimik", "colorpipe", "pipewide", "colordimmer"]):
            return "", ""

    desc = description.strip()

    # 0.0 Удаляем расширения файлов, если они есть на конце описания
    desc = re.sub(r'\.(zip|pdf|rar|bin)$', '', desc, flags=re.IGNORECASE).strip()

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

    # Для Creamsource сопоставляем модель прибора по ключевым словам
    if brand == "Creamsource":
        desc_lower = desc.lower()
        model_name = ""
        if "vortex" in desc_lower:
            model_name = "Vortex"
        elif "spacex" in desc_lower:
            model_name = "SpaceX"
        elif "sky" in desc_lower:
            model_name = "Sky"
        elif "micro" in desc_lower:
            model_name = "Micro"
        elif "mini" in desc_lower:
            model_name = "Mini"
        elif "crmx" in desc_lower:
            model_name = "CRM-X"
        elif "dot" in desc_lower:
            model_name = "Dot"
        else:
            # Проверяем, есть ли признак P в описании или в URL
            desc = re.sub(r'^P\s+', '', desc).strip()
        if model_name:
            return model_name, version

    # Для Litepanels сопоставляем модель прибора по ключевым словам
    if brand == "Litepanels":
        desc_lower = desc.lower()
        model_name = ""
        if "gemini" in desc_lower:
            model_name = "Gemini"
        elif "astra" in desc_lower:
            model_name = "Astra"
        elif "caliber" in desc_lower:
            model_name = "Caliber"
        elif "studio" in desc_lower:
            model_name = "Studio"
        elif "solis" in desc_lower:
            model_name = "Solis"
        elif "nova" in desc_lower:
            model_name = "Nova"
        elif "chroma" in desc_lower:
            model_name = "Chroma"
        elif "daylight" in desc_lower:
            model_name = "Daylight"
        elif "1x1" in desc_lower:
            model_name = "1x1"
        elif "inova" in desc_lower:
            model_name = "Inova"
        elif "croma" in desc_lower:
            model_name = "Croma"
        elif "dracast" in desc_lower:
            model_name = "Dracast"
        if model_name:
            return model_name, version

    # Для GVM сопоставляем модель
    if brand == "GVM":
        desc_lower = desc.lower()
        model_name = ""
        if "pixel" in desc_lower:
            model_name = "Pixel"
        elif "led" in desc_lower:
            # Определяем модель по цифровому коду
            model_match = re.search(r'\b(12\d{2}|SD\d{3}|PR\d{3}|GB\d{3})\b', desc)
            if model_match:
                model_name = model_match.group(1)
        if model_name:
            return model_name, version

    # Для LiteGear сопоставляем модель
    if brand == "LiteGear":
        desc_lower = desc.lower()
        model_name = ""
        if "litemat" in desc_lower:
            model_name = "LiteMat"
        elif "liteblade" in desc_lower:
            model_name = "LiteBlade"
        elif "liteflow" in desc_lower:
            model_name = "LiteFlow"
        elif "litetile" in desc_lower:
            model_name = "LiteTile"
        elif "litedrop" in desc_lower:
            model_name = "LiteDrop"
        elif "gator" in desc_lower:
            model_name = "Gator"
        if model_name:
            return model_name, version

    # Для PipeLighting сопоставляем модель
    if brand == "Pipe Lighting":
        desc_lower = desc.lower()
        model_name = ""
        if "colorpipe" in desc_lower:
            model_name = "ColorPipe"
        elif "pipewide" in desc_lower:
            model_name = "PipeWide"
        elif "colordimmer" in desc_lower:
            model_name = "ColorDimmer"
        elif "pipeblade" in desc_lower:
            model_name = "PipeBlade"
        if model_name:
            return model_name, version

    # Для Pheon Lux сопоставляем модель
    if brand == "Pheon Lux":
        desc_lower = desc.lower()
        model_name = ""
        if "freestyle" in desc_lower:
            model_name = "Freestyle"
        elif "image" in desc_lower:
            model_name = "Image"
        elif "mimik" in desc_lower:
            model_name = "Mimik"
        elif "colorpipe" in desc_lower:
            model_name = "ColorPipe"
        elif "rainbow" in desc_lower:
            model_name = "Rainbow"
        if model_name:
            return model_name, version

    # Для Lightstar сопоставляем модель
    if brand == "Lightstar":
        desc_lower = desc.lower()
        model_name = ""
        if "q-lion" in desc_lower:
            model_name = "Q-Lion"
        elif "celeb" in desc_lower:
            model_name = "Celeb"
        elif "diva" in desc_lower:
            model_name = "Diva"
        if model_name:
            return model_name, version

    # Для Kino Flo сопоставляем модель
    if brand == "Kino Flo":
        desc_lower = desc.lower()
        model_name = ""
        if "select" in desc_lower or "select " in desc_lower:
            model_name = "Select"
        elif "freestyle" in desc_lower:
            model_name = "Freestyle"
        elif "cele" in desc_lower:
            model_name = "Celeb"
        elif "diva" in desc_lower:
            model_name = "Diva"
        elif "image" in desc_lower:
            model_name = "Image"
        elif "mimik" in desc_lower:
            model_name = "Mimik"
        if model_name:
            return model_name, version

    # Для Aputure / Amaran: извлекаем модель из первой части описания до версии
    if brand in ("Aputure", "Amaran"):
        desc_lower = desc.lower()
        model_name = ""
        if "amaran" in desc_lower and brand == "Aputure":
            return "", ""
        if "none" in desc_lower and "none" == desc_lower.strip():
            return "", ""
        # Извлекаем первую значащую часть до версии
        desc_clean_part = desc
        # Если есть номер модели вида LS 600c Pro, STORM 1200x и т.д.
        model_map = {
            "storm": "STORM",
            "evoke": "EVOKE",
            "ls": "LS",
            "nova": "NOVA",
            "infibar": "INFIBAR",
            "accux": "ACCUX",
            "mc": "MC",
            "mt": "MT",
            "hr": "HR",
            "f10": "F10",
            "f22": "F22",
            "f7": "F7"
        }
        for key, val in model_map.items():
            if key in desc_lower:
                # Извлекаем полную модель: ключ + номер (например, LS 600c Pro)
                pattern = re.escape(key) + r'\s+\S+(?:\s+\S+)?'
                pm = re.search(pattern, desc, re.IGNORECASE)
                if pm:
                    model_name = pm.group(0).strip()
                    # Удаляем версию, если попала в model_name
                    model_name = re.sub(r'\s*v?\d+(?:\.\d+)+\b.*$', '', model_name, flags=re.IGNORECASE).strip()
                    break
                else:
                    model_name = val
                    break

        if not model_name:
            # Если не нашли по карте, используем первую часть до запятой, новой строки или тире
            first_part = re.split(r'[,;\n\-–—]+', desc)[0].strip()
            # Удаляем название бренда
            first_part = re.sub(r'\bAputure\b|\bAmaran\b', '', first_part, flags=re.IGNORECASE).strip()
            if first_part:
                model_name = first_part

        if model_name:
            return model_name, version

    # Для остальных брендов: извлекаем модель из первой части описания
    # Удаляем название бренда из описания, если оно есть
    desc_no_brand = re.sub(r'\b' + re.escape(brand) + r'\b', '', desc, flags=re.IGNORECASE).strip()

    # Извлекаем первую значащую часть до запятой, новой строки или тире
    first_part = re.split(r'[,;\n\-–—]+', desc_no_brand)[0].strip()

    # Если первая часть пустая или состоит только из версии — пробуем вторую
    if not first_part or re.match(r'^v?\d+(?:\.\d+)+\s*$', first_part, re.IGNORECASE):
        parts = re.split(r'[,;\n\-–—]+', desc_no_brand)
        if len(parts) > 1:
            first_part = parts[1].strip()

    model = first_part if first_part else desc_no_brand

    # 2. Удаляем упоминание бренда (если осталось внутри модели)
    model = re.sub(r'\b' + re.escape(brand) + r'\b', '', model, flags=re.IGNORECASE).strip()

    # 3. Удаляем ключевые слова типов файлов на конце описания
    model = re.sub(r'\s*(PDF|ZIP|RAR|BIN|Firmware|Manual|Guide|Sheet|Chart|File|Download|Update)\s*$', '', model, flags=re.IGNORECASE).strip()

    # 4. Очищаем висящие знаки препинания и разделители
    model = re.sub(r'^[\s\-_]+', '', model)
    model = re.sub(r'[\s\-_]+$', '', model)

    # 5. Приводим модель к верхнему регистру
    model = model.upper()

    # Заменяем подчеркивания на пробелы для человекочитаемости модели
    model = model.replace('_', ' ')

    # Стандартизируем формат версии (всегда с большой 'V')
    if version:
        version_upper = version.upper()
        if not version_upper.startswith('V'):
            version = "V" + version
        else:
            version = "V" + version[1:]

    return model, version

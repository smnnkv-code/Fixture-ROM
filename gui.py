#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FIXTURE_ROM GUI Dashboard Server
Легковесный локальный сервер для управления синхронизацией FIXTURE_ROM
через красивый и современный веб-интерфейс в браузере.
Без внешних зависимостей.
"""

import os
import re
import sys
import json
import threading
import subprocess
import webbrowser
import socketserver
import http.server
from urllib.parse import parse_qs, urlparse

# --- Константы путей ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_DOWNLOADS_ROOT = os.path.join(SCRIPT_DIR, "Downloads")
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
SNAPSHOTS_DIR = os.path.join(SCRIPT_DIR, "Snapshots")
STATS_FILE = os.path.join(SNAPSHOTS_DIR, "sync_stats.json")

# Глобальная переменная для хранения статистики
sync_stats_data = {
    "last_cached_run_duration": None,
    "last_empty_run_duration": None,
    "last_run_download_count": None,
    "history_cached_durations": [],
    "history_empty_durations": [],
    "average_cached_duration": None,
    "average_empty_duration": None
}

def load_sync_stats():
    """Загружает статистику выполнения из файла."""
    global sync_stats_data
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    sync_stats_data.update(data)
        except (OSError, json.JSONDecodeError):
            pass

# Сразу загружаем при старте
load_sync_stats()

from rom_common import get_usb_root, clean_model_and_version

def get_clean_fallback_model(raw_filename, brand):
    """
    Извлекает чистое имя модели из имени файла, если нет описания.
    Аналогично sync.py.
    """
    base = os.path.splitext(raw_filename)[0]
    model, _ = clean_model_and_version(base, brand)
    if not model:
        model = base.upper()
        model = re.sub(rf'\b{brand.upper()}\b', '', model).strip()
        model = re.sub(r'[\s\-_]+$', '', model).strip()
    return model

def get_all_models_from_db():
    """
    Парсит metadata.json и возвращает список уникальных моделей приборов по брендам.
    """
    db_path = os.path.join(LOCAL_DOWNLOADS_ROOT, "metadata.json")
    if not os.path.exists(db_path):
        return {}
    try:
        with open(db_path, "r", encoding="utf-8") as f:
            db = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}

    models_by_brand = {}
    for raw_fn, info in db.items():
        brand = info.get("brand")
        desc = info.get("description", "")
        if not brand:
            continue
        model, _ = clean_model_and_version(desc, brand)
        if not model:
            model = get_clean_fallback_model(raw_fn, brand)
            
        models_by_brand.setdefault(brand, set()).add(model)
        
    sorted_models = {}
    for brand, models in models_by_brand.items():
        sorted_models[brand] = sorted(list(models))
    return sorted_models

# Состояние синхронизации
sync_logs = []
is_syncing = False
sync_thread = None
sync_lock = threading.Lock()  # защита is_syncing от гонки между потоками

# Шаблон HTML с премиальным дизайном (Glassmorphism, Dark Mode, Google Fonts)
HTML_CONTENT = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FIXTURE_ROM ⚡ Control Panel</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0b0f19;
            --panel-bg: rgba(22, 28, 45, 0.6);
            --border-color: rgba(255, 255, 255, 0.08);
            --accent-primary: #3b82f6;
            --accent-glow: rgba(59, 130, 246, 0.3);
            --success-color: #10b981;
            --success-glow: rgba(16, 185, 129, 0.3);
            --warning-color: #f59e0b;
            --danger-color: #ef4444;
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow-x: hidden;
            background-image: 
                radial-gradient(circle at 10% 20%, rgba(59, 130, 246, 0.05) 0%, transparent 40%),
                radial-gradient(circle at 90% 80%, rgba(16, 185, 129, 0.05) 0%, transparent 40%);
        }

        header {
            padding: 24px 40px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            background: rgba(11, 15, 25, 0.8);
            backdrop-filter: blur(10px);
            position: sticky;
            top: 0;
            z-index: 100;
        }

        .logo {
            font-weight: 800;
            font-size: 24px;
            background: linear-gradient(135deg, #3b82f6 0%, #10b981 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .status-badge {
            padding: 8px 16px;
            border-radius: 99px;
            font-size: 14px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.3s ease;
        }

        .status-badge.connected {
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid var(--success-color);
            color: var(--success-color);
            box-shadow: 0 0 10px var(--success-glow);
        }

        .status-badge.disconnected {
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid var(--danger-color);
            color: var(--danger-color);
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background-color: currentColor;
            display: inline-block;
        }

        .status-badge.connected .status-dot {
            animation: pulse 1.5s infinite;
        }

        @keyframes pulse {
            0% { transform: scale(0.9); opacity: 0.6; }
            50% { transform: scale(1.2); opacity: 1; }
            100% { transform: scale(0.9); opacity: 0.6; }
        }

        main {
            flex: 1;
            padding: 40px;
            max-width: 1400px;
            width: 100%;
            margin: 0 auto;
            display: grid;
            grid-template-columns: 350px 1fr;
            gap: 32px;
        }

        .sidebar {
            display: flex;
            flex-direction: column;
            gap: 24px;
        }

        .card {
            background: var(--panel-bg);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            padding: 24px;
            backdrop-filter: blur(12px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            transition: transform 0.3s ease, border-color 0.3s ease;
        }

        .card:hover {
            border-color: rgba(59, 130, 246, 0.2);
        }

        .card-title {
            font-size: 16px;
            font-weight: 600;
            color: var(--text-muted);
            margin-bottom: 16px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 16px;
        }

        .stat-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 0;
            border-bottom: 1px solid rgba(255,255,255,0.04);
        }

        .stat-item:last-child {
            border-bottom: none;
        }

        .stat-label {
            font-size: 15px;
            color: var(--text-muted);
        }

        .stat-value {
            font-size: 18px;
            font-weight: 600;
            color: var(--text-main);
        }

        .btn {
            width: 100%;
            padding: 16px 24px;
            border: none;
            border-radius: 12px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 10px;
        }

        .btn-primary {
            background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
            color: white;
            box-shadow: 0 4px 15px var(--accent-glow);
        }

        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(59, 130, 246, 0.4);
        }

        .btn-primary:disabled {
            background: #1e293b;
            color: #64748b;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }

        .btn-secondary {
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-main);
            border: 1px solid var(--border-color);
            margin-top: 12px;
        }

        .btn-secondary:hover {
            background: rgba(255, 255, 255, 0.1);
            border-color: rgba(255, 255, 255, 0.2);
        }

        .workspace {
            display: flex;
            flex-direction: column;
            gap: 32px;
        }

        .tabs-header {
            display: flex;
            gap: 12px;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 16px;
        }

        .tab-btn {
            background: transparent;
            border: none;
            color: var(--text-muted);
            padding: 8px 16px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            position: relative;
        }

        .tab-btn.active {
            color: var(--accent-primary);
        }

        .tab-btn.active::after {
            content: '';
            position: absolute;
            bottom: -17px;
            left: 0;
            right: 0;
            height: 2px;
            background-color: var(--accent-primary);
            box-shadow: 0 0 10px var(--accent-primary);
        }

        .tab-content {
            display: none;
        }

        .tab-content.active {
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        .console-container {
            background: #060913;
            border: 1px solid var(--border-color);
            border-radius: 16px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            height: 500px;
            box-shadow: inset 0 2px 8px rgba(0,0,0,0.8);
        }

        .console-header {
            background: rgba(255,255,255,0.02);
            padding: 12px 20px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .console-title {
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px;
            color: var(--text-muted);
        }

        .console-body {
            font-family: 'JetBrains Mono', monospace;
            padding: 20px;
            overflow-y: auto;
            flex: 1;
            font-size: 14px;
            line-height: 1.6;
            display: flex;
            flex-direction: column;
            gap: 8px;
            scroll-behavior: smooth;
        }

        .console-line {
            color: #d1d5db;
            white-space: pre-wrap;
        }

        .console-line.success { color: #10b981; }
        .console-line.warning { color: #f59e0b; }
        .console-line.error { color: #ef4444; }
        .console-line.info { color: #3b82f6; }
        .console-line.bold { font-weight: bold; }

        .search-container {
            display: flex;
            gap: 16px;
            margin-bottom: 12px;
        }

        .search-input {
            flex: 1;
            background: rgba(255,255,255,0.03);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 12px 20px;
            color: var(--text-main);
            font-family: inherit;
            font-size: 15px;
            transition: all 0.3s ease;
        }

        .search-input:focus {
            outline: none;
            border-color: var(--accent-primary);
            box-shadow: 0 0 10px var(--accent-glow);
            background: rgba(255,255,255,0.05);
        }

        .files-table-container {
            max-height: 500px;
            overflow-y: auto;
            border: 1px solid var(--border-color);
            border-radius: 16px;
            background: var(--panel-bg);
        }

        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 14px;
        }

        th {
            background: rgba(255,255,255,0.02);
            padding: 16px 20px;
            font-weight: 600;
            color: var(--text-muted);
            border-bottom: 1px solid var(--border-color);
            position: sticky;
            top: 0;
            z-index: 10;
            backdrop-filter: blur(10px);
        }

        td {
            padding: 16px 20px;
            border-bottom: 1px solid rgba(255,255,255,0.03);
            color: var(--text-main);
        }

        tr:hover td {
            background: rgba(255, 255, 255, 0.02);
        }

        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
        }

        .badge-fw {
            background: rgba(59, 130, 246, 0.1);
            color: var(--accent-primary);
            border: 1px solid rgba(59, 130, 246, 0.2);
        }

        .badge-dmx {
            background: rgba(16, 185, 129, 0.1);
            color: var(--success-color);
            border: 1px solid rgba(16, 185, 129, 0.2);
        }

        /* Scrollbars */
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        ::-webkit-scrollbar-track {
            background: transparent;
        }
        ::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 99px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: rgba(255, 255, 255, 0.2);
        }
    </style>
</head>
<body>

    <header>
        <div class="logo">
            <span>FIXTURE_ROM</span>
            <span style="font-weight: 300; font-size: 20px;">⚡</span>
            <span style="font-weight: 300; font-size: 20px; color: var(--text-muted);">Dashboard</span>
        </div>
        <div id="usb-status" class="status-badge disconnected">
            <span class="status-dot"></span>
            <span id="usb-text">Проверка диска...</span>
        </div>
    </header>

    <main>
        <div class="sidebar">
            <div class="card">
                <div class="card-title">Управление</div>
                <button id="sync-btn" class="btn btn-primary" onclick="startSync()">
                    <span id="sync-icon">🔄</span>
                    <span id="sync-btn-text">Запустить синхронизацию</span>
                </button>
                <button class="btn btn-secondary" onclick="openFinder()">
                    📂 Открыть в Finder
                </button>
            </div>

            <!-- Сайдбар Карточка Фильтрации -->
            <div class="card" style="margin-top: 4px;">
                <div class="card-title">Фильтрация</div>
                <div style="margin-bottom: 16px;">
                    <div style="font-size: 13px; font-weight: 600; color: var(--text-muted); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;">Категории файлов</div>
                    <label style="display: flex; align-items: center; gap: 8px; font-size: 14px; margin-bottom: 8px; cursor: pointer;">
                        <input type="checkbox" id="filter-cat-fw" onchange="saveSidebarConfig()" checked>
                        Прошивки (Firmware)
                    </label>
                    <label style="display: flex; align-items: center; gap: 8px; font-size: 14px; cursor: pointer;">
                        <input type="checkbox" id="filter-cat-dmx" onchange="saveSidebarConfig()" checked>
                        DMX-карты (DMX Charts)
                    </label>
                </div>
                <div>
                    <div style="font-size: 13px; font-weight: 600; color: var(--text-muted); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;">Сайты брендов</div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                        <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                            <input type="checkbox" id="filter-brand-aputure" onchange="saveSidebarConfig()" checked> Aputure
                        </label>
                        <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                            <input type="checkbox" id="filter-brand-amaran" onchange="saveSidebarConfig()" checked> Amaran
                        </label>
                        <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                            <input type="checkbox" id="filter-brand-nanlite" onchange="saveSidebarConfig()" checked> Nanlite
                        </label>
                        <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                            <input type="checkbox" id="filter-brand-nanlux" onchange="saveSidebarConfig()" checked> Nanlux
                        </label>
                        <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                            <input type="checkbox" id="filter-brand-godox" onchange="saveSidebarConfig()" checked> Godox
                        </label>
                        <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                            <input type="checkbox" id="filter-brand-knowled" onchange="saveSidebarConfig()" checked> Knowled
                        </label>
                        <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                            <input type="checkbox" id="filter-brand-arri" onchange="saveSidebarConfig()" checked> ARRI
                        </label>
                        <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                            <input type="checkbox" id="filter-brand-astera" onchange="saveSidebarConfig()" checked> Astera
                        </label>
                        <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                            <input type="checkbox" id="filter-brand-creamsource" onchange="saveSidebarConfig()" checked> Creamsource
                        </label>
                        <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                            <input type="checkbox" id="filter-brand-gvm" onchange="saveSidebarConfig()" checked> GVM
                        </label>
                        <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                            <input type="checkbox" id="filter-brand-litegear" onchange="saveSidebarConfig()" checked> LiteGear
                        </label>
                        <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                            <input type="checkbox" id="filter-brand-lightstar" onchange="saveSidebarConfig()" checked> Lightstar
                        </label>
                        <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                            <input type="checkbox" id="filter-brand-litepanels" onchange="saveSidebarConfig()" checked> Litepanels
                        </label>
                        <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                            <input type="checkbox" id="filter-brand-quasar-science" onchange="saveSidebarConfig()" checked> Quasar Science
                        </label>
                        <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                            <input type="checkbox" id="filter-brand-kino-flo" onchange="saveSidebarConfig()" checked> Kino Flo
                        </label>
                        <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                            <input type="checkbox" id="filter-brand-pipe-lighting" onchange="saveSidebarConfig()" checked> Pipe Lighting
                        </label>
                        <label style="display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;">
                            <input type="checkbox" id="filter-brand-pheon-lux" onchange="saveSidebarConfig()" checked> Pheon Lux
                        </label>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-title">Статистика кэша Mac</div>
                <div class="stats-grid">
                    <div class="stat-item">
                        <span class="stat-label">Прошивки</span>
                        <span id="stat-fw" class="stat-value">0</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">DMX-карты</span>
                        <span id="stat-dmx" class="stat-value">0</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Размер кэша</span>
                        <span id="stat-size" class="stat-value">0 MB</span>
                    </div>
                </div>
            </div>
        </div>

        <div class="workspace">
            <div class="tabs-header">
                <button id="tab-btn-console" class="tab-btn active" onclick="switchTab('console')">Лог консоли</button>
                <button id="tab-btn-files" class="tab-btn" onclick="switchTab('files')">База приборов и файлов</button>
            </div>

            <!-- Вкладка Консоль -->
            <div id="tab-console" class="tab-content active">
                <!-- Блок времени выполнения синхронизации -->
                <div class="stats-card-container" style="display: flex; gap: 16px; margin-bottom: 16px;">
                    <div class="card" style="flex: 1; padding: 14px 18px; display: flex; align-items: center; gap: 16px; margin-bottom: 0; border: 1px solid rgba(255,255,255,0.03);">
                        <div style="font-size: 24px;">🔍</div>
                        <div>
                            <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); font-weight: 600;">Сканирование источников (Source Scanning)</div>
                            <div style="display: flex; align-items: baseline; gap: 8px; margin-top: 2px;">
                                <span id="stats-time-cached" style="font-size: 16px; font-weight: 700; color: var(--accent-primary);">--</span>
                                <span id="stats-time-cached-avg" style="font-size: 10px; color: var(--text-muted); font-weight: 500;">(в среднем: ~75 сек)</span>
                            </div>
                            <div style="font-size: 10px; color: var(--text-muted); margin-top: 1px;">Проверка обновлений.</div>
                            <div style="font-size: 10px; color: var(--text-muted); margin-top: 1px; font-weight: 500;">Режим: Энергосберегающий (без загрузки).</div>
                        </div>
                    </div>
                    <div class="card" style="flex: 1; padding: 14px 18px; display: flex; align-items: center; gap: 16px; margin-bottom: 0; border: 1px solid rgba(255,255,255,0.03);">
                        <div style="font-size: 24px;">📥</div>
                        <div>
                            <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); font-weight: 600;">Полная загрузка (Full Sync Interval)</div>
                            <div style="display: flex; align-items: baseline; gap: 8px; margin-top: 2px;">
                                <span id="stats-time-empty" style="font-size: 16px; font-weight: 700; color: var(--accent-primary);">--</span>
                                <span id="stats-time-empty-avg" style="font-size: 10px; color: var(--text-muted); font-weight: 500;">(в среднем: ~300 сек)</span>
                            </div>
                            <div style="font-size: 10px; color: var(--text-muted); margin-top: 1px;">Скачивание файлов.</div>
                            <div style="font-size: 10px; color: var(--text-muted); margin-top: 1px; font-weight: 500;">Объем загрузки: <span id="stats-download-count" style="color: var(--text-main); font-weight: 600;">--</span> файлов.</div>
                        </div>
                    </div>
                </div>

                <div class="console-container">
                    <div class="console-header">
                        <div class="console-title">sync_stdout.log</div>
                        <div id="console-status" style="font-size: 12px; color: var(--text-muted);">Готов к работе</div>
                    </div>
                    <div id="console-body" class="console-body">
                        <div class="console-line info">Нажмите "Запустить синхронизацию", чтобы начать проверку сайтов.</div>
                    </div>
                </div>
            </div>

            <!-- Вкладка База файлов -->
            <div id="tab-files" class="tab-content">
                <!-- Встроенная панель выбора моделей устройств -->
                <div class="card" style="margin-bottom: 16px; padding: 18px 24px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; cursor: pointer;" onclick="toggleModelsPanel()">
                        <div class="card-title" style="margin-bottom: 0; font-size: 15px; color: var(--text-main); font-weight: 600;">⚙️ Выбор моделей приборов для синхронизации</div>
                        <span id="models-panel-arrow" style="font-size: 14px; color: var(--text-muted);">▶</span>
                    </div>
                    <div id="models-panel-content" style="display: none; margin-top: 16px; border-top: 1px solid var(--border-color); padding-top: 16px;">
                        <div style="display: flex; gap: 12px; margin-bottom: 16px;">
                            <button class="btn btn-secondary" style="width: auto; padding: 6px 14px; font-size: 12px; margin: 0; border-radius: 8px;" onclick="selectAllModels(true)">Выбрать все</button>
                            <button class="btn btn-secondary" style="width: auto; padding: 6px 14px; font-size: 12px; margin: 0; border-radius: 8px;" onclick="selectAllModels(false)">Снять выбор</button>
                        </div>
                        <div id="models-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; max-height: 250px; overflow-y: auto; padding-right: 8px;">
                            <div style="grid-column: 1/-1; text-align: center; color: var(--text-muted); font-size: 14px;">Загрузка списка моделей приборов...</div>
                        </div>
                    </div>
                </div>

                <div class="search-container">
                    <input id="search-bar" type="text" class="search-input" placeholder="Поиск по модели, бренду или имени файла..." oninput="filterFiles()">
                </div>
                <div class="files-table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Имя файла</th>
                                <th>Бренд</th>
                                <th>Категория</th>
                            </tr>
                        </thead>
                        <tbody id="files-table-body">
                            <tr>
                                <td colspan="3" style="text-align: center; color: var(--text-muted);">Загрузка списка файлов...</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </main>

    <script>
        let isSyncing = false;
        let activeTab = 'console';
        let allFiles = [];

        function switchTab(tabId) {
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
            
            document.getElementById(`tab-btn-${tabId}`).classList.add('active');
            document.getElementById(`tab-${tabId}`).classList.add('active');
            activeTab = tabId;
            
            if (tabId === 'files') {
                loadFiles();
                loadConfig();
            }
        }

        async function updateStatus() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();
                
                // USB статус
                const usbBadge = document.getElementById('usb-status');
                const usbText = document.getElementById('usb-text');
                if (data.usb_connected) {
                    usbBadge.className = 'status-badge connected';
                    usbText.innerText = 'FIXTURE_ROM подключена';
                } else {
                    usbBadge.className = 'status-badge disconnected';
                    usbText.innerText = 'Накопитель не найден';
                }
                
                // Статистика
                document.getElementById('stat-fw').innerText = data.firmware_count;
                document.getElementById('stat-dmx').innerText = data.dmx_count;
                document.getElementById('stat-size').innerText = `${data.cache_size_mb} MB`;
                
                // Обновляем статистику времени выполнения
                if (data.sync_stats) {
                    const cachedTime = data.sync_stats.last_cached_run_duration;
                    const emptyTime = data.sync_stats.last_empty_run_duration;
                    const downloadCount = data.sync_stats.last_run_download_count;
                    const avgCached = data.sync_stats.average_cached_duration;
                    const avgEmpty = data.sync_stats.average_empty_duration;
                    
                    document.getElementById('stats-time-cached').innerText = cachedTime !== null ? `${cachedTime.toFixed(2)} сек` : '--';
                    document.getElementById('stats-time-empty').innerText = emptyTime !== null ? `${emptyTime.toFixed(2)} сек` : '--';
                    document.getElementById('stats-download-count').innerText = downloadCount !== null ? downloadCount : '--';
                    
                    document.getElementById('stats-time-cached-avg').innerText = avgCached !== null ? `(в среднем: ~${avgCached.toFixed(1)} сек)` : '(в среднем: ~75 сек)';
                    document.getElementById('stats-time-empty-avg').innerText = avgEmpty !== null ? `(в среднем: ~${avgEmpty.toFixed(1)} сек)` : '(в среднем: ~300 сек)';
                }
                
                // Статус синхронизации
                const syncBtn = document.getElementById('sync-btn');
                const syncBtnText = document.getElementById('sync-btn-text');
                const syncIcon = document.getElementById('sync-icon');
                const consoleStatus = document.getElementById('console-status');
                
                isSyncing = data.is_syncing;
                if (isSyncing) {
                    syncBtn.disabled = true;
                    syncBtnText.innerText = 'Синхронизация...';
                    syncIcon.className = '';
                    consoleStatus.innerText = 'Активный процесс...';
                    consoleStatus.style.color = 'var(--warning-color)';
                } else {
                    syncBtn.disabled = false;
                    syncBtnText.innerText = 'Запустить синхронизацию';
                    consoleStatus.innerText = 'Процесс завершен';
                    consoleStatus.style.color = 'var(--text-muted)';
                }
            } catch (err) {
                console.error("Ошибка обновления статуса:", err);
            }
        }

        async function loadConfig() {
            try {
                const response = await fetch('/api/config');
                const data = await response.json();
                
                const config = data.config;
                const availableModels = data.models;
                
                // 1. Категории в сайдбаре
                document.getElementById('filter-cat-fw').checked = config.enabled_categories.firmware;
                document.getElementById('filter-cat-dmx').checked = config.enabled_categories.dmx;
                
                // 2. Бренды в сайдбаре
                const brands = ['Aputure', 'Amaran', 'Nanlite', 'Nanlux', 'Godox', 'Knowled', 'ARRI', 'Astera', 'Creamsource', 'GVM', 'LiteGear', 'Lightstar', 'Litepanels', 'Quasar Science', 'Kino Flo', 'Pipe Lighting', 'Pheon Lux'];
                brands.forEach(b => {
                    const el = document.getElementById(`filter-brand-${b.toLowerCase().replace(' ', '-')}`);
                    if (el) el.checked = config.enabled_brands[b] !== false;
                });
                
                // 3. Модели приборов
                renderModelsGrid(availableModels, config.enabled_models);
            } catch (err) {
                console.error("Ошибка загрузки конфигурации:", err);
            }
        }

        async function saveSidebarConfig() {
            const firmware = document.getElementById('filter-cat-fw').checked;
            const dmx = document.getElementById('filter-cat-dmx').checked;
            
            const brands = ['Aputure', 'Amaran', 'Nanlite', 'Nanlux', 'Godox', 'Knowled', 'ARRI', 'Astera', 'Creamsource', 'GVM', 'LiteGear', 'Lightstar', 'Litepanels', 'Quasar Science', 'Kino Flo', 'Pipe Lighting', 'Pheon Lux'];
            const enabled_brands = {};
            brands.forEach(b => {
                const el = document.getElementById(`filter-brand-${b.toLowerCase().replace(' ', '-')}`);
                enabled_brands[b] = el ? el.checked : true;
            });
            
            const enabled_models = getSelectedModelsFromGrid();
            
            const payload = {
                enabled_categories: { firmware, dmx },
                enabled_brands,
                enabled_models
            };
            
            await sendConfigSave(payload);
        }

        async function sendConfigSave(payload) {
            try {
                await fetch('/api/config/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
            } catch (err) {
                console.error("Ошибка сохранения конфигурации:", err);
            }
        }

        function renderModelsGrid(availableModels, enabledModels) {
            const grid = document.getElementById('models-grid');
            if (!availableModels || Object.keys(availableModels).length === 0) {
                grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--text-muted); font-size: 14px; padding: 16px 0;">База приборов пуста. Запустите первую синхронизацию для сбора информации о моделях!</div>`;
                return;
            }
            
            let html = '';
            for (const [brand, modelsList] of Object.entries(availableModels)) {
                html += `
                    <div style="grid-column: 1/-1; margin-top: 12px; border-bottom: 1px solid rgba(255,255,255,0.04); padding-bottom: 6px; display: flex; align-items: center; justify-content: space-between;">
                        <span style="font-weight: 600; color: var(--accent-primary); font-size: 13px; text-transform: uppercase;">${brand}</span>
                    </div>
                `;
                modelsList.forEach(model => {
                    const brandModels = enabledModels[brand] || [];
                    const isChecked = brandModels.length === 0 || brandModels.includes(model);
                    html += `
                        <label style="display: flex; align-items: center; gap: 8px; font-size: 13px; cursor: pointer; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding: 4px 0;" title="${model}">
                            <input type="checkbox" class="model-checkbox" data-brand="${brand}" data-model="${model}" onchange="saveModelsConfig()" ${isChecked ? 'checked' : ''}>
                            ${model}
                        </label>
                    `;
                });
            }
            grid.innerHTML = html;
        }

        function getSelectedModelsFromGrid() {
            const enabled_models = {};
            document.querySelectorAll('.model-checkbox').forEach(cb => {
                const brand = cb.getAttribute('data-brand');
                const model = cb.getAttribute('data-model');
                if (cb.checked) {
                    enabled_models[brand] = enabled_models[brand] || [];
                    enabled_models[brand].push(model);
                } else {
                    enabled_models[brand] = enabled_models[brand] || [];
                }
            });
            return enabled_models;
        }

        async function saveModelsConfig() {
            const firmware = document.getElementById('filter-cat-fw').checked;
            const dmx = document.getElementById('filter-cat-dmx').checked;
            
            const brands = ['Aputure', 'Amaran', 'Nanlite', 'Nanlux', 'Godox', 'Knowled', 'ARRI', 'Astera', 'Creamsource', 'GVM', 'LiteGear', 'Lightstar', 'Litepanels', 'Quasar Science', 'Kino Flo', 'Pipe Lighting', 'Pheon Lux'];
            const enabled_brands = {};
            brands.forEach(b => {
                const el = document.getElementById(`filter-brand-${b.toLowerCase().replace(' ', '-')}`);
                enabled_brands[b] = el ? el.checked : true;
            });
            
            const enabled_models = getSelectedModelsFromGrid();
            
            const payload = {
                enabled_categories: { firmware, dmx },
                enabled_brands,
                enabled_models
            };
            
            await sendConfigSave(payload);
        }

        function selectAllModels(state) {
            document.querySelectorAll('.model-checkbox').forEach(cb => {
                cb.checked = state;
            });
            saveModelsConfig();
        }

        let isModelsPanelOpen = false;
        function toggleModelsPanel() {
            const content = document.getElementById('models-panel-content');
            const arrow = document.getElementById('models-panel-arrow');
            isModelsPanelOpen = !isModelsPanelOpen;
            if (isModelsPanelOpen) {
                content.style.display = 'block';
                arrow.innerText = '▼';
            } else {
                content.style.display = 'none';
                arrow.innerText = '▶';
            }
        }

        async function loadFiles() {
            try {
                const response = await fetch('/api/files');
                allFiles = await response.json();
                renderFiles(allFiles);
            } catch (err) {
                console.error("Ошибка загрузки файлов:", err);
            }
        }

        function renderFiles(files) {
            const tbody = document.getElementById('files-table-body');
            if (files.length === 0) {
                tbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--text-muted);">Файлы не найдены</td></tr>`;
                return;
            }
            
            tbody.innerHTML = files.map(file => {
                const isFW = file.category === '01_Firmware';
                const badgeClass = isFW ? 'badge-fw' : 'badge-dmx';
                const badgeText = isFW ? 'Firmware' : 'DMX Chart';
                return `
                    <tr>
                        <td style="font-family: 'JetBrains Mono', monospace; font-size: 13px;">${file.filename}</td>
                        <td><span style="font-weight: 600;">${file.brand}</span></td>
                        <td><span class="badge ${badgeClass}">${badgeText}</span></td>
                    </tr>
                `;
            }).join('');
        }

        function filterFiles() {
            const query = document.getElementById('search-bar').value.toLowerCase();
            const filtered = allFiles.filter(file => {
                return file.filename.toLowerCase().includes(query) || 
                       file.brand.toLowerCase().includes(query) ||
                       file.category.toLowerCase().includes(query);
            });
            renderFiles(filtered);
        }



        async function startSync() {
            if (isSyncing) return;
            
            const consoleBody = document.getElementById('console-body');
            consoleBody.innerHTML = `<div class="console-line info">🚀 Запуск процесса синхронизации...</div>`;
            
            try {
                await fetch('/api/sync', { method: 'POST' });
                updateStatus();
                pollLogs();
            } catch (err) {
                console.error("Ошибка старта синхронизации:", err);
            }
        }

        let logOffset = 0;
        let pollInterval = null;

        function formatLogLine(line) {
            let cleanLine = line.replace(/\\x1b\\[[0-9;]*m/g, ''); // Удаляем ANSI
            let className = 'console-line';
            
            if (line.includes('❌') || line.includes('Error')) className += ' error';
            else if (line.includes('✅') || line.includes('успешно')) className += ' success';
            else if (line.includes('⚠️') || line.includes('Warning') || line.includes('Skip:')) className += ' warning';
            else if (line.includes('⚡') || line.includes('====') || line.includes('🚀')) className += ' info bold';
            
            return `<div class="${className}">${cleanLine}</div>`;
        }

        async function pollLogs() {
            if (pollInterval) clearInterval(pollInterval);
            
            logOffset = 0;
            const consoleBody = document.getElementById('console-body');
            
            pollInterval = setInterval(async () => {
                try {
                    const response = await fetch(`/api/logs?offset=${logOffset}`);
                    const data = await response.json();
                    
                    if (data.lines && data.lines.length > 0) {
                        data.lines.forEach(line => {
                            if (line.includes('\\r') && !line.includes('\\n')) return;
                            consoleBody.innerHTML += formatLogLine(line);
                        });
                        logOffset += data.lines.length;
                        consoleBody.scrollTop = consoleBody.scrollHeight;
                    }
                    
                    if (!data.is_syncing && logOffset > 0) {
                        clearInterval(pollInterval);
                        updateStatus();
                        if (activeTab === 'files') loadFiles();
                    }
                } catch (err) {
                    console.error("Ошибка получения логов:", err);
                }
            }, 500);
        }

        async function openFinder() {
            await fetch('/api/open', { method: 'POST' });
        }

        // Первичная загрузка
        updateStatus();
        loadConfig();
        setInterval(updateStatus, 3000); // Опрос раз в 3 сек
        
        // Автоматически запускаем опрос логов при перезагрузке страницы, если уже идет синхронизация
        fetch('/api/status').then(r => r.json()).then(data => {
            if (data.is_syncing) {
                pollLogs();
            }
        });
    </script>
</body>
</html>
"""

class DashboardHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        parsed_url = urlparse(self.path)
        
        if parsed_url.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode('utf-8'))
            
        elif parsed_url.path == '/api/status':
            global is_syncing
            with sync_lock:
                sync_status = is_syncing
            usb_root = get_usb_root()
            usb_connected = usb_root is not None
            
            # Статистика кэша
            fw_count = 0
            dmx_count = 0
            total_size_bytes = 0
            
            if os.path.exists(LOCAL_DOWNLOADS_ROOT):
                for root, _, files in os.walk(LOCAL_DOWNLOADS_ROOT):
                    for f in files:
                        if f.startswith('.'):
                            continue
                        f_path = os.path.join(root, f)
                        try:
                            total_size_bytes += os.path.getsize(f_path)
                            if "01_Firmware" in root:
                                fw_count += 1
                            elif "02_DMX_Charts" in root:
                                dmx_count += 1
                        except OSError:
                            pass

            cache_size_mb = total_size_bytes // (1024 * 1024)
            
            status_data = {
                "usb_connected": usb_connected,
                "firmware_count": fw_count,
                "dmx_count": dmx_count,
                "cache_size_mb": cache_size_mb,
                "is_syncing": sync_status,
                "sync_stats": sync_stats_data
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(status_data).encode('utf-8'))
            
        elif parsed_url.path == '/api/logs':
            query = parse_qs(parsed_url.query)
            try:
                offset = int(query.get('offset', [0])[0])
            except ValueError:
                self.send_response(400)
                self.end_headers()
                self.wfile.write("Invalid 'offset' parameter — must be an integer".encode())
                return

            requested_lines = sync_logs[offset:]

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "lines": requested_lines,
                "is_syncing": is_syncing
            }).encode('utf-8'))
            
        elif parsed_url.path == '/api/files':
            files_list = []
            if os.path.exists(LOCAL_DOWNLOADS_ROOT):
                for category in ["01_Firmware", "02_DMX_Charts"]:
                    cat_dir = os.path.join(LOCAL_DOWNLOADS_ROOT, category)
                    if not os.path.exists(cat_dir):
                        continue
                    for brand in os.listdir(cat_dir):
                        brand_dir = os.path.join(cat_dir, brand)
                        if not os.path.isdir(brand_dir) or brand.startswith('.'):
                            continue
                        
                        brand_ui_name = brand
                        if brand in ["Quasar_Science", "Quasar"]:
                            brand_ui_name = "Quasar Science"
                        elif brand in ["Kino_Flo", "KinoFlo"]:
                            brand_ui_name = "Kino Flo"
                        elif brand == "PipeLighting":
                            brand_ui_name = "Pipe Lighting"
                        elif brand == "PheonLux":
                            brand_ui_name = "Pheon Lux"
                            
                        # Рекурсивный обход папки бренда для сбора реальных файлов
                        for root, _, files in os.walk(brand_dir):
                            for file in files:
                                if file.startswith('.') or file == "metadata.json":
                                    continue
                                files_list.append({
                                    "filename": file,
                                    "brand": brand_ui_name,
                                    "category": category
                                })
                            
            files_list.sort(key=lambda x: (x["brand"], x["filename"]))
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(files_list).encode('utf-8'))

            
        elif parsed_url.path == '/api/config':
            # Читаем config.json
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
            config_data = default_config
            if os.path.exists(CONFIG_FILE):
                try:
                    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                        config_data = json.load(f)
                except (OSError, json.JSONDecodeError):
                    pass

            # Получаем все уникальные модели устройств
            available_models = get_all_models_from_db()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "config": config_data,
                "models": available_models
            }).encode('utf-8'))
            
        else:
            self.send_error(404, "Page Not Found")

    def do_POST(self):
        parsed_url = urlparse(self.path)
        
        if parsed_url.path == '/api/sync':
            global is_syncing, sync_thread
            with sync_lock:
                if is_syncing:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Already syncing")
                    return
                is_syncing = True
            sync_logs.clear()
            
            sync_thread = threading.Thread(target=run_sync_process)
            sync_thread.daemon = True
            sync_thread.start()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "started"}).encode('utf-8'))
            
        elif parsed_url.path == '/api/open':
            try:
                if sys.platform == "win32":
                    os.startfile(LOCAL_DOWNLOADS_ROOT)
                else:
                    subprocess.run(["open", LOCAL_DOWNLOADS_ROOT])
            except OSError:
                pass
            self.send_response(200)
            self.end_headers()


        elif parsed_url.path == '/api/config/save':
            # Валидация входных данных
            content_length_str = self.headers.get('Content-Length', '0')
            try:
                content_length = int(content_length_str)
            except (ValueError, TypeError):
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Invalid Content-Length")
                return
            if content_length < 0 or content_length > 2 ** 20:  # макс 1 MB
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Request entity too large")
                return

            try:
                post_data = self.rfile.read(content_length)
                payload = json.loads(post_data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Invalid JSON")
                return

            if not isinstance(payload, dict):
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Config must be a JSON object")
                return

            # Валидация структуры: проверяем типы ожидаемых полей
            expected_fields = {
                "enabled_categories": dict,
                "enabled_brands": dict,
                "enabled_models": dict,
            }
            for field, expected_type in expected_fields.items():
                if field in payload and not isinstance(payload[field], expected_type):
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(f"Field '{field}' must be a {expected_type.__name__}".encode('utf-8'))
                    return

            try:
                config_tmp = CONFIG_FILE + ".tmp"
                with open(config_tmp, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=4, ensure_ascii=False)
                os.replace(config_tmp, CONFIG_FILE)
            except (OSError, IOError) as e:
                if os.path.exists(config_tmp):
                    os.remove(config_tmp)
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Failed to write config: {e}".encode('utf-8'))
                return

            self.send_response(200)
            self.end_headers()
            
        else:
            self.send_error(404, "Not Found")

def run_sync_process():
    global is_syncing, sync_logs, sync_stats_data
    sync_script_path = os.path.join(SCRIPT_DIR, "sync.py")
    
    process = subprocess.Popen(
        [sys.executable, "-u", sync_script_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    link_checking_time = None
    download_verification_time = None
    is_empty_run = False
    downloaded_files_count = None
    total_time = None
    
    while True:
        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break
        if line:
            clean_line = line.rstrip('\n')
            sync_logs.append(clean_line)
            
            # Парсинг служебных логов времени
            if clean_line.startswith("[TIME_STATS]"):
                parts = clean_line.replace("[TIME_STATS] ", "").split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    val = parts[1].strip()
                    try:
                        if "Link checking" in key:
                            link_checking_time = float(val.replace(" seconds", ""))
                        elif "Downloading and hashing" in key:
                            download_verification_time = float(val.replace(" seconds", ""))
                        elif "Empty run" in key:
                            is_empty_run = (val.lower() == "true")
                        elif "Downloaded files" in key:
                            downloaded_files_count = int(val)
                        elif "Total" in key:
                            total_time = float(val.replace(" seconds", ""))
                    except ValueError:
                        pass
            
    process.wait()
    with sync_lock:
        is_syncing = False
    
    # Сохраняем замеры в базу статистики
    updated = False
    
    # Инициализация пустых массивов на случай старого JSON
    if "history_cached_durations" not in sync_stats_data:
        sync_stats_data["history_cached_durations"] = []
    if "history_empty_durations" not in sync_stats_data:
        sync_stats_data["history_empty_durations"] = []
        
    if is_empty_run:
        if total_time is not None:
            sync_stats_data["last_empty_run_duration"] = total_time
            sync_stats_data["history_empty_durations"].append(total_time)
            # Ограничиваем историю 10 записями
            sync_stats_data["history_empty_durations"] = sync_stats_data["history_empty_durations"][-10:]
            # Расчет среднего
            sync_stats_data["average_empty_duration"] = sum(sync_stats_data["history_empty_durations"]) / len(sync_stats_data["history_empty_durations"])
            updated = True
    else:
        if link_checking_time is not None:
            sync_stats_data["last_cached_run_duration"] = link_checking_time
            sync_stats_data["history_cached_durations"].append(link_checking_time)
            # Ограничиваем историю 10 записями
            sync_stats_data["history_cached_durations"] = sync_stats_data["history_cached_durations"][-10:]
            # Расчет среднего
            sync_stats_data["average_cached_duration"] = sum(sync_stats_data["history_cached_durations"]) / len(sync_stats_data["history_cached_durations"])
            updated = True
            
    if downloaded_files_count is not None:
        sync_stats_data["last_run_download_count"] = downloaded_files_count
        updated = True
            
    if updated:
        try:
            os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
            with open(STATS_FILE, "w", encoding="utf-8") as f:
                json.dump(sync_stats_data, f, indent=4, ensure_ascii=False)
        except OSError:
            pass

def main():
    PORT = 8080
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    
    print(f"\n⚡ FIXTURE_ROM Dashboard Server ⚡")
    print(f"==================================================")
    
    server = None
    for port in range(PORT, PORT + 20):
        try:
            server = socketserver.ThreadingTCPServer(("127.0.0.1", port), DashboardHTTPRequestHandler)
            PORT = port
            break
        except OSError:
            continue
            
    if not server:
        print("❌ Ошибка: Не удалось запустить локальный сервер. Все порты заняты.")
        sys.exit(1)
        
    url = f"http://localhost:{PORT}"
    print(f"🚀 Сервер успешно запущен по адресу: {url}")
    print(f"📂 Директория кэша: {LOCAL_DOWNLOADS_ROOT}")
    print(f"🛑 Для остановки нажмите Ctrl + C")
    print(f"==================================================\n")
    
    webbrowser.open(url)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n🛑 Сервер остановлен пользователем.")
        server.server_close()

if __name__ == "__main__":
    main()

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

# Состояние синхронизации
sync_logs = []
is_syncing = False
sync_thread = None

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
            background: rgba(255,255,255,0.02);
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
                <button id="tab-btn-files" class="tab-btn" onclick="switchTab('files')">База файлов на Mac</button>
            </div>

            <!-- Вкладка Консоль -->
            <div id="tab-console" class="tab-content active">
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
                            // Игнорируем длинные перерисовки прогресс-баров, чтобы не засорять консоль
                            if (line.includes('\\r') && !line.includes('\\n')) return;
                            consoleBody.innerHTML += formatLogLine(line);
                        });
                        logOffset += data.lines.length;
                        consoleBody.scrollTop = consoleBody.scrollHeight;
                    }
                    
                    if (!data.is_syncing && logOffset > 0) {
                        clearInterval(pollInterval);
                        updateStatus();
                        // Если вкладка базы открыта, обновляем список файлов
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
        # Отключаем дефолтные логи запросов в терминал, чтобы не мешать
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
                        except Exception:
                            pass
                            
            cache_size_mb = total_size_bytes // (1024 * 1024)
            
            status_data = {
                "usb_connected": usb_connected,
                "firmware_count": fw_count,
                "dmx_count": dmx_count,
                "cache_size_mb": cache_size_mb,
                "is_syncing": is_syncing
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(status_data).encode('utf-8'))
            
        elif parsed_url.path == '/api/logs':
            query = parse_qs(parsed_url.query)
            offset = int(query.get('offset', [0])[0])
            
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
                        for f in os.listdir(brand_dir):
                            if f.startswith('.') or f == "metadata.json":
                                continue
                            files_list.append({
                                "filename": f,
                                "brand": brand,
                                "category": category
                            })
                            
            # Сортируем по бренду, затем по имени
            files_list.sort(key=lambda x: (x["brand"], x["filename"]))
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(files_list).encode('utf-8'))
            
        else:
            self.send_error(404, "Page Not Found")

    def do_POST(self):
        parsed_url = urlparse(self.path)
        
        if parsed_url.path == '/api/sync':
            global is_syncing, sync_thread
            if is_syncing:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Already syncing")
                return
                
            is_syncing = True
            sync_logs.clear()
            
            # Запускаем sync.py в фоновом потоке
            sync_thread = threading.Thread(target=run_sync_process)
            sync_thread.daemon = True
            sync_thread.start()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "started"}).encode('utf-8'))
            
        elif parsed_url.path == '/api/open':
            # Открываем Finder / Explorer
            try:
                if sys.platform == "win32":
                    os.startfile(LOCAL_DOWNLOADS_ROOT)
                else:
                    subprocess.run(["open", LOCAL_DOWNLOADS_ROOT])
            except Exception:
                pass
            self.send_response(200)
            self.end_headers()
            
        else:
            self.send_error(404, "Not Found")

def run_sync_process():
    global is_syncing, sync_logs
    sync_script_path = os.path.join(SCRIPT_DIR, "sync.py")
    
    # Запускаем sync.py с небуферизованным выводом (-u)
    process = subprocess.Popen(
        [sys.executable, "-u", sync_script_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    while True:
        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break
        if line:
            sync_logs.append(line.rstrip('\n'))
            
    process.wait()
    is_syncing = False

def main():
    PORT = 8080
    socketserver.TCPServer.allow_reuse_address = True
    
    print(f"\n⚡ FIXTURE_ROM Dashboard Server ⚡")
    print(f"==================================================")
    
    # Пытаемся запустить сервер. Если порт 8080 занят, ищем следующий свободный.
    server = None
    for port in range(PORT, PORT + 20):
        try:
            server = socketserver.TCPServer(("", port), DashboardHTTPRequestHandler)
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
    
    # Автоматически открываем браузер
    webbrowser.open(url)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n🛑 Сервер остановлен пользователем.")
        server.server_close()

if __name__ == "__main__":
    main()

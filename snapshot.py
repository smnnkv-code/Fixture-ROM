import os
import json
import hashlib
import datetime

# Пути
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, "Downloads")
SNAPSHOTS_DIR = os.path.join(BASE_DIR, "Snapshots")

def get_sha256(filepath):
    """Вычисляет контрольную сумму SHA-256 для файла."""
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(65536), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        print(f"Ошибка при вычислении хэша для {filepath}: {e}")
        return None

def scan_downloads():
    """Сканирует папку Downloads и собирает информацию о файлах."""
    files_data = {}
    if not os.path.exists(DOWNLOADS_DIR):
        print(f"Папка {DOWNLOADS_DIR} не найдена.")
        return files_data

    for root, _, files in os.walk(DOWNLOADS_DIR):
        for file in files:
            if file.startswith('.') or file == "metadata.json":
                continue
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, DOWNLOADS_DIR)
            
            # Собираем данные
            size = os.path.getsize(full_path)
            sha = get_sha256(full_path)
            if sha is None:
                continue
            mtime = os.path.getmtime(full_path)
            
            files_data[rel_path] = {
                "rel_path": rel_path,
                "filename": file,
                "size": size,
                "sha256": sha,
                "mtime": mtime
            }
    return files_data

def get_next_version():
    """Определяет следующую версию слепка на основе существующих файлов."""
    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
    max_ver = 0
    for name in os.listdir(SNAPSHOTS_DIR):
        if name.startswith("structure_v") and name.endswith(".json"):
            try:
                # Извлекаем версию из structure_v[N].json
                ver_str = name.replace("structure_v", "").replace(".json", "")
                ver = int(ver_str)
                if ver > max_ver:
                    max_ver = ver
            except ValueError:
                pass
    return max_ver + 1

def main():
    print("=== Сканирование папки Downloads ===")
    files_data = scan_downloads()
    
    version = get_next_version()
    filename = f"structure_v{version}.json"
    snapshot_path = os.path.join(SNAPSHOTS_DIR, filename)
    
    snapshot_content = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "version": version,
        "files": files_data
    }
    
    try:
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(snapshot_content, f, indent=4, ensure_ascii=False)
        print(f"Слепок структуры успешно сохранен:")
        print(f"📂 {snapshot_path}")
        print(f"Найдено файлов: {len(files_data)}")
    except Exception as e:
        print(f"Ошибка при сохранении слепка: {e}")

if __name__ == "__main__":
    main()

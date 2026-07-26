import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SNAPSHOTS_DIR = os.path.join(BASE_DIR, "Snapshots")
BLACKLIST_FILE = os.path.join(SNAPSHOTS_DIR, "blacklist.json")
REPORT_FILE = os.path.join(SNAPSHOTS_DIR, "diff_report.txt")

def load_snapshot(filename):
    path = os.path.join(SNAPSHOTS_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_sorted_snapshots():
    if not os.path.exists(SNAPSHOTS_DIR):
        return []
    files = []
    for name in os.listdir(SNAPSHOTS_DIR):
        if name.startswith("structure_v") and name.endswith(".json"):
            try:
                ver = int(name.replace("structure_v", "").replace(".json", ""))
                files.append((ver, name))
            except ValueError:
                pass
    files.sort()
    return files

def main():
    print("=== Запуск Diff Engine ===")
    snapshots = get_sorted_snapshots()
    if len(snapshots) < 2:
        print("Ошибка: Найдено менее двух слепков в папке Snapshots/.")
        print("Необходимо создать хотя бы два слепка с помощью snapshot.py.")
        return

    v_prev_ver, v_prev_name = snapshots[-2]
    v_curr_ver, v_curr_name = snapshots[-1]
    
    print(f"Сравниваем слепки: {v_prev_name} (v{v_prev_ver}) и {v_curr_name} (v{v_curr_ver})")
    
    snap_prev = load_snapshot(v_prev_name)
    snap_curr = load_snapshot(v_curr_name)
    
    prev_files = snap_prev.get("files", {})
    curr_files = snap_curr.get("files", {})
    
    # Индексируем текущие файлы по хэшу
    hash_to_curr = {}
    for rel_path, info in curr_files.items():
        sha = info["sha256"]
        if sha not in hash_to_curr:
            hash_to_curr[sha] = []
        hash_to_curr[sha].append(rel_path)
        
    # Индексируем старые файлы по хэшу
    hash_to_prev = {}
    for rel_path, info in prev_files.items():
        sha = info["sha256"]
        if sha not in hash_to_prev:
            hash_to_prev[sha] = []
        hash_to_prev[sha].append(rel_path)

    deleted = []
    added = []
    renamed = []
    modified = []
    rules = {}
    new_blacklist = set()
    # 1. Проверяем файлы из старого слепка
    for rel_path, info_prev in prev_files.items():
        sha = info_prev["sha256"]
        fn = info_prev["filename"]

        if rel_path in curr_files:
            # Файл остался на месте, проверяем хэш
            info_curr = curr_files[rel_path]
            if info_curr["sha256"] != sha:
                # Файл был изменен (тот же путь, другой хэш)
                modified.append(rel_path)
        else:
            # Пути больше нет. Смотрим, остался ли хэш в новом слепке
            if sha in hash_to_curr:
                # Файл переименован или перемещен
                new_rel_paths = hash_to_curr[sha]
                for new_path in new_rel_paths:
                    renamed.append({
                        "old_path": rel_path,
                        "new_path": new_path,
                        "sha256": sha
                    })
                    # Формируем правила переименования
                    rules[fn] = new_path
                    rules[sha] = new_path
            else:
                # Файл удален (мусор)
                deleted.append(rel_path)
                new_blacklist.add(sha)
                new_blacklist.add(fn)
                # raw-имя/URL из метаданных, чтобы sync.py отсеивал ДО скачивания
                meta_path = os.path.join(BASE_DIR, "Downloads", "metadata.json")
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, "r", encoding="utf-8") as mf:
                            metadata_db = json.load(mf)
                        for _key, _info in metadata_db.items():
                            if _info.get("filename") == fn or _key == fn:
                                if _info.get("url"):
                                    new_blacklist.add(_info["url"])
                                new_blacklist.add(_key)
                    except (OSError, json.JSONDecodeError):
                        pass

    # 2. Проверяем новые файлы в текущем слепке
    for rel_path, info_curr in curr_files.items():
        sha = info_curr["sha256"]
        if rel_path not in prev_files:
            # Путь новый. Проверяем, был ли хэш в старом слепке
            if sha not in hash_to_prev:
                # Файл действительно новый
                added.append(rel_path)
                
    # 3. Сохраняем отчет (diff_report.txt)
    report_lines = [
        f"=== Отчет о разнице структуры (v{v_prev_ver} -> v{v_curr_ver}) ===",
        f"Дата сравнения: {snap_curr.get('timestamp')}",
        "",
        f"Удалено файлов (мусор): {len(deleted)}",
        f"Добавлено новых файлов: {len(added)}",
        f"Переименовано/перемещено файлов: {len(renamed)}",
        f"Изменено файлов (тот же путь, другой хэш): {len(modified)}",
        "",
        "--- ДЕТАЛЬНЫЙ СПИСОК ---",
    ]

    if deleted:
        report_lines.append("\n❌ Удаленные файлы:")
        for p in deleted:
            report_lines.append(f"  - {p}")

    if added:
        report_lines.append("\n✨ Новые файлы:")
        for p in added:
            report_lines.append(f"  - {p}")

    if renamed:
        report_lines.append("\n🔄 Переименованные/перемещенные файлы:")
        for r in renamed:
            report_lines.append(f"  - Из: {r['old_path']}\n    В:  {r['new_path']}\n    Хэш: {r['sha256']}")

    if modified:
        report_lines.append("\n✏️ Изменённые файлы:")
        for p in modified:
            report_lines.append(f"  - {p}")
            
    report_content = "\n".join(report_lines)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report_content)
        
    print(f"Отчет успешно сохранен в: {REPORT_FILE}")
    
    # 4. Сохраняем карту правил (rules_v[N].json)
    rules_filename = f"rules_v{v_curr_ver}.json"
    rules_path = os.path.join(SNAPSHOTS_DIR, rules_filename)
    with open(rules_path, "w", encoding="utf-8") as f:
        json.dump(rules, f, indent=4, ensure_ascii=False)
    print(f"Карта переименований сохранена в: {rules_path}")
    
    # Также сохраняем/обновляем общую карту rules.json в Snapshots/
    master_rules_path = os.path.join(SNAPSHOTS_DIR, "rules.json")
    master_rules = {}
    if os.path.exists(master_rules_path):
        try:
            with open(master_rules_path, "r", encoding="utf-8") as f:
                master_rules = json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    master_rules.update(rules)
    with open(master_rules_path, "w", encoding="utf-8") as f:
        json.dump(master_rules, f, indent=4, ensure_ascii=False)
    
    # 5. Обновляем blacklist.json
    blacklist_data = []
    if os.path.exists(BLACKLIST_FILE):
        try:
            with open(BLACKLIST_FILE, "r", encoding="utf-8") as f:
                blacklist_data = json.load(f)
                if not isinstance(blacklist_data, list):
                    blacklist_data = []
        except (OSError, json.JSONDecodeError):
            pass

    # Объединяем списки уникально
    blacklist_set = set(blacklist_data)
    blacklist_set.update(new_blacklist)
    blacklist_data = sorted(list(blacklist_set))
    
    with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(blacklist_data, f, indent=4, ensure_ascii=False)
    print(f"Черный список blacklist.json обновлен. Всего записей: {len(blacklist_data)}")

if __name__ == "__main__":
    main()

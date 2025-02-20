import os

def collect_repo_code(repo_path: str, output_file: str = "collected_code.txt"):
    with open(output_file, "w", encoding="utf-8") as f_out:
        for root, dirs, files in os.walk(repo_path):
            # Исключаем каталог venv
            if "venv" in root:
                continue
            
            for file_name in files:
                # Пропускаем скрытые и потенциально бинарные файлы
                if file_name.startswith('.') or any(file_name.endswith(ext) for ext in ['.png','.jpg','.jpeg','.gif','.pdf','.exe','.dll']):
                    continue

                file_path = os.path.join(root, file_name)
                try:
                    with open(file_path, "r", encoding="utf-8") as f_in:
                        f_out.write(f"\n\n--- File: {file_path} ---\n\n")
                        f_out.write(f_in.read())
                except:
                    # Если не удаётся прочитать файл как текст, пропускаем
                    continue

if __name__ == "__main__":
    # Задайте путь к репозиторию
    collect_repo_code("./")

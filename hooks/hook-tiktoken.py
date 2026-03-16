from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# Собираем все подмодули tiktoken_ext, которые отвечают за кодировки
hiddenimports = collect_submodules('tiktoken_ext')

# Если есть какие-то дополнительные файлы данных (хотя обычно их нет)
datas = collect_data_files('tiktoken')

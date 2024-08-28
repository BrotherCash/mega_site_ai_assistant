from modules.database_manager import SQLiteDB
from modules.html_parser import ContentDownloader, FolderCleaner  # moved
from modules.logger_config import setup_logging  # moved

# Настройка логгера
logger = setup_logging()

# Создаем подключение к базе данных
db = SQLiteDB("bot.db")

# Загрузка настроек для data_downloader_settings
dds_query = "SELECT folder, content_formatter FROM data_downloader_settings LIMIT 1"
db.cur.execute(dds_query)
settings = db.cur.fetchone()
if settings:
    folder, content_formatter = settings
else:
    logger.warning("No data_downloader_settings found.")
    folder, content_formatter = None, None

# Загрузка URL-адресов
urls_query = "SELECT url FROM urls"
db.cur.execute(urls_query)
urls_to_crawl = set(url[0] for url in db.cur.fetchall())

print(f"Будет обработано ссылок -  {len(urls_to_crawl)}")

# Чистим целевую папку
folder_cleaner = FolderCleaner()
folder_cleaner.clear_folder(folder)

# Создаем экземпляр загрузчика, задаем целевую папку и форматтер контента
content_downloader = ContentDownloader(folder, content_formatter)

# Скачиваем контент
for url in urls_to_crawl:
    content_downloader.save_content(url)

# Не забываем закрыть соединение с базой данных
db.close()

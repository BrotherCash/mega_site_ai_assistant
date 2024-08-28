import asyncio
import sys
from dotenv import load_dotenv
import os

from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.extractors import (
    SummaryExtractor,
    QuestionsAnsweredExtractor,
    TitleExtractor,
    KeywordExtractor,
)

from modules.data_indexer import DataIndexer
from modules.logger_config import setup_logging
from modules.database_manager import SQLiteDB  # Импорт класса для работы с базой данных

# Настройка логгера
logger = setup_logging()

# предотвращение бага asyncio при ответе на Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Загрузка переменных окружения
dotenv_path = '../.env'
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

# Подключение к базе данных
db = SQLiteDB("bot.db")

# Извлечение настроек для загрузки данных
downloader_settings_query = "SELECT folder, content_formatter FROM data_downloader_settings WHERE id = 1"
db.cur.execute(downloader_settings_query)
downloader_settings = db.cur.fetchone()
if downloader_settings:
    download_folder, content_format = downloader_settings
else:
    logger.warning("No downloader settings found.")
    download_folder, content_format = None, None

# Извлечение настроек индексации данных
indexer_settings_query = """
SELECT title_extractor_nodes, questions_answered_extractor_questions, 
       keyword_extractor_keywords, index_persist_dir, force_index, chunk_size, 
       chunk_overlap, llm_temperature, llm_model 
FROM data_indexer_settings WHERE id = 1"""
db.cur.execute(indexer_settings_query)
indexer_settings = db.cur.fetchone()
if indexer_settings:
    (title_nodes, qa_questions, keywords, index_directory, force_index,
     data_chunk_size, overlap, model_temperature, llm_model_name) = indexer_settings
else:
    logger.warning("No indexer settings found.")
    # Задать значения по умолчанию или обработать отсутствие настроек

# Извлечение настроек запроса
request_settings_query = "SELECT top_k_value, question, question_extra_data FROM request_settings WHERE id = 1"
db.cur.execute(request_settings_query)
request_settings = db.cur.fetchone()
if request_settings:
    top_k, initial_question, extra_data = request_settings
    full_question = f"{initial_question} {extra_data}"
else:
    logger.warning("No request settings found.")
    top_k, full_question = None, ""

# Определение трансформаций для индексации
transformations = [
    SentenceSplitter(),
    TitleExtractor(nodes=title_nodes),
    QuestionsAnsweredExtractor(questions=qa_questions),
    SummaryExtractor(summaries=["prev", "self"]),
    KeywordExtractor(keywords=keywords),
]

# Индексация данных
data_indexer = DataIndexer(
    folder=download_folder,
    persist_dir=index_directory,
    force_indexing=bool(force_index)
)
index = data_indexer.index_data(
    transformations=transformations,
    chunk_size=data_chunk_size,
    chunk_overlap=overlap,
    temperature=model_temperature,
    model=llm_model_name
)

# Выполнение запроса
query_engine = index.as_query_engine(similarity_top_k=top_k)
response = query_engine.query(full_question)

print(response)

# Закрытие подключения к базе данных
db.close()


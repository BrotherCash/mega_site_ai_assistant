import asyncio
import sys
from dotenv import load_dotenv
import os

from modules.database_manager import SQLiteDB
from modules.html_parser import ContentDownloader, FolderCleaner
from modules.data_indexer import DataIndexer
from modules.logger_config import setup_logging
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.extractors import (
    SummaryExtractor,
    QuestionsAnsweredExtractor,
    TitleExtractor,
    KeywordExtractor,
)

# Настройка логгера и переменных окружения
logger = setup_logging()
dotenv_path = '../.env'
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def main():
    with SQLiteDB("bot.db") as db:
        # Извлечение настроек
        db.cur.execute("SELECT folder, content_formatter FROM data_downloader_settings LIMIT 1")
        downloader_settings = db.cur.fetchone()
        if downloader_settings:
            folder, content_formatter, download_enabled = downloader_settings
        else:
            logger.warning("No data_downloader_settings found.")
            return

        db.cur.execute("SELECT url FROM urls")
        urls_to_crawl = set(url[0] for url in db.cur.fetchall())

        db.cur.execute("""
        SELECT title_extractor_nodes, questions_answered_extractor_questions, keyword_extractor_keywords, 
               index_persist_dir, force_index, chunk_size, chunk_overlap, llm_temperature, llm_model 
        FROM data_indexer_settings WHERE id = 1""")
        indexer_settings = db.cur.fetchone()

        db.cur.execute("SELECT top_k_value, question, question_extra_data FROM request_settings WHERE id = 1")
        request_settings = db.cur.fetchone()

    if not indexer_settings or not request_settings:
        logger.warning("Missing indexer or request settings.")
        return
    (title_nodes,
     qa_questions,
     keywords,
     index_directory,
     force_index,
     data_chunk_size,
     overlap,
     model_temperature,
     llm_model_name) = indexer_settings
    top_k, initial_question, extra_data = request_settings
    full_question = f"{initial_question} {extra_data}"
    # Проверка, требуется ли загрузка данных
    if download_enabled:
        print(f"Будет обработано ссылок - {len(urls_to_crawl)}")

        # Загрузка и обработка контента
        folder_cleaner = FolderCleaner()
        folder_cleaner.clear_folder(folder)
        content_downloader = ContentDownloader(folder, content_formatter)
        for url in urls_to_crawl:
            content_downloader.save_content(url)

    # Индексация и выполнение запроса
    data_indexer = DataIndexer(folder=folder, persist_dir=index_directory, force_indexing=bool(force_index))

    transformations = [
        SentenceSplitter(),
        TitleExtractor(nodes=title_nodes),
        QuestionsAnsweredExtractor(questions=qa_questions),
        SummaryExtractor(summaries=["prev", "self"]),
        KeywordExtractor(keywords=keywords),
    ]
    index = data_indexer.index_data(transformations=transformations, chunk_size=data_chunk_size, chunk_overlap=overlap, temperature=model_temperature, model=llm_model_name)

    query_engine = index.as_query_engine(similarity_top_k=top_k)
    response = query_engine.query(full_question)
    print(response)


if __name__ == "__main__":
    main()

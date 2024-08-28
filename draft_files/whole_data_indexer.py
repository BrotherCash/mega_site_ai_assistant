import asyncio

import os
from dotenv import load_dotenv

# импорт библиотек для логирования
import logging
import sys
from llama_index.llms.openai import OpenAI
# импортируем библиотеки векторного хранилища и веб-лоадера
from llama_index.core import VectorStoreIndex, StorageContext, load_index_from_storage, Settings, SimpleDirectoryReader
from llama_index.core.node_parser import SentenceSplitter

from llama_index.core.extractors import (
    SummaryExtractor,
    QuestionsAnsweredExtractor,
    TitleExtractor,
    KeywordExtractor,
)
from llama_index.core.ingestion import IngestionPipeline

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Загрузка ключа OPEN-AI из переменной окружения
dotenv_path = os.path.join(os.path.dirname(__file__), '../.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)


# Логирование событий в лайтовом режиме INFO
logging.basicConfig(stream=sys.stdout, format='%(levelname)s:%(message)s', level=logging.INFO)
# logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler(stream=sys.stdout))

# Global library settings
Settings.chunk_size = 1024  # default is 1024, требует пересоздания индекса
Settings.chunk_overlap = 20  # default is 20, требует пересоздания индекса
Settings.llm = OpenAI(temperature=0, model='gpt-3.5-turbo')  # от 0 до 2
top_k_value = 5  # default 2, but 5 seems a bit better, пересоздание индекса не требуется

# базовые локальные переменные
FOLDER = "./help"
PERSIST_DIR = "../storage"  # Директория для хранения индекса
force_indexing = False

question = "Я хочу фотогаллерею на свой сайт. Отвечай на русском. Ответь в развернутой форме. В конце ответа добавь ссылку на основную статью."

transformations = [
    SentenceSplitter(),
    TitleExtractor(nodes=5),
    QuestionsAnsweredExtractor(questions=3),
    SummaryExtractor(summaries=["prev", "self"]),
    KeywordExtractor(keywords=10),
]

pipeline = IngestionPipeline(transformations=transformations)


if not os.path.exists(PERSIST_DIR) or force_indexing is True:
    documents = SimpleDirectoryReader(FOLDER).load_data()
    logger.info(f"Загружено документов - {len(documents)}")

    nodes = pipeline.run(documents=documents)

        # Создаем индекс
    index = VectorStoreIndex.from_documents(
        documents
    )
    logger.info("Cоздан индекс")

    index.insert_nodes(nodes)
    # store it for later
    index.storage_context.persist(persist_dir=PERSIST_DIR)
    logger.info("Индекс сохранен")
else:
    # load the existing index
    storage_context = StorageContext.from_defaults(persist_dir=PERSIST_DIR)
    index = load_index_from_storage(storage_context)
    logger.info("Загружен сохраненный ранее индекс")


# Создаем движок запросов
query_engine = index.as_query_engine(similarity_top_k=top_k_value)

# Отправляем запрос и выводим ответ

response = query_engine.query(question)


print(response)

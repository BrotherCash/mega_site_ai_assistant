import os
from dotenv import load_dotenv

# импорт библиотек для логирования
import logging
import sys

# импортируем библиотеки векторного хранилища и веб-лоадера
from llama_index.core import VectorStoreIndex, StorageContext, load_index_from_storage, Settings, SimpleDirectoryReader


from llama_index.llms.openai import OpenAI
from llama_index.core.node_parser import HTMLNodeParser, TokenTextSplitter, SentenceSplitter
from llama_index.core.extractors import TitleExtractor, QuestionsAnsweredExtractor
from llama_index.core.ingestion import IngestionPipeline


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
Settings.chunk_size = 512  # default is 1024, требует пересоздания индекса
Settings.chunk_overlap = 20  # default is 20, требует пересоздания индекса
Settings.llm = OpenAI(temperature=0, model='gpt-3.5-turbo')  # от 0 до 2
top_k_value = 2  # default 2, but 5 seems a bit better, пересоздание индекса не требуется

# базовые локальные переменные
FOLDER = "./help"
PERSIST_DIR = "../storage"  # Директория для хранения индекса
force_indexing = True
# urls_to_index = ['https://help.megagroup.ru/cms/basic/new']
question = "Как мне создать новую страницу?. Отвечай на русском. Ответь в развернутой форме. В конце ответа добавь ссылку на статью."

text_splitter = TokenTextSplitter(
    separator=" ", chunk_size=512, chunk_overlap=128
)
parser = HTMLNodeParser()
title_extractor = TitleExtractor(nodes=3)
qa_extractor = QuestionsAnsweredExtractor(questions=2)

pipeline = IngestionPipeline(
    transformations=[text_splitter, title_extractor, qa_extractor]
)

if not os.path.exists(PERSIST_DIR) or force_indexing is True:
    documents = SimpleDirectoryReader(FOLDER).load_data()
    logger.info(f"Загружено документов - {len(documents)}")

    # nodes = parser.get_nodes_from_documents(documents)
    nodes = pipeline.run(
        documents=documents,
        in_place=True,
        show_progress=True,
    )
    logger.info(f"Создано нод - {len(nodes)}")

        # Создаем индекс
    index = VectorStoreIndex.from_documents(documents)
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
#
# Отправляем запрос и выводим ответ
response = query_engine.query(question)
print(response)

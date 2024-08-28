import os
from dotenv import load_dotenv

# импорт библиотек для логирования
import logging
import sys

# импортируем библиотеки векторного хранилища и веб-лоадера
from llama_index.core import VectorStoreIndex, StorageContext, load_index_from_storage, Settings
from llama_index.readers.web import BeautifulSoupWebReader


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
Settings.chunk_size = 1024  # default is 1024
Settings.chunk_overlap = 20  # default is 20
top_k_value = 5  # default 2, but 5 seems a bit better

# базовые локальные переменные
PERSIST_DIR = "../storage"  # Директория для хранения индекса
force_indexing = True
urls_to_index = ['https://help.megagroup.ru/cms/basic/new']
question = "Не могу создать страницу на сайте. Отвечай на русском. Распиши действия по пунктам. К ответу добавь ссылку на статью."

# создаем экземпляр лоадера
loader = BeautifulSoupWebReader()

# check if storage already exists
if not os.path.exists(PERSIST_DIR) or force_indexing is True:

    print('Reindexing...')

    # Грузим данные лоадером
    print(f"Будет обработано ссылок - {len(urls_to_index)}")
    documents = loader.load_data(urls=urls_to_index, custom_hostname='help.megagroup.ru')
    print(f"Загружено документов - {len(documents)}")

    # Создаем индекс
    index = VectorStoreIndex.from_documents(documents)

    # store it for later
    index.storage_context.persist(persist_dir=PERSIST_DIR)
else:
    # load the existing index
    storage_context = StorageContext.from_defaults(persist_dir=PERSIST_DIR)
    index = load_index_from_storage(storage_context)

# Создаем движок запросов
query_engine = index.as_query_engine(similarity_top_k=top_k_value)

# Отправляем запрос и выводим ответ
response = query_engine.query(question)
print(response)

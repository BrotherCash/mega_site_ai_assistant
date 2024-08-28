import os
import json
from .logger_config import setup_logging
from llama_index.core import VectorStoreIndex, StorageContext, load_index_from_storage, Settings, SimpleDirectoryReader, Document
from llama_index.core.ingestion import IngestionPipeline
from llama_index.llms.openai import OpenAI
import pickle


class DataIndexer:
    def __init__(self, folder="./help", persist_dir="./storage", force_indexing=False, add_to_index=True):
        self.folder = folder
        self.persist_dir = persist_dir
        self.force_indexing = force_indexing
        self.logger = setup_logging()
        self.add_to_index = add_to_index

    def index_data(self, transformations=[], chunk_size=256, chunk_overlap=25, temperature=0, model='gpt-3.5-turbo'):
        Settings.chunk_size = chunk_size
        Settings.chunk_overlap = chunk_overlap
        Settings.llm = OpenAI(temperature=temperature, model=model)

        pipeline = IngestionPipeline(transformations=transformations)

        if not os.path.exists(self.persist_dir) or self.force_indexing is True:
            def get_meta(file_path):
                meta_data = {}

                with open(file_path, 'r', encoding='utf-8') as file:
                    lines = file.readlines()

                    for line in lines:
                        if line.startswith("[Ссылка на статью:"):
                            meta_data["article_url"] = line.split(": ", 1)[1].strip().strip("]")
                        elif line.startswith("[Заголовок статьи:"):
                            meta_data["article_title"] = line.split(": ", 1)[1].strip().strip("]")
                        elif line.startswith("[Видео:"):
                            video_links = line.split(": ", 1)[1].strip().strip("[]").replace("'", "").split(", ")
                            meta_data["article_video"] = video_links

                return meta_data

            reader = SimpleDirectoryReader(input_dir=self.folder, file_metadata=get_meta)
            documents = reader.load_data()
            self.logger.info(f"Загружено документов - {len(documents)}")

            nodes = pipeline.run(
                documents=documents
            )

            # 1st we make index
            if self.add_to_index is False:
                index = VectorStoreIndex(nodes)
                self.logger.info("Cоздан индекс")
            else:
                # then we load index make new nodes and insert them
                storage_context = StorageContext.from_defaults(persist_dir=self.persist_dir)
                index = load_index_from_storage(storage_context)
                index.insert_nodes(nodes)
                self.logger.info("Индекс расширен новыми нодами")

            index.storage_context.persist(persist_dir=self.persist_dir)
            self.logger.info("Индекс сохранен")
        else:
            storage_context = StorageContext.from_defaults(persist_dir=self.persist_dir)
            index = load_index_from_storage(storage_context)
            self.logger.info("Загружен сохраненный ранее индекс")

            return index


class DataIndexer_old:
    def __init__(self, folder="./help", persist_dir="./storage", force_indexing=False, add_to_index=True):
        self.folder = folder
        self.persist_dir = persist_dir
        self.force_indexing = force_indexing
        self.logger = setup_logging()
        self.add_to_index = add_to_index

    def get_meta(self, file_path):
        meta_data = {}

        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)

            meta_data["chapter"] = data.get("chapter", "")
            meta_data["article_url"] = data.get("article_url", "")
            meta_data["article_title"] = data.get("article_title", "")
            # meta_data["article subtitles"] = ", ".join(
            #     data.get("article_subtitles", []))  # Объединяем подзаголовки в строку
            # meta_data["article images"] = ", ".join(
            #     data.get("article_images", []))  # Объединяем ссылки на изображения в строку
            meta_data["article_video"] = ", ".join(data.get("article_video", []))  # Объединяем ссылки на видео в строку
            meta_data["article_text"] = data.get("article_text", "")

        return meta_data

    def index_data(self, transformations=[], chunk_size=256, chunk_overlap=25, temperature=0, model='gpt-3.5-turbo'):
        Settings.chunk_size = chunk_size
        Settings.chunk_overlap = chunk_overlap
        Settings.llm = OpenAI(temperature=temperature, model=model)

        pipeline = IngestionPipeline(transformations=transformations)

        if not os.path.exists(self.persist_dir) or self.force_indexing is True:
            files = [os.path.join(self.folder, f) for f in os.listdir(self.folder) if
                     os.path.isfile(os.path.join(self.folder, f))]
            self.logger.info(f"Загружено файлов - {len(files)}")

            nodes = []
            for file_path in files:
                meta_data = self.get_meta(file_path)
                node = Document(
                    text=meta_data.pop("article_text"),  # Используем article_text в качестве текста документа
                    metadata=meta_data  # Используем остальные поля в качестве метаданных
                )
                nodes.append(node)

            nodes = pipeline.run(documents=nodes)

            if self.add_to_index is False:
                index = VectorStoreIndex(nodes)
                self.logger.info("Создан индекс")
            else:
                storage_context = StorageContext.from_defaults(persist_dir=self.persist_dir)
                index = load_index_from_storage(storage_context)
                index.insert_nodes(nodes)
                self.logger.info("Индекс расширен новыми нодами")

            index.storage_context.persist(persist_dir=self.persist_dir)
            self.logger.info("Индекс сохранен")
        else:
            storage_context = StorageContext.from_defaults(persist_dir=self.persist_dir)
            index = load_index_from_storage(storage_context)
            self.logger.info("Загружен сохраненный ранее индекс")

        return index



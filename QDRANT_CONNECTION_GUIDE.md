***REMOVED*** Руководство по подключению к Qdrant

***REMOVED******REMOVED*** Обзор

Qdrant развернут на удаленном сервере и доступен как локально (на сервере), так и удаленно (с вашей машины).

***REMOVED******REMOVED******REMOVED*** Информация о сервере

- **IP адрес**: REDACTED_VPS_IP
- **SSH порт**: 1654
- **SSH пользователь**: admin
- **SSH ключ**: ~/.ssh/vps_access_key
- **Алиас для подключения**: `vps` (определен в ~/.zshrc)

***REMOVED******REMOVED******REMOVED*** Информация о Qdrant

- **Версия**: 1.15.4
- **Docker контейнер**: `ai-qdrant`
- **HTTP порт**: 6333
- **gRPC порт**: 6334
- **API ключ**: REDACTED_QDRANT_KEY

***REMOVED******REMOVED*** Текущее состояние

***REMOVED******REMOVED******REMOVED*** Коллекции

На данный момент существует **1 коллекция**:

**legal_documents**
- Точек (vectors): 1,294
- Индексированных векторов: 3,878
- Статус: GREEN (здоров)
- Конфигурация векторов:
  - **dense**: 1024-размерность, Cosine similarity, HNSW индекс (M=16, ef_construct=200)
    - Квантизация: int8 (scalar)
    - On-disk хранение
  - **colbert**: 1024-размерность, Cosine similarity, мультивектор (max_sim)
    - HNSW отключен (M=0)
  - **sparse**: IDF модификатор для sparse vectors

***REMOVED******REMOVED*** Конфигурация подключения

***REMOVED******REMOVED******REMOVED*** 1. Для локальной разработки (с вашей машины)

Используйте основной `.env` файл:

```bash
***REMOVED*** .env
QDRANT_URL=http://REDACTED_VPS_IP:6333
QDRANT_API_KEY=REDACTED_QDRANT_KEY
```

***REMOVED******REMOVED******REMOVED*** 2. Для работы на сервере

Используйте `.env.server`:

```bash
***REMOVED*** Скопировать конфигурацию для сервера
cp .env.server .env

***REMOVED*** Или создать символическую ссылку
ln -sf .env.server .env
```

Содержимое `.env.server`:
```bash
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=REDACTED_QDRANT_KEY
```

***REMOVED******REMOVED*** Проверка подключения

***REMOVED******REMOVED******REMOVED*** 1. Через curl (с локальной машины)

```bash
***REMOVED*** Получить список коллекций
curl -s -H 'api-key: REDACTED_QDRANT_KEY' \
  http://REDACTED_VPS_IP:6333/collections

***REMOVED*** Информация о конкретной коллекции
curl -s -H 'api-key: REDACTED_QDRANT_KEY' \
  http://REDACTED_VPS_IP:6333/collections/legal_documents
```

***REMOVED******REMOVED******REMOVED*** 2. Через curl (на сервере)

```bash
***REMOVED*** Подключиться к серверу
ssh -i ~/.ssh/vps_access_key -p 1654 admin@REDACTED_VPS_IP

***REMOVED*** Или используя алиас из ~/.zshrc
zsh -c "$(grep 'alias vps=' ~/.zshrc | cut -d'=' -f2-)"

***REMOVED*** Проверить коллекции
curl -s -H 'api-key: REDACTED_QDRANT_KEY' \
  http://localhost:6333/collections
```

***REMOVED******REMOVED******REMOVED*** 3. Через Python (тестовый скрипт)

Создан тестовый скрипт `test_qdrant_connection.py`:

```bash
***REMOVED*** На сервере (с установленными зависимостями)
python3 test_qdrant_connection.py

***REMOVED*** Или через poetry (если установлен)
poetry run python test_qdrant_connection.py
```

***REMOVED******REMOVED******REMOVED*** 4. Проверка Docker контейнера

```bash
***REMOVED*** На сервере
ssh -i ~/.ssh/vps_access_key -p 1654 admin@REDACTED_VPS_IP \
  "docker ps | grep qdrant"

***REMOVED*** Вывод:
***REMOVED*** 218ec1ea2aa1   qdrant/qdrant:v1.15.4   Up 2 hours (healthy)
```

***REMOVED******REMOVED*** Использование в коде

***REMOVED******REMOVED******REMOVED*** Python (qdrant-client)

```python
from qdrant_client import QdrantClient
from src.config.settings import Settings

***REMOVED*** Загрузить настройки из .env
settings = Settings()

***REMOVED*** Создать клиента
client = QdrantClient(
    url=settings.qdrant_url,  ***REMOVED*** Автоматически берется из .env
    api_key=settings.qdrant_api_key
)

***REMOVED*** Получить коллекции
collections = client.get_collections()
print(f"Коллекций: {len(collections.collections)}")

***REMOVED*** Получить информацию о коллекции
info = client.get_collection("legal_documents")
print(f"Точек: {info.points_count}")
```

***REMOVED******REMOVED*** Важные заметки

1. **API ключ обязателен**: Qdrant настроен с обязательной аутентификацией
2. **Порты открыты**: Порты 6333 и 6334 доступны извне (0.0.0.0)
3. **Два варианта конфигурации**:
   - `.env` - для локальной разработки (удаленное подключение)
   - `.env.server` - для запуска на сервере (localhost)
4. **Безопасность**: API ключ хранится в .env (добавлен в .gitignore)

***REMOVED******REMOVED*** Troubleshooting

***REMOVED******REMOVED******REMOVED*** Ошибка: "Must provide an API key"

Убедитесь что передаете API ключ:
- В curl: `-H 'api-key: YOUR_KEY'`
- В Python: `api_key=settings.qdrant_api_key`

***REMOVED******REMOVED******REMOVED*** Ошибка: "Connection refused"

1. Проверьте что Qdrant запущен: `docker ps | grep qdrant`
2. Проверьте правильность URL в .env
3. Проверьте доступность порта 6333

***REMOVED******REMOVED******REMOVED*** Ошибка: "ModuleNotFoundError: qdrant_client"

Установите зависимости:
```bash
***REMOVED*** Через poetry
poetry install

***REMOVED*** Через pip (в виртуальном окружении)
python3 -m venv .venv
source .venv/bin/activate
pip install qdrant-client python-dotenv sentence-transformers
```

***REMOVED******REMOVED*** Полезные команды

```bash
***REMOVED*** Подключиться к серверу через SSH
ssh -i ~/.ssh/vps_access_key -p 1654 admin@REDACTED_VPS_IP

***REMOVED*** Проверить статус контейнера
docker ps -a | grep qdrant

***REMOVED*** Логи Qdrant
docker logs ai-qdrant --tail 100

***REMOVED*** Рестарт Qdrant
docker restart ai-qdrant

***REMOVED*** Проверить использование ресурсов
docker stats ai-qdrant --no-stream
```

***REMOVED******REMOVED*** Дополнительная информация

- **Документация Qdrant**: https://qdrant.tech/documentation/
- **API Reference**: https://qdrant.tech/documentation/api-reference/
- **Python Client**: https://github.com/qdrant/qdrant-client

---

**Последнее обновление**: 2025-10-29
**Статус**: ✅ Подключение настроено и протестировано

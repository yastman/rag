# Руководство по подключению к Qdrant

## Обзор

Qdrant развернут на удаленном сервере и доступен как локально (на сервере), так и удаленно (с вашей машины).

### Информация о сервере

- **IP адрес**: 95.111.252.29
- **SSH порт**: 1654
- **SSH пользователь**: admin
- **SSH ключ**: ~/.ssh/vps_access_key
- **Алиас для подключения**: `vps` (определен в ~/.zshrc)

### Информация о Qdrant

- **Версия**: 1.15.4
- **Docker контейнер**: `ai-qdrant`
- **HTTP порт**: 6333
- **gRPC порт**: 6334
- **API ключ**: REDACTED_QDRANT_KEY

## Текущее состояние

### Коллекции

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

## Конфигурация подключения

### 1. Для локальной разработки (с вашей машины)

Используйте основной `.env` файл:

```bash
# .env
QDRANT_URL=http://95.111.252.29:6333
QDRANT_API_KEY=REDACTED_QDRANT_KEY
```

### 2. Для работы на сервере

Используйте `.env.server`:

```bash
# Скопировать конфигурацию для сервера
cp .env.server .env

# Или создать символическую ссылку
ln -sf .env.server .env
```

Содержимое `.env.server`:
```bash
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=REDACTED_QDRANT_KEY
```

## Проверка подключения

### 1. Через curl (с локальной машины)

```bash
# Получить список коллекций
curl -s -H 'api-key: REDACTED_QDRANT_KEY' \
  http://95.111.252.29:6333/collections

# Информация о конкретной коллекции
curl -s -H 'api-key: REDACTED_QDRANT_KEY' \
  http://95.111.252.29:6333/collections/legal_documents
```

### 2. Через curl (на сервере)

```bash
# Подключиться к серверу
ssh -i ~/.ssh/vps_access_key -p 1654 admin@95.111.252.29

# Или используя алиас из ~/.zshrc
zsh -c "$(grep 'alias vps=' ~/.zshrc | cut -d'=' -f2-)"

# Проверить коллекции
curl -s -H 'api-key: REDACTED_QDRANT_KEY' \
  http://localhost:6333/collections
```

### 3. Через Python (тестовый скрипт)

Создан тестовый скрипт `test_qdrant_connection.py`:

```bash
# На сервере (с установленными зависимостями)
python3 test_qdrant_connection.py

# Или через poetry (если установлен)
poetry run python test_qdrant_connection.py
```

### 4. Проверка Docker контейнера

```bash
# На сервере
ssh -i ~/.ssh/vps_access_key -p 1654 admin@95.111.252.29 \
  "docker ps | grep qdrant"

# Вывод:
# 218ec1ea2aa1   qdrant/qdrant:v1.15.4   Up 2 hours (healthy)
```

## Использование в коде

### Python (qdrant-client)

```python
from qdrant_client import QdrantClient
from src.config.settings import Settings

# Загрузить настройки из .env
settings = Settings()

# Создать клиента
client = QdrantClient(
    url=settings.qdrant_url,  # Автоматически берется из .env
    api_key=settings.qdrant_api_key
)

# Получить коллекции
collections = client.get_collections()
print(f"Коллекций: {len(collections.collections)}")

# Получить информацию о коллекции
info = client.get_collection("legal_documents")
print(f"Точек: {info.points_count}")
```

## Важные заметки

1. **API ключ обязателен**: Qdrant настроен с обязательной аутентификацией
2. **Порты открыты**: Порты 6333 и 6334 доступны извне (0.0.0.0)
3. **Два варианта конфигурации**:
   - `.env` - для локальной разработки (удаленное подключение)
   - `.env.server` - для запуска на сервере (localhost)
4. **Безопасность**: API ключ хранится в .env (добавлен в .gitignore)

## Troubleshooting

### Ошибка: "Must provide an API key"

Убедитесь что передаете API ключ:
- В curl: `-H 'api-key: YOUR_KEY'`
- В Python: `api_key=settings.qdrant_api_key`

### Ошибка: "Connection refused"

1. Проверьте что Qdrant запущен: `docker ps | grep qdrant`
2. Проверьте правильность URL в .env
3. Проверьте доступность порта 6333

### Ошибка: "ModuleNotFoundError: qdrant_client"

Установите зависимости:
```bash
# Через poetry
poetry install

# Через pip (в виртуальном окружении)
python3 -m venv .venv
source .venv/bin/activate
pip install qdrant-client python-dotenv sentence-transformers
```

## Полезные команды

```bash
# Подключиться к серверу через SSH
ssh -i ~/.ssh/vps_access_key -p 1654 admin@95.111.252.29

# Проверить статус контейнера
docker ps -a | grep qdrant

# Логи Qdrant
docker logs ai-qdrant --tail 100

# Рестарт Qdrant
docker restart ai-qdrant

# Проверить использование ресурсов
docker stats ai-qdrant --no-stream
```

## Дополнительная информация

- **Документация Qdrant**: https://qdrant.tech/documentation/
- **API Reference**: https://qdrant.tech/documentation/api-reference/
- **Python Client**: https://github.com/qdrant/qdrant-client

---

**Последнее обновление**: 2025-10-29
**Статус**: ✅ Подключение настроено и протестировано

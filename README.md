# Algorithm Testing Service

Сервіс для тестування алгоритмів з системою черг та воркерів.

## Архітектура

```
API Request → Queue 1 (algorithm_calculation) → Worker 1 → Queue 2 (result_processing) → Worker 2
```

## Компоненти

-   **FastAPI** - API сервер
-   **Redis** - система черг
-   **RQ (Redis Queue)** - воркери для обробки завдань
-   **Docker** - контейнеризація

## Запуск

### Через Docker Compose (рекомендовано)

```bash
docker-compose up --build
```

### Локальний запуск

1. Встановити Redis локально
2. Встановити залежності:

```bash
pip install -r requirements.txt
```

3. Запустити API сервер:

```bash
uvicorn app.main:app --reload
```

4. Запустити воркерів (в окремих терміналах):

```bash
python workers/start_algorithm_worker.py
python workers/start_result_worker.py
```

## API Endpoints

### Основні endpoints

-   `GET /` - головна сторінка
-   `GET /health` - перевірка здоров'я
-   `GET /api/v1/start-testing/` - ініціалізація тестування
-   `POST /api/v1/start-testing/start` - запуск тестування алгоритму
-   `GET /api/v1/start-testing/status` - статус черг

### Моніторинг endpoints

-   `GET /api/v1/monitoring/queues` - детальна інформація про черги
-   `GET /api/v1/monitoring/workers` - інформація про воркерів
-   `GET /api/v1/monitoring/jobs/{queue_name}` - завдання в черзі
-   `GET /api/v1/monitoring/stats` - загальна статистика системи

## Приклад використання

### Запуск тестування алгоритму

```bash
curl -X POST "http://localhost:8000/api/v1/start-testing/start" \
     -H "Content-Type: application/json" \
     -d '{
       "algorithm_name": "quicksort",
       "input_data": {
         "array": [64, 34, 25, 12, 22, 11, 90]
       },
       "parameters": {
         "reverse": false
       }
     }'
```

### Перевірка статусу черг

```bash
curl -X GET "http://localhost:8000/api/v1/start-testing/status"
```

## Структура проекту

```
algorithm-testing-service/
├── app/
│   ├── main.py                    # FastAPI додаток
│   ├── controllers/               # Контролери
│   ├── models/                    # Pydantic моделі
│   ├── services/                  # Сервіси
│   ├── config/                    # Конфігурація
│   └── workers/                   # Воркери
├── workers/                       # Скрипти запуску воркерів
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## Додавання логіки

### Воркер алгоритмів (перша черга)

Файл: `app/workers/algorithm_worker.py`
Функція: `process_algorithm_task()`

### Воркер результатів (друга черга)

Файл: `app/workers/result_worker.py`
Функція: `process_result_task()`

## Моніторинг

### Веб-інтерфейси

-   **API документація**: http://localhost:8000/docs
-   **RQ Dashboard**: http://localhost:9181 - веб-інтерфейс для моніторингу черг
-   **Redis**: localhost:6379

### Моніторинг через API

-   `GET /api/v1/monitoring/queues` - статус черг
-   `GET /api/v1/monitoring/workers` - статус воркерів
-   `GET /api/v1/monitoring/stats` - загальна статистика

### Логи

-   Логи воркерів доступні через `docker-compose logs`
-   Логи всіх сервісів: `docker-compose logs -f`

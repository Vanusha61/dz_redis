# High Performance Storage Project

Один проект сразу для трёх ТЗ:

1. PostgreSQL + Memcached — кэширование блога.
2. Redis — аналитика и рекомендации в реальном времени.
3. DynamoDB Local — пользовательские профили SaaS.

## Запуск

Нужен только Docker Desktop.

```bash
docker compose up --build
```

После запуска:

- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- DynamoDB Local с хоста: http://localhost:8001

## Остановка

```bash
docker compose down
```

Удалить также все сохранённые данные:

```bash
docker compose down -v
```

---

# ТЗ 1 — Memcached

## Получить статью

```bash
curl -i http://localhost:8000/cache/articles/1
```

Первый запрос вернёт заголовок:

```text
X-Cache: MISS
```

Повторный запрос:

```text
X-Cache: HIT
```

## HTML-страница

```bash
curl -i http://localhost:8000/cache/articles/1/page
```

## Популярные статьи

```bash
curl -i http://localhost:8000/cache/articles/popular
```

## Добавить просмотр

```bash
curl -X POST http://localhost:8000/cache/articles/1/view
```

После изменения статьи связанный кэш инвалидируется.

---

# ТЗ 2 — Redis

## Зарегистрировать просмотр

```bash
curl -X POST http://localhost:8000/analytics/events/view \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"ivan\",\"article_id\":1}"
```

Используется:

- `INCR` — атомарный счётчик просмотров;
- `LIST` — последние действия;
- `SORTED SET` — рейтинг популярных статей;
- `STREAM` — очередь событий;
- AOF — персистентность Redis.

## Получить просмотры

```bash
curl http://localhost:8000/analytics/articles/1/views
```

## Последние действия пользователя

```bash
curl http://localhost:8000/analytics/users/ivan/actions
```

## Топ статей

```bash
curl http://localhost:8000/analytics/top
```

## Поставить оценку

```bash
curl -X POST http://localhost:8000/analytics/events/rating \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"ivan\",\"article_id\":1,\"rating\":5}"
```

Рейтинг пересчитывается атомарно Lua-скриптом внутри Redis.

## Топ по рейтингу

```bash
curl http://localhost:8000/analytics/ratings/top
```

## Последние события

```bash
curl http://localhost:8000/analytics/events
```

---

# ТЗ 3 — DynamoDB

## Создать профиль

```bash
curl -X POST http://localhost:8000/profiles \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\":\"ivan\",
    \"name\":\"Ivan\",
    \"email\":\"ivan@example.com\",
    \"plan\":\"premium\",
    \"preferences\":{
      \"theme\":\"dark\",
      \"language\":\"ru\"
    },
    \"subscription_history\":[
      {
        \"plan\":\"free\",
        \"started_at\":\"2026-01-01\"
      }
    ]
  }"
```

## Получить профиль

```bash
curl http://localhost:8000/profiles/ivan
```

## Обновить профиль

```bash
curl -X PATCH http://localhost:8000/profiles/ivan \
  -H "Content-Type: application/json" \
  -d "{
    \"plan\":\"business\",
    \"preferences\":{
      \"theme\":\"light\",
      \"language\":\"ru\",
      \"notifications\":true
    }
  }"
```

## Удалить профиль

```bash
curl -X DELETE http://localhost:8000/profiles/ivan
```

---

## Структура

```text
dz_redis/
├── main.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .gitignore
└── README.md
```

Главное место для проверки — Swagger:

http://localhost:8000/docs

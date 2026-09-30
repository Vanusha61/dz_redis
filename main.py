import json
import os
import time
from decimal import Decimal
from typing import Any

import boto3
import psycopg
import redis
from botocore.exceptions import ClientError
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr, Field
from pymemcache.client.base import Client as MemcachedClient


POSTGRES_DSN = os.getenv(
    "POSTGRES_DSN",
    "postgresql://blog:blog@postgres:5432/blog",
)

MEMCACHED_HOST = os.getenv("MEMCACHED_HOST", "memcached")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
DYNAMODB_ENDPOINT = os.getenv(
    "DYNAMODB_ENDPOINT",
    "http://dynamodb:8000",
)

memcached = MemcachedClient((MEMCACHED_HOST, 11211))
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=6379,
    decode_responses=True,
)

dynamodb = boto3.resource(
    "dynamodb",
    region_name="eu-central-1",
    endpoint_url=DYNAMODB_ENDPOINT,
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "local"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "local"),
)

profile_table = None

app = FastAPI(
    title="High Performance Storage Demo",
    version="1.0.0",
)


class ArticleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)


class ViewEvent(BaseModel):
    user_id: str
    article_id: int = Field(gt=0)


class RatingEvent(BaseModel):
    user_id: str
    article_id: int = Field(gt=0)
    rating: int = Field(ge=1, le=5)


class UserProfileCreate(BaseModel):
    user_id: str
    name: str
    email: EmailStr
    plan: str
    preferences: dict[str, Any] = {}
    subscription_history: list[dict[str, Any]] = []


class UserProfileUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    plan: str | None = None
    preferences: dict[str, Any] | None = None
    subscription_history: list[dict[str, Any]] | None = None


def db_connection():
    return psycopg.connect(POSTGRES_DSN)


def wait_for_services():
    global profile_table

    for _ in range(30):
        try:
            with db_connection() as conn:
                conn.execute("SELECT 1")
            redis_client.ping()
            memcached.set("healthcheck", "ok", expire=5)

            names = dynamodb.meta.client.list_tables()["TableNames"]

            if "user_profiles" not in names:
                profile_table = dynamodb.create_table(
                    TableName="user_profiles",
                    KeySchema=[
                        {
                            "AttributeName": "user_id",
                            "KeyType": "HASH",
                        }
                    ],
                    AttributeDefinitions=[
                        {
                            "AttributeName": "user_id",
                            "AttributeType": "S",
                        }
                    ],
                    BillingMode="PAY_PER_REQUEST",
                )
                profile_table.wait_until_exists()
            else:
                profile_table = dynamodb.Table("user_profiles")

            return
        except Exception:
            time.sleep(1)

    raise RuntimeError("Services are unavailable")


def init_postgres():
    with db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS articles (
                id SERIAL PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                content TEXT NOT NULL,
                views INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        count = conn.execute(
            "SELECT COUNT(*) FROM articles"
        ).fetchone()[0]

        if count == 0:
            conn.executemany(
                """
                INSERT INTO articles (title, content, views)
                VALUES (%s, %s, %s)
                """,
                [
                    ("Redis", "Статья про Redis", 150),
                    ("Memcached", "Статья про Memcached", 120),
                    ("DynamoDB", "Статья про DynamoDB", 90),
                ],
            )

        conn.commit()


def article_from_db(article_id: int):
    with db_connection() as conn:
        row = conn.execute(
            """
            SELECT id, title, content, views, created_at
            FROM articles
            WHERE id = %s
            """,
            (article_id,),
        ).fetchone()

    if row is None:
        return None

    return {
        "id": row[0],
        "title": row[1],
        "content": row[2],
        "views": row[3],
        "created_at": row[4].isoformat(),
    }


def cache_get_json(key: str):
    value = memcached.get(key)

    if value is None:
        return None

    return json.loads(value.decode("utf-8"))


def cache_set_json(key: str, value: Any, ttl: int = 60):
    memcached.set(
        key,
        json.dumps(value, ensure_ascii=False),
        expire=ttl,
    )


def to_dynamo(value: Any):
    if isinstance(value, float):
        return Decimal(str(value))

    if isinstance(value, dict):
        return {
            key: to_dynamo(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [to_dynamo(item) for item in value]

    return value


@app.on_event("startup")
def startup():
    wait_for_services()
    init_postgres()


@app.get("/")
def root():
    return {
        "task_1": "PostgreSQL + Memcached",
        "task_2": "Redis",
        "task_3": "DynamoDB",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {
        "postgres": True,
        "memcached": True,
        "redis": redis_client.ping(),
        "dynamodb": profile_table.table_status,
    }


@app.post("/cache/articles", tags=["Task 1 - Memcached"])
def create_article(article: ArticleCreate):
    with db_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO articles (title, content)
            VALUES (%s, %s)
            RETURNING id, title, content, views, created_at
            """,
            (article.title, article.content),
        ).fetchone()
        conn.commit()

    memcached.delete("articles:popular")

    return {
        "id": row[0],
        "title": row[1],
        "content": row[2],
        "views": row[3],
        "created_at": row[4].isoformat(),
    }


@app.get("/cache/articles/popular", tags=["Task 1 - Memcached"])
def popular_articles(response: Response):
    key = "articles:popular"
    cached = cache_get_json(key)

    if cached is not None:
        response.headers["X-Cache"] = "HIT"
        return cached

    with db_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, views
            FROM articles
            ORDER BY views DESC
            LIMIT 5
            """
        ).fetchall()

    result = [
        {"id": row[0], "title": row[1], "views": row[2]}
        for row in rows
    ]

    cache_set_json(key, result, ttl=30)
    response.headers["X-Cache"] = "MISS"

    return result


@app.get("/cache/articles/{article_id}", tags=["Task 1 - Memcached"])
def get_article(article_id: int, response: Response):
    key = f"article:json:{article_id}"
    cached = cache_get_json(key)

    if cached is not None:
        response.headers["X-Cache"] = "HIT"
        return cached

    article = article_from_db(article_id)

    if article is None:
        raise HTTPException(404, "Статья не найдена")

    cache_set_json(key, article)
    response.headers["X-Cache"] = "MISS"

    return article


@app.get(
    "/cache/articles/{article_id}/page",
    response_class=HTMLResponse,
    tags=["Task 1 - Memcached"],
)
def article_page(article_id: int):
    key = f"article:html:{article_id}"
    cached = memcached.get(key)

    if cached is not None:
        return HTMLResponse(
            cached.decode("utf-8"),
            headers={"X-Cache": "HIT"},
        )

    article = article_from_db(article_id)

    if article is None:
        raise HTTPException(404, "Статья не найдена")

    html = f"""
    <html>
        <body>
            <h1>{article["title"]}</h1>
            <p>{article["content"]}</p>
            <p>Просмотров: {article["views"]}</p>
        </body>
    </html>
    """

    memcached.set(key, html, expire=60)

    return HTMLResponse(
        html,
        headers={"X-Cache": "MISS"},
    )


@app.post(
    "/cache/articles/{article_id}/view",
    tags=["Task 1 - Memcached"],
)
def add_article_view(article_id: int):
    with db_connection() as conn:
        row = conn.execute(
            """
            UPDATE articles
            SET views = views + 1
            WHERE id = %s
            RETURNING views
            """,
            (article_id,),
        ).fetchone()
        conn.commit()

    if row is None:
        raise HTTPException(404, "Статья не найдена")

    memcached.delete(f"article:json:{article_id}")
    memcached.delete(f"article:html:{article_id}")
    memcached.delete("articles:popular")

    return {
        "article_id": article_id,
        "views": row[0],
    }


@app.post("/analytics/events/view", tags=["Task 2 - Redis"])
def register_view(event: ViewEvent):
    actions_key = f"user:{event.user_id}:actions"

    with redis_client.pipeline(transaction=True) as pipe:
        pipe.incr(f"article:{event.article_id}:views")

        pipe.lpush(
            actions_key,
            json.dumps(
                {
                    "type": "view",
                    "article_id": event.article_id,
                }
            ),
        )
        pipe.ltrim(actions_key, 0, 99)

        pipe.zincrby(
            "popular_articles",
            1,
            str(event.article_id),
        )

        pipe.xadd(
            "events",
            {
                "type": "view",
                "user_id": event.user_id,
                "article_id": str(event.article_id),
            },
            maxlen=10000,
            approximate=True,
        )

        result = pipe.execute()

    return {
        "article_id": event.article_id,
        "views": result[0],
    }


RATING_SCRIPT = """
local sum_key = KEYS[1]
local count_key = KEYS[2]
local ranking_key = KEYS[3]

local article_id = ARGV[1]
local rating = tonumber(ARGV[2])

local sum = redis.call('INCRBYFLOAT', sum_key, rating)
local count = redis.call('INCR', count_key)
local average = sum / count

redis.call('ZADD', ranking_key, average, article_id)

return {tostring(count), tostring(average)}
"""


@app.post("/analytics/events/rating", tags=["Task 2 - Redis"])
def register_rating(event: RatingEvent):
    result = redis_client.eval(
        RATING_SCRIPT,
        3,
        f"article:{event.article_id}:rating_sum",
        f"article:{event.article_id}:rating_count",
        "article_ratings",
        str(event.article_id),
        str(event.rating),
    )

    return {
        "article_id": event.article_id,
        "rating_count": int(result[0]),
        "average_rating": round(float(result[1]), 2),
    }


@app.get("/analytics/top", tags=["Task 2 - Redis"])
def top_articles(limit: int = 10):
    rows = redis_client.zrevrange(
        "popular_articles",
        0,
        max(0, limit - 1),
        withscores=True,
    )

    return [
        {
            "article_id": int(article_id),
            "score": int(score),
        }
        for article_id, score in rows
    ]


@app.get(
    "/analytics/users/{user_id}/actions",
    tags=["Task 2 - Redis"],
)
def user_actions(user_id: str, limit: int = 10):
    items = redis_client.lrange(
        f"user:{user_id}:actions",
        0,
        max(0, limit - 1),
    )

    return [json.loads(item) for item in items]


@app.get("/analytics/events", tags=["Task 2 - Redis"])
def events(limit: int = 20):
    rows = redis_client.xrevrange(
        "events",
        count=limit,
    )

    return [
        {
            "event_id": event_id,
            **data,
        }
        for event_id, data in rows
    ]


@app.post("/profiles", tags=["Task 3 - DynamoDB"])
def create_profile(profile: UserProfileCreate):
    item = to_dynamo(profile.model_dump(mode="json"))

    try:
        profile_table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(user_id)",
        )
    except ClientError as exc:
        if (
            exc.response["Error"]["Code"]
            == "ConditionalCheckFailedException"
        ):
            raise HTTPException(
                409,
                "Пользователь уже существует",
            )
        raise

    return profile


@app.get("/profiles/{user_id}", tags=["Task 3 - DynamoDB"])
def get_profile(user_id: str):
    response = profile_table.get_item(
        Key={"user_id": user_id},
        ConsistentRead=True,
    )

    item = response.get("Item")

    if item is None:
        raise HTTPException(404, "Пользователь не найден")

    return item


@app.patch("/profiles/{user_id}", tags=["Task 3 - DynamoDB"])
def update_profile(user_id: str, data: UserProfileUpdate):
    updates = data.model_dump(
        exclude_none=True,
        mode="json",
    )

    if not updates:
        raise HTTPException(400, "Нет данных для обновления")

    names = {}
    values = {}
    parts = []

    for index, (field, value) in enumerate(updates.items()):
        name_key = f"#f{index}"
        value_key = f":v{index}"

        names[name_key] = field
        values[value_key] = to_dynamo(value)
        parts.append(f"{name_key} = {value_key}")

    try:
        response = profile_table.update_item(
            Key={"user_id": user_id},
            UpdateExpression="SET " + ", ".join(parts),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression="attribute_exists(user_id)",
            ReturnValues="ALL_NEW",
        )
    except ClientError as exc:
        if (
            exc.response["Error"]["Code"]
            == "ConditionalCheckFailedException"
        ):
            raise HTTPException(404, "Пользователь не найден")
        raise

    return response["Attributes"]


@app.delete("/profiles/{user_id}", tags=["Task 3 - DynamoDB"])
def delete_profile(user_id: str):
    try:
        response = profile_table.delete_item(
            Key={"user_id": user_id},
            ConditionExpression="attribute_exists(user_id)",
            ReturnValues="ALL_OLD",
        )
    except ClientError as exc:
        if (
            exc.response["Error"]["Code"]
            == "ConditionalCheckFailedException"
        ):
            raise HTTPException(404, "Пользователь не найден")
        raise

    return {
        "deleted": True,
        "profile": response.get("Attributes"),
    }

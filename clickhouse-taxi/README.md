# ClickHouse: аналитика поездок такси Нью-Йорка

Домашнее задание по дисциплине «Нереляционные базы данных», тема «Колоночные (аналитические) базы данных».

## Данные и методика

Источник: [официальный пример ClickHouse](https://clickhouse.com/docs/getting-started/example-datasets/nyc-taxi).
Использованы оба файла `trips_1.gz` и `trips_2.gz`, все **1 999 657 строк**, без выборки и ограничения LIMIT при загрузке. Даты начала поездок: 2015-07-01 — 2015-09-30.
В таблицу MergeTree загружены семь необходимых для задания столбцов; остальные поля прочитаны из файлов, но не сохраняются.
Денежные поля хранятся как Decimal(12, 2), чтобы суммировать доллары и центы без погрешности Float.
Названия зон берутся непосредственно из `pickup_ntaname` — это районы NTA данного набора, не отдельный справочник TLC Taxi Zones.
Время сохраняется без сдвига: UTC используется как техническая зона, чтобы разность временных меток не зависела от настроек машины.
Выручка определяется как сумма `total_amount`, включая чаевые и сборы; группировка — по дате начала поездки.

## Шаг 1. ClickHouse в Docker

Конфигурация: [compose.yaml](compose.yaml). Нужны Docker Engine с Docker Compose v2, Bash и curl.

```bash
git clone https://github.com/Vanusha61/dz_redis.git
cd dz_redis/clickhouse-taxi
bash run.sh
```

Скрипт скачивает файлы, запускает ClickHouse, создаёт таблицу, загружает данные и сохраняет результаты пяти запросов в `results/`.
Пароль в compose предназначен только для локальной учебной среды. HTTP-порт привязан к 127.0.0.1.

**Статус проверки:** в среде выполнения отсутствует Docker, поэтому контейнер здесь не запускался. Приложена воспроизводимая конфигурация Docker; фактическая загрузка в MergeTree и все запросы выполнены через `clickhouse local` версии **26.11.1.660**. В compose выбрана стабильная ветка **25.8**; её запуск в Docker здесь не проверен. Результаты ниже получены исполнением запросов, а не скопированы из документации.

Остановка без удаления данных:

```bash
docker compose down
```

## Шаг 2. Загрузка

Схема находится в [sql/01_create.sql](sql/01_create.sql), загрузка — в [sql/02_load.sql](sql/02_load.sql).
Файлы доступны внутри контейнера через `file()` и формат `TabSeparatedWithNames`. Полная структура входного файла задана явно строковыми полями, затем нужные значения преобразуются в типы таблицы.
Повторный запуск `run.sh` пропускает загрузку, если уже есть ожидаемое число строк; при неожиданном числе строк останавливается для проверки. Ручной повторный INSERT добавит дубликаты.

## Шаг 3. Запросы и результаты исполнения

### 1. Общее количество поездок

```sql
SELECT count() AS total_trips FROM trips;
```

Результат:

```text
total_trips
1999657
```

### 2. Поездки с чаевыми больше $20

```sql
SELECT count() AS trips_with_tip_over_20 FROM trips WHERE tip_amount > 20;
```

Результат:

```text
trips_with_tip_over_20
1580
```

### 3. Средняя продолжительность поездки в минутах

```sql
SELECT round(avg(dateDiff('second', pickup_datetime, dropoff_datetime) / 60.0), 2) AS avg_duration_minutes FROM trips;
```

Результат:

```text
avg_duration_minutes
15.13
```

### 4. Пять самых популярных зон начала поездки

```sql
SELECT pickup_ntaname AS pickup_zone, count() AS trips_count
FROM trips
WHERE notEmpty(trimBoth(pickup_ntaname))
GROUP BY pickup_ntaname
ORDER BY trips_count DESC, pickup_zone ASC
LIMIT 5;
```

Результат:

```text
pickup_zone	trips_count
Midtown-Midtown South	351722
Hudson Yards-Chelsea-Flatiron-Union Square	192086
West Village	140390
Turtle Bay-East Midtown	131659
Upper East Side-Carnegie Hill	122928
```

### 5. Три дня с наибольшей суммарной выручкой

```sql
SELECT pickup_date AS trip_day, sum(total_amount) AS revenue_usd
FROM trips
GROUP BY pickup_date
ORDER BY revenue_usd DESC, trip_day ASC
LIMIT 3;
```

Результат:

```text
trip_day	revenue_usd
2015-08-06	649918.97
2015-08-20	641317.04
2015-08-13	637238.56
```

## Проверка качества данных

```text
negative_duration	zero_duration	unknown_pickup	min(pickup_date)	max(pickup_date)
25	2117	29209	2015-07-01	2015-09-30
```

Основная средняя посчитана по всей таблице, без скрытой фильтрации, как сформулировано в задании. Есть 25 отрицательных и 2 117 нулевых длительностей. Дополнительный запрос без отрицательных длительностей находится в `sql/06_quality.sql`.
Для топа именованных зон исключены 29 209 строк с пустым названием, поскольку у них нельзя вывести название зоны. В остальных расчётах эти строки сохранены.
При совпадении значений в рейтингах предусмотрена дополнительная сортировка по названию зоны или дате.

Исходные файлы не включены в Git: они скачиваются скриптом. Контрольные суммы скачанных файлов и сведения о выполнении находятся в `results/manifest.json`.

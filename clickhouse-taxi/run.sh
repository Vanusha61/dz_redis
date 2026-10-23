#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p data results
for n in 1 2; do
  if [ ! -f "data/trips_${n}.gz" ]; then
    curl --fail --location --retry 3 "https://datasets-documentation.s3.eu-west-3.amazonaws.com/nyc-taxi/trips_${n}.gz" -o "data/trips_${n}.gz.part"
    mv "data/trips_${n}.gz.part" "data/trips_${n}.gz"
  fi
done
docker compose up -d --wait
ch() { docker compose exec -T clickhouse clickhouse-client --user student --password taxi_practice_local --database taxi "$@"; }
ch --multiquery < sql/01_create.sql
# Не загружаем данные повторно: MergeTree не удаляет дубликаты автоматически.
rows=$(ch --query 'SELECT count() FROM trips')
if [ "$rows" = 0 ]; then
  ch --multiquery < sql/02_load.sql
elif [ "$rows" != 1999657 ]; then
  echo "В trips неожиданное количество строк: $rows. Проверьте таблицу перед повторной загрузкой." >&2
  exit 1
fi
for query in sql/*_query.sql; do
  name=$(basename "$query" _query.sql)
  ch --format TabSeparatedWithNames < "$query" > "results/${name}.tsv"
  cat "results/${name}.tsv"
done

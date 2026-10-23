SELECT
    countIf(dropoff_datetime < pickup_datetime) AS negative_duration,
    countIf(dropoff_datetime = pickup_datetime) AS zero_duration,
    countIf(empty(trimBoth(pickup_ntaname))) AS unknown_pickup,
    min(pickup_date), max(pickup_date)
FROM trips;

-- Дополнительная оценка без отрицательных длительностей.
SELECT round(avg(dateDiff('second', pickup_datetime, dropoff_datetime) / 60.0), 2)
    AS avg_nonnegative_duration_minutes
FROM trips WHERE dropoff_datetime >= pickup_datetime;

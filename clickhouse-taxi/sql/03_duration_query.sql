SELECT round(avg(dateDiff('second', pickup_datetime, dropoff_datetime) / 60.0), 2) AS avg_duration_minutes FROM trips;

SELECT pickup_date AS trip_day, sum(total_amount) AS revenue_usd
FROM trips
GROUP BY pickup_date
ORDER BY revenue_usd DESC, trip_day ASC
LIMIT 3;

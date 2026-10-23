SELECT pickup_ntaname AS pickup_zone, count() AS trips_count
FROM trips
WHERE notEmpty(trimBoth(pickup_ntaname))
GROUP BY pickup_ntaname
ORDER BY trips_count DESC, pickup_zone ASC
LIMIT 5;

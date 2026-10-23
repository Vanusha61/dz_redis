CREATE TABLE IF NOT EXISTS trips
(
    trip_id UInt32,
    pickup_date Date,
    pickup_datetime DateTime('UTC'),
    dropoff_datetime DateTime('UTC'),
    tip_amount Decimal(12, 2),
    total_amount Decimal(12, 2),
    pickup_ntaname String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(pickup_date)
ORDER BY (pickup_datetime, trip_id);

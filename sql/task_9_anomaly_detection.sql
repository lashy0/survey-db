-- Выявление аномалий

-- поиск тех кто быстро проходит опросы
-- Z-Score = (Значение - Среднее) / Стд.Отклонение
WITH survey_stats AS (
    SELECT 
        survey_id,
        AVG(EXTRACT(EPOCH FROM duration)) AS avg_duration_sec,
        STDDEV(EXTRACT(EPOCH FROM duration)) AS stddev_duration_sec
    FROM survey_responses
    WHERE duration IS NOT NULL
    GROUP BY survey_id
)
SELECT 
    r.response_id,
    r.user_id,
    s.title AS survey_title,
    EXTRACT(EPOCH FROM r.duration) AS user_duration_sec,
    round(stats.avg_duration_sec) AS survey_avg_sec,
    ROUND((EXTRACT(EPOCH FROM r.duration) - stats.avg_duration_sec) / NULLIF(stats.stddev_duration_sec, 0), 2) AS z_score
FROM survey_responses r
JOIN surveys s ON r.survey_id = s.survey_id
JOIN survey_stats stats ON r.survey_id = stats.survey_id
WHERE EXTRACT(EPOCH FROM r.duration) < (stats.avg_duration_sec - 1.5 * stats.stddev_duration_sec)
ORDER BY z_score ASC;

-- поиск всплеска активности
WITH daily_activity AS (
    SELECT 
        DATE(completed_at) AS activity_date,
        COUNT(*) AS response_count
    FROM survey_responses
    WHERE completed_at IS NOT NULL
    GROUP BY DATE(completed_at)
),
moving_stats AS (
    SELECT 
        activity_date,
        response_count,
        AVG(response_count) OVER (
            ORDER BY activity_date 
            ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
        ) AS moving_avg
    FROM daily_activity
)
SELECT 
    activity_date,
    response_count,
    ROUND(moving_avg, 1) AS expected_count,
    ROUND(response_count / NULLIF(moving_avg, 0), 1) AS spike_factor
FROM moving_stats
WHERE response_count > moving_avg * 2
ORDER BY activity_date DESC;
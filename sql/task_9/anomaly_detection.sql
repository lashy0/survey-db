-- 1. Статистический метод: Поиск "спидраннеров" (Speed Runners)
-- Аномалия: Пользователи, которые проходят опрос слишком быстро.
-- Метод: Z-Score. Ищем тех, кто быстрее среднего на 2 стандартных отклонения.

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
    -- Z-Score = (Значение - Среднее) / Стд.Отклонение
    ROUND((EXTRACT(EPOCH FROM r.duration) - stats.avg_duration_sec) / NULLIF(stats.stddev_duration_sec, 0), 2) AS z_score
FROM survey_responses r
JOIN surveys s ON r.survey_id = s.survey_id
JOIN survey_stats stats ON r.survey_id = stats.survey_id
-- Фильтр: время меньше (среднее - 1.5 отклонения). Это очень быстро.
WHERE EXTRACT(EPOCH FROM r.duration) < (stats.avg_duration_sec - 1.5 * stats.stddev_duration_sec)
ORDER BY z_score ASC;


-- 2. Временные ряды: Поиск всплесков активности (Spike Detection)
-- Аномалия: Количество ответов в день, превышающее обычное в 3 раза.

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
        -- Среднее за 7 предыдущих дней
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
    -- Насколько текущее значение превышает среднее
    ROUND(response_count / NULLIF(moving_avg, 0), 1) AS spike_factor
FROM moving_stats
-- Аномалия: активность в 2 раза выше средней
WHERE response_count > moving_avg * 2
ORDER BY activity_date DESC;




-- Создаем "ленивого" бота для первого запроса
INSERT INTO survey_responses (survey_id, user_id, started_at, completed_at, ip_address)
VALUES (1, 1, NOW(), NOW(), '1.1.1.1'); -- ID пользователя 1, Опрос 1

-- Он отвечает на вопросы, всегда выбирая варианты с минимальным ID (первые в списке)
INSERT INTO user_answers (response_id, question_id, selected_option_id)
VALUES 
((SELECT MAX(response_id) FROM survey_responses), 1, 1), -- Вопрос 1, Вариант 1 (Python)
((SELECT MAX(response_id) FROM survey_responses), 2, 6); -- Вопрос 2, Вариант 6 (0-1 год)
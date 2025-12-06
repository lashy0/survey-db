-- Задание 10: Анализ сложных наборов данных
-- Цель: Провести сегментацию пользователей (RFM), построить воронку конверсии и определить интересы.

-- =================================================================================================
-- ЧАСТЬ 1: RFM-анализ (Recency, Frequency, Activity)
-- Сегментация пользователей на основе давности активности и частоты прохождения опросов.
-- =================================================================================================

WITH rfm_metrics AS (
    SELECT 
        u.user_id,
        u.email,
        -- Recency: Сколько дней прошло с последнего завершенного опроса (или регистрации, если нет опросов)
        -- COALESCE берет дату регистрации, если опросов не было
        EXTRACT(DAY FROM NOW() - COALESCE(MAX(sr.completed_at), u.registration_date)) AS recency_days,

        -- Frequency: Сколько всего опросов прошел пользователь
        COUNT(sr.response_id) AS frequency_count
    FROM users u
    LEFT JOIN survey_responses sr ON u.user_id = sr.user_id AND sr.completed_at IS NOT NULL
    GROUP BY u.user_id, u.email
),
rfm_scores AS (
    SELECT 
        *,
        -- Разбиваем на 5 групп по Давности (1 - недавние/лучшие, 5 - старые/худшие)
        -- NTILE(5) делит всех на 5 равных кусков
        NTILE(5) OVER (ORDER BY recency_days ASC) as r_score,

        -- Разбиваем на 5 групп по Частоте (1 - редкие/худшие, 5 - частые/лучшие)
        NTILE(5) OVER (ORDER BY frequency_count ASC) as f_score
    FROM rfm_metrics
)
SELECT 
    user_id,
    email,
    recency_days,
    frequency_count,
    r_score,
    f_score,
    -- Присваиваем понятные названия сегментам на основе баллов
    CASE 
        WHEN r_score <= 2 AND f_score >= 4 THEN 'Чемпионы (Активные и частые)'
        WHEN r_score <= 2 AND f_score <= 3 THEN 'Новички / Перспективные'
        WHEN r_score >= 4 AND f_score >= 4 THEN 'Лояльные, но теряем (Давно не были)'
        WHEN r_score >= 4 AND f_score <= 2 THEN 'Спящие / Потерянные'
        ELSE 'Среднестатистические'
    END AS user_segment
FROM rfm_scores
ORDER BY f_score DESC, r_score ASC;


-- =================================================================================================
-- ЧАСТЬ 2: Воронка Конверсии (Funnel Analysis)
-- Анализ пути пользователя: Регистрация -> Старт опроса -> Завершение опроса.
-- =================================================================================================

SELECT 
    '1. Регистрация' as step_name, 
    COUNT(*) as user_count, 
    100.0 as conversion_pct 
FROM users
UNION ALL
SELECT 
    '2. Начали хотя бы 1 опрос', 
    COUNT(DISTINCT user_id),
    ROUND(COUNT(DISTINCT user_id)::numeric / (SELECT COUNT(*) FROM users) * 100, 1)
FROM survey_responses
UNION ALL
SELECT 
    '3. Завершили хотя бы 1 опрос', 
    COUNT(DISTINCT user_id),
    ROUND(COUNT(DISTINCT user_id)::numeric / (SELECT COUNT(*) FROM users) * 100, 1)
FROM survey_responses 
WHERE completed_at IS NOT NULL
ORDER BY user_count DESC;


-- =================================================================================================
-- ЧАСТЬ 3: Профилирование интересов (Tag Clustering)
-- Определение тематического профиля пользователя на основе пройденных опросов.
-- =================================================================================================

SELECT 
    u.user_id,
    u.email,
    -- Собираем все теги в одну строку через запятую
    STRING_AGG(DISTINCT t.name, ', ') AS interest_profile,
    COUNT(DISTINCT sr.survey_id) as surveys_completed
FROM users u
JOIN survey_responses sr ON u.user_id = sr.user_id
JOIN surveys s ON sr.survey_id = s.survey_id
JOIN survey_tags st ON s.survey_id = st.survey_id
JOIN tags t ON st.tag_id = t.tag_id
WHERE sr.completed_at IS NOT NULL
GROUP BY u.user_id, u.email
ORDER BY surveys_completed DESC;
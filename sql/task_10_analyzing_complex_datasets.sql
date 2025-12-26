-- Анализ сложных наборов данных

-- воронка конверсии
-- какой процент зарегистрированных пользователей доходит до конца опроса
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

-- определение интересов пользователя на основе тегов пройденных опросов
SELECT 
    u.user_id,
    u.full_name,
    STRING_AGG(DISTINCT t.name, ', ') AS interest_profile,
    COUNT(DISTINCT sr.survey_id) as surveys_completed
FROM users u
JOIN survey_responses sr ON u.user_id = sr.user_id
JOIN surveys s ON sr.survey_id = s.survey_id
JOIN survey_tags st ON s.survey_id = st.survey_id
JOIN tags t ON st.tag_id = t.tag_id
WHERE sr.completed_at IS NOT NULL
GROUP BY u.user_id, u.full_name
ORDER BY surveys_completed DESC;
-- Задача: Загрузить пользователей из CSV файла "import_users.csv" в таблицу users.
-- Файл содержит "сырые" данные: лишние пробелы, разный регистр букв, названия стран текстом.

-- ШАГ 1. Создание временной таблицы для "сырых" данных (Staging Table)
-- Мы не грузим сразу в чистовик, чтобы не сломать базу ошибками форматов.
CREATE TABLE users_import_staging (
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    birth_date DATE,
    city TEXT,
    country_name TEXT
);

-- ШАГ 2. Команда импорта (Выберите вариант, который работает у вас)

-- ВАРИАНТ А: Через DBeaver (Графический интерфейс)
-- 1. Нажмите правой кнопкой на таблицу users_import_staging -> Импорт данных
-- 2. Выберите файл import_users.csv
-- 3. Выполните импорт

-- ВАРИАНТ Б: Команда COPY (Требует прав суперпользователя и доступа к файловой системе сервера)
-- COPY users_import_staging(first_name, last_name, email, birth_date, city, country_name)
-- FROM '/path/to/your/file/import_users.csv' 
-- WITH (FORMAT csv, HEADER true, DELIMITER ',');

-- ВАРИАНТ В: Команда \copy (Для psql / консоли, работает с локальным файлом клиента)
-- \copy users_import_staging FROM 'import_users.csv' WITH (FORMAT csv, HEADER true, DELIMITER ',');


-- ШАГ 3. Предварительная предобработка и перенос в основную таблицу
-- Здесь мы чистим данные и приводим их к стандартам нашей базы.

INSERT INTO users (first_name, last_name, email, password_hash, birth_date, city, country_id, role)
SELECT 
    INITCAP(TRIM(temp.first_name)),
    INITCAP(TRIM(temp.last_name)),
    LOWER(TRIM(temp.email)),
    'temp_pass_123',
    temp.birth_date,
    TRIM(temp.city),
    c.country_id,
    'user'::user_role_enum
FROM users_import_staging temp
LEFT JOIN countries c ON c.name = temp.country_name
WHERE NOT EXISTS (
    SELECT 1 FROM users u WHERE u.email = LOWER(TRIM(temp.email))
);

-- Проверка результата
SELECT * FROM users WHERE email IN ('ivan_new@mail.ru', 'peter_sid@gmail.com');

-- Очистка временной таблицы
DROP TABLE users_import_staging;
-- Создание базы данных

-- типы
CREATE TYPE survey_status AS ENUM ('draft', 'active', 'completed', 'archived');
CREATE TYPE question_type_enum AS ENUM ('single_choice', 'multiple_choice', 'text_answer', 'rating');
CREATE TYPE user_role_enum AS ENUM ('user', 'creator', 'admin');

-- Таблицы

-- справочник стран
CREATE TABLE countries (
    country_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);

-- пользователи
CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    birth_date DATE,
    city VARCHAR(100),
    country_id INTEGER REFERENCES countries(country_id) ON DELETE SET NULL,
    role user_role_enum NOT NULL DEFAULT 'user',
    registration_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT check_birth_date CHECK (birth_date < CURRENT_DATE)
);

-- опросы
CREATE TABLE surveys (
    survey_id SERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    status survey_status NOT NULL DEFAULT 'draft',
    author_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    start_date TIMESTAMPTZ,
    end_date TIMESTAMPTZ,
    CONSTRAINT check_dates CHECK (end_date > start_date)
);

-- теги
CREATE TABLE tags (
    tag_id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE
);

-- опрос <-> теги
CREATE TABLE survey_tags (
    survey_id INTEGER REFERENCES surveys(survey_id) ON DELETE CASCADE,
    tag_id INTEGER REFERENCES tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY (survey_id, tag_id)
);

-- вопросы
CREATE TABLE questions (
    question_id SERIAL PRIMARY KEY,
    survey_id INTEGER REFERENCES surveys(survey_id) ON DELETE CASCADE,
    question_text TEXT NOT NULL,
    question_type question_type_enum NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    is_required BOOLEAN NOT NULL DEFAULT TRUE
);

-- варианты ответов
CREATE TABLE options (
    option_id SERIAL PRIMARY KEY,
    question_id INTEGER REFERENCES questions(question_id) ON DELETE CASCADE,
    option_text VARCHAR(255) NOT NULL,
    is_correct BOOLEAN DEFAULT FALSE
);

-- сессии
CREATE TABLE survey_responses (
    response_id SERIAL PRIMARY KEY,
    survey_id INTEGER REFERENCES surveys(survey_id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    duration INTERVAL GENERATED ALWAYS AS (completed_at - started_at) STORED,
    ip_address INET,
    device_type VARCHAR(50),
    CONSTRAINT unique_user_survey_attempt UNIQUE (survey_id, user_id),
    CONSTRAINT check_completion_time CHECK (completed_at >= started_at)
);

-- ответы
CREATE TABLE user_answers (
    answer_id SERIAL PRIMARY KEY,
    response_id INTEGER REFERENCES survey_responses(response_id) ON DELETE CASCADE,
    question_id INTEGER REFERENCES questions(question_id) ON DELETE CASCADE,
    selected_option_id INTEGER REFERENCES options(option_id),
    text_answer TEXT,
    CONSTRAINT check_answer_content CHECK (selected_option_id IS NOT NULL OR text_answer IS NOT NULL)
);

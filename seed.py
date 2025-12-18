import asyncio
import random
from datetime import date, datetime, timedelta, timezone
import sys
import os

# Добавляем текущую директорию в путь, чтобы видеть app
sys.path.append(os.getcwd())

from faker import Faker
from sqlalchemy import text, select
from sqlalchemy.orm import selectinload
from app.core.database import async_session_maker
from app.models import (
    User, Country, Tag, Survey, Question, Option, 
    SurveyResponse, UserAnswer, SurveyStatus, UserRole, 
    QuestionType
)
from app.core.security import get_password_hash

fake = Faker('ru_RU')

# НАСТРОЙКИ
NUM_USERS = 52          # 2 админа + 50 ботов
RESPONSES_PER_USER_AVG = 4
DEFAULT_PASSWORD = "123456"

# === БАЗА ЗНАНИЙ ДЛЯ ОПРОСОВ ===
# Формат: (Название, Описание, [Индексы тегов], [Список вопросов])
# Теги: 0:IT, 1:Здоровье, 2:Гейминг, 3:Образование, 4:Работа, 5:Психология, 
#       6:Маркетинг, 7:Кино, 8:Путешествия, 9:Еда, 10:Спорт, 11:Финансы

SURVEY_SCENARIOS = [
    {
        "title": "Тренды IT 2025",
        "desc": "Исследование популярности языков программирования и фреймворков.",
        "tags": [0, 4],
        "questions": [
            {"text": "Ваш основной язык программирования?", "type": "single_choice", "options": ["Python", "JavaScript/TypeScript", "Java", "Go", "C#", "PHP", "Rust"]},
            {"text": "Какой формат работы вы предпочитаете?", "type": "single_choice", "options": ["Полная удаленка", "Гибрид", "Офис"]},
            {"text": "Планируете ли менять работу в этом году?", "type": "single_choice", "options": ["Да", "Нет", "Пассивно рассматриваю"]},
            {"text": "Какие технологии хотите изучить? (Текст)", "type": "text_answer"}
        ]
    },
    {
        "title": "Здоровый сон",
        "desc": "Как жители мегаполисов справляются с недосыпом.",
        "tags": [1, 5],
        "questions": [
            {"text": "Сколько часов вы спите в сутки?", "type": "single_choice", "options": ["Меньше 5", "5-6 часов", "7-8 часов", "Более 9 часов"]},
            {"text": "Что мешает вам уснуть?", "type": "multiple_choice", "options": ["Стресс", "Гаджеты перед сном", "Шум", "Кофеин", "Ничего, сплю отлично"]},
            {"text": "Оцените качество вашего сна (1-5)", "type": "rating", "scale": 5}
        ]
    },
    {
        "title": "Игровая индустрия: Итоги",
        "desc": "Во что играли в этом году и чего ждем.",
        "tags": [2, 0],
        "questions": [
            {"text": "Ваша основная платформа?", "type": "single_choice", "options": ["PC (Master Race)", "PlayStation 5", "Xbox Series", "Nintendo Switch", "Мобильные игры"]},
            {"text": "Любимый жанр?", "type": "single_choice", "options": ["RPG / Action-RPG", "Shooter (FPS/TPS)", "Strategy", "MOBA", "Simulators"]},
            {"text": "Сколько денег тратите на игры в месяц?", "type": "single_choice", "options": ["0 (Free-to-play / Пират)", "До 1000 руб", "1000 - 5000 руб", "Более 5000 руб"]}
        ]
    },
    {
        "title": "Качество образования",
        "desc": "Опрос студентов и выпускников о качестве ВУЗов.",
        "tags": [3, 4],
        "questions": [
            {"text": "Ваш уровень образования?", "type": "single_choice", "options": ["Среднее", "Бакалавриат", "Магистратура", "Кандидат наук"]},
            {"text": "Помогают ли знания из ВУЗа в реальной работе?", "type": "rating", "scale": 10},
            {"text": "Чего не хватает современной системе образования?", "type": "text_answer"}
        ]
    },
    {
        "title": "Удаленка vs Офис",
        "desc": "Где продуктивнее работать и почему.",
        "tags": [4, 5],
        "questions": [
            {"text": "Где вы сейчас работаете?", "type": "single_choice", "options": ["Дома", "В офисе", "В коворкинге", "В кафе"]},
            {"text": "Главный плюс удаленки для вас?", "type": "multiple_choice", "options": ["Экономия времени на дорогу", "Тишина и покой", "Можно работать в пижаме", "Гибкий график"]},
            {"text": "Главный минус удаленки?", "type": "single_choice", "options": ["Нет живого общения", "Сложно сосредоточиться", "Переработки", "Соседи делают ремонт"]}
        ]
    },
    {
        "title": "Психология успеха",
        "desc": "Что мотивирует вас двигаться вперед?",
        "tags": [5, 4],
        "questions": [
            {"text": "Что для вас успех?", "type": "text_answer"},
            {"text": "Испытываете ли вы синдром самозванца?", "type": "single_choice", "options": ["Постоянно", "Иногда", "Редко", "Никогда"]},
            {"text": "Ваш уровень стресса на этой неделе (1-10)", "type": "rating", "scale": 10}
        ]
    },
    {
        "title": "Лучшие фильмы года",
        "desc": "Что вы смотрели в этом году?",
        "tags": [7, 2],
        "questions": [
            {"text": "Как часто ходите в кинотеатр?", "type": "single_choice", "options": ["Раз в неделю", "Раз в месяц", "Несколько раз в год", "Не хожу, смотрю дома"]},
            {"text": "Любимый жанр кино?", "type": "multiple_choice", "options": ["Фантастика", "Драма", "Комедия", "Хоррор", "Документальное"]},
            {"text": "Лучший фильм, который вы видели недавно?", "type": "text_answer"}
        ]
    },
    {
        "title": "Гастрономический тур",
        "desc": "Какую кухню вы предпочитаете?",
        "tags": [9, 8],
        "questions": [
            {"text": "Какая кухня ваша любимая?", "type": "single_choice", "options": ["Итальянская", "Грузинская", "Японская/Азиатская", "Русская", "Фастфуд"]},
            {"text": "Вы готовите дома?", "type": "single_choice", "options": ["Каждый день", "По выходным", "Редко, заказываю доставку"]},
            {"text": "Ваше любимое блюдо?", "type": "text_answer"}
        ]
    },
    {
        "title": "Финансовая грамотность",
        "desc": "Как вы ведете бюджет?",
        "tags": [11, 4],
        "questions": [
            {"text": "Ведете ли вы учет расходов?", "type": "single_choice", "options": ["Да, в приложении", "Да, в Excel", "Примерно в уме", "Нет"]},
            {"text": "Есть ли у вас финансовая подушка?", "type": "single_choice", "options": ["Да, на 6+ месяцев", "Да, на 1-2 месяца", "Нет, живу от зарплаты до зарплаты"]},
            {"text": "Куда инвестируете?", "type": "multiple_choice", "options": ["Акции/Облигации", "Недвижимость", "Криптовалюта", "Депозиты", "Никуда"]}
        ]
    },
    {
        "title": "Спорт для всех",
        "desc": "Как часто вы тренируетесь?",
        "tags": [10, 1],
        "questions": [
            {"text": "Ваш вид активности?", "type": "multiple_choice", "options": ["Фитнес зал", "Бег", "Плавание", "Йога", "Командные игры", "Прогулки"]},
            {"text": "Сколько раз в неделю занимаетесь?", "type": "single_choice", "options": ["1-2 раза", "3-4 раза", "Каждый день", "Не занимаюсь"]},
            {"text": "Оцените вашу физическую форму (1-5)", "type": "rating", "scale": 5}
        ]
    },
    {
        "title": "Путешествия по России",
        "desc": "Где вы отдыхали этим летом?",
        "tags": [8, 7],
        "questions": [
            {"text": "Где лучше отдыхать?", "type": "single_choice", "options": ["Море (Сочи, Крым)", "Горы (Алтай, Кавказ)", "Города (Питер, Казань)", "На даче"]},
            {"text": "Ваш бюджет на отпуск (на человека)?", "type": "single_choice", "options": ["До 30к", "30-50к", "50-100к", "Более 100к"]},
            {"text": "Ваше впечатление от сервиса (1-10)", "type": "rating", "scale": 10}
        ]
    },
    {
        "title": "Маркетинг в соцсетях",
        "desc": "Какой контент вам нравится?",
        "tags": [6, 0],
        "questions": [
            {"text": "В какой соцсети проводите больше времени?", "type": "single_choice", "options": ["Telegram", "VK", "YouTube", "TikTok", "Instagram"]},
            {"text": "Раздражает ли вас реклама у блогеров?", "type": "single_choice", "options": ["Бесит", "Терпимо", "Иногда даже полезно"]},
            {"text": "Какой формат контента любите?", "type": "multiple_choice", "options": ["Короткие видео", "Длинные видео", "Текстовые посты", "Подкасты"]}
        ]
    }
]

async def clean_database(session):
    print("🧹 Очистка базы данных...")
    tables = [
        "user_answers", "survey_responses", "options", "questions", 
        "survey_tags", "tags", "surveys", "users", "countries"
    ]
    for table in tables:
        await session.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE;"))
    await session.commit()

async def create_countries_and_tags(session):
    print("🌍 Создание стран и тегов...")
    countries_list = ['Россия', 'Беларусь', 'Казахстан', 'Узбекистан', 'Германия', 'США', 'Франция', 'Китай']
    countries = [Country(name=name) for name in countries_list]
    session.add_all(countries)

    tags_list = [
        'IT', 'Здоровье', 'Гейминг', 'Образование', 'Работа', 'Психология', 
        'Маркетинг', 'Кино', 'Путешествия', 'Еда', 'Спорт', 'Финансы'
    ]
    tags = [Tag(name=name) for name in tags_list]
    session.add_all(tags)
    
    await session.commit()
    return (
        (await session.execute(select(Country))).scalars().all(),
        (await session.execute(select(Tag))).scalars().all()
    )

async def create_users(session, countries):
    print(f"👥 Создание {NUM_USERS} пользователей...")
    hashed_pw = get_password_hash(DEFAULT_PASSWORD)
    users_batch = []

    # 1. Админ
    users_batch.append(User(
        full_name="Главный Администратор", email="admin@main.com", password_hash=hashed_pw,
        birth_date=date(1990, 1, 1), city="Москва", country_id=countries[0].country_id, role=UserRole.admin
    ))
    
    # 2. Тестер
    users_batch.append(User(
        full_name="Иван Тестовый", email="user@test.com", password_hash=hashed_pw,
        birth_date=date(2000, 5, 20), city="Санкт-Петербург", country_id=countries[0].country_id, role=UserRole.user
    ))

    # 3. Боты
    for _ in range(NUM_USERS):
        b_date = fake.date_of_birth(minimum_age=16, maximum_age=65) if random.random() > 0.1 else None
        users_batch.append(User(
            full_name=fake.name(),
            email=fake.unique.email(),
            password_hash=hashed_pw,
            birth_date=b_date,
            city=fake.city(),
            country_id=random.choice(countries).country_id,
            role=UserRole.user,
            registration_date=fake.date_time_between(start_date='-1y', end_date='now', tzinfo=timezone.utc)
        ))

    session.add_all(users_batch)
    await session.commit()
    return (await session.execute(select(User))).scalars().all()

async def create_surveys(session, users, tags):
    print("📝 Создание детализированных опросов...")
    author = users[0]
    
    created_surveys = []
    
    for i, data in enumerate(SURVEY_SCENARIOS):
        # Статусы: "Путешествия" (idx 10) сделаем завершенным
        status = SurveyStatus.active
        if i == 10: status = SurveyStatus.completed
        if i == 11: status = SurveyStatus.draft 

        s = Survey(
            title=data["title"],
            description=data["desc"],
            status=status,
            author_id=author.user_id,
            created_at=datetime.now(timezone.utc) - timedelta(days=random.randint(20, 120)),
            start_date=datetime.now(timezone.utc) - timedelta(days=random.randint(10, 100)),
            end_date=datetime.now(timezone.utc) + timedelta(days=30)
        )
        
        # Теги
        for t_idx in data["tags"]:
            if t_idx < len(tags):
                s.tags.append(tags[t_idx])
        
        # Вопросы
        questions_objects = []
        for q_idx, q_data in enumerate(data["questions"]):
            q_type_enum = QuestionType.single_choice # Default
            if q_data["type"] == "multiple_choice": q_type_enum = QuestionType.multiple_choice
            elif q_data["type"] == "text_answer": q_type_enum = QuestionType.text_answer
            elif q_data["type"] == "rating": q_type_enum = QuestionType.rating

            quest = Question(
                question_text=q_data["text"],
                question_type=q_type_enum,
                position=q_idx + 1
            )
            
            # Опции
            if "options" in q_data:
                quest.options = [Option(option_text=opt) for opt in q_data["options"]]
            elif q_type_enum == QuestionType.rating:
                scale = q_data.get("scale", 5)
                quest.options = [Option(option_text=str(x)) for x in range(1, scale + 1)]
            
            questions_objects.append(quest)
        
        s.questions = questions_objects
        session.add(s)
        created_surveys.append(s)

    await session.commit()
    return (await session.execute(select(Survey))).scalars().all()

def create_single_response(user_id, survey, user_reg_date):
    """Создает один ответ на опрос"""
    # Симуляция Retention:
    # 60% активности в первый месяц (M+0)
    # 20% во второй (M+1)
    # 10% в третий (M+2)
    # 10% позже
    
    rand = random.random()
    if rand < 0.6:
        lag_days = random.randint(0, 30)
    elif rand < 0.8:
        lag_days = random.randint(31, 60)
    elif rand < 0.9:
        lag_days = random.randint(61, 90)
    else:
        lag_days = random.randint(91, 180)
    
    # Дата начала = Дата регистрации юзера + Лаг
    # Но не позже "сегодня"
    start_time = user_reg_date + timedelta(days=lag_days)
    if start_time > datetime.now(timezone.utc):
        start_time = datetime.now(timezone.utc) - timedelta(hours=random.randint(1, 24))
    
    # 25% незавершенных
    if random.random() < 0.25:
        completed_at = None
    else:
        completed_at = start_time  + timedelta(seconds=random.randint(45, 900))

    response = SurveyResponse(
        survey_id=survey.survey_id,
        user_id=user_id,
        started_at=start_time ,
        completed_at=completed_at,
        ip_address=fake.ipv4(),
        device_type=random.choice(["Desktop", "Mobile", "Tablet"])
    )
    
    user_answers = []
    # Если опрос брошен, отвечаем не на всё
    questions_to_answer = survey.questions
    if completed_at is None:
        limit = random.randint(0, max(0, len(survey.questions) - 1))
        questions_to_answer = survey.questions[:limit]

    for q in questions_to_answer:
        ans = UserAnswer(question_id=q.question_id)
        if q.question_type == QuestionType.text_answer:
            # Более осмысленные фейковые ответы (просто заглушка, но лучше чем рандомные буквы)
            ans.text_answer = fake.sentence(nb_words=6)
        elif q.options:
            if q.question_type == QuestionType.multiple_choice:
                # Выбираем 1 или 2 опции
                opts = random.sample(q.options, k=random.randint(1, min(2, len(q.options))))
                # Технически модель UserAnswer хранит 1 option_id, для multiple нужно несколько строк UserAnswer
                # Но наш сидер упрощен: берем первую (для аналитики пойдет) или нужно переделывать логику
                # У нас связь UserAnswer -> selected_option_id (один к одному в строке).
                # Поэтому для мульти-выбора надо создавать НЕСКОЛЬКО UserAnswer.
                # Сделаем правильно:
                pass # Логика ниже
            else:
                # Single choice / Rating
                ans.selected_option_id = random.choice(q.options).option_id
                user_answers.append(ans)
        
        # Специальная обработка Multiple Choice (создаем несколько ответов)
        if q.question_type == QuestionType.multiple_choice and q.options:
             opts = random.sample(q.options, k=random.randint(1, min(3, len(q.options))))
             for opt in opts:
                 multi_ans = UserAnswer(question_id=q.question_id, selected_option_id=opt.option_id)
                 user_answers.append(multi_ans)

    response.answers = user_answers
    return response

async def generate_responses(session, users, surveys):
    print(f"🚀 Генерация ответов с Retention...")
    
    stmt = select(Survey).options(
        selectinload(Survey.questions).selectinload(Question.options)
    )
    surveys_full = (await session.execute(stmt)).scalars().all()
    valid_surveys = [s for s in surveys_full if s.status != SurveyStatus.draft]

    responses_to_add = []
    
    # Словарик дат регистрации для быстрого доступа
    # users - это список объектов, у них есть поле registration_date
    
    for user in users[2:]:
        num_to_take = random.randint(2, 5)
        surveys_taken = random.sample(valid_surveys, min(num_to_take, len(valid_surveys)))
        
        for survey in surveys_taken:
            # ПЕРЕДАЕМ ДАТУ РЕГИСТРАЦИИ ЮЗЕРА
            resp = create_single_response(user.user_id, survey, user.registration_date)
            responses_to_add.append(resp)

    # Тестер
    tester_user = users[1]
    target_surveys = [s for s in valid_surveys if "IT" in s.title or "Игры" in s.title]
    for survey in target_surveys:
        resp = create_single_response(tester_user.user_id, survey, tester_user.registration_date)
        responses_to_add.append(resp)

    session.add_all(responses_to_add)
    await session.commit()
    print(f"✅ Создано {len(responses_to_add)} прохождений.")

async def main():
    async with async_session_maker() as session:
        try:
            await clean_database(session)
            countries, tags = await create_countries_and_tags(session)
            users = await create_users(session, countries)
            surveys = await create_surveys(session, users, tags)
            await generate_responses(session, users, surveys)
            
            print("\n🎉 ГОТОВО!")
            print(f"🔑 Admin: admin@main.com / {DEFAULT_PASSWORD}")
            print(f"🔑 User:  user@test.com  / {DEFAULT_PASSWORD}")
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            await session.rollback()

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
import json
from typing import Optional, Union
from datetime import datetime, date
from fastapi import APIRouter, Request, Depends, HTTPException, Body
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, case, text, extract, inspect
from app.core.database import get_db, engine
from app.core.deps import get_current_user
from app.models import User, Survey, SurveyResponse, Tag, survey_tags, UserRole

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/analytics", response_class=HTMLResponse)
async def analytics_dashboard(
    request: Request,
    survey_id: Union[int, str, None] = None, 
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
) -> HTMLResponse:
    if survey_id is not None:
        try:
            survey_id = int(survey_id)
        except ValueError:
            survey_id = None
    
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Доступ запрещен")

    # --- 0. ЗАГРУЗКА СПИСКА ОПРОСОВ (для фильтра) ---
    all_surveys = (await db.execute(select(Survey).order_by(Survey.title))).scalars().all()

    # --- KPI и ГРАФИКИ (Оставляем как есть) ---
    total_users = await db.scalar(select(func.count(User.user_id))) or 0
    total_surveys = await db.scalar(select(func.count(Survey.survey_id))) or 0
    total_responses = await db.scalar(select(func.count(SurveyResponse.response_id))) or 0
    
    cnt_users = total_users
    # Используем метод .distinct() у колонки - это самый надежный способ в ORM
    cnt_started = await db.scalar(select(func.count(SurveyResponse.user_id.distinct()))) or 0
    
    cnt_completed = await db.scalar(
        select(func.count(SurveyResponse.user_id.distinct()))
        .where(SurveyResponse.completed_at.is_not(None))
    ) or 0
    
    funnel_data = {
        "labels": ["Регистрация", "Начали опрос", "Завершили опрос"],
        "counts": [int(cnt_users), int(cnt_started), int(cnt_completed)]
    }

    activity_query = (
        select(
            func.date(SurveyResponse.started_at).label("date"),
            func.count(SurveyResponse.response_id).label("cnt")
        )
        .group_by(func.date(SurveyResponse.started_at))
        .order_by(func.date(SurveyResponse.started_at))
    )
    activity_res = (await db.execute(activity_query)).all()
    time_series_data = {
        "dates": [str(row.date) for row in activity_res],
        "counts": [int(row.cnt) for row in activity_res]
    }

    tags_query = (
        select(Tag.name, func.count(SurveyResponse.response_id).label("popularity"))
        .select_from(SurveyResponse)
        .join(Survey, SurveyResponse.survey_id == Survey.survey_id)
        .join(survey_tags, Survey.survey_id == survey_tags.c.survey_id)
        .join(Tag, survey_tags.c.tag_id == Tag.tag_id)
        .where(SurveyResponse.completed_at.is_not(None))
        .group_by(Tag.name)
        .order_by(desc("popularity"))
        .limit(7)
    )
    tags_res = (await db.execute(tags_query)).all()
    tags_data = {
        "labels": [str(row.name) for row in tags_res],
        "counts": [int(row.popularity) for row in tags_res]
    }

    # --- 4. ANOMALIES (С ФИЛЬТРАЦИЕЙ) ---
    stats_cte = (
        select(
            SurveyResponse.survey_id,
            func.avg(extract('epoch', SurveyResponse.duration)).label("avg_sec"),
            func.stddev(extract('epoch', SurveyResponse.duration)).label("std_sec")
        )
        .where(SurveyResponse.duration.is_not(None))
        .group_by(SurveyResponse.survey_id)
        .cte("survey_stats")
    )

    anomalies_query = (
        select(
            User.full_name,
            User.email,
            Survey.title,
            extract('epoch', SurveyResponse.duration).label("user_sec"),
            stats_cte.c.avg_sec,
            stats_cte.c.std_sec
        )
        .join(stats_cte, SurveyResponse.survey_id == stats_cte.c.survey_id)
        .join(User, SurveyResponse.user_id == User.user_id)
        .join(Survey, SurveyResponse.survey_id == Survey.survey_id)
        .where(
            extract('epoch', SurveyResponse.duration) < (stats_cte.c.avg_sec - 1.5 * func.coalesce(stats_cte.c.std_sec, 0))
        )
        .order_by("user_sec")
        # Убрали limit(10), чтобы показать всех
    )
    
    # ЕСЛИ ВЫБРАН ОПРОС — ДОБАВЛЯЕМ WHERE
    if survey_id:
        anomalies_query = anomalies_query.where(Survey.survey_id == survey_id)
    
    anomalies_res = (await db.execute(anomalies_query)).all()

    # --- 5. HEATMAP (День недели x Час) ---
    # 0 = Sunday, 1 = Monday in PostgreSQL (или 1-7 isodow)
    # Лучше использовать isodow: 1=Monday, 7=Sunday
    heatmap_query = (
        select(
            extract('isodow', SurveyResponse.started_at).label("dow"),
            extract('hour', SurveyResponse.started_at).label("hour"),
            func.count(SurveyResponse.response_id).label("cnt")
        )
        .group_by("dow", "hour")
    )
    heatmap_res = (await db.execute(heatmap_query)).all()

    heatmap_z = [[0 for _ in range(24)] for _ in range(7)]
    
    for row in heatmap_res:
        d = int(row.dow) - 1 # 1..7 -> 0..6
        h = int(row.hour)    # 0..23
        if 0 <= d < 7 and 0 <= h < 24:
            heatmap_z[d][h] = row.cnt

    heatmap_data = {
        "z": heatmap_z,
        "x": [f"{h:02d}:00" for h in range(24)],
        "y": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    }

    return templates.TemplateResponse(
        name="admin/analytics.html",
        context={
            "request": request,
            "user": user,
            "kpi": {
                "users": total_users,
                "surveys": total_surveys,
                "responses": total_responses
            },
            "funnel_data": funnel_data,
            "time_series_data": time_series_data,
            "tags_data": tags_data,
            "anomalies": anomalies_res,
            "heatmap_data": heatmap_data,
            "all_surveys": all_surveys, # Передаем список опросов
            "selected_survey_id": survey_id # Передаем текущий выбор
        }
    )


@router.get("/analytics/anomalies", response_class=HTMLResponse)
async def get_anomalies_partial(
    request: Request,
    survey_id: Union[int, str, None] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Возвращает только HTML-фрагмент таблицы аномалий."""
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403)

    # Обработка survey_id (так же как выше)
    if survey_id == "": survey_id = None
    if survey_id is not None:
        try: survey_id = int(survey_id)
        except: survey_id = None

    # Повторяем запрос аномалий (можно вынести в отдельную функцию, чтобы не дублировать)
    stats_cte = (
        select(
            SurveyResponse.survey_id,
            func.avg(extract('epoch', SurveyResponse.duration)).label("avg_sec"),
            func.stddev(extract('epoch', SurveyResponse.duration)).label("std_sec")
        )
        .where(SurveyResponse.duration.is_not(None))
        .group_by(SurveyResponse.survey_id)
        .cte("survey_stats")
    )

    anomalies_query = (
        select(
            User.full_name,
            User.email,
            Survey.title,
            extract('epoch', SurveyResponse.duration).label("user_sec"),
            stats_cte.c.avg_sec,
            stats_cte.c.std_sec
        )
        .join(stats_cte, SurveyResponse.survey_id == stats_cte.c.survey_id)
        .join(User, SurveyResponse.user_id == User.user_id)
        .join(Survey, SurveyResponse.survey_id == Survey.survey_id)
        .where(
            extract('epoch', SurveyResponse.duration) < (stats_cte.c.avg_sec - 1.5 * func.coalesce(stats_cte.c.std_sec, 0))
        )
        .order_by("user_sec")
    )
    
    if survey_id:
        anomalies_query = anomalies_query.where(Survey.survey_id == survey_id)
    
    anomalies_res = (await db.execute(anomalies_query)).all()

    # Возвращаем только фрагмент!
    return templates.TemplateResponse(
        "admin/partials/anomalies_table.html",
        {"request": request, "anomalies": anomalies_res}
    )



@router.get("/tables_view", response_class=HTMLResponse)
async def view_tables_dashboard(
    request: Request,
    user: User = Depends(get_current_user)
):
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403)

    # ИСПОЛЬЗУЕМ SQLALCHEMY INSPECT (через run_sync для асинхронного engine)
    def get_table_names(connection):
        inspector = inspect(connection)
        return inspector.get_table_names()

    # Запускаем синхронную функцию в асинхронном контексте
    async with engine.connect() as conn:
        table_names = await conn.run_sync(get_table_names)
    
    # Сортируем для красоты
    table_names.sort()

    return templates.TemplateResponse(
        "admin/tables.html",
        {
            "request": request,
            "user": user,
            "tables": table_names
        }
    )

@router.get("/tables/data/{table_name}", response_class=HTMLResponse)
async def get_table_data(
    request: Request,
    table_name: str,
    page: int = 1,      # Добавили пагинацию
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403)

    # Валидация имени таблицы (как и раньше)
    def check_table_exists(connection):
        inspector = inspect(connection)
        return inspector.has_table(table_name)
    
    async with engine.connect() as conn:
        if not await conn.run_sync(check_table_exists):
            return HTMLResponse("Таблица не найдена")

    # 1. Получаем колонки и PK
    def get_table_info(connection):
        inspector = inspect(connection)
        pk_constraint = inspector.get_pk_constraint(table_name)
        pk_columns = pk_constraint['constrained_columns']
        columns = [col['name'] for col in inspector.get_columns(table_name)]
        return columns, pk_columns

    async with engine.connect() as conn:
        columns, pk_columns = await conn.run_sync(get_table_info)
    
    # Пока поддерживаем редактирование только таблиц с простым (одинарным) PK
    pk_col = pk_columns[0] if pk_columns else None

    pk_col_idx = 0
    if pk_col and pk_col in columns:
        pk_col_idx = columns.index(pk_col)

    # 2. Получаем данные с пагинацией
    offset = (page - 1) * limit
    try:
        # Считаем общее кол-во для пагинации
        count_res = await db.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
        total_rows = count_res.scalar()

        # Выбираем данные
        # Важно: сортируем по PK, чтобы порядок был стабильным
        order_clause = f'ORDER BY "{pk_col}"' if pk_col else ''
        query = text(f'SELECT * FROM "{table_name}" {order_clause} LIMIT {limit} OFFSET {offset}')
        result = await db.execute(query)
        rows = result.all()
    except Exception as e:
        return HTMLResponse(f"Ошибка: {e}")

    # Считаем всего страниц
    total_pages = (total_rows + limit - 1) // limit

    return templates.TemplateResponse(
        "admin/partials/table_content.html",
        {
            "request": request,
            "table_name": table_name,
            "columns": columns,
            "rows": rows,
            "pk_col": pk_col,
            "pk_col_idx": pk_col_idx,
            "page": page,
            "total_pages": total_pages,
            "limit": limit
        }
    )

@router.get("/tables/edit-form/{table_name}/{pk_val}", response_class=HTMLResponse)
async def get_edit_form(
    request: Request,
    table_name: str,
    pk_val: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Возвращает форму редактирования для модального окна."""
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403)

    # 1. Интроспекция (нужны колонки, типы и PK)
    def get_info(connection):
        inspector = inspect(connection)
        pk_constraint = inspector.get_pk_constraint(table_name)
        pk_columns = pk_constraint['constrained_columns']
        # Получаем детальную информацию о колонках (тип, nullable и т.д.)
        columns = inspector.get_columns(table_name)
        return columns, pk_columns

    async with engine.connect() as conn:
        columns_info, pk_columns = await conn.run_sync(get_info)
    
    pk_col = pk_columns[0] if pk_columns else None
    if not pk_col:
        return HTMLResponse("PK не найден")

    # 2. Получаем данные строки
    # Приводим pk_val к int если надо
    pk_val_typed = int(pk_val) if pk_val.isdigit() else pk_val
        
    query = text(f'SELECT * FROM "{table_name}" WHERE "{pk_col}" = :pk')
    res = await db.execute(query, {"pk": pk_val_typed})
    row = res.mappings().one_or_none() # Используем mappings() для доступа по имени
    
    if not row:
        return HTMLResponse("Запись не найдена")

    return templates.TemplateResponse(
        "admin/partials/edit_modal.html",
        {
            "request": request,
            "table_name": table_name,
            "row": row,
            "columns": columns_info, # Передаем метаданные колонок
            "pk_col": pk_col,
            "pk_val": pk_val
        }
    )

@router.post("/tables/update-row/{table_name}/{pk_val}")
async def update_table_row_modal(
    request: Request,
    table_name: str,
    pk_val: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403)

    form_data = await request.form()
    
    # 1. Получаем информацию о типах колонок
    def get_table_meta(connection):
        inspector = inspect(connection)
        pk_constraint = inspector.get_pk_constraint(table_name)
        pk_col = pk_constraint['constrained_columns'][0]
        columns = inspector.get_columns(table_name)
        # Создаем словарь: имя колонки -> тип (строкой или объектом)
        col_types = {c['name']: c['type'] for c in columns}
        return pk_col, col_types
    
    async with engine.connect() as conn:
        pk_col, col_types = await conn.run_sync(get_table_meta)

    # 2. Формируем запрос и конвертируем типы
    set_clauses = []
    params = {"pk": int(pk_val) if pk_val.isdigit() else pk_val}
    
    for col, val in form_data.items():
        if col == pk_col: continue
        
        # Получаем тип колонки
        col_type = str(col_types.get(col, '')).upper()
        
        set_clauses.append(f'"{col}" = :{col}')
        
        if val == "" or val == "NULL":
            params[col] = None
        else:
            # --- КОНВЕРТАЦИЯ ТИПОВ ---
            try:
                if 'DATE' in col_type:
                    # '1990-01-01' -> date object
                    params[col] = datetime.strptime(val, '%Y-%m-%d').date()
                elif 'TIMESTAMP' in col_type or 'DATETIME' in col_type:
                    # Попытка парсинга с временем
                    # HTML datetime-local дает формат 'YYYY-MM-DDTHH:MM'
                    # Простой date input дает 'YYYY-MM-DD'
                    if 'T' in val:
                         params[col] = datetime.strptime(val, '%Y-%m-%dT%H:%M')
                    else:
                         params[col] = datetime.strptime(val, '%Y-%m-%d %H:%M:%S') # Или другой формат, который у вас в инпуте
                elif 'INT' in col_type:
                    params[col] = int(val)
                elif 'BOOL' in col_type:
                    params[col] = val.lower() == 'true'
                else:
                    # По умолчанию строка
                    params[col] = val
            except ValueError:
                # Если не смогли распарсить, пробуем отправить как есть (Postgres может сам выкинуть ошибку)
                # Или для дат это может быть формат с временем
                if 'TIMESTAMP' in col_type:
                     try:
                         # Попробуем распарсить то, что пришло из БД ранее (если формат строки специфичный)
                         params[col] = datetime.fromisoformat(val)
                     except:
                         params[col] = val
                else:
                    params[col] = val

    if set_clauses:
        query = text(f'UPDATE "{table_name}" SET {", ".join(set_clauses)} WHERE "{pk_col}" = :pk')
        try:
            await db.execute(query, params)
            await db.commit()
        except Exception as e:
            return HTMLResponse(f"<div class='bg-red-100 text-red-700 p-4 rounded mb-4'>Ошибка БД: {e}</div>", status_code=200)

    # Успех
    return HTMLResponse(
        '<div id="modal-container" hx-swap-oob="true"></div>', 
        headers={"HX-Trigger": "tableUpdated"}
    )

@router.delete("/tables/row/delete/{table_name}/{pk_val}")
async def delete_table_row(
    request: Request,
    table_name: str,
    pk_val: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Удаляет строку из таблицы."""
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403)

    # 1. Получаем PK колонку (для безопасности и where clause)
    def get_pk(connection):
        # Обработка ошибки, если PK нет
        try:
            return inspect(connection).get_pk_constraint(table_name)['constrained_columns'][0]
        except (IndexError, KeyError):
            return None
    
    async with engine.connect() as conn:
        pk_col = await conn.run_sync(get_pk)

    if not pk_col:
        return HTMLResponse("Невозможно удалить: у таблицы нет Primary Key", status_code=400)

    # 2. Удаляем
    # Приводим тип, если это число
    pk_val_typed = int(pk_val) if pk_val.isdigit() else pk_val
    
    try:
        query = text(f'DELETE FROM "{table_name}" WHERE "{pk_col}" = :pk')
        await db.execute(query, {"pk": pk_val_typed})
        await db.commit()
    except Exception as e:
        # Можно вернуть тост с ошибкой
        return HTMLResponse(status_code=200, headers={"HX-Trigger": json.dumps({"showToast": f"Ошибка удаления: {e}"})})

    # 3. Возвращаем пустой ответ (строка исчезнет) + Тост успеха
    return HTMLResponse(
        content="", 
        status_code=200,
        headers={"HX-Trigger": json.dumps({"showToast": "Запись удалена"})}
    )

@router.get("/tables/create-form/{table_name}", response_class=HTMLResponse)
async def get_create_form(
    request: Request,
    table_name: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Возвращает форму создания записи."""
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403)

    # Интроспекция: получаем список колонок и их типы
    def get_columns_info(connection):
        inspector = inspect(connection)
        # Получаем PK, чтобы (возможно) скрыть его из формы, если он auto-increment
        pk_constraint = inspector.get_pk_constraint(table_name)
        pk_col = pk_constraint['constrained_columns'][0] if pk_constraint['constrained_columns'] else None
        
        columns = inspector.get_columns(table_name)
        return columns, pk_col

    async with engine.connect() as conn:
        columns, pk_col = await conn.run_sync(get_columns_info)

    return templates.TemplateResponse(
        "admin/partials/create_modal.html",
        {
            "request": request,
            "table_name": table_name,
            "columns": columns,
            "pk_col": pk_col
        }
    )

@router.post("/tables/create-row/{table_name}")
async def create_table_row(
    request: Request,
    table_name: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Создает новую запись."""
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403)

    form_data = await request.form()
    
    # Интроспекция для типов данных
    def get_col_types(connection):
        return {c['name']: c['type'] for c in inspect(connection).get_columns(table_name)}
    
    async with engine.connect() as conn:
        col_types = await conn.run_sync(get_col_types)

    # Формируем INSERT
    cols = []
    params = {}
    
    for col, val in form_data.items():
        # Пропускаем пустые PK (обычно они SERIAL/AUTO_INCREMENT)
        if val == "" and col == form_data.get("pk_col_name"):
            continue
            
        cols.append(f'"{col}"')
        
        # Конвертация типов (аналогично update)
        col_type = str(col_types.get(col, '')).upper()
        
        if val == "" or val == "NULL":
             params[col] = None
        else:
             try:
                if 'DATE' in col_type:
                    params[col] = datetime.strptime(val, '%Y-%m-%d').date()
                elif 'INT' in col_type:
                    params[col] = int(val)
                elif 'BOOL' in col_type:
                    params[col] = val.lower() == 'true'
                else:
                    params[col] = val
             except:
                 params[col] = val # Fallback

    if cols:
        placeholders = [f":{c.replace('\"', '')}" for c in cols]
        query = text(f'INSERT INTO "{table_name}" ({", ".join(cols)}) VALUES ({", ".join(placeholders)})')
        
        try:
            await db.execute(query, params)
            await db.commit()
        except Exception as e:
            return HTMLResponse(f"<div class='bg-red-100 text-red-700 p-4 rounded mb-4'>Ошибка: {e}</div>", status_code=200)

    # Успех: Закрываем модалку и обновляем таблицу
    return HTMLResponse(
        '<div id="modal-container" hx-swap-oob="true"></div>', 
        headers={"HX-Trigger": json.dumps({"tableUpdated": True, "showToast": "Запись создана"})}
    )
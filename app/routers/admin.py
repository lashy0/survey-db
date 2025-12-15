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
from app.core.security import get_password_hash

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")

# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ---
async def _get_table_options(conn, table_name, columns_info):
    """
    Собирает варианты выбора (options) для Foreign Keys и Enums.
    """
    options_map = {}
    print(f"--- [DEBUG] Loading options for table: {table_name} ---")

    # 1. Заполняем хардкод (Гарантированные значения)
    for col in columns_info:
        col_name = col['name']
        col_type_str = str(col['type']).upper()
        
        if col_name == 'role':
            options_map[col_name] = ['user', 'creator', 'admin']
        elif col_name == 'status':
            options_map[col_name] = ['draft', 'active', 'completed', 'archived']
        elif col_name == 'question_type':
            options_map[col_name] = ['single_choice', 'multiple_choice', 'text_answer', 'rating']
        elif "ENUM" in col_type_str and "(" in col_type_str and col_name not in options_map:
            try:
                content = col_type_str.split("(")[1].split(")")[0]
                variants = [v.strip().strip("'") for v in content.split(",")]
                options_map[col_name] = variants
            except:
                pass

    # 2. Ищем Foreign Keys (Связи)
    def get_fks(connection):
        return inspect(connection).get_foreign_keys(table_name)
    
    try:
        fks = await conn.run_sync(get_fks)
        for fk in fks:
            col_name = fk['constrained_columns'][0]
            ref_table = fk['referred_table']
            ref_col = fk['referred_columns'][0]
            
            def get_ref_cols(connection):
                return inspect(connection).get_columns(ref_table)
            
            try:
                ref_cols_info = await conn.run_sync(get_ref_cols)
                display_col = ref_col 
                for c in ref_cols_info:
                    if c['name'] in ['name', 'title', 'full_name', 'email', 'label', 'option_text']:
                        display_col = c['name']
                        break
                
                query = text(f'SELECT "{ref_col}", "{display_col}" FROM "{ref_table}" LIMIT 100')
                res = await conn.execute(query)
                options_map[col_name] = res.all()
            except Exception as e:
                print(f"Error checking FK {col_name}: {e}")

    except Exception as e:
        print(f"Error getting FKs: {e}")

    return options_map


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
    
    all_surveys = (await db.execute(select(Survey).order_by(Survey.title))).scalars().all()
    
    total_users = await db.scalar(select(func.count(User.user_id))) or 0
    total_surveys = await db.scalar(select(func.count(Survey.survey_id))) or 0
    total_responses = await db.scalar(select(func.count(SurveyResponse.response_id))) or 0
    
    cnt_users = total_users
    cnt_started = await db.scalar(select(func.count(SurveyResponse.user_id.distinct()))) or 0
    cnt_completed = await db.scalar(select(func.count(SurveyResponse.user_id.distinct())).where(SurveyResponse.completed_at.is_not(None))) or 0
    
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
        d = int(row.dow) - 1
        h = int(row.hour)
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
            "kpi": {"users": total_users, "surveys": total_surveys, "responses": total_responses},
            "funnel_data": funnel_data,
            "time_series_data": time_series_data,
            "tags_data": tags_data,
            "anomalies": anomalies_res,
            "heatmap_data": heatmap_data,
            "all_surveys": all_surveys,
            "selected_survey_id": survey_id
        }
    )

@router.get("/analytics/anomalies", response_class=HTMLResponse)
async def get_anomalies_partial(
    request: Request,
    survey_id: Union[int, str, None] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403)
    if survey_id == "": survey_id = None
    if survey_id is not None:
        try: survey_id = int(survey_id)
        except: survey_id = None
    
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
    def get_table_names(connection):
        inspector = inspect(connection)
        return inspector.get_table_names()
    async with engine.connect() as conn:
        table_names = await conn.run_sync(get_table_names)
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
    page: int = 1,
    limit: int = 100,
    q: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403)

    def check_table_exists(connection):
        return inspect(connection).has_table(table_name)
    async with engine.connect() as conn:
        if not await conn.run_sync(check_table_exists):
            return HTMLResponse("Таблица не найдена")

    def get_meta(connection):
        inspector = inspect(connection)
        pk_constraint = inspector.get_pk_constraint(table_name)
        pk_cols = pk_constraint['constrained_columns']
        columns_data = inspector.get_columns(table_name)
        fks = inspector.get_foreign_keys(table_name)
        return columns_data, pk_cols, fks

    async with engine.connect() as conn:
        columns_data, pk_cols, fks = await conn.run_sync(get_meta)

    columns = [c['name'] for c in columns_data]
    pk_col = pk_cols[0] if pk_cols else None
    pk_col_idx = columns.index(pk_col) if pk_col and pk_col in columns else 0

    where_clause = ""
    params = {}
    if q and q.strip():
        search_filters = [f'"{col["name"]}"::text ILIKE :search_q' for col in columns_data]
        if search_filters:
            where_clause = "WHERE " + " OR ".join(search_filters)
            params["search_q"] = f"%{q.strip()}%"

    offset = (page - 1) * limit
    order_col = pk_col if pk_col else columns[0]
    
    try:
        count_res = await db.execute(text(f'SELECT COUNT(*) FROM "{table_name}" {where_clause}'), params)
        total_rows = count_res.scalar()

        query_text = f'SELECT * FROM "{table_name}" {where_clause} ORDER BY "{order_col}" LIMIT {limit} OFFSET {offset}'
        result = await db.execute(text(query_text), params)
        rows = result.all()
    except Exception as e:
        return HTMLResponse(f"Ошибка SQL: {e}")

    total_pages = (total_rows + limit - 1) // limit

    resolved_data = {} 
    if rows and fks:
        async with engine.connect() as conn:
            for fk in fks:
                local_col = fk['constrained_columns'][0]
                remote_table = fk['referred_table']
                remote_col = fk['referred_columns'][0]
                
                ids_to_fetch = set()
                col_idx = columns.index(local_col)
                
                for row in rows:
                    val = row[col_idx]
                    if val is not None:
                        ids_to_fetch.add(val)
                
                if not ids_to_fetch:
                    continue

                def get_ref_cols(c): return inspect(c).get_columns(remote_table)
                ref_cols = await conn.run_sync(get_ref_cols)
                
                display_col = remote_col
                for rc in ref_cols:
                    if rc['name'] in ['full_name', 'title', 'name', 'label', 'email', 'question_text', 'option_text']:
                        display_col = rc['name']
                        break
                
                if ids_to_fetch:
                    ids_list = list(ids_to_fetch)
                    q_resolve = text(f'SELECT "{remote_col}", "{display_col}" FROM "{remote_table}" WHERE "{remote_col}" = ANY(:ids)')
                    
                    try:
                        res = await conn.execute(q_resolve, {"ids": ids_list})
                        mapping = {r[0]: str(r[1]) for r in res.all()}
                        resolved_data[local_col] = mapping
                    except Exception as e:
                        print(f"Failed to resolve FK {local_col}: {e}")

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
            "limit": limit,
            "q": q if q else "",
            "resolved_data": resolved_data
        }
    )

@router.get("/tables/create-form/{table_name}", response_class=HTMLResponse)
async def get_create_form(
    request: Request,
    table_name: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403)

    def get_schema_info(connection):
        inspector = inspect(connection)
        pk_constraint = inspector.get_pk_constraint(table_name)
        pk_col = pk_constraint['constrained_columns'][0] if pk_constraint['constrained_columns'] else None
        columns = inspector.get_columns(table_name)
        return columns, pk_col

    async with engine.connect() as conn:
        columns, pk_col = await conn.run_sync(get_schema_info)
        options_map = await _get_table_options(conn, table_name, columns)

    return templates.TemplateResponse(
        "admin/partials/create_modal.html",
        {
            "request": request,
            "table_name": table_name,
            "columns": columns,
            "pk_col": pk_col,
            "options_map": options_map
        }
    )

@router.post("/tables/create-row/{table_name}")
async def create_table_row(
    request: Request,
    table_name: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403)
    
    form_data = await request.form()
    
    def get_col_types(connection):
        return {c['name']: c['type'] for c in inspect(connection).get_columns(table_name)}
    async with engine.connect() as conn:
        col_types = await conn.run_sync(get_col_types)

    cols = []
    params = {}
    
    for col, val in form_data.items():
        if val == "" and col == form_data.get("pk_col_name"):
            continue
        
        if ('password' in col or 'hash' in col) and val:
            val = get_password_hash(val)

        cols.append(f'"{col}"')
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
                 params[col] = val

    if cols:
        placeholders = [f":{c.replace('\"', '')}" for c in cols]
        query = text(f'INSERT INTO "{table_name}" ({", ".join(cols)}) VALUES ({", ".join(placeholders)})')
        
        try:
            await db.execute(query, params)
            await db.commit()
        except Exception as e:
            return HTMLResponse(f"<div class='bg-red-100 text-red-700 p-4 rounded mb-4'>Ошибка: {e}</div>", status_code=200)

    return HTMLResponse(
        '<div id="modal-container" hx-swap-oob="true"></div>', 
        headers={"HX-Trigger": json.dumps({"tableUpdated": True, "showToast": "Запись создана"})}
    )

@router.get("/tables/edit-form/{table_name}/{pk_val}", response_class=HTMLResponse)
async def get_edit_form(
    request: Request,
    table_name: str,
    pk_val: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403)

    # Инициализация переменной, чтобы она ВСЕГДА была определена
    options_map = {} 

    def get_info(connection):
        inspector = inspect(connection)
        pk_constraint = inspector.get_pk_constraint(table_name)
        pk_columns = pk_constraint['constrained_columns']
        columns = inspector.get_columns(table_name)
        return columns, pk_columns

    async with engine.connect() as conn:
        columns_info, pk_columns = await conn.run_sync(get_info)
        # Загружаем опции и сохраняем в переменную
        options_map = await _get_table_options(conn, table_name, columns_info)

    pk_col = pk_columns[0] if pk_columns else None
    
    pk_val_typed = int(pk_val) if pk_val.isdigit() else pk_val
    query = text(f'SELECT * FROM "{table_name}" WHERE "{pk_col}" = :pk')
    res = await db.execute(query, {"pk": pk_val_typed})
    row = res.mappings().one_or_none()

    if not row:
        return HTMLResponse("Запись не найдена")

    return templates.TemplateResponse(
        "admin/partials/edit_modal.html",
        {
            "request": request,
            "table_name": table_name,
            "row": row,
            "columns": columns_info,
            "pk_col": pk_col,
            "pk_val": pk_val,
            "options_map": options_map # Передаем переменную в шаблон
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
    
    def get_table_meta(connection):
        inspector = inspect(connection)
        pk_constraint = inspector.get_pk_constraint(table_name)
        pk_col = pk_constraint['constrained_columns'][0]
        columns = inspector.get_columns(table_name)
        col_types = {c['name']: c['type'] for c in columns}
        return pk_col, col_types

    async with engine.connect() as conn:
        pk_col, col_types = await conn.run_sync(get_table_meta)
    
    set_clauses = []
    params = {"pk": int(pk_val) if pk_val.isdigit() else pk_val}
    
    for col, val in form_data.items():
        if col == pk_col: continue
        col_type = str(col_types.get(col, '')).upper()
        set_clauses.append(f'"{col}" = :{col}')
        
        if val == "" or val == "NULL":
            params[col] = None
        else:
            try:
                if 'DATE' in col_type:
                    params[col] = datetime.strptime(val, '%Y-%m-%d').date()
                elif 'TIMESTAMP' in col_type or 'DATETIME' in col_type:
                    if 'T' in val:
                         params[col] = datetime.strptime(val, '%Y-%m-%dT%H:%M')
                    else:
                         params[col] = datetime.strptime(val, '%Y-%m-%d %H:%M:%S')
                elif 'INT' in col_type:
                    params[col] = int(val)
                elif 'BOOL' in col_type:
                    params[col] = val.lower() == 'true'
                else:
                    params[col] = val
            except ValueError:
                if 'TIMESTAMP' in col_type:
                     try:
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
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403)

    def get_pk(connection):
        try:
            return inspect(connection).get_pk_constraint(table_name)['constrained_columns'][0]
        except (IndexError, KeyError):
            return None

    async with engine.connect() as conn:
        pk_col = await conn.run_sync(get_pk)

    if not pk_col:
        return HTMLResponse("Невозможно удалить: у таблицы нет Primary Key", status_code=400)

    pk_val_typed = int(pk_val) if pk_val.isdigit() else pk_val
    
    try:
        query = text(f'DELETE FROM "{table_name}" WHERE "{pk_col}" = :pk')
        await db.execute(query, {"pk": pk_val_typed})
        await db.commit()
    except Exception as e:
        return HTMLResponse(status_code=200, headers={"HX-Trigger": json.dumps({"showToast": f"Ошибка удаления: {e}"})})

    return HTMLResponse(
        content="", 
        status_code=200,
        headers={"HX-Trigger": json.dumps({"showToast": "Запись удалена"})}
    )
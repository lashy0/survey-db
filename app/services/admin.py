from datetime import datetime, date
from typing import Optional, Dict, List, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import (
    text, inspect, select, func, desc, extract, case,
    cast, Date, Numeric
)
from app.core.database import engine
from app.core.security import get_password_hash
from app.models import User, Survey, SurveyResponse, Tag, survey_tags

class AdminService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_dashboard_stats(self) -> Dict[str, Any]:
        """Собирает всю статистику для аналитической панели."""
        # 1. Базовые метрики
        total_users = await self.db.scalar(select(func.count(User.user_id))) or 0
        total_surveys = await self.db.scalar(select(func.count(Survey.survey_id))) or 0
        total_responses = await self.db.scalar(select(func.count(SurveyResponse.response_id))) or 0
        
        # 2. Воронка
        cnt_started = await self.db.scalar(select(func.count(SurveyResponse.user_id.distinct()))) or 0
        cnt_completed = await self.db.scalar(select(func.count(SurveyResponse.user_id.distinct())).where(SurveyResponse.completed_at.is_not(None))) or 0
        
        # 3. Активность по дням
        activity_res = await self.db.execute(
            select(
                func.date(SurveyResponse.started_at).label("date"),
                func.count(SurveyResponse.response_id).label("cnt")
            ).group_by(func.date(SurveyResponse.started_at))
             .order_by(func.date(SurveyResponse.started_at))
        )
        activity_rows = activity_res.all()

        # 4. Популярные теги
        tags_res = await self.db.execute(
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
        tags_rows = tags_res.all()

        # 5. Тепловая карта
        heatmap_res = await self.db.execute(
            select(
                extract('isodow', SurveyResponse.started_at).label("dow"),
                extract('hour', SurveyResponse.started_at).label("hour"),
                func.count(SurveyResponse.response_id).label("cnt")
            ).group_by("dow", "hour")
        )
        heatmap_rows = heatmap_res.all()

        # Возрастная группа
        age_val = extract('year', func.age(User.birth_date))

        age_case = case(
            (age_val < 18, 'До 18'),
            (age_val.between(18, 24), '18-24'),
            (age_val.between(25, 34), '25-34'),
            (age_val.between(35, 44), '35-44'),
            (age_val >= 45, '45+'),
            else_='Не указано'
        ).label("age_group")

        demographics_res = await self.db.execute(
            select(
                age_case, 
                func.count(SurveyResponse.response_id).label("cnt")
            )
            .select_from(SurveyResponse)
            .join(User, SurveyResponse.user_id == User.user_id)
            .where(SurveyResponse.completed_at.is_not(None)) # Только завершенные
            .group_by(age_case)
            .order_by(age_case)
        )
        demographics_rows = demographics_res.all()

        sort_order = {'До 18': 1, '18-24': 2, '25-34': 3, '35-44': 4, '45+': 5, 'Не указано': 6}
        sorted_demo = sorted(demographics_rows, key=lambda x: sort_order.get(x.age_group, 99))

        # Форматирование данных
        heatmap_z = [[0 for _ in range(24)] for _ in range(7)]
        for row in heatmap_rows:
            d = int(row.dow) - 1
            h = int(row.hour)
            if 0 <= d < 7 and 0 <= h < 24:
                heatmap_z[d][h] = row.cnt

        return {
            "kpi": {"users": total_users, "surveys": total_surveys, "responses": total_responses},
            "funnel": {
                "labels": ["Регистрация", "Начали опрос", "Завершили опрос"],
                "counts": [int(total_users), int(cnt_started), int(cnt_completed)]
            },
            "time_series": {
                "dates": [str(row.date) for row in activity_rows],
                "counts": [int(row.cnt) for row in activity_rows]
            },
            "tags": {
                "labels": [str(row.name) for row in tags_rows],
                "counts": [int(row.popularity) for row in tags_rows]
            },
            "heatmap": {
                "z": heatmap_z,
                "x": [f"{h:02d}:00" for h in range(24)],
                "y": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
            },
            "demographics": {
                "labels": [row.age_group for row in sorted_demo],
                "counts": [int(row.cnt) for row in sorted_demo]
            }
        }
    
    async def get_heatmap_stats(self, period: str = "all") -> Dict[str, Any]:
        """
        Получает данные для тепловой карты с учетом фильтра по времени.
        period: '7d', '30d', 'year', 'all'
        """
        # 1. Формируем условие фильтрации
        where_clause = SurveyResponse.started_at.is_not(None) # Базовое условие
        
        if period == '7d':
            # За последние 7 дней
            where_clause = (SurveyResponse.started_at >= func.now() - text("INTERVAL '7 days'"))
        elif period == '30d':
            # За последние 30 дней
            where_clause = (SurveyResponse.started_at >= func.now() - text("INTERVAL '30 days'"))
        elif period == 'year':
             # С начала текущего года
            where_clause = (extract('year', SurveyResponse.started_at) == extract('year', func.now()))
        
        # 2. Запрос
        heatmap_res = await self.db.execute(
            select(
                extract('isodow', SurveyResponse.started_at).label("dow"),
                extract('hour', SurveyResponse.started_at).label("hour"),
                func.count(SurveyResponse.response_id).label("cnt")
            )
            .where(where_clause) # <--- Применяем фильтр
            .group_by("dow", "hour")
        )
        heatmap_rows = heatmap_res.all()

        # 3. Формирование матрицы Z (7 дней * 24 часа)
        heatmap_z = [[0 for _ in range(24)] for _ in range(7)]
        total_hits = 0 # Для отладки или заголовка
        
        for row in heatmap_rows:
            d = int(row.dow) - 1 # isodow: 1=Monday -> index 0
            h = int(row.hour)
            if 0 <= d < 7 and 0 <= h < 24:
                heatmap_z[d][h] = row.cnt
                total_hits += row.cnt
        
        return {
            "z": heatmap_z,
            "x": [f"{h:02d}:00" for h in range(24)],
            "y": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
            "period": period,
            "total": total_hits
        }

    async def get_anomalies(self, survey_id: Optional[int] = None):
        """Поиск аномально быстрых прохождений."""
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
        query = (
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
            query = query.where(Survey.survey_id == survey_id)
            
        return (await self.db.execute(query)).all()

    async def get_all_surveys(self):
        return (await self.db.execute(select(Survey).order_by(Survey.title))).scalars().all()

    async def get_table_names(self):
        def _inspect(conn):
            return inspect(conn).get_table_names()
        async with engine.connect() as conn:
            names = await conn.run_sync(_inspect)
        names.sort()
        return names

    async def check_table_exists(self, table_name: str) -> bool:
        def _check(conn):
            return inspect(conn).has_table(table_name)
        async with engine.connect() as conn:
            return await conn.run_sync(_check)

    async def get_paginated_table_data(self, table_name: str, page: int, limit: int, q: Optional[str]):
        """Основная логика получения данных таблицы с поиском и пагинацией."""
        
        # 1. Интроспекция (Колонки и FK)
        def _get_meta(conn):
            inspector = inspect(conn)
            pk_constraint = inspector.get_pk_constraint(table_name)
            pk_cols = pk_constraint['constrained_columns']
            columns_data = inspector.get_columns(table_name)
            fks = inspector.get_foreign_keys(table_name)
            return columns_data, pk_cols, fks

        async with engine.connect() as conn:
            columns_data, pk_cols, fks = await conn.run_sync(_get_meta)

        columns = [c['name'] for c in columns_data]
        pk_col = pk_cols[0] if pk_cols else None
        pk_col_idx = columns.index(pk_col) if pk_col and pk_col in columns else 0

        # 2. Построение запроса (Поиск)
        where_clause = ""
        params = {}
        
        if q and q.strip():
            params["search_q"] = f"%{q.strip()}%"
            search_filters = []

            # А. Поиск по колонкам текущей таблицы
            for col in columns_data:
                search_filters.append(f'"{col["name"]}"::text ILIKE :search_q')
            
            # Б. Поиск по связанным таблицам (Foreign Keys) - НОВАЯ ЛОГИКА
            # Мы генерируем подзапросы: 
            # OR local_id IN (SELECT id FROM remote_table WHERE name ILIKE '%q%')
            if fks:
                async with engine.connect() as conn:
                    for fk in fks:
                        local_col = fk['constrained_columns'][0]
                        remote_table = fk['referred_table']
                        remote_pk = fk['referred_columns'][0]

                        # Инспектируем удаленную таблицу, чтобы найти текстовое поле
                        def _get_remote_cols(c): return inspect(c).get_columns(remote_table)
                        remote_cols = await conn.run_sync(_get_remote_cols)
                        
                        display_col = None
                        # Пытаемся найти колонку с названием
                        for rc in remote_cols:
                            if rc['name'] in ['name', 'title', 'full_name', 'email', 'label', 'question_text', 'option_text', 'text']:
                                display_col = rc['name']
                                break
                        
                        # Если нашли подходящую колонку в связанной таблице, добавляем поиск по ней
                        if display_col:
                            subquery = f'"{local_col}" IN (SELECT "{remote_pk}" FROM "{remote_table}" WHERE "{display_col}"::text ILIKE :search_q)'
                            search_filters.append(subquery)

            if search_filters:
                where_clause = "WHERE " + " OR ".join(search_filters)

        # 3. Выполнение запросов (Count + Select)
        offset = (page - 1) * limit
        order_col = pk_col if pk_col else columns[0] # Fallback сортировка

        try:
            count_sql = text(f'SELECT COUNT(*) FROM "{table_name}" {where_clause}')
            total_rows = (await self.db.execute(count_sql, params)).scalar()

            data_sql = text(f'SELECT * FROM "{table_name}" {where_clause} ORDER BY "{order_col}" LIMIT {limit} OFFSET {offset}')
            rows = (await self.db.execute(data_sql, params)).all()
        except Exception as e:
            raise e

        # 4. Резолвинг внешних ключей (Красивые имена вместо ID) - Оставляем как есть
        resolved_data = {}
        if rows and fks:
            async with engine.connect() as conn:
                for fk in fks:
                    local_col = fk['constrained_columns'][0]
                    col_idx = columns.index(local_col)
                    
                    ids_to_fetch = {row[col_idx] for row in rows if row[col_idx] is not None}
                    
                    if not ids_to_fetch: continue

                    remote_table = fk['referred_table']
                    remote_col = fk['referred_columns'][0]
                    
                    def _get_ref_cols(c): return inspect(c).get_columns(remote_table)
                    ref_cols = await conn.run_sync(_get_ref_cols)
                    display_col = remote_col
                    for rc in ref_cols:
                        if rc['name'] in ['full_name', 'title', 'name', 'label', 'email', 'question_text', 'option_text', 'text']:
                            display_col = rc['name']
                            break
                    
                    try:
                        ids_list = list(ids_to_fetch)
                        q_resolve = text(f'SELECT "{remote_col}", "{display_col}" FROM "{remote_table}" WHERE "{remote_col}" = ANY(:ids)')
                        res = await conn.execute(q_resolve, {"ids": ids_list})
                        resolved_data[local_col] = {r[0]: str(r[1]) for r in res.all()}
                    except Exception:
                        pass 

        return {
            "columns": columns,
            "rows": rows,
            "pk_col": pk_col,
            "pk_col_idx": pk_col_idx,
            "total_pages": (total_rows + limit - 1) // limit,
            "resolved_data": resolved_data
        }

    async def get_form_options(self, table_name: str, columns_info=None):
        """Собирает опции для выпадающих списков."""
        options_map = {}
        
        # Если columns_info не переданы, получаем их
        if not columns_info:
             def _get_cols(c): return inspect(c).get_columns(table_name)
             async with engine.connect() as conn:
                 columns_info = await conn.run_sync(_get_cols)

        # 1. Хардкод значений (для Enum)
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
                    options_map[col_name] = [v.strip().strip("'") for v in content.split(",")]
                except: pass

        # 2. Foreign Keys
        def _get_fks(c): return inspect(c).get_foreign_keys(table_name)
        async with engine.connect() as conn:
            try:
                fks = await conn.run_sync(_get_fks)
                for fk in fks:
                    col_name = fk['constrained_columns'][0]
                    ref_table = fk['referred_table']
                    ref_col = fk['referred_columns'][0]
                    
                    # Ищем display column
                    def _get_ref(c): return inspect(c).get_columns(ref_table)
                    ref_cols = await conn.run_sync(_get_ref)
                    display_col = ref_col
                    for c in ref_cols:
                        if c['name'] in ['name', 'title', 'full_name', 'email', 'label']:
                            display_col = c['name']
                            break
                    
                    query = text(f'SELECT "{ref_col}", "{display_col}" FROM "{ref_table}" LIMIT 100')
                    res = await conn.execute(query)
                    options_map[col_name] = res.all()
            except Exception as e:
                print(f"FK Load Error: {e}")

        return options_map

    async def create_row(self, table_name: str, form_data: dict):
        def _get_types(c): return {col['name']: col['type'] for col in inspect(c).get_columns(table_name)}
        async with engine.connect() as conn:
            col_types = await conn.run_sync(_get_types)

        cols = []
        params = {}
        for col, val in form_data.items():
            if val == "" and col == form_data.get("pk_col_name"): continue
            
            if ('password' in col or 'hash' in col) and val:
                val = get_password_hash(val)
            
            cols.append(f'"{col}"')
            
            # Базовое приведение типов
            if val == "" or val == "NULL":
                params[col] = None
            else:
                col_type = str(col_types.get(col, '')).upper()
                try:
                    if 'INT' in col_type: params[col] = int(val)
                    elif 'BOOL' in col_type: params[col] = (val.lower() == 'true')
                    elif 'DATE' in col_type: params[col] = datetime.strptime(val, '%Y-%m-%d').date()
                    else: params[col] = val
                except:
                    params[col] = val

        if cols:
            placeholders = [f":{c.replace('\"', '')}" for c in cols]
            sql = text(f'INSERT INTO "{table_name}" ({", ".join(cols)}) VALUES ({", ".join(placeholders)})')
            await self.db.execute(sql, params)
            await self.db.commit()

    async def update_row(self, table_name: str, pk_val: int, form_data: dict):
        def _get_meta(c): 
            insp = inspect(c)
            pk = insp.get_pk_constraint(table_name)['constrained_columns'][0]
            types = {col['name']: col['type'] for col in insp.get_columns(table_name)}
            return pk, types

        async with engine.connect() as conn:
            pk_col, col_types = await conn.run_sync(_get_meta)

        set_clauses = []
        params = {"pk": pk_val}
        
        for col, val in form_data.items():
            if col == pk_col: continue
            
            set_clauses.append(f'"{col}" = :{col}')
            col_type = str(col_types.get(col, '')).upper()
            
            if val == "" or val == "NULL":
                params[col] = None
            else:
                try:
                     if 'INT' in col_type: params[col] = int(val)
                     elif 'BOOL' in col_type: params[col] = (val.lower() == 'true')
                     elif 'DATE' in col_type: params[col] = datetime.strptime(val, '%Y-%m-%d').date()
                     # Добавьте хеширование пароля при обновлении, если он не пустой
                     elif ('password' in col or 'hash' in col):
                         params[col] = get_password_hash(val)
                     else: params[col] = val
                except:
                    params[col] = val
        
        if set_clauses:
            sql = text(f'UPDATE "{table_name}" SET {", ".join(set_clauses)} WHERE "{pk_col}" = :pk')
            await self.db.execute(sql, params)
            await self.db.commit()

    async def delete_row(self, table_name: str, pk_val: int):
        def _get_pk(c): return inspect(c).get_pk_constraint(table_name)['constrained_columns'][0]
        async with engine.connect() as conn:
            pk_col = await conn.run_sync(_get_pk)
        
        sql = text(f'DELETE FROM "{table_name}" WHERE "{pk_col}" = :pk')
        await self.db.execute(sql, {"pk": pk_val})
        await self.db.commit()
    
    async def get_data_for_export(self, table_name: str, q: Optional[str]):
        """Получает итератор данных для экспорта (без пагинации)."""
        
        # 1. Интроспекция (нужны имена колонок для заголовка CSV и фильтрации)
        def _get_meta(conn):
            insp = inspect(conn)
            return insp.get_columns(table_name), insp.get_pk_constraint(table_name)['constrained_columns']

        async with engine.connect() as conn:
            columns_data, pk_cols = await conn.run_sync(_get_meta)

        columns = [c['name'] for c in columns_data]
        pk_col = pk_cols[0] if pk_cols else columns[0]

        # 2. Фильтрация (Копия логики из get_paginated_table_data)
        where_clause = ""
        params = {}
        if q and q.strip():
            search_filters = [f'"{col["name"]}"::text ILIKE :search_q' for col in columns_data]
            if search_filters:
                where_clause = "WHERE " + " OR ".join(search_filters)
                params["search_q"] = f"%{q.strip()}%"

        # 3. Запрос (Без LIMIT/OFFSET)
        # Используем stream() для эффективного чтения больших таблиц
        sql = text(f'SELECT * FROM "{table_name}" {where_clause} ORDER BY "{pk_col}"')
        
        # Возвращаем имена колонок и сам объект результата (который можно итерировать)
        result = await self.db.stream(sql, params)
        return columns, result
    
    async def get_activity_stats(self, start_date: Optional[date] = None, end_date: Optional[date] = None) -> Dict[str, Any]:
        """Получает статистику активности с фильтрацией по датам."""
        
        query = (
            select(
                func.date(SurveyResponse.started_at).label("date"),
                func.count(SurveyResponse.response_id).label("cnt")
            )
            .group_by(func.date(SurveyResponse.started_at))
            .order_by(func.date(SurveyResponse.started_at))
        )

        # Фильтры
        if start_date:
            query = query.where(func.date(SurveyResponse.started_at) >= start_date)
        if end_date:
            query = query.where(func.date(SurveyResponse.started_at) <= end_date)

        activity_res = await self.db.execute(query)
        activity_rows = activity_res.all()

        return {
            "dates": [str(row.date) for row in activity_rows],
            "counts": [int(row.cnt) for row in activity_rows]
        }
    
    async def get_cohort_stats(self) -> Dict[str, Any]:
        """
        Строит данные для когортного анализа (Retention Rate) с использованием SQLAlchemy Core.
        """
        
        # 1. CTE: Когорты пользователей (User Cohorts)
        # Получаем месяц регистрации для каждого пользователя
        uc_cte = (
            select(
                User.user_id,
                cast(func.date_trunc('month', User.registration_date), Date).label('cohort_month')
            )
            .cte('user_cohorts')
        )

        # 2. CTE: Размер когорты (Cohort Size)
        # Считаем сколько людей зарегистрировалось в каждом месяце
        cs_cte = (
            select(
                uc_cte.c.cohort_month,
                func.count().label('total_users')
            )
            .group_by(uc_cte.c.cohort_month)
            .cte('cohort_size')
        )

        # 3. CTE: Активность пользователей (User Activities)
        # Группируем ответы по пользователям и месяцам
        ua_cte = (
            select(
                SurveyResponse.user_id,
                cast(func.date_trunc('month', SurveyResponse.completed_at), Date).label('activity_month')
            )
            .where(SurveyResponse.completed_at.is_not(None))
            .group_by(SurveyResponse.user_id, text("2")) # Группировка по user_id и месяцу
            .cte('user_activities')
        )

        # 4. Вычисление Month Lag (разница в месяцах)
        # Формула: (Год активности - Год когорты)*12 + (Месяц активности - Месяц когорты)
        # Используем func.age (Postgres specific)
        age_expression = func.age(ua_cte.c.activity_month, uc_cte.c.cohort_month)
        month_lag_col = cast(
            extract('year', age_expression) * 12 + extract('month', age_expression), 
            Numeric
        ).label('month_lag')

        # 5. Вычисление Retention %
        # (Активные / Всего) * 100
        active_count = func.count(func.distinct(uc_cte.c.user_id))
        retention_pct = func.round(
            cast(active_count, Numeric) / cs_cte.c.total_users * 100, 
            1
        ).label('retention_pct')

        # 6. Финальный запрос
        stmt = (
            select(
                func.to_char(uc_cte.c.cohort_month, 'YYYY-MM').label('cohort'),
                cs_cte.c.total_users,
                month_lag_col,
                retention_pct
            )
            .select_from(uc_cte)
            .join(cs_cte, uc_cte.c.cohort_month == cs_cte.c.cohort_month)
            .join(ua_cte, uc_cte.c.user_id == ua_cte.c.user_id)
            .where(ua_cte.c.activity_month >= uc_cte.c.cohort_month) # Активность после регистрации
            .group_by(uc_cte.c.cohort_month, cs_cte.c.total_users, month_lag_col)
            .order_by(uc_cte.c.cohort_month, month_lag_col)
        )

        # Выполнение
        result = (await self.db.execute(stmt)).all()
        
        # --- ДАЛЕЕ ЛОГИКА ФОРМАТИРОВАНИЯ (ОСТАЕТСЯ ПРЕЖНЕЙ) ---
        if not result:
            return {"z": [], "x": [], "y": [], "text": []}

        # 1. Оси
        cohorts = sorted(list(set(row.cohort for row in result)))
        # Преобразуем lag в int, так как из базы может прийти decimal
        lags_values = [int(row.month_lag) for row in result]
        max_lag = max(lags_values) if lags_values else 0
        lags = list(range(max_lag + 1))
        
        # 2. Матрицы
        z = [[None for _ in lags] for _ in cohorts]
        annotation_text = [["" for _ in lags] for _ in cohorts]
        
        cohort_idx = {c: i for i, c in enumerate(cohorts)}
        
        for row in result:
            r_idx = cohort_idx[row.cohort]
            c_idx = int(row.month_lag)
            
            if c_idx < len(lags):
                val = float(row.retention_pct)
                z[r_idx][c_idx] = val
                annotation_text[r_idx][c_idx] = f"{val}%"

        return {
            "y": cohorts,
            "x": [f"M+{i}" for i in lags],
            "z": z,
            "text": annotation_text
        }

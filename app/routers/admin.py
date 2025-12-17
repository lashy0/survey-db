import json
import csv
import io
from typing import Optional, Union
from datetime import datetime, date
from fastapi import APIRouter, Request, Depends, HTTPException, Body
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, case, text, extract, inspect

from app.core.database import get_db, engine
from app.core.deps import get_current_user
from app.models import User, Survey, SurveyResponse, Tag, survey_tags, UserRole
from app.core.security import get_password_hash
from app.services.admin import AdminService

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")

# Зависимость для получения сервиса
def get_admin_service(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> AdminService:
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    return AdminService(db)

@router.get("/analytics", response_class=HTMLResponse)
async def analytics_dashboard(
    request: Request,
    survey_id: Union[int, str, None] = None, 
    service: AdminService = Depends(get_admin_service),
    user: User = Depends(get_current_user) # <--- ВЕРНУЛИ USER
) -> HTMLResponse:
    if survey_id is not None:
        try:
            survey_id = int(survey_id)
        except ValueError:
            survey_id = None
            
    # Получаем данные через сервис
    data = await service.get_dashboard_stats()
    anomalies = await service.get_anomalies(survey_id)
    all_surveys = await service.get_all_surveys()

    return templates.TemplateResponse(
        request=request,
        name="admin/analytics.html",
        context={
            "user": user, # <--- ПЕРЕДАЕМ В ШАБЛОН
            "kpi": data['kpi'],
            "funnel_data": data['funnel'],
            "time_series_data": data['time_series'],
            "tags_data": data['tags'],
            "heatmap_data": data['heatmap'],
            "anomalies": anomalies,
            "all_surveys": all_surveys,
            "selected_survey_id": survey_id
        }
    )

@router.get("/analytics/anomalies", response_class=HTMLResponse)
async def get_anomalies_partial(
    request: Request,
    survey_id: Union[int, str, None] = None,
    service: AdminService = Depends(get_admin_service)
):
    # Здесь user не нужен, это частичный HTML для таблицы
    if survey_id == "": survey_id = None
    if survey_id: survey_id = int(survey_id)
    
    anomalies = await service.get_anomalies(survey_id)
    return templates.TemplateResponse(
        request=request,
        name="admin/partials/anomalies_table.html",
        context={
            "anomalies": anomalies
        }
    )

@router.get("/tables_view", response_class=HTMLResponse)
async def view_tables_dashboard(
    request: Request,
    service: AdminService = Depends(get_admin_service),
    user: User = Depends(get_current_user) # <--- ВЕРНУЛИ USER
):
    tables = await service.get_table_names()
    return templates.TemplateResponse(
        request=request,
        name="admin/tables.html", 
        context={
            "user": user, # <--- ПЕРЕДАЕМ В ШАБЛОН
            "tables": tables
        }
    )

@router.get("/tables/data/{table_name}", response_class=HTMLResponse)
async def get_table_data(
    request: Request,
    table_name: str,
    page: int = 1,
    limit: int = 100,
    q: Optional[str] = None,
    service: AdminService = Depends(get_admin_service)
):
    if not await service.check_table_exists(table_name):
        return HTMLResponse("Таблица не найдена")

    try:
        data = await service.get_paginated_table_data(table_name, page, limit, q)
    except Exception as e:
        return HTMLResponse(f"Error: {e}")

    return templates.TemplateResponse(
        request=request,
        name="admin/partials/table_content.html",
        context={
            "table_name": table_name,
            **data, 
            "page": page,
            "limit": limit,
            "q": q if q else ""
        }
    )

@router.get("/tables/create-form/{table_name}", response_class=HTMLResponse)
async def get_create_form(
    request: Request,
    table_name: str,
    service: AdminService = Depends(get_admin_service)
):
    def _get_cols(c): 
        insp = inspect(c)
        return insp.get_columns(table_name), insp.get_pk_constraint(table_name)['constrained_columns'][0]
    
    async with engine.connect() as conn:
        columns, pk_col = await conn.run_sync(_get_cols)
    
    options = await service.get_form_options(table_name, columns)
    
    return templates.TemplateResponse(
        request=request,
        name="admin/partials/create_modal.html",
        context={
            "table_name": table_name,
            "columns": columns,
            "pk_col": pk_col,
            "options_map": options
        }
    )

@router.post("/tables/create-row/{table_name}")
async def create_table_row(
    request: Request,
    table_name: str,
    service: AdminService = Depends(get_admin_service)
):
    form_data = await request.form()
    try:
        await service.create_row(table_name, dict(form_data))
        return HTMLResponse('<div id="modal-container" hx-swap-oob="true"></div>', headers={"HX-Trigger": json.dumps({"tableUpdated": True, "showToast": "Запись создана"})})
    except Exception as e:
        return HTMLResponse(f"<div class='bg-red-100 text-red-700 p-4 rounded mb-4'>Ошибка: {e}</div>", status_code=200)

@router.get("/tables/edit-form/{table_name}/{pk_val}", response_class=HTMLResponse)
async def get_edit_form(
    request: Request,
    table_name: str,
    pk_val: str,
    service: AdminService = Depends(get_admin_service)
):
    def _get_info(c): 
        insp = inspect(c)
        return insp.get_columns(table_name), insp.get_pk_constraint(table_name)['constrained_columns'][0]

    async with engine.connect() as conn:
        columns, pk_col = await conn.run_sync(_get_info)

    pk_val = int(pk_val) if pk_val.isdigit() else pk_val
    
    res = await service.db.execute(text(f'SELECT * FROM "{table_name}" WHERE "{pk_col}" = :pk'), {"pk": pk_val})
    row = res.mappings().one_or_none()
    
    if not row: return HTMLResponse("Запись не найдена")

    options = await service.get_form_options(table_name, columns)

    return templates.TemplateResponse(
        request=request,
        name="admin/partials/edit_modal.html",
        context={
            "table_name": table_name,
            "row": row,
            "columns": columns,
            "pk_col": pk_col,
            "pk_val": pk_val,
            "options_map": options
        }
    )

@router.post("/tables/update-row/{table_name}/{pk_val}")
async def update_table_row_modal(
    request: Request,
    table_name: str,
    pk_val: str,
    service: AdminService = Depends(get_admin_service)
):
    form_data = await request.form()
    pk_val = int(pk_val) if pk_val.isdigit() else pk_val
    
    try:
        await service.update_row(table_name, pk_val, dict(form_data))
        return HTMLResponse('<div id="modal-container" hx-swap-oob="true"></div>', headers={"HX-Trigger": "tableUpdated"})
    except Exception as e:
        return HTMLResponse(f"<div class='bg-red-100 text-red-700 p-4 rounded mb-4'>Ошибка: {e}</div>", status_code=200)

@router.delete("/tables/row/delete/{table_name}/{pk_val}")
async def delete_table_row(
    request: Request,
    table_name: str,
    pk_val: str,
    service: AdminService = Depends(get_admin_service)
):
    pk_val = int(pk_val) if pk_val.isdigit() else pk_val
    try:
        await service.delete_row(table_name, pk_val)
        return HTMLResponse("", headers={"HX-Trigger": json.dumps({"showToast": "Запись удалена"})})
    except Exception as e:
        return HTMLResponse(status_code=200, headers={"HX-Trigger": json.dumps({"showToast": f"Ошибка: {e}"})})

@router.get("/tables/export/{table_name}")
async def export_table_csv(
    table_name: str,
    q: Optional[str] = None,
    service: AdminService = Depends(get_admin_service)
):
    """Генерация CSV файла на лету."""
    
    # 1. Получаем данные
    try:
        columns, result_stream = await service.get_data_for_export(table_name, q)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка экспорта: {e}")

    # 2. Создаем генератор
    async def iter_csv():
        output = io.StringIO()
        writer = csv.writer(output)

        # Пишем заголовок
        writer.writerow(columns)
        # ВАЖНО: Только первый чанк кодируем с BOM (utf-8-sig)
        yield output.getvalue().encode('utf-8-sig') 
        output.seek(0)
        output.truncate(0)

        # Пишем строки асинхронно
        async for row in result_stream:
            writer.writerow(row)
            # ВАЖНО: Остальные строки кодируем просто в utf-8
            yield output.getvalue().encode('utf-8') 
            output.seek(0)
            output.truncate(0)

    # 3. Отдаем поток
    filename = f"{table_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return StreamingResponse(
        iter_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
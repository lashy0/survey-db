from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.deps import get_optional_user
from app.models import Survey, User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def read_root(
    request: Request, 
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user)
) -> HTMLResponse:
    """
    Renders the homepage with a list of available surveys.

    Args:
        request (Request): The raw HTTP request object (required for Jinja2).
        db (AsyncSession): Database session dependency.

    Returns:
        HTMLResponse: The rendered 'index.html' template.
    """
    # Create query to fetch surveys sorted by creation date
    query = select(Survey).order_by(Survey.created_at.desc())
    
    # Execute query
    result = await db.execute(query)
    surveys = result.scalars().all()

    return templates.TemplateResponse(
        name="index.html", 
        context={
            "request": request, 
            "surveys": surveys,
            "user": user
        }
    )
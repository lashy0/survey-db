from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/analytics", response_class=HTMLResponse)
async def analytics_dashboard(request: Request) -> HTMLResponse:
    """
    Renders the admin analytics dashboard.

    Args:
        request (Request): The raw HTTP request object.

    Returns:
        HTMLResponse: The rendered analytics template (to be created).
    """
    # Logic for graphs will go here later
    return templates.TemplateResponse(
        name="base.html", # Temporary, replace with analytics.html
        context={"request": request}
    )
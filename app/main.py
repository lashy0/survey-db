from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.routers import general, admin, auth, users

def create_app() -> FastAPI:
    """
    Application factory to configure and return the FastAPI app.

    Returns:
        FastAPI: Configured application instance.
    """
    app_instance = FastAPI(
        title="SurveyPlatform",
        description="A course project for analyzing survey data.",
        version="1.0.0"
    )

    # Mount static files (if you have CSS/JS files locally)
    # app_instance.mount("/static", StaticFiles(directory="static"), name="static")

    # Include routers
    app_instance.include_router(general.router)
    app_instance.include_router(admin.router)
    app_instance.include_router(auth.router)
    app_instance.include_router(users.router)

    return app_instance

app = create_app()
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.routers import general, admin, auth, users, surveys
from app.core.middleware import refresh_token_middleware

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

    # Middleware
    app_instance.middleware("http")(refresh_token_middleware)

    # Include routers
    app_instance.include_router(admin.router)
    app_instance.include_router(auth.router)
    app_instance.include_router(users.router)
    app_instance.include_router(surveys.router)
    app_instance.include_router(general.router)

    return app_instance

app = create_app()
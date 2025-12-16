from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.gzip import GZipMiddleware
from app.routers import general, admin, auth, users, surveys
from app.core.middleware import refresh_token_middleware, CsrfMiddleware
from app.core.exceptions import not_found_handler, forbidden_handler, server_error_handler, unauthorized_handler

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
    app_instance.add_middleware(CsrfMiddleware)
    app_instance.middleware("http")(refresh_token_middleware)
    app_instance.add_middleware(GZipMiddleware, minimum_size=1000)

    app_instance.add_exception_handler(404, not_found_handler)
    app_instance.add_exception_handler(403, forbidden_handler)
    app_instance.add_exception_handler(401, unauthorized_handler)
    app_instance.add_exception_handler(500, server_error_handler)

    # Include routers
    app_instance.include_router(admin.router)
    app_instance.include_router(auth.router)
    app_instance.include_router(users.router)
    app_instance.include_router(surveys.router)
    app_instance.include_router(general.router)

    return app_instance

app = create_app()
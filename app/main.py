import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi import APIRouter
from .routers import auth as auth_router, words as words_router
from .exceptions import validation_exception_handler, http_exception_handler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(title="English Learning API")

# Глобальный обработчик ошибок
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Incoming request: {request.method} {request.url}")
    try:
        response = await call_next(request)
    except Exception as e:
        logger.error(f"Request failed: {str(e)}")
        raise
    logger.info(f"Request completed: {response.status_code}")
    return response

# Версионирование API
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router.router, prefix="/auth")
api_router.include_router(words_router.router)

app.include_router(api_router)

from fastapi.responses import RedirectResponse

@app.get("/")
def root():
    return {"message": "English Learning API работает"}

# Редиректы для обратной совместимости
@app.post("/login")
def redirect_login():
    return RedirectResponse(url="/api/v1/auth/login", status_code=307)

@app.post("/register")
def redirect_register():
    return RedirectResponse(url="/api/v1/auth/register", status_code=307)

@app.get("/me")
def redirect_me():
    return RedirectResponse(url="/api/v1/auth/me", status_code=307)

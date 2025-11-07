import logging
 
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


# Routers
from routers.auth_route import router as auth_router
from routers.chat_route import router as chat_router
from routers.generate_doc import router as generate_doc_router

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger("legal_genie")
 
# Lifespan Events (Startup/Shutdown)
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up Legal Genie API...")
    yield
    logger.info("Shutting down Legal Genie API...")
 
 
# FastAPI App Setup
app = FastAPI(
    title="Legal Genie",
    description="AI-powered legal assistance API.",
    version="1.0.0",
    lifespan=lifespan,
)
 
origins = [
    "http://192.168.0.112:8085", # Your React app's default development URL
    "http://localhost:3000", # Vite's default development URL
    # Add your production frontend URL here later
]

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
 
# Routers
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])

app.include_router(chat_router, prefix="/api", tags=["Chat"])

app.include_router(generate_doc_router, prefix="/api", tags=["Document Generation"])

# Health & Root Endpoints
@app.get("/health", tags=["System"], summary="Health Check")
async def health_check():
    """Check if the API is healthy and running."""
    logger.info("Health check requested")
    return {"status": "ok"}
 
@app.get("/", tags=["Root"], summary="API Root")
async def root():
    """Welcome message and basic info."""
    return {"message": "Welcome to Legal Genie API"}
 
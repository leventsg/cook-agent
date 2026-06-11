from app.config import settings
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.database.session import init_db, close_db
from app.database.document_repository import DocumentRepository
from app.services.rag_service import rag_service_instance
from app.security.middleware.rate_limiter import rate_limiter
from app.services.auth_service import auth_service
from app.security.audit import audit_logger
from app.api.v1.endpoints import (
    conversation,
    auth,
    personal_docs,
    user,
    evaluation,
    llm_stats,
    agent,
    diet,
)
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def lifespan(app: FastAPI):
    """应用生命周期管理器，用于处理启动和关闭事件"""
    # 启动

    # jwt-key 检查
    if not settings.JWT_SECRET_KEY:
        logger.error("SECURITY ERROR: JWT_SECRET_KEY environment variable is not set!")
        logger.error(
            "Please set JWT_SECRET_KEY in your .env file or environment variables."
        )
        raise RuntimeError("JWT_SECRET_KEY must be configured for security")
    
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized.")

    # # 初始化 Agent 模块(default agent, tools, skills)
    # logger.info("Initializing Agent module...")
    # from app.agent import setup_agent_module, setup_mcp_servers

    # setup_agent_module()
    # logger.info("Agent module initialized.")

    # # 注册 MCP 服务
    # logger.info("Registering MCP servers...")
    # try:
    #     await setup_mcp_servers()
    #     logger.info("MCP servers registered.")
    # except Exception as e:
    #     logger.warning(f"Failed to register MCP servers: {e}")

    # 初始化知识文档缓存
    logger.info("Initializing metadata cache...")
    await DocumentRepository.init_all_metadata_cache()
    logger.info("Metadata cache initialized.")

    # # 清除 Redis 缓存并初始化 Redis 限流器
    # if (
    #     rag_service_instance.cache_manager
    #     and rag_service_instance.cache_manager.redis_client
    # ):
    #     # 初始化限流器的Redis
    #     rate_limiter.set_redis(rag_service_instance.cache_manager.redis_client)
    #     logger.info("Rate limiter initialized with Redis.")
    #     # 初始化认证服务的Redis
    #     auth_service.set_redis(rag_service_instance.cache_manager.redis_client)
    #     logger.info("Auth service initialized with Redis for login tracking.")

    yield
    # 关闭
    logger.info("Closing database connections...")
    await close_db()
    logger.info("Database connections closed.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="The backend API for the CookAgent intelligent dietary assistant.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:8000",
        "http://localhost:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

EXEMPT_PATHS = {
    f"{settings.API_V1_STR}/auth/login",
    f"{settings.API_V1_STR}/auth/register",
}

@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """添加安全头到所有响应"""
    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'"
    )
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

    # 添加速率限制头
    if hasattr(request.state, "rate_limit_remaining"):
        response.headers["X-RateLimit-Remaining"] = str(
            request.state.rate_limit_remaining
        )
        response.headers["X-RateLimit-Limit"] = str(request.state.rate_limit_limit)

    return response


# @app.middleware("http")
# async def rate_limit_middleware(request: Request, call_next):
#     """限流中间件"""
#     rate_limit_response = await rate_limiter.check_rate_limit(request)
#     if rate_limit_response:
#         audit_logger.rate_limit_exceeded(
#             request=request,
#             user_id=getattr(request.state, "user_id", None),
#             endpoint=str(request.url.path),
#         )
#         return rate_limit_response

#     return await call_next(request)

@app.middleware("http")
async def auth_gateway(request: Request, call_next):
    """简易网关: 验证 JWT 令牌，除了登录和注册接口"""
    path = request.url.path
    if (
        path in EXEMPT_PATHS
        or path == "/"
        or path.startswith("/docs")
        or path.startswith("/redoc")
        or path.startswith("/openapi")
        or path.startswith("/static")
    ):
        return await call_next(request)

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return JSONResponse(status_code=401, content={"detail": "需要登录"})

    token = auth_header.split(" ", 1)[1].strip()
    identity = auth_service.decode_token(token)
    if not identity or not identity.get("username"):
        return JSONResponse(
            status_code=401, content={"detail": "登录已失效，请重新登录"}
        )

    request.state.username = identity.get("username")
    request.state.user_id = identity.get("user_id")

    return await call_next(request)


# 添加路由
app.include_router(
    conversation.router, prefix=settings.API_V1_STR, tags=["Conversation"]
)
app.include_router(auth.router, prefix=settings.API_V1_STR, tags=["Auth"])
app.include_router(user.router, prefix=settings.API_V1_STR, tags=["User"])
app.include_router(
    personal_docs.router, prefix=settings.API_V1_STR, tags=["KnowledgeBase"]
)
app.include_router(evaluation.router, prefix=settings.API_V1_STR, tags=["Evaluation"])
app.include_router(
    llm_stats.router, prefix=settings.API_V1_STR, tags=["LLM Statistics"]
)
app.include_router(agent.router, prefix=settings.API_V1_STR, tags=["Agent"])
app.include_router(diet.router, prefix=settings.API_V1_STR, tags=["Diet"])

@app.get("/")
async def root():
    """根路径接口，用于检查 API 服务运行状态"""
    return {"message": "Welcome to CookAgent API!"}
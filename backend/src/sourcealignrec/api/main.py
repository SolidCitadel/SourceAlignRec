from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sourcealignrec.api.mcp_server import mcp
from sourcealignrec.api.routers import (
    admin,
    auth,
    courses,
    history,
    offerings,
    professors,
    recommend,
    reviews,
    search,
    timetables,
    wishlist,
)
from sourcealignrec.core.config import settings
from sourcealignrec.db.session import init_db

# MCP를 FastAPI와 같은 프로세스로 mount (deployment-design §3.1 #1·#3).
# streamable HTTP(/mcp) + 레거시 SSE(/mcp/sse) 둘 다 노출 — ChatKHU가 transport 협상.
# 각 http_app은 자체 lifespan(session manager)이 있어 FastAPI lifespan에서 함께 기동해야 한다.
_mcp_http = mcp.http_app(path="/", transport="http")
_mcp_sse = mcp.http_app(path="/", transport="sse")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with _mcp_http.lifespan(app), _mcp_sse.lifespan(app):
        init_db()
        yield


app = FastAPI(title="SourceAlignRec", lifespan=lifespan)

# CORS — api-contract/_common.md §1. env로 origin 교체.
_origins = [o.strip() for o in settings.sar_cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(search.router)
app.include_router(offerings.router)
app.include_router(recommend.router)
app.include_router(wishlist.router)
app.include_router(timetables.router)
app.include_router(reviews.router)
app.include_router(professors.router)
app.include_router(courses.router)
app.include_router(history.router)
app.include_router(admin.router)

# MCP ASGI sub-app mount — streamable HTTP + 레거시 SSE.
app.mount("/mcp", _mcp_http)
app.mount("/mcp-sse", _mcp_sse)


@app.get("/version")
def version():
    """배포된 코드 커밋 추적 — 이미지 build-arg GIT_SHA."""
    import os
    return {"git_sha": os.getenv("GIT_SHA", "unknown")}

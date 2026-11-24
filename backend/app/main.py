import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pathlib import Path
from app.database import engine, Base
from app.routes import auth, tasks, payment, ws, admin
from app.config import CORS_ORIGINS, TRUSTED_HOST

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Auto CC - 云校园自动化", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if CORS_ORIGINS else ["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PUT"],
    allow_headers=["Content-Type", "Authorization"],
)

allowed_host = TRUSTED_HOST or "*"
if allowed_host != "*":
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[allowed_host])

app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(payment.router)
app.include_router(ws.router)
app.include_router(admin.router)

frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "2.0.0"}


@app.get("/api/config/public")
async def public_config():
    from app.services.payment import get_payment_config_from_db
    from app.config import CONTACT_EMAIL, PAYMENT_BASE_PRICE

    db_config = get_payment_config_from_db()
    try:
        base_price = float(db_config.get("base_price", PAYMENT_BASE_PRICE))
    except (TypeError, ValueError):
        base_price = PAYMENT_BASE_PRICE
    return {
        "contact_email": db_config.get("contact_email") or CONTACT_EMAIL,
        "base_price": base_price,
    }


if frontend_dist.exists() and frontend_dist.is_dir():
    app.mount(
        "/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets"
    )

    @app.get("/{full_path:path}", response_class=HTMLResponse)
    async def serve_frontend(full_path: str, request: Request):
        file_path = frontend_dist / full_path
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        index_path = frontend_dist / "index.html"
        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                return f.read()
        return HTMLResponse(
            "Frontend not built. Run: cd frontend && npm run build", status_code=503
        )

    @app.get("/")
    async def serve_root(request: Request):
        index_path = frontend_dist / "index.html"
        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                return HTMLResponse(f.read())
        return HTMLResponse(
            "Frontend not built. Run: cd frontend && npm run build", status_code=503
        )

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from auth.router import router as auth_router
from media.router import router as media_router
from perception.router import router as perception_router
from platform_app.router import router as platform_router
from prediction.router import router as prediction_router
from rag.router import router as assistant_router
from realtime.router import router as realtime_router
from routing.router import router as routing_router
from shared.config import MEDIA_PUBLIC_PREFIX, MEDIA_ROOT
from shared.storage import ensure_media_dirs
from system.router import router as system_router

ensure_media_dirs()

app = FastAPI(
    title="THNIYETNA API",
    version="2.0.0",
    description="Road perception, risk, routing and operational platform API",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(MEDIA_PUBLIC_PREFIX, StaticFiles(directory=str(MEDIA_ROOT)), name="media-files")
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(system_router)
app.include_router(perception_router, prefix="/perception", tags=["M1 Perception"])
app.include_router(prediction_router, prefix="/prediction", tags=["M2 Risk"])
app.include_router(routing_router, prefix="/routing", tags=["M3 Routing"])
app.include_router(platform_router, prefix="/platform", tags=["M4 Platform"])
app.include_router(realtime_router, prefix="/realtime", tags=["Realtime"])
app.include_router(media_router, prefix="/media", tags=["Media"])
app.include_router(assistant_router, prefix="/assistant", tags=["Assistant (RAG)"])


@app.get("/health")
def health():
    return {"status": "ok", "service": "api", "version": "2.0.0"}

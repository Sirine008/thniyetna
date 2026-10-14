import asyncio,json
from datetime import datetime,timezone
from fastapi import APIRouter,Depends,Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from shared.db import get_db,SessionLocal

router=APIRouter()

@router.get("/snapshot")
def snapshot(db:Session=Depends(get_db)):
    rows=db.execute(text("SELECT id::text,topic,recipient_ref,payload,status,created_at FROM notification_outbox ORDER BY created_at DESC LIMIT 100")).mappings().all()
    return {"generated_at":datetime.now(timezone.utc),"events":list(rows)}

@router.get("/stream")
async def stream(request:Request,since:str|None=None):
    async def gen():
        last=since
        cursor=datetime.now(timezone.utc)
        yield "event: connected\ndata: {\"status\":\"connected\"}\n\n"
        while not await request.is_disconnected():
            db=SessionLocal()
            try:
                if last:
                    rows=db.execute(text("SELECT id::text,topic,recipient_ref,payload,created_at FROM notification_outbox WHERE created_at>(SELECT created_at FROM notification_outbox WHERE id=:id) ORDER BY created_at LIMIT 100"),{"id":last}).mappings().all()
                else:
                    rows=db.execute(text("SELECT id::text,topic,recipient_ref,payload,created_at FROM notification_outbox WHERE created_at>:cursor ORDER BY created_at LIMIT 100"),{"cursor":cursor}).mappings().all()
                for r in rows:
                    last=r["id"]
                    cursor=r["created_at"]
                    data={**dict(r),"created_at":r["created_at"].isoformat()}
                    yield f"id: {r['id']}\nevent: {r['topic']}\ndata: {json.dumps(data,default=str)}\n\n"
            finally: db.close()
            yield ": keepalive\n\n"
            await asyncio.sleep(1)
    return StreamingResponse(gen(),media_type="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

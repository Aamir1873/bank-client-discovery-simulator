"""The web app: JSON routes under /api and the page from app/static.

    uvicorn app.main:app --reload
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import content, sessions
from .llm import AIError
from .sessions import ApiError

# Fail at startup, naming the broken file, rather than on the first request.
content.validate_all()

app = FastAPI(title="Bank Client Discovery Simulator", docs_url=None, redoc_url=None)
STATIC = Path(__file__).resolve().parent / "static"
EXPORT_ENDED = "/#export-ended"  # the feedback screen looks for this to explain a failed export


@app.exception_handler(ApiError)
async def _api_error(_: Request, e: ApiError):
    return JSONResponse({"error": e.message}, status_code=e.status)


@app.exception_handler(AIError)
async def _ai_error(_: Request, e: AIError):
    return JSONResponse({"error": "The model didn't answer. Check AI_BASE_URL and that the model is running, then try again."}, status_code=502)


@app.exception_handler(RequestValidationError)
async def _bad_request(_: Request, e: RequestValidationError):
    return JSONResponse({"error": "Part of the request is missing or the wrong kind. Reload the page and try again."}, status_code=400)


HTTP_MESSAGES = {
    404: "That address doesn't exist. Go back to the start page.",
    405: "That action isn't allowed here. Reload the page and try again.",
}


@app.exception_handler(StarletteHTTPException)
async def _http_error(_: Request, e: StarletteHTTPException):
    msg = HTTP_MESSAGES.get(e.status_code, "Something went wrong on the server. Reload the page and try again.")
    return JSONResponse({"error": msg}, status_code=e.status_code)


@app.exception_handler(content.ContentError)
async def _content_error(_: Request, e: content.ContentError):
    return JSONResponse({"error": f"A content file is broken: {e}"}, status_code=500)


class StartBody(BaseModel):
    client_id: str


class MessageBody(BaseModel):
    text: str


class Pick(BaseModel):
    product_id: str
    reason: str = ""


class FeedbackBody(BaseModel):
    summary: str = ""
    picks: list[Pick] = []


@app.get("/api/clients")
def clients():
    return sessions.list_clients()


@app.get("/api/clients/{client_id}")
def client(client_id: str):
    return sessions.get_client(client_id)


@app.get("/api/products")
def products():
    return sessions.get_products()


@app.post("/api/interviews")
def start(body: StartBody):
    return sessions.start(body.client_id)


@app.post("/api/interviews/{iid}/messages")
def message(iid: str, body: MessageBody):
    return sessions.send(iid, body.text)


@app.post("/api/interviews/{iid}/hint")
def hint(iid: str):
    return sessions.hint(iid)


@app.post("/api/interviews/{iid}/feedback")
def feedback(iid: str, body: FeedbackBody):
    return sessions.feedback(iid, body.summary, [p.model_dump() for p in body.picks])


@app.get("/api/interviews/{iid}/export")
def export(iid: str, request: Request):
    try:
        name, text = sessions.export(iid)
    except ApiError as e:
        # The page opens this as a plain link, so after a server restart a browser would show raw JSON.
        # Send it back to the page instead; the feedback screen is kept in the tab and says why.
        if e.status == 404 and "text/html" in request.headers.get("accept", ""):
            return RedirectResponse(EXPORT_ENDED, status_code=303)
        raise
    return Response(text, media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# The page. index.html asks for its files under /static/, so serve them there and the page itself at /.
if STATIC.exists():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")

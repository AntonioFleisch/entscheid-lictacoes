import uuid
import time
import json
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

# Setup basic logging config if not already suitable
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("api_logger")

class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Ensure request_id exists (requires RequestIdMiddleware before this, or generate here logic)
        # We rely on RequestIdMiddleware being added *before* or *outer*? 
        # FastAPI executes generic middlewares .. wait, order matters.
        # If RequestIdMiddleware runs first (outer), then request.state.request_id is available here.
        
        request_id = getattr(request.state, "request_id", "unknown")
        
        response = await call_next(request)
        
        process_time = (time.time() - start_time) * 1000
        
        log_entry = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(process_time, 2)
        }
        
        # Avoid logging Auth header?
        # Standard logging doesn't define it here, but if we extended to log headers we should sanitize.
        
        logger.info(json.dumps(log_entry))
        
        return response

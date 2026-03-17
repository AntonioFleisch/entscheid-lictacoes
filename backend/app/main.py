from fastapi import FastAPI, Request, HTTPException, Body, Depends, Header, Query, BackgroundTasks
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from typing import Any, List, Optional
import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv

# Internal imports
from app.db.models import WorkflowItemCreate, WorkflowItemUpdate, WorkflowItemResponse, IngestAction, WorkflowStatus, PNCPBatch, PaginatedResponse, PaginatedRuns
from app.utils import workflow_utils, idempotency_utils
from app.services.pncp import utils as pncp_utils
from app.core import middleware
from app.api import deps as auth_deps
from app.api.router import api_router

logger = logging.getLogger(__name__)
load_dotenv(override=True)

# Admin Configuration
# These are loaded at module level but will be checked dynamically in dependencies
# to support hot-loading if the process remains alive.
ENV = os.getenv("ENV", "production")
DEV_ALLOW_NO_KEYS = os.getenv("DEV_ALLOW_NO_KEYS", "0")

def get_admin_api_key():
    load_dotenv(override=True)
    return os.getenv("ADMIN_API_KEY")

N8N_SERVICE_EMAIL = "n8n@local"

# 0. App initialization & immediate CORS
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://0.0.0.0:3000"
]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

app.include_router(api_router, prefix='/api')

from fastapi import Response, Request

@app.options("/{full_path:path}")
async def preflight_handler(full_path: str, request: Request):
    return Response(status_code=204)

@app.get("/api/health")
def api_health_check():
    return {"ok": True}

# Middlewares
app.add_middleware(middleware.StructuredLoggingMiddleware)
app.add_middleware(middleware.SecurityHeadersMiddleware)
app.add_middleware(middleware.RequestIdMiddleware)

@app.on_event("startup")
async def startup_event():
    """Startup tasks."""
    # 0. Check API Key
    if ENV == "production" and not get_admin_api_key():
        raise RuntimeError("ADMIN_API_KEY not configured. Application cannot start.")

    # 1. Ensure service user + personal workspace in PostgreSQL
    from app.db.session import get_job_conn
    from app.core.security import hash_password
    import uuid
    from datetime import datetime
    
    with get_job_conn() as db:
        c = db.cursor()
        c.execute("SELECT id FROM users WHERE email = %s", (N8N_SERVICE_EMAIL,))
        existing = c.fetchone()
        if not existing:
            sys_user_id = str(uuid.uuid4())
            now_str = datetime.utcnow().isoformat()
            pwd_hash = hash_password("n8n_automated_user")
            
            c.execute("""
                INSERT INTO users (id, email, password_hash, is_active, is_email_verified, created_at, updated_at)
                VALUES (%s, %s, %s, TRUE, TRUE, %s, %s)
            """, (sys_user_id, N8N_SERVICE_EMAIL, pwd_hash, now_str, now_str))
            
            # Create personal workspace for service user
            ws_id = str(uuid.uuid4())
            c.execute("""
                INSERT INTO workspaces (id, type, name, slug, owner_user_id, created_at, updated_at)
                VALUES (%s, 'personal', 'Meu Espaço', %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (ws_id, f'personal-{sys_user_id}', sys_user_id, now_str, now_str))
            db.commit()
        else:
            # Ensure personal workspace exists for pre-existing service user
            sys_user_id = existing['id']
            c.execute("SELECT id FROM workspaces WHERE owner_user_id = %s AND type = 'personal'", (sys_user_id,))
            if not c.fetchone():
                ws_id = str(uuid.uuid4())
                now_str = datetime.utcnow().isoformat()
                c.execute("""
                    INSERT INTO workspaces (id, type, name, slug, owner_user_id, created_at, updated_at)
                    VALUES (%s, 'personal', 'Meu Espaço', %s, %s, %s, %s)
                """, (ws_id, f'personal-{sys_user_id}', sys_user_id, now_str, now_str))
                db.commit()
    
    print("INFO: Backend started. Workspace-based architecture active.")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# Dependencies
async def require_workflow_permission(user = Depends(auth_deps.get_current_user)):
    if not user.get("can_use_workflow", True):
         raise HTTPException(
            status_code=403,
            detail={"code": "NOT_AUTHORIZED", "message": "User does not have workflow permissions"}
        )
    return user

from fastapi.security import APIKeyHeader
from fastapi import Security

api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False, description="Admin API Key for protected routes")

async def verify_admin_api_key(
    x_api_key: Optional[str] = Security(api_key_scheme),
    x_api_key_old: Optional[str] = Header(None, alias="X-API-KEY")
):
    current_key = get_admin_api_key()
    key = x_api_key or x_api_key_old
    if x_api_key_old and not x_api_key:
        logger.warning("Deprecated header 'X-API-KEY' was used. Please update to 'X-API-Key'.")

    if not current_key:
        if ENV == "development" and DEV_ALLOW_NO_KEYS == "1":
            return {"email": N8N_SERVICE_EMAIL}
        raise HTTPException(
            status_code=500,
            detail={"code": "SERVER_MISCONFIG", "message": "Missing ADMIN_API_KEY configuration"}
        )
    
    if key != current_key:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_API_KEY", "message": "Invalid API Key"}
        )
    
    return {"email": N8N_SERVICE_EMAIL}


# Standardized Error Response Helper
def create_error_response(status_code: int, code: str, message: str):
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message
            }
        }
    )

# Exception Handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Constructing a readable error message from validation errors
    error_messages = "; ".join([f"{err['loc'][-1]}: {err['msg']}" for err in exc.errors()])
    return create_error_response(422, "VALIDATION_ERROR", f"Invalid input: {error_messages}")

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # Pass through code if provided in detail, else generic
    if isinstance(exc.detail, dict):
        code = exc.detail.get("code", "GENERIC_ERROR")
        message = exc.detail.get("message", "An unexpected error occurred.")
    elif exc.status_code == 500:
        code = "INTERNAL_SERVER_ERROR"
        message = "An unexpected error occurred."
    else:
        code = f"HTTP_{exc.status_code}"
        message = str(exc.detail)
        
    return create_error_response(exc.status_code, code, message)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return create_error_response(500, "INTERNAL_SERVER_ERROR", "An unexpected error occurred.")


# --- Admin Endpoints ---

@app.post("/api/admin/backfill-segment-unclassified")
async def admin_backfill_segment_unclassified(user = Depends(verify_admin_api_key)):
    """
    Backfill NULL or empty segments to 'unclassified'.
    """
    from app.services.pncp import utils as pncp_utils
    conn = pncp_utils.get_db_connection()
    c = conn.cursor()
    
    # Update 'contratacoes' table (Underlying table)
    c.execute("""
        UPDATE contratacoes 
        SET segmento_principal = 'unclassified' 
        WHERE segmento_principal IS NULL OR segmento_principal = ''
    """)
    rows_affected = c.rowcount
    
    conn.commit()
    conn.close()
    
    return {
        "status": "ok",
        "message": f"Successfully backfilled {rows_affected} items to 'unclassified'.",
        "count": rows_affected
    }

@app.get("/api/admin/debug-segments-audit")
async def admin_debug_segments_audit(user = Depends(verify_admin_api_key)): # Use API key for easier access
    """
    Audit segment consistency using the same universe logic.
    Returns total_default (classified), total_unclassified, total_all, and per-segment breakdown.
    """
    from app.services.pncp import utils as pncp_utils
    conn = pncp_utils.get_db_connection()
    c = conn.cursor()
    
    CLASSIFIED_SEGMENTS = ('diversos', 'kit_escolar', 'almoxarifado_virtual')
    
    # Exact same base WHERE as the real list endpoint (portability)
    where_clause = "WHERE is_valid IS TRUE AND (status IS NULL OR status != 'IGNORED')"
    
    # 1. Total All (every valid, non-ignored row)
    total_all = c.execute(f"SELECT COUNT(*) FROM licitacoes {where_clause}").fetchone()[0]
    
    # 2. By Segment
    c.execute(f"""
        SELECT COALESCE(segmento_principal, 'unclassified'), COUNT(*)
        FROM licitacoes 
        {where_clause}
        GROUP BY 1
    """)
    by_segment = {row[0]: row[1] for row in c.fetchall()}
    
    # 3. Derived totals
    total_unclassified = by_segment.get('unclassified', 0)
    by_segment_classificados = {k: v for k, v in by_segment.items() if k in CLASSIFIED_SEGMENTS}
    total_default = sum(by_segment_classificados.values())
    
    conn.close()
    
    return {
        "total_all": total_all,
        "total_default": total_default,
        "total_unclassified": total_unclassified,
        "by_segment": by_segment,
        "by_segment_classificados": by_segment_classificados,
        "diff": total_all - total_default - total_unclassified
    }

# ============================================================================
# BACKFILL ARQUIVOS
# ============================================================================

@app.post("/api/admin/backfill-arquivos")
async def admin_backfill_arquivos(
    limit: int = 50,
    pncp_id: Optional[str] = Query(None),
    dry_run: int = 0,
    per_record_timeout_seconds: float = 12.0,
    debug: int = 1,
    user = Depends(verify_admin_api_key)
):
    """
    Robust arquivos backfill with strict audit and locking.
    Metrics: eligible_total, selected, picked (lock acquired), skipped_locked.
    """
    import os
    import json
    import time
    from datetime import datetime
    from app.services.pncp.client import PNCPClient

    start_time_total = time.time()

    if debug:
        logger.info(f"backfill-arquivos start | dry_run={dry_run} | pncp_id={pncp_id} | limit={limit}")

    conn = pncp_utils.get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    try:
        # --- AUTO-RECOVER stuck FETCHING records with expired locks ---
        recovered = conn.execute("""
            UPDATE contratacoes
            SET arquivos_status = 'FAILED_TEMP',
                arquivos_last_error = 'AUTO_RECOVER_EXPIRED_LOCK',
                arquivos_next_retry_at = CURRENT_TIMESTAMP,
                arquivos_lock_owner = NULL,
                arquivos_lock_until = NULL
            WHERE arquivos_status = 'FETCHING'
              AND arquivos_lock_until IS NOT NULL
              AND arquivos_lock_until <= CURRENT_TIMESTAMP
        """).rowcount
        conn.commit()
        if recovered > 0 and debug:
            logger.info(f"Auto-recovered {recovered} stuck FETCHING arquivos records")

        # --- Eligible query ---
        where_parts = [
            "is_valid IS TRUE",
            "status = 'ACTIVE'",
            "COALESCE(arquivos_status, 'NOT_FETCHED') IN ('NOT_FETCHED', 'FAILED_TEMP')"
        ]
        params = []

        where_parts.append("(arquivos_next_retry_at IS NULL OR arquivos_next_retry_at <= CURRENT_TIMESTAMP)")
        where_parts.append("(arquivos_lock_until IS NULL OR arquivos_lock_until <= CURRENT_TIMESTAMP)")

        if pncp_id:
            where_parts = ["pncp_id = %s"]
            params = [pncp_id]

        where_clause = " AND ".join(where_parts)

        count_query = f"SELECT COUNT(*) FROM licitacoes WHERE {where_clause}"
        eligible_total = c.execute(count_query, params).fetchone()[0]

        if eligible_total == 0 and not pncp_id:
            if debug: logger.info("backfill-arquivos done | No eligible records")
            return {
                "eligible_total": 0,
                "selected": 0,
                "picked": 0,
                "reason": "No eligible records"
            }

        query = f"SELECT pncp_id, orgao_cnpj, ano, sequencial FROM licitacoes WHERE {where_clause} LIMIT %s"
        rows = c.execute(query, params + [limit]).fetchall()
        selected = len(rows)
        processed_sample_ids = [row['pncp_id'] for row in rows[:10]]

        if debug:
            logger.info(f"Eligible total: {eligible_total} | Selected {selected} records. Sample: {processed_sample_ids}")

        # DRY RUN FAST PATH
        if dry_run == 1:
            return {
                "dry_run": True,
                "eligible_total": eligible_total,
                "selected": selected,
                "sample_pncp_ids": processed_sample_ids,
                "auto_recovered": recovered
            }

        if not rows:
            return {
                "eligible_total": eligible_total,
                "selected": 0,
                "picked": 0,
                "reason": "No eligible records after selection"
            }

        stats = {
            "eligible_total": eligible_total,
            "selected": selected,
            "picked": 0,
            "completed": 0,
            "failed_temp": 0,
            "failed_auth": 0,
            "not_available": 0,
            "skipped_locked": 0,
            "failed": 0,
            "auto_recovered": recovered,
            "processed_sample": processed_sample_ids,
            "duration_ms": 0
        }

        worker_id = f"backfill-arq-{os.getpid()}"
        client = PNCPClient()

        for row in rows:
            record_start_time = time.time()
            pid = row['pncp_id']
            cnpj = row['orgao_cnpj']
            ano = row['ano']
            seq = row['sequencial']
            seq_int = str(int(seq))  # Strip leading zeros

            # Lock
            res = conn.execute("""
                UPDATE contratacoes
                SET arquivos_status = 'FETCHING',
                    arquivos_lock_owner = %s,
                    arquivos_lock_until = CURRENT_TIMESTAMP + interval '5 minutes',
                    arquivos_attempts = COALESCE(arquivos_attempts, 0) + 1,
                    arquivos_last_fetch_at = CURRENT_TIMESTAMP,
                    arquivos_updated_at = CURRENT_TIMESTAMP
                WHERE pncp_id = %s
                  AND (COALESCE(arquivos_status, 'NOT_FETCHED') IN ('NOT_FETCHED', 'FAILED_TEMP') 
                       OR (arquivos_status = 'FETCHING' AND arquivos_lock_until <= CURRENT_TIMESTAMP))
                  AND (arquivos_lock_until IS NULL OR arquivos_lock_until <= CURRENT_TIMESTAMP)
            """, (worker_id, pid))
            conn.commit()

            if res.rowcount != 1:
                stats["skipped_locked"] += 1
                if debug: logger.info(f"Arquivos lock skipped for {pid}")
                continue

            stats["picked"] += 1
            if debug: logger.info(f"Arquivos lock acquired for {pid}")

            try:
                fetch_url = f"https://pncp.gov.br/pncp-api/v1/orgaos/{cnpj}/compras/{ano}/{seq_int}/arquivos"
                if debug: logger.info(f"Fetch start: {fetch_url}")

                res_fetch = client.fetch_compra_arquivos(cnpj, ano, seq_int)

                duration_fetch = int((time.time() - record_start_time) * 1000)
                status_code = res_fetch.get("status_code", 0)
                error_msg = res_fetch.get("error")

                # Timeout guard
                elapsed_sec = time.time() - record_start_time
                if elapsed_sec > per_record_timeout_seconds:
                    logger.warning(f"Timeout guard triggered for {pid} ({elapsed_sec:.1f}s)")
                    error_msg = "PER_RECORD_TIMEOUT"
                    status_code = 408
                    res_fetch["status"] = "FAILED_TEMP"

                if debug: logger.info(f"Fetch done for {pid} | Status: {status_code} | Duration: {duration_fetch}ms")

                c.execute("""
                    INSERT INTO pncp_request_log (pncp_id, endpoint, url, status_code, duration_ms, error, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """, (pid, "get_arquivos", fetch_url, status_code, duration_fetch, error_msg))
                conn.commit()

                final_status = res_fetch.get("status")

                if final_status == "COMPLETED":
                    raw_files = res_fetch.get("files", [])
                    if debug: logger.info(f"Persist arquivos start for {pid} | {len(raw_files)} files")

                    # Build preview (top 5)
                    preview = []
                    for f in raw_files[:5]:
                        preview.append({
                            "titulo": f.get("titulo"),
                            "tipo_documento_nome": f.get("tipoDocumentoNome") or f.get("tipo"),
                            "url": f.get("url") or f.get("uri")
                        })

                    with conn:
                        conn.execute("DELETE FROM licitacao_arquivos WHERE pncp_id = %s", (pid,))
                        if raw_files:
                            insert_data = []
                            for f in raw_files:
                                seq_val = f.get("sequencialDocumento")
                                if seq_val is None:
                                    seq_val = f.get("sequencial")
                                if seq_val is None:
                                    continue

                                tipo_doc_id = f.get("tipoDocumentoId")
                                if tipo_doc_id is not None:
                                    tipo_doc_id = int(tipo_doc_id)

                                insert_data.append((
                                    pid,
                                    int(seq_val),
                                    f.get("titulo"),
                                    tipo_doc_id,
                                    f.get("tipoDocumentoNome") or f.get("tipo"),
                                    f.get("url") or f.get("uri"),
                                    json.dumps(f),
                                    datetime.now().isoformat(),
                                    datetime.now().isoformat()
                                ))
                            conn.executemany("""
                                INSERT INTO licitacao_arquivos 
                                (pncp_id, doc_seq, titulo, tipo_documento_id, tipo_documento_nome, url, raw_json, created_at, updated_at)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """, insert_data)

                        conn.execute("""
                            UPDATE contratacoes
                            SET arquivos_count = %s,
                                arquivos_preview_json = %s,
                                arquivos_status = 'COMPLETED',
                                arquivos_updated_at = CURRENT_TIMESTAMP,
                                arquivos_lock_owner = NULL,
                                arquivos_lock_until = NULL,
                                arquivos_last_error = NULL,
                                arquivos_next_retry_at = NULL
                            WHERE pncp_id = %s
                        """, (len(raw_files), json.dumps(preview), pid))

                    if debug: logger.info(f"Persist done for {pid} | Inserts: {len(raw_files)}")
                    stats["completed"] += 1

                elif final_status == "FAILED_AUTH":
                    conn.execute("UPDATE contratacoes SET arquivos_status = 'FAILED_AUTH', arquivos_lock_owner=NULL, arquivos_lock_until=NULL WHERE pncp_id = %s", (pid,))
                    conn.commit()
                    stats["failed_auth"] += 1
                elif final_status == "NOT_AVAILABLE":
                    conn.execute("UPDATE contratacoes SET arquivos_status = 'NOT_AVAILABLE', arquivos_lock_owner=NULL, arquivos_lock_until=NULL WHERE pncp_id = %s", (pid,))
                    conn.commit()
                    stats["not_available"] += 1
                else:
                    conn.execute("""
                        UPDATE contratacoes
                        SET arquivos_status = 'FAILED_TEMP',
                            arquivos_next_retry_at = CURRENT_TIMESTAMP + interval '15 minutes',
                            arquivos_lock_owner = NULL,
                            arquivos_lock_until = NULL,
                            arquivos_last_error = %s
                        WHERE pncp_id = %s
                    """, (error_msg or f"Status {status_code}", pid))
                    conn.commit()
                    stats["failed_temp"] += 1

                if debug: logger.info(f"Record completed: {pid} -> {final_status}")

            except Exception as e:
                logger.error(f"Error processing {pid} in arquivos backfill: {e}")
                conn.execute("UPDATE contratacoes SET arquivos_status = 'FAILED', arquivos_last_error = %s, arquivos_lock_owner=NULL, arquivos_lock_until=NULL WHERE pncp_id = %s", (str(e), pid))
                conn.commit()
                stats["failed"] += 1

            # Politeness delay
            if limit > 1:
                time.sleep(1.0)

        stats["skipped_locked"] = selected - stats["picked"]
        stats["duration_ms"] = int((time.time() - start_time_total) * 1000)
        if debug: logger.info(f"backfill-arquivos done | selected={selected} picked={stats['picked']} completed={stats['completed']} | Duration: {stats['duration_ms']}ms")

        return stats

    except Exception as e:
        logger.error(f"Critical Backfill arquivos failure: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e), "status": "job_failed"}
    finally:
        conn.close()


@app.post("/api/admin/backfill-itens")
async def admin_backfill_itens(
    limit: int = 1,
    max_records: int = 1,
    pncp_id: Optional[str] = Query(None),
    dry_run: int = 0,
    per_record_timeout_seconds: float = 12.0,
    max_pages: int = 20,
    debug: int = 1,
    user = Depends(verify_admin_api_key)
):
    """
    Robust items backfill with strict audit and locking.
    Metrics: eligible_total, selected, picked (lock acquired), skipped_locked.
    When pncp_id is given: returns pre-lock state and lock failure reason.
    Auto-recovers FETCHING records with expired locks.
    """
    from app.services.enrichment import utils as enrichment_utils
    actual_limit = max_records if max_records != 1 else limit
    return enrichment_utils.run_itens_backfill(
        limit=actual_limit,
        max_records=actual_limit,
        pncp_id=pncp_id,
        dry_run=dry_run,
        per_record_timeout_seconds=per_record_timeout_seconds,
        max_pages=max_pages,
        debug=debug
    )

@app.get("/api/admin/enrichment-backlog")
async def admin_enrichment_backlog(user=Depends(verify_admin_api_key)):
    conn = pncp_utils.get_db_connection()
    c = conn.cursor()
    
    try:
        where_clause = "is_valid IS TRUE AND (status IS NULL OR status != 'IGNORED')"
        
        # Total
        eligible = c.execute(f"SELECT COUNT(*) FROM licitacoes WHERE {where_clause}").fetchone()[0]
        
        # Items metrics
        c.execute(f"""
            SELECT COALESCE(itens_status, 'NOT_FETCHED'), COUNT(*)
            FROM licitacoes
            WHERE {where_clause}
            GROUP BY 1
        """)
        itens_metrics = {k: v for k, v in c.fetchall()}
        
        # Add basic zeros if not present
        for status in ['NOT_FETCHED', 'FAILED_TEMP', 'COMPLETED', 'NOT_AVAILABLE', 'FAILED_AUTH', 'FAILED']:
             itens_metrics.setdefault(status, 0)

        # Arquivos metrics
        c.execute(f"""
            SELECT COALESCE(arquivos_status, 'NOT_FETCHED'), COUNT(*)
            FROM licitacoes
            WHERE {where_clause}
            GROUP BY 1
        """)
        arquivos_metrics = {k: v for k, v in c.fetchall()}
        for status in ['NOT_FETCHED', 'FAILED_TEMP', 'COMPLETED', 'NOT_AVAILABLE', 'FAILED_AUTH', 'FAILED']:
             arquivos_metrics.setdefault(status, 0)
        
        # Oldest pending
        oldest = c.execute(f"""
            SELECT MIN(data_publicacao)
            FROM licitacoes
            WHERE {where_clause}
              AND (COALESCE(itens_status, 'NOT_FETCHED') IN ('NOT_FETCHED', 'FAILED_TEMP')
                   OR COALESCE(arquivos_status, 'NOT_FETCHED') IN ('NOT_FETCHED', 'FAILED_TEMP'))
        """).fetchone()[0]
        
        # Sample pending
        sample_rows = c.execute(f"""
            SELECT pncp_id
            FROM licitacoes
            WHERE {where_clause}
              AND (COALESCE(itens_status, 'NOT_FETCHED') IN ('NOT_FETCHED', 'FAILED_TEMP')
                   OR COALESCE(arquivos_status, 'NOT_FETCHED') IN ('NOT_FETCHED', 'FAILED_TEMP'))
            LIMIT 10
        """).fetchall()
        sample_pending = [r['pncp_id'] for r in sample_rows]
        
        return {
            "total_contratacoes_eligible": eligible,
            "itens": itens_metrics,
            "arquivos": arquivos_metrics,
            "oldest_pending_first_seen_at": oldest,
            "sample_pending_pncp_ids": sample_pending
        }
    finally:
        conn.close()


# --- Force Unlock & Debug Endpoints ---

@app.post("/api/admin/itens/force-unlock")
async def admin_force_unlock_itens(
    pncp_id: str = Query(...),
    user = Depends(verify_admin_api_key)
):
    """Force-unlock a stuck record's itens enrichment lock."""
    import sqlite3
    conn = pncp_utils.get_db_connection()
    conn.row_factory = sqlite3.Row
    try:
        # Read current state
        row = conn.execute("""
            SELECT pncp_id, itens_status, itens_lock_until, itens_lock_owner, itens_attempts, itens_last_error
            FROM contratacoes WHERE pncp_id = %s
        """, (pncp_id,)).fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"pncp_id '{pncp_id}' not found"})
        
        before = dict(row)
        
        # Apply unlock
        if row["itens_status"] == "FETCHING":
            conn.execute("""
                UPDATE contratacoes
                SET itens_status = 'FAILED_TEMP',
                    itens_lock_owner = NULL,
                    itens_lock_until = NULL,
                    itens_last_error = 'FORCE_UNLOCK',
                    itens_next_retry_at = CURRENT_TIMESTAMP
                WHERE pncp_id = %s
            """, (pncp_id,))
        else:
            conn.execute("""
                UPDATE contratacoes
                SET itens_lock_owner = NULL,
                    itens_lock_until = NULL
                WHERE pncp_id = %s
            """, (pncp_id,))
        conn.commit()
        
        # Read after state
        row_after = conn.execute("""
            SELECT pncp_id, itens_status, itens_lock_until, itens_lock_owner, itens_attempts, itens_last_error
            FROM contratacoes WHERE pncp_id = %s
        """, (pncp_id,)).fetchone()
        
        return {
            "action": "force_unlock",
            "pncp_id": pncp_id,
            "before": before,
            "after": dict(row_after)
        }
    finally:
        conn.close()

@app.get("/api/admin/itens/debug")
async def admin_itens_debug(
    pncp_id: str = Query(...),
    user = Depends(verify_admin_api_key)
):
    """Debug endpoint: returns control fields and recent request logs for a pncp_id."""
    import sqlite3
    conn = pncp_utils.get_db_connection()
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("""
            SELECT pncp_id, itens_status, itens_count, itens_lock_until, itens_lock_owner,
                   itens_attempts, itens_last_error, itens_next_retry_at, itens_last_fetch_at,
                   itens_updated_at, itens_preview_json
            FROM contratacoes WHERE pncp_id = %s
        """, (pncp_id,)).fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"pncp_id '{pncp_id}' not found"})
        
        # Last 5 request logs
        logs = conn.execute("""
            SELECT pncp_id, endpoint, url, status_code, duration_ms, error, created_at
            FROM pncp_request_log
            WHERE pncp_id = %s
            ORDER BY created_at DESC
            LIMIT 5
        """, (pncp_id,)).fetchall()
        
        return {
            "record": dict(row),
            "recent_logs": [dict(l) for l in logs]
        }
    finally:
        conn.close()

@app.get("/api/admin/debug/itens-state")
async def admin_debug_itens_state(
    pncp_id: str = Query(...),
    user = Depends(verify_admin_api_key)
):
    """Dual state debug: returns state from contratacoes and licitacoes view."""
    import sqlite3
    conn = pncp_utils.get_db_connection()
    conn.row_factory = sqlite3.Row
    try:
        # 1. Select from contratacoes
        res_contratacoes = conn.execute("""
            SELECT itens_status, itens_count, itens_updated_at, itens_preview_json
            FROM contratacoes WHERE pncp_id = %s
        """, (pncp_id,)).fetchone()
        
        # 2. Select from licitacoes view
        res_licitacoes = conn.execute("""
            SELECT itens_status, itens_count, itens_updated_at, itens_preview_json
            FROM licitacoes WHERE pncp_id = %s
        """, (pncp_id,)).fetchone()
        
        return {
            "pncp_id": pncp_id,
            "contratacoes": dict(res_contratacoes) if res_contratacoes else None,
            "licitacoes_view": dict(res_licitacoes) if res_licitacoes else None
        }
    finally:
        conn.close()

@app.post("/api/admin/reset-itens")
async def admin_reset_itens(pncp_id: str, force: bool = False, user = Depends(verify_admin_api_key)):
    """Reset items enrichment status for a record."""
    from app.services.pncp import utils as pncp_utils
    conn = pncp_utils.get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT itens_status FROM contratacoes WHERE pncp_id=%s", (pncp_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Licitação not found")
        
    if row[0] == 'COMPLETED' and not force:
         conn.close()
         raise HTTPException(status_code=400, detail="Status is already COMPLETED. Use force=true to reset.")
         
    c.execute("""
        UPDATE contratacoes 
        SET itens_status='NOT_FETCHED', 
            itens_attempts=0, 
            itens_next_retry_at=NULL,
            itens_last_error=NULL,
            itens_lock_owner=NULL,
            itens_lock_until=NULL
        WHERE pncp_id=%s
    """, (pncp_id,))
    conn.commit()
    conn.close()
    return {"status": "ok", "pncp_id": pncp_id, "message": "Itens status reset to NOT_FETCHED"}

@app.post("/api/admin/reset-arquivos")
async def admin_reset_arquivos(pncp_id: str, force: bool = False, user = Depends(verify_admin_api_key)):
    """Reset arquivos enrichment status for a record."""
    conn = pncp_utils.get_db_connection()
    c = conn.cursor()

    c.execute("SELECT arquivos_status FROM contratacoes WHERE pncp_id=%s", (pncp_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Licitação not found")

    if row[0] == 'COMPLETED' and not force:
         conn.close()
         raise HTTPException(status_code=400, detail="Status is already COMPLETED. Use force=true to reset.")

    c.execute("""
        UPDATE contratacoes
        SET arquivos_status='NOT_FETCHED',
            arquivos_attempts=0,
            arquivos_next_retry_at=NULL,
            arquivos_last_error=NULL,
            arquivos_lock_owner=NULL,
            arquivos_lock_until=NULL
        WHERE pncp_id=%s
    """, (pncp_id,))
    conn.commit()
    conn.close()
    return {"status": "ok", "pncp_id": pncp_id, "message": "Arquivos status reset to NOT_FETCHED"}


@app.get("/api/licitacoes/modalidades")
async def get_modalidades(ws_context: dict = Depends(auth_deps.get_current_workspace)):
    from app.services.pncp import utils as pncp_utils
    return pncp_utils.get_modalidades_info(workspace_id=ws_context["workspace_id"])

@app.get("/api/licitacoes/sidebar-counts")
async def get_sidebar_counts(
    q: Optional[str] = None,
    valor_min: Optional[float] = None,
    valor_max: Optional[float] = None,
    pub_from: Optional[str] = None,
    pub_to: Optional[str] = None,
    prazo_from: Optional[str] = None,
    prazo_to: Optional[str] = None,
    expira_em_dias: Optional[int] = None,
    capag: Optional[str] = None,
    uf: Optional[str] = None,
    modalidades: Optional[str] = None,
    segmento: Optional[str] = None,
    status: Optional[str] = None
, ws_context: dict = Depends(auth_deps.get_current_workspace)):
    """
    Returns counts for sidebar segments + ignored items.
    Respects common filters (q, valor, dates, capag, uf, modalidades).
    """
    from app.services.pncp import utils as pncp_utils
    mods_list = [m.strip() for m in modalidades.split(",")] if modalidades else None
    seg_list = [s.strip() for s in segmento.split(",")] if segmento else None
    
    ws_id = ws_context["workspace_id"]
    
    return pncp_utils.get_sidebar_counts(
        q=q, valor_min=valor_min, valor_max=valor_max,
        pub_from=pub_from, pub_to=pub_to,
        prazo_from=prazo_from, prazo_to=prazo_to,
        expira_em_dias=expira_em_dias,
        capag=capag,
        uf=uf,
        modalidades=mods_list,
        segmento=seg_list,
        status=status,
        workspace_id=ws_id
    )

@app.get("/api/licitacoes")
async def list_licitacoes(
    q: Optional[str] = None,
    # Filters
    valor_min: Optional[float] = None,
    valor_max: Optional[float] = None,
    pub_from: Optional[str] = None,
    pub_to: Optional[str] = None,
    prazo_from: Optional[str] = None,
    prazo_to: Optional[str] = None,
    expira_em_dias: Optional[int] = None,
    capag: Optional[str] = None,
    segmento: Optional[str] = None,
    modalidades: Optional[str] = None,
    uf: Optional[str] = None,
    status: Optional[str] = None, # 'ignored' or None
    pncp_id: Optional[str] = None,
    # Pagination & Sort
    page: int = 1,
    page_size: int = 20,
    order_by: str = "default"
, ws_context: dict = Depends(auth_deps.get_current_workspace)):
    """
    List licitacoes with server-side filtering and pagination.
    Default scope gate: when segmento is not provided, only classified items are shown.
    """
    from app.services.pncp import utils as pncp_utils
    import logging
    _logger = logging.getLogger("api_logger")

    # Validate page_size
    if page_size > 100: page_size = 100
    if page_size < 1: page_size = 20
    
    ws_id = ws_context["workspace_id"]
    
    # Diagnostic log (temporary)
    _logger.info(f"[LIST_LICITACOES] ws_id={ws_id}, segmento={segmento!r} (type={type(segmento).__name__}), status={status!r}, q={q!r}, uf={uf!r}, page={page}")
    
    seg_list = [s.strip() for s in segmento.split(",")] if segmento else None
    mods_list = [m.strip() for m in modalidades.split(",")] if modalidades else None
    
    items, total, meta = pncp_utils.search_licitacoes_advanced(
        q=q,
        valor_min=valor_min, valor_max=valor_max,
        pub_from=pub_from, pub_to=pub_to,
        prazo_from=prazo_from, prazo_to=prazo_to,
        expira_em_dias=expira_em_dias,
        capag=capag,
        segmento=seg_list,
        modalidades=mods_list,
        uf=uf,
        status=status,
        pncp_id=pncp_id,
        page=page,
        page_size=page_size,
        order_by=order_by,
        workspace_id=ws_id
    )
    
    # Diagnostic log (temporary)
    _logger.info(f"[LIST_LICITACOES] total={total}, items_returned={len(items)}")
    
    response = {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
        "order_by": order_by,
        "results": items
    }
    
    if meta:
        response["meta"] = meta
        
    return response

@app.get("/api/licitacoes/{pncp_id:path}/arquivos")
async def get_licitacao_arquivos(pncp_id: str, user = Depends(auth_deps.get_current_user)):
    """Returns list of archivos/attachments for a bidding."""
    try:
        conn = pncp_utils.get_db_connection()
        c = conn.cursor()
        
        # Check if bidding exists
        c.execute("SELECT pncp_id, arquivos_status FROM contratacoes WHERE pncp_id = %s", (pncp_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Licitação not found")
        
        status = row['arquivos_status']
        
        # Only return full list if status is COMPLETED
        if status != 'COMPLETED':
            conn.close()
            return {"pncp_id": pncp_id, "status": status, "files": []}
            
        c.execute("""
            SELECT doc_seq, titulo, tipo_documento_id, tipo_documento_nome, url, created_at
            FROM licitacao_arquivos
            WHERE pncp_id = %s
            ORDER BY doc_seq ASC
        """, (pncp_id,))
        rows = c.fetchall()

        # Also get updated_at from contratacoes
        meta = c.execute("SELECT arquivos_updated_at FROM contratacoes WHERE pncp_id = %s", (pncp_id,)).fetchone()

        files = []
        for r in rows:
            files.append({
                "doc_seq": r['doc_seq'],
                "titulo": r['titulo'],
                "tipo_documento_id": r['tipo_documento_id'],
                "tipo_documento_nome": r['tipo_documento_nome'],
                "url": r['url'],
                "created_at": r['created_at']
            })

        conn.close()
        return {
            "pncp_id": pncp_id,
            "status": status,
            "count": len(files),
            "arquivos": files,
            "updated_at": meta['arquivos_updated_at'] if meta else None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching arquivos for {pncp_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/licitacoes/{pncp_id:path}/itens")
async def get_licitacao_itens(pncp_id: str, user = Depends(auth_deps.get_current_user)):
    """
    Public Items Endpoint (Part F).
    Returns full items list only if COMPLETED.
    """
    from app.services.pncp import utils as pncp_utils
    conn = pncp_utils.get_db_connection()
    c = conn.cursor()
    
    # Requirement: Strict ownership check
    c.execute("SELECT itens_status, itens_count, itens_updated_at, itens_last_error FROM contratacoes WHERE pncp_id=%s", (pncp_id,))
    row = c.fetchone()
    
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Licitação not found")
        
    items_list = []
    if row['itens_status'] == 'COMPLETED':
        c.execute("SELECT * FROM licitacao_itens WHERE pncp_id=%s ORDER BY item_num ASC", (pncp_id,))
        items_list = [dict(r) for r in c.fetchall()]
        
    conn.close()
    
    return {
        "pncp_id": pncp_id,
        "status": row['itens_status'],
        "count": row['itens_count'],
        "items": items_list,
        "updated_at": row['itens_updated_at'],
        "error": row['itens_last_error']
    }


# Endpoints
@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/echo")
async def echo(payload: Any = Body(...)):
    return payload

# Auth Endpoints
@app.post("/workflow-items", response_model=WorkflowItemResponse)
async def create_workflow_item(
    request: Request,
    item: WorkflowItemCreate, 
    user = Depends(require_workflow_permission),
    idempotency_key: Optional[str] = Header(None)
):
    if idempotency_key:
        saved_response = idempotency_utils.get_saved_response(user["email"], request.method, request.url.path, idempotency_key)
        if saved_response:
             # Ideally check body hash, but user said optional. Just returning saved.
             return saved_response

    try:
        new_item = workflow_utils.create_item(user["email"], item.tender_id, item.status)
        
        if idempotency_key:
             idempotency_utils.save_response(user["email"], request.method, request.url.path, idempotency_key, new_item)
             
        return new_item
    except workflow_utils.WorkflowError as e:
        status_code = 400
        if e.code == "DUPLICATE_TENDER": status_code = 400
        raise HTTPException(status_code=status_code, detail={"code": e.code, "message": e.message})

@app.post("/ingest/workflow-items", response_model=WorkflowItemResponse)
async def ingest_workflow_item(
    request: Request,
    item: WorkflowItemCreate,
    # This dependency enforces API Key presence and validity.
    # The returned user object is just a placeholder, we use N8N_SERVICE_EMAIL.
    user = Depends(verify_admin_api_key),
    idempotency_key: Optional[str] = Header(None)
):
    target_email = N8N_SERVICE_EMAIL

    if idempotency_key:
        saved_response = idempotency_utils.get_saved_response(target_email, request.method, request.url.path, idempotency_key)
        if saved_response:
             return saved_response

    try:
        # Map Action -> Status
        initial_status = WorkflowStatus.watching
        if item.action == IngestAction.participate:
            initial_status = WorkflowStatus.participating
        elif item.action == IngestAction.discard:
            initial_status = WorkflowStatus.discarded
            
        new_item = workflow_utils.create_item(target_email, item.tender_id, initial_status)
        
        if idempotency_key:
             idempotency_utils.save_response(target_email, request.method, request.url.path, idempotency_key, new_item)
             
        return new_item
    except workflow_utils.WorkflowError as e:
        status_code = 400
        if e.code == "DUPLICATE_TENDER": status_code = 400
        raise HTTPException(status_code=status_code, detail={"code": e.code, "message": e.message})

@app.get("/ingest/workflow-items", response_model=List[WorkflowItemResponse])
async def list_ingest_workflow_items(user = Depends(verify_admin_api_key)):
    """List workflow items for the n8n service user (Debug)."""
    return workflow_utils.get_user_items(N8N_SERVICE_EMAIL)

@app.post("/ingest/pncp/batch")
async def ingest_pncp_batch(
    request: Request,
    batch: PNCPBatch,
    user = Depends(verify_admin_api_key)
):
    request_id = getattr(request.state, "request_id", "unknown")
    
    # Upsert items
    # batch.items is already a list of dicts due to models.py definition
    stats = pncp_utils.upsert_items(batch.items, source=batch.source)
    
    # Determine status
    status = "ok"
    if stats["failed"] > 0:
        if stats["failed"] == stats["received"]:
             status = "error"
        else:
             status = "partial"
             
    # Persist Run Log
    try:
        run_log = {
            "run_id": batch.run_id,
            "source": batch.source,
            "window": batch.window,
            "status": status,
            "counts": stats
        }
        # Add timestamp
        import datetime
        run_log["created_at"] = datetime.datetime.now().isoformat()
        
        # Store errors in run log if any
        if stats["errors"]:
            run_log["errors"] = stats["errors"]

        pncp_utils.save_run(run_log)
    except Exception as e:
        # Don't fail the request if run log fails, but log it
        import logging
        logger = logging.getLogger("api_logger")
        logger.error(f"Failed to save run log: {e}")

    # Log metrics
    log_payload = {
        "event": "pncp_batch_ingest",
        "request_id": request_id,
        "status": status,
        "stats": stats
    }
    import logging
    logger = logging.getLogger("api_logger")
    logger.info(json.dumps(log_payload))

    return {
        "status": status,
        "meta": {
            "run_id": batch.run_id,
            "source": batch.source,
            "window": batch.window
        },
        "counts": {
            "received": stats["received"],
            "inserted": stats["inserted"],
            "updated": stats["updated"],
            "skipped": stats["skipped"],
            "failed": stats["failed"]
        },
        "errors": stats["errors"],
        "debug_sample": stats.get("debug_sample", []),
        "_debug": stats.get("_debug", {})
    }

# --- Read APIs ---

@app.get("/pncp/search", response_model=PaginatedResponse)
async def search_pncp(
    q: Optional[str] = None,
    uf: Optional[str] = None,
    municipio: Optional[str] = None,
    modalidade_id: Optional[int] = None,
    situacao_id: Optional[int] = None,
    min_estimado: Optional[float] = None,
    max_estimado: Optional[float] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    srp: Optional[bool] = None,
    page: int = 1,
    page_size: int = 25,
    sort: Optional[str] = None,
    dir: str = "desc",
    segmento: Optional[str] = None,
    added_since: Optional[str] = None,
    deadline_in: Optional[str] = None
, user = Depends(auth_deps.get_current_user)):
    """Search for PNCP items."""
    return pncp_utils.search_items(
        q=q, uf=uf, municipio=municipio,
        modalidade_id=modalidade_id, situacao_id=situacao_id,
        min_estimado=min_estimado, max_estimado=max_estimado,
        date_from=date_from, date_to=date_to,
        srp=srp,
        page=page, page_size=page_size,
        sort_by=sort, sort_dir=dir,
        segmento=segmento,
        added_since=added_since,
        deadline_in=deadline_in
    )

@app.get("/api/stats")
async def get_stats(user = Depends(auth_deps.get_current_user)):
    """Get counts for sidebar filters."""
    return pncp_utils.get_sidebar_stats()

@app.post("/api/admin/enrich-capag")
async def enrich_capag(limit: int = 50, user = Depends(verify_admin_api_key)):
    """
    Enrich orgaos with CAPAG data. (Disabled / Obsolete)
    Still maps orgaos to contratacoes.
    """
    from app.services.pncp import utils as pncp_utils
    
    conn = pncp_utils.get_db_connection()
    c = conn.cursor()
    
    # 1. Insert/Ignore orgaos from contratacoes
    # We first ensure all orgaos from contratacoes exist in orgaos table
    c.execute("""
        INSERT INTO orgaos (cnpj, nome, municipio, uf)
        SELECT DISTINCT orgao_cnpj, orgao_nome, municipio, uf
        FROM contratacoes
        WHERE orgao_cnpj IS NOT NULL
        ON CONFLICT (cnpj) DO NOTHING
    """)
    conn.commit()
    
    # 2. Update contratacoes with orgao_id
    c.execute("""
        UPDATE contratacoes
        SET orgao_id = (SELECT id FROM orgaos WHERE orgaos.cnpj = contratacoes.orgao_cnpj)
        WHERE orgao_id IS NULL
    """)
            
    conn.commit()
    conn.close()
    
    return {"status": "ok", "stats": {"processed": 0, "updated": 0}}


@app.post("/api/licitacoes/{pncp_id:path}/ignore")
async def ignore_licitacao(pncp_id: str, ws_context = Depends(auth_deps.get_current_workspace)):
    """Set status to IGNORED."""
    try:
        pncp_utils.update_workflow_status(pncp_id, ws_context["workspace_id"], 'IGNORED')
        return {"status": "ok", "pncp_id": pncp_id, "workflow_status": "IGNORED"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/licitacoes/{pncp_id:path}/unignore")
async def unignore_licitacao(pncp_id: str, ws_context = Depends(auth_deps.get_current_workspace)):
    """Set status to ACTIVE."""
    try:
        pncp_utils.update_workflow_status(pncp_id, ws_context["workspace_id"], 'ACTIVE')
        return {"status": "ok", "pncp_id": pncp_id, "workflow_status": "ACTIVE"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/licitacoes/{id}/details")
async def get_licitacao_details(id: str, user = Depends(auth_deps.get_current_user)):
    """
    Get detailed information about a licitacao.
    Triggers enrichment if data is missing or stale.
    """
    # Trigger enrichment logic synchronously for MVP (or async task in production)
    # The utils logic will handle idempotency
    # For now we just return the full details from DB
    
    # Check if exists
    conn = pncp_utils.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM licitacoes WHERE canonical_id = %s", (id,))
    item = c.fetchone()
    
    if not item:
        conn.close()
        raise HTTPException(status_code=404, detail="Licitação not found")
        
    # Get Items
    c.execute("SELECT * FROM licitacao_itens WHERE licitacao_id = %s", (id,))
    lic_items = [dict(r) for r in c.fetchall()]
    
    # Get Docs
    c.execute("SELECT * FROM licitacao_documentos WHERE licitacao_id = %s", (id,))
    lic_docs = [dict(r) for r in c.fetchall()]
    
    conn.close()
    
    # Cast to dict
    item_dict = dict(item)
    item_dict["itens"] = lic_items
    item_dict["documentos"] = lic_docs
    
    return item_dict

# Backward compatibility / specific search (still used by frontend until refactor)
@app.get("/pncp/{id}")
async def get_pncp_item(id: str, user = Depends(auth_deps.get_current_user)):
    """
    Legacy: Get single PNCP item by idempotency_key.
    Forwarding to new detail endpoint logic if possible, or keeping old logic?
    The user wants to replace logic. Let's point this to the DB look up too if feasible.
    """
    # For now, keep as is for legacy `pncp.json` fallback, or redirect?
    # The old `pncp_utils.load_pncp_data` might be deprecated/removed. 
    # Let's simple return 404 if not found in NEW DB to encourage migration
    return await get_licitacao_details(id) 

@app.get("/ingest/runs", response_model=PaginatedRuns)
async def list_runs(page: int = 1, page_size: int = 25, user = Depends(auth_deps.get_current_user)):
    """List ingestion runs."""
    runs = pncp_utils.load_runs()
    total = len(runs)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "runs": runs[start:end]
    }

@app.get("/ingest/runs/{run_id}")
async def get_run_details(run_id: str, user = Depends(auth_deps.get_current_user)):
    """Get specific run details."""
    runs = pncp_utils.load_runs()
    for r in runs:
        if r["run_id"] == run_id:
            return r
    raise HTTPException(status_code=404, detail="Run not found")



@app.get("/workflow-items", response_model=List[WorkflowItemResponse])
async def list_workflow_items(user = Depends(auth_deps.get_current_user)):
    # Note: Requirement says "Somente usuários com permissão... podem criar ou alterar".
    # But usually viewing implies authentication. The spec says "Todas as rotas... exigem token".
    # It doesn't strictly say viewing requires permission flag, but let's assume standard Auth is enough for viewing own items unless specified.
    # Spec: "Somente usuários com permissão de workflow can_use_workflow == true podem criar ou alterar itens." -> Reads as Read is allowed for all authed users?
    # Or should we enforce it for ALL workflow routes? "Todas as rotas de workflow exigem usuário autenticado... Somente usuários com permissão ... podem criar ou alterar".
    # I will allow GET for all Authed users to be safe, but restrict POST/PATCH.
    return workflow_utils.get_user_items(user["email"])

@app.patch("/workflow-items/{item_id}", response_model=WorkflowItemResponse)
async def update_workflow_item(item_id: str, update: WorkflowItemUpdate, user = Depends(require_workflow_permission)):
    try:
        updated_item = workflow_utils.update_item_status(user["email"], item_id, update.status)
        return updated_item
    except workflow_utils.WorkflowError as e:
        status_code = 400
        if e.code == "NOT_FOUND": status_code = 404
        if e.code == "INVALID_TRANSITION": status_code = 400
        raise HTTPException(status_code=status_code, detail={"code": e.code, "message": e.message})

# --- Jobs ---
@app.post("/jobs/pncp/ingest")
async def job_pncp_ingest(
    request: Request,
    data_inicial: Optional[str] = None,
    data_final: Optional[str] = None,
    user = Depends(verify_admin_api_key)
):
    """
    Trigger 2-phase PNCP ingestion job.
    """
    from app.jobs.pncp_ingest import PNCPIngestJob
    from datetime import datetime
    
    # Default to today if not provided
    if not data_inicial:
        data_inicial = datetime.now().strftime('%Y%m%d')
    if not data_final:
        data_final = datetime.now().strftime('%Y%m%d')
        
    try:
        job = PNCPIngestJob()
        result = job.run_full_job(data_inicial, data_final)
        
        if result["status"] == "locked":
            raise HTTPException(status_code=409, detail="Job is already running")
            
        return {
            "status": "success",
            "phase_a": result.get("phase_a"),
            "phase_b": result.get("phase_b"),
            "phase_c": result.get("phase_c")
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/jobs/pncp/reclassify")
async def job_pncp_reclassify(
    force: bool = False,
    user = Depends(verify_admin_api_key)
):
    """
    Manually trigger re-classification of all biddings using v3 logic.
    """
    from app.services.segmentation.classifier import finalize_contract_segment
    from app.services.pncp import utils as pncp_utils
    from datetime import datetime
    
    conn = pncp_utils.get_db_connection()
    c = conn.cursor()
    
    # Get all candidate contracts
    c.execute("SELECT pncp_id, objeto FROM contratacoes")
    contracts = c.fetchall()
    
    stats = {"processed": 0, "updated": 0}
    
    for row in contracts:
        pncp_id = row[0]
        objeto = row[1] or ""
        
        # Get related item descriptions
        c.execute("SELECT descricao FROM contratacao_itens WHERE pncp_id = %s", (pncp_id,))
        item_rows = c.fetchall()
        item_texts = [str(r[0] or "") for r in item_rows]
        
        # v3 Classification
        seg_id, evidence_json = finalize_contract_segment(objeto, item_texts)
        
        # Update contract if changed or forced
        c.execute("""
            UPDATE contratacoes SET 
                segmento_principal = %s,
                segmentos_json = %s,
                segmento_updated_at = %s
            WHERE pncp_id = %s
        """, (seg_id, evidence_json, datetime.now().isoformat(), pncp_id))
        
        stats["processed"] += 1
        stats["updated"] += 1
        
    conn.commit()
    conn.close()
    
    return {
        "status": "success",
        "stats": stats
    }


# ============================================================================
# DB BACKFILL: Rebuild Item Derived Fields from raw_json
# ============================================================================

@app.post("/api/admin/rebuild-itens-derived")
async def rebuild_itens_derived(
    pncp_id: Optional[str] = None,
    user = Depends(verify_admin_api_key)
):
    """
    Recalculates valor_unit and valor_total from raw_json for items already in the DB.
    Also rebuilds the preview JSON in contratacoes.
    Fixes the 'zero value' bug where 0.0 was being saved as NULL.
    """
    logger.info(f"Starting rebuild of derived item fields. Filter pncp_id={pncp_id}")
    conn = pncp_utils.get_db_connection()
    c = conn.cursor()
    
    stats = {"processed": 0, "updated": 0, "errors": 0}
    
    # Identify which records to process
    if pncp_id:
        c.execute("SELECT DISTINCT pncp_id FROM licitacao_itens WHERE pncp_id = %s", (pncp_id,))
    else:
        c.execute("SELECT DISTINCT pncp_id FROM licitacao_itens")
        
    records = c.fetchall()
    
    for row in records:
        pid = row[0]
        stats["processed"] += 1
        
        try:
            # Rebuild all items for this licitacao
            c.execute("SELECT item_num, raw_json FROM licitacao_itens WHERE pncp_id = %s", (pid,))
            items_rows = c.fetchall()
            
            rebuilt_items = []
            preview_items = []
            
            for index, i_row in enumerate(items_rows):
                item_num = i_row[0]
                raw_json_str = i_row[1]
                
                if not raw_json_str:
                    continue
                    
                it = json.loads(raw_json_str)
                rebuilt_items.append((item_num, it))
                
                v_unit_raw = it.get("valorUnitarioEstimado") if it.get("valorUnitarioEstimado") is not None else it.get("valorUnitario")
                v_total_raw = it.get("valorTotal") if it.get("valorTotal") is not None else it.get("valorTotalEstimado")
                
                qtd = it.get("quantidade") if it.get("quantidade") is not None else 0
                v_unit = float(v_unit_raw) if v_unit_raw is not None else None
                
                if v_total_raw is not None:
                    v_total = float(v_total_raw)
                elif v_unit is not None:
                    v_total = float(qtd * v_unit)
                else:
                    v_total = None
                    
                # Update item record
                c.execute("""
                    UPDATE licitacao_itens 
                    SET valor_unit = %s, valor_total = %s 
                    WHERE pncp_id = %s AND item_num = %s
                """, (v_unit, v_total, pid, item_num))
                
                # Build preview (top 5)
                if index < 5:
                    preview_items.append({
                        "descricao": it.get("descricao"),
                        "quantidade": qtd,
                        "unidadeMedida": it.get("unidadeMedida") or it.get("unidade"),
                        "valor_total": v_total
                    })
                    
            # Update contratacoes table preview
            if preview_items:
                c.execute("""
                    UPDATE contratacoes 
                    SET itens_preview_json = %s, itens_updated_at = %s
                    WHERE pncp_id = %s
                """, (json.dumps(preview_items), datetime.now().isoformat(), pid))
                
            stats["updated"] += 1
            
        except Exception as e:
            logger.error(f"Error rebuilding items for {pid}: {e}")
            stats["errors"] += 1
            
    conn.commit()
    conn.close()
    
    return {
        "status": "success",
        "stats": stats
    }


# ============================================================================
# COUNTERS ENDPOINT
# ============================================================================

@app.get("/api/licitacoes/counters")
async def get_licitacoes_counters(ws_context: dict = Depends(auth_deps.get_current_workspace)):
    """
    Returns dashboard counters for quick filters.
    Uses single optimized SQL query.
    Returns generated_at and anti-cache headers.
    """
    import sqlite3
    from datetime import datetime
    
    ws_id = ws_context["workspace_id"]
    conn = pncp_utils.get_db_connection()
    c = conn.cursor()
    
    # Single query with subselects for efficiency
    sql = """
    SELECT
      (SELECT COUNT(*) FROM contratacoes
       WHERE (status IS NULL OR status != 'IGNORED')
         AND workspace_id = %s
         AND date(replace(first_seen_at,'T',' ')) = CURRENT_DATE
      ) AS added_today,

      (SELECT COUNT(*) FROM contratacoes
       WHERE (status IS NULL OR status != 'IGNORED')
         AND workspace_id = %s
         AND situacao_nome = 'Divulgada no PNCP'
         AND deadline_at IS NOT NULL AND deadline_at != ''
         AND deadline_at >= CURRENT_TIMESTAMP
         AND deadline_at < (CURRENT_TIMESTAMP + interval '7 days')
      ) AS due_soon,

      (SELECT COUNT(*) FROM contratacoes
       WHERE status = 'IGNORED' AND workspace_id = %s
      ) AS ignored
    """
    
    c.execute(sql, (ws_id, ws_id, ws_id))
    row = c.fetchone()
    conn.close()
    
    content = {
        "added_today": row['added_today'] or 0,
        "due_soon": row['due_soon'] or 0,
        "ignored": row['ignored'] or 0,
        "generated_at": datetime.now().isoformat()
    }

    return JSONResponse(content=content, headers={
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache"
    })


@app.get("/api/licitacoes/fill")
async def get_licitacoes_fill(
    limit: int = 1,
    exclude_ids: str = "", # CSV
    quick: Optional[str] = None,
    segmento: Optional[str] = None,
    uf: Optional[str] = None,
    sort: Optional[str] = None,
    q: Optional[str] = None
, ws_context: dict = Depends(auth_deps.get_current_workspace)):
    """
    Returns replacement items to keep pagination consistent.
    Honors active filters and excludes explicit IDs.
    """
    excluded = [x.strip() for x in exclude_ids.split(',') if x.strip()]
    ws_id = ws_context["workspace_id"]
    
    items, _, _, _ = pncp_utils.search_licitacoes_sql(
        q=q,
        uf=uf, 
        segmento=segmento, 
        quick=quick, 
        page=1, 
        per_page=limit,
        exclude_ids=excluded,
        workspace_id=ws_id
    )
    
    return {"items": items}

@app.get("/api/debug/db-duplicates")
def get_db_duplicates():
    """
    Diagnostic endpoint to find duplicate records in the database.
    """
    from app.services.pncp import utils as pncp_utils
    conn = pncp_utils.get_db_connection()
    c = conn.cursor()
    
    # 1. Duplicates by PNCP ID (Raw DB check)
    c.execute("""
        SELECT pncp_id, COUNT(*) c 
        FROM licitacoes 
        GROUP BY pncp_id 
        HAVING c > 1 
        ORDER BY c DESC 
        LIMIT 50
    """)
    dupes_pncp = [dict(row) for row in c.fetchall()]
    
    # 2. Duplicates by Canonical Key (CNPJ + Ano + Sequencial)
    c.execute("""
        SELECT orgao_cnpj, ano, CAST(sequencial AS INT) as seq_int, COUNT(*) c
        FROM licitacoes
        GROUP BY orgao_cnpj, ano, seq_int
        HAVING c > 1
        ORDER BY c DESC
        LIMIT 50
    """)
    dupes_canonical = [dict(row) for row in c.fetchall()]
    
    conn.close()
    
    return {
        "duplicates_by_pncp_id": dupes_pncp,
        "duplicates_by_canonical": dupes_canonical,
        "total_pncp_dupes": len(dupes_pncp),
        "total_canonical_dupes": len(dupes_canonical)
    }


# ============================================================================
# BACKFILL DEADLINES ENDPOINT
# ============================================================================

@app.post("/api/admin/backfill-deadlines")
async def backfill_deadlines(
    limit: int = 300,
    dry_run: bool = False
):
    """
    Administrative endpoint to backfill deadline_at for records missing it.
    Rate-limited and with retry logic for robustness.
    """
    import sqlite3
    import time
    import requests
    from datetime import datetime
    
    start_time = time.time()
    
    conn = sqlite3.connect('pncp.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Select records needing backfill
    sql = """
    SELECT pncp_id, orgao_cnpj, ano, sequencial
    FROM licitacoes
    WHERE (deadline_at IS NULL OR deadline_at = '')
      AND (status IS NULL OR status != 'IGNORED')
      AND situacao_nome = 'Divulgada no PNCP'
    LIMIT %s
    """
    
    rows = c.execute(sql, (limit,)).fetchall()
    
    stats = {
        "processed": 0,
        "updated": 0,
        "failed": 0,
        "skipped": 0,
        "fail_reasons": {
            "http_error": 0,
            "no_deadline_in_detail": 0,
            "parse_error": 0,
            "no_identifier": 0
        }
    }
    
    for row in rows:
        stats["processed"] += 1
        pncp_id = row["pncp_id"]
        cnpj = row["orgao_cnpj"]
        ano = row["ano"]
        seq = row["sequencial"]
        
        # Validate identifiers
        if not (cnpj and ano and seq):
            stats["failed"] += 1
            stats["fail_reasons"]["no_identifier"] += 1
            continue
        
        # Build detail URL
        seq_int = str(int(seq)) if seq else seq  # Remove leading zeros
        detail_url = f"https://pncp.gov.br/api/consulta/v1/orgaos/{cnpj}/compras/{ano}/{seq_int}"
        
        # Fetch with retry
        detail = None
        for attempt in range(2):
            try:
                r = requests.get(detail_url, timeout=15)
                if r.status_code == 200:
                    detail = r.json()
                    break
                elif r.status_code >= 500:
                    time.sleep(0.5)  # Wait before retry
                    continue
                else:
                    break  # 4xx - don't retry
            except Exception:
                if attempt == 0:
                    time.sleep(0.5)
                    continue
                break
        
        if not detail:
            stats["failed"] += 1
            stats["fail_reasons"]["http_error"] += 1
            time.sleep(0.15)
            continue
        
        # Extract deadline (priority order per user spec)
        deadline_raw = None
        deadline_at = None
        
        candidates = [
            detail.get('dataEncerramentoProposta'),
            detail.get('dataFimRecebimentoPropostas')
        ]
        
        for val in candidates:
            if val:
                deadline_raw = str(val)
                deadline_at = val
                break
        
        if not deadline_at:
            stats["skipped"] += 1
            stats["fail_reasons"]["no_deadline_in_detail"] += 1
            time.sleep(0.15)
            continue
        
        # Persist if not dry run
        if not dry_run:
            try:
                c.execute("""
                    UPDATE contratacoes SET
                        deadline_at = %s,
                        deadline_source = 'detail',
                        deadline_raw = %s,
                        last_seen_at = %s
                    WHERE pncp_id = %s
                """, (deadline_at, deadline_raw, datetime.now().isoformat(), pncp_id))
                conn.commit()
                stats["updated"] += 1
            except Exception:
                stats["failed"] += 1
                stats["fail_reasons"]["parse_error"] += 1
        else:
            stats["updated"] += 1  # Would have updated
        
        # Rate limit
        time.sleep(0.15)
    
    conn.close()
    
    elapsed = time.time() - start_time
    
    return {
        "processed": stats["processed"],
        "updated": stats["updated"],
        "failed": stats["failed"],
        "skipped": stats["skipped"],
        "fail_reasons": stats["fail_reasons"],
        "elapsed_seconds": round(elapsed, 2),
        "dry_run": dry_run
    }

@app.post("/api/admin/backfill-valores")
async def backfill_valores(limit: int = 500, dry_run: bool = False):
    """
    Scans for corrupted or missing values and repairs them from payloads.
    Corrupted values are typically date strings containing 'T'.
    """
    import sqlite3
    import time
    from app.services.pncp.utils import normalize_valor_estimado_centavos
    
    start_time = time.time()
    conn = sqlite3.connect('pncp.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # 1. Identify candidates:
    # - Contains 'T' (date corruption)
    # - Is NULL or 0 (might be missing but present in payload)
    # - Or we can just scan everything limited by time/count
    sql = """
    SELECT pncp_id, valor_estimado_centavos, payload_publicacao_json, payload_detalhe_json
    FROM contratacoes
    WHERE (valor_estimado_centavos IS NULL OR valor_estimado_centavos = 0 OR valor_estimado_centavos LIKE '%T%' OR typeof(valor_estimado_centavos) = 'text')
    LIMIT %s
    """
    rows = c.execute(sql, (limit,)).fetchall()
    
    stats = {"processed": 0, "fixed": 0, "skipped": 0, "errors": 0}
    fixed_ids = []

    for row in rows:
        stats["processed"] += 1
        pncp_id = row["pncp_id"]
        
        try:
            pub_payload = json.loads(row["payload_publicacao_json"]) if row["payload_publicacao_json"] else None
            det_payload = json.loads(row["payload_detalhe_json"]) if row["payload_detalhe_json"] else None
            
            new_val = normalize_valor_estimado_centavos(pub_payload, det_payload)
            
            # Check if it actually changed
            old_val = row["valor_estimado_centavos"]
            
            # Note: We comparison here might be tricky if old_val is a string '2026...' and new_val is an int
            orig_is_bad = False
            if old_val is None: orig_is_bad = True
            elif isinstance(old_val, str) and 'T' in old_val: orig_is_bad = True
            elif old_val == 0 and new_val and new_val > 0: orig_is_bad = True
            
            if new_val is not None and orig_is_bad:
                if not dry_run:
                    c.execute("UPDATE contratacoes SET valor_estimado_centavos = %s WHERE pncp_id = %s", (new_val, pncp_id))
                stats["fixed"] += 1
                if len(fixed_ids) < 10: fixed_ids.append(pncp_id)
            else:
                stats["skipped"] += 1
                
        except Exception as e:
            stats["errors"] += 1
            print(f"Error repairing {pncp_id}: {e}")

    if not dry_run:
        conn.commit()
    conn.close()
    
    return {
        "stats": stats,
        "fixed_examples": fixed_ids,
        "elapsed": round(time.time() - start_time, 2),
        "dry_run": dry_run
    }

@app.post("/api/admin/backfill-itens-from-payload")
async def admin_backfill_itens_from_payload(
    limit: int = 200,
    user = Depends(verify_admin_api_key)
):
    """
    Hypothesis Test: Try to extract items from already stored payloads (DET/PUB).
    """
    from app.services.enrichment.utils import extract_items_from_payload, persist_items
    from app.db.session import get_db_connection
    import time
    import sqlite3
    
    start_time = time.time()
    stats = {
        "picked": 0,
        "completed_from_payload": 0,
        "not_available_no_payload": 0,
        "errors": 0
    }
    completed_ids = []
    
    conn = get_db_connection()
    try:
        # Selection: valid records, not fetched yet, missing item data
        cur = conn.execute("""
            SELECT pncp_id, payload_publicacao_json, payload_detalhe_json 
            FROM contratacoes
            WHERE is_valid IS TRUE
              AND itens_status IN ('NOT_FETCHED', 'FAILED_TEMP', 'NOT_AVAILABLE', 'FAILED')
              AND (itens_count = 0 OR itens_preview_json IS NULL)
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()
        
        for row in rows:
            stats["picked"] += 1
            pncp_id = row['pncp_id']
            try:
                items = extract_items_from_payload(row)
                if items and len(items) > 0:
                    persist_items(pncp_id, items)
                    stats["completed_from_payload"] += 1
                    if len(completed_ids) < 10: completed_ids.append(pncp_id)
                else:
                    # Skip or mark as not available in payload for this test
                    conn.execute("""
                        UPDATE contratacoes 
                        SET itens_status = 'NOT_AVAILABLE',
                            itens_last_error = 'NO_ITEMS_IN_PAYLOAD'
                        WHERE pncp_id = %s
                    """, (pncp_id,))
                    stats["not_available_no_payload"] += 1
            except Exception as e:
                stats["errors"] += 1
                import traceback
                traceback.print_exc()
                print(f"Error in fallback extraction for {pncp_id}: {e}")
        
        conn.commit()
    finally:
        conn.close()
        
    return {
        "stats": stats,
        "completed_examples": completed_ids,
        "elapsed": round(time.time() - start_time, 2)
    }


@app.post("/api/admin/drain-backlog")
async def admin_drain_backlog(
    max_seconds: int = 50,
    batch_itens: int = 80,
    batch_arquivos: int = 80,
    per_record_timeout_seconds: float = 12.0,
    mode: str = "both",
    user=Depends(verify_admin_api_key)
):
    """
    Time-bounded drain slice. Runs for at most `max_seconds` calling batch
    drain functions, then returns metrics. Call repeatedly to empty backlog.
    Does NOT block indefinitely — safe against HTTP proxy timeouts.
    """
    from app.services.enrichment.utils import run_itens_backfill, run_arquivos_backfill
    import time as _time

    start_wall = _time.time()

    totals = {
        "mode": mode,
        "max_seconds": max_seconds,
        "itens": {"batches": 0, "completed": 0, "failed_temp": 0, "failed_auth": 0,
                  "not_available": 0, "failed": 0, "eligible_total": 0},
        "arquivos": {"batches": 0, "completed": 0, "failed_temp": 0, "failed_auth": 0,
                     "not_available": 0, "failed": 0, "eligible_total": 0},
        "budget_hit": False,
        "duration_ms": 0,
    }

    while True:
        elapsed = _time.time() - start_wall
        if elapsed >= max_seconds:
            totals["budget_hit"] = True
            break

        remaining = max_seconds - int(elapsed)
        any_eligible = False

        if mode in ("itens", "both"):
            s = run_itens_backfill(
                limit=batch_itens,
                max_records=batch_itens,
                per_record_timeout_seconds=per_record_timeout_seconds,
                budget_seconds=remaining,
                debug=0,
            )
            totals["itens"]["batches"] += 1
            totals["itens"]["completed"] += s.get("completed", 0)
            totals["itens"]["failed_temp"] += s.get("failed_temp", 0)
            totals["itens"]["failed_auth"] += s.get("failed_auth", 0)
            totals["itens"]["not_available"] += s.get("not_available", 0)
            totals["itens"]["failed"] += s.get("failed", 0)
            totals["itens"]["eligible_total"] = s.get("eligible_total", 0)
            if s.get("eligible_total", 0) > 0:
                any_eligible = True

        if mode in ("arquivos", "both"):
            remaining2 = max_seconds - int(_time.time() - start_wall)
            if remaining2 <= 0:
                totals["budget_hit"] = True
                break
            s = run_arquivos_backfill(
                limit=batch_arquivos,
                per_record_timeout_seconds=per_record_timeout_seconds,
                budget_seconds=remaining2,
                debug=0,
            )
            totals["arquivos"]["batches"] += 1
            totals["arquivos"]["completed"] += s.get("completed", 0)
            totals["arquivos"]["failed_temp"] += s.get("failed_temp", 0)
            totals["arquivos"]["failed_auth"] += s.get("failed_auth", 0)
            totals["arquivos"]["not_available"] += s.get("not_available", 0)
            totals["arquivos"]["failed"] += s.get("failed", 0)
            totals["arquivos"]["eligible_total"] = s.get("eligible_total", 0)
            if s.get("eligible_total", 0) > 0:
                any_eligible = True

        if not any_eligible:
            break  # Backlog is empty


    totals["duration_ms"] = int((_time.time() - start_wall) * 1000)
    return totals

# ============================================================================
# SEGMENTATION APIs
# ============================================================================

import uuid

# Check if a job is currently locking segments
def _is_reclassify_job_running(conn) -> bool:
    c = conn.cursor()
    c.execute("SELECT id FROM jobs WHERE type='reclassify' AND status IN ('pending', 'running') LIMIT 1")
    return bool(c.fetchone())

@app.get("/api/segments")
async def get_segments(ws_context: dict = Depends(auth_deps.require_workspace_access)):
    """List all segments and their terms, ordered by priority."""
    from app.db.session import get_db_connection
    ws_id = ws_context["workspace_id"]
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, slug, name, is_active, priority, match_mode, min_hits FROM segments WHERE workspace_id = %s ORDER BY priority DESC", (ws_id,))
    segments = [dict(row) for row in c.fetchall()]
    
    # Enrich with terms
    for s in segments:
        c.execute("SELECT id, term, term_type, group_id FROM segment_terms WHERE segment_id = %s", (s['id'],))
        s['terms'] = [dict(row) for row in c.fetchall()]
        
    conn.close()
    return segments

@app.post("/api/segments")
async def create_segment(payload: dict, ws_context: dict = Depends(auth_deps.require_workspace_access)):
    """Create a new segment."""
    try:
        from app.db.session import get_db_connection
        ws_id = ws_context["workspace_id"]
        conn = get_db_connection()
        if _is_reclassify_job_running(conn):
            conn.close()
            raise HTTPException(status_code=409, detail="Cannot edit segments while a reclassification job is running.")
            
        c = conn.cursor()
        new_id = str(uuid.uuid4())
        
        min_hits = max(1, payload.get('min_hits', 1))
        c.execute("""
            INSERT INTO segments (id, slug, name, priority, match_mode, min_hits, is_active, workspace_id)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s)
        """, (new_id, payload['slug'], payload['name'], payload['priority'], payload['match_mode'].upper(), min_hits, ws_id))
        
        conn.commit()
        conn.close()
        return {"id": new_id, "slug": payload['slug']}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/segments/{segment_id}")
async def update_segment(segment_id: str, payload: dict, ws_context: dict = Depends(auth_deps.require_workspace_access)):
    """Update a segment's properties."""
    from app.db.session import get_db_connection
    ws_id = ws_context["workspace_id"]
    conn = get_db_connection()
    if _is_reclassify_job_running(conn):
        conn.close()
        raise HTTPException(status_code=409, detail="Cannot edit segments while a reclassification job is running.")
        
    c = conn.cursor()
    updates = []
    params = []
    
    if 'name' in payload:
        updates.append("name = %s")
        params.append(payload['name'])
    if 'priority' in payload:
        updates.append("priority = %s")
        params.append(payload['priority'])
    if 'match_mode' in payload:
        updates.append("match_mode = %s")
        params.append(payload['match_mode'].upper())
    if 'min_hits' in payload:
        updates.append("min_hits = %s")
        params.append(max(1, payload['min_hits']))
    if 'is_active' in payload:
        updates.append("is_active = %s")
        params.append(1 if payload['is_active'] else 0)
        
    if not updates:
        conn.close()
        return {"status": "ok"}
        
    params.extend([segment_id, ws_id])
    query = f"UPDATE segments SET {', '.join(updates)} WHERE id = %s AND workspace_id = %s"
    
    c.execute(query, params)
    if c.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Segment not found")
        
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.delete("/api/segments/{segment_id}")
async def delete_segment(segment_id: str, ws_context: dict = Depends(auth_deps.require_workspace_access)):
    """Delete a segment and its terms (cascade)."""
    from app.db.session import get_db_connection
    ws_id = ws_context["workspace_id"]
    conn = get_db_connection()
    if _is_reclassify_job_running(conn):
        conn.close()
        raise HTTPException(status_code=409, detail="Cannot edit segments while a reclassification job is running.")
        
    c = conn.cursor()
    c.execute("DELETE FROM segments WHERE id = %s AND workspace_id = %s", (segment_id, ws_id))
    if c.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Segment not found")
        
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.post("/api/segments/{segment_id}/terms")
async def add_segment_term(segment_id: str, payload: dict, ws_context: dict = Depends(auth_deps.require_workspace_access)):
    from app.db.session import get_db_connection
    ws_id = ws_context["workspace_id"]
    conn = get_db_connection()
    if _is_reclassify_job_running(conn):
        conn.close()
        raise HTTPException(status_code=409, detail="Cannot edit segments while a reclassification job is running.")
        
    c = conn.cursor()
    new_id = str(uuid.uuid4())
    c.execute("""
        INSERT INTO segment_terms (id, segment_id, term, term_type, group_id, workspace_id)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (new_id, segment_id, payload['term'], payload['term_type'], payload.get('group_id'), ws_id))
    
    conn.commit()
    conn.close()
    return {"id": new_id}

@app.delete("/api/segments/{segment_id}/terms/{term_id}")
async def delete_segment_term(segment_id: str, term_id: str, ws_context: dict = Depends(auth_deps.require_workspace_access)):
    from app.db.session import get_db_connection
    ws_id = ws_context["workspace_id"]
    conn = get_db_connection()
    if _is_reclassify_job_running(conn):
        conn.close()
        raise HTTPException(status_code=409, detail="Cannot edit segments while a reclassification job is running.")
        
    c = conn.cursor()
    c.execute("DELETE FROM segment_terms WHERE segment_id = %s AND id = %s AND workspace_id = %s", (segment_id, term_id, ws_id))
    if c.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Term not found or unauthorized")
        
    conn.commit()
    conn.close()
    return {"status": "ok"}


# Background Worker Function
def run_reclassify_job_worker(job_id: str, frozen_rules: list, ws_id: str):
    import time
    from app.db.session import get_db_connection
    from app.services.segmentation.classifier import DeterministicClassifier, finalize_contract_segment_frozen
    
    classifier = DeterministicClassifier(frozen_rules)
    conn = get_db_connection()
    c = conn.cursor()
    
    try:
        # Mark as running
        c.execute("UPDATE jobs SET status='running', started_at=NOW() WHERE id=%s", (job_id,))
        conn.commit()
        
        # We must process batches
        batch_size = 500
        offset = 0
        total_errors = 0
        total_processed = 0
        
        while True:
            # Strictly filtering out IGNORED user items!
            c.execute("""
                SELECT c.pncp_id, c.objeto, c.modalidade_nome
                FROM contratacoes c
                LEFT JOIN licitacao_workflow w ON c.pncp_id = w.pncp_id AND w.workspace_id = %s
                WHERE COALESCE(w.status, 'ACTIVE') != 'IGNORED'
                  AND c.workspace_id = %s
                ORDER BY c.pncp_id ASC
                LIMIT %s OFFSET %s
            """, (ws_id, ws_id, batch_size, offset))
            batch = c.fetchall()
            if not batch:
                break
                
            updates = []
            for row in batch:
                pid = row['pncp_id']
                objeto = row['objeto'] or ""
                modalidade_nome = row['modalidade_nome']
                
                try:
                    if modalidade_nome is None:
                        seg_id = 'unclassified'
                        evidence_json = "{}"
                    else:
                        # Get items text
                        it_cur = c.execute("SELECT descricao FROM licitacao_itens WHERE pncp_id = %s", (pid,))
                        it_rows = it_cur.fetchall()
                        item_descriptions = []
                        for it in it_rows:
                            text_part1 = it['descricao'] or ""
                            item_descriptions.append(text_part1)
                            
                        # Deterministic Match with Frozen Rules
                        seg_id, evidence_json = finalize_contract_segment_frozen(classifier, objeto, item_descriptions)
                    
                    updates.append((seg_id, evidence_json, datetime.now().isoformat(), pid))
                    total_processed += 1
                except Exception as e:
                    total_errors += 1
                    logger.error(f"Error reclassifying {pid}: {e}")
            
            if updates:
                c.executemany("""
                    UPDATE contratacoes SET 
                        segment_id = %s,
                        segmentos_json = %s,
                        segmento_updated_at = %s
                    WHERE pncp_id = %s
                """, updates)
            
            # Progress reporting
            c.execute("UPDATE jobs SET processed=%s, errors=%s WHERE id=%s", (total_processed, total_errors, job_id))
            conn.commit()
            
            offset += batch_size
            time.sleep(0.01) # Small yield
            
        # Done
        c.execute("UPDATE jobs SET status='done', finished_at=CURRENT_TIMESTAMP WHERE id=%s", (job_id,))
        conn.commit()
        logger.info(f"Reclassify job {job_id} completed. Processed: {total_processed}, Errors: {total_errors}")
    except Exception as e:
        logger.error(f"Reclassify job crashed: {e}")
        conn.execute("UPDATE jobs SET status='error', finished_at=CURRENT_TIMESTAMP WHERE id=%s", (job_id,))
        conn.commit()
    finally:
        conn.close()

@app.post("/api/segments/reclassify")
async def start_reclassify_job(background_tasks: BackgroundTasks, ws_context: dict = Depends(auth_deps.require_workspace_access)):
    """Start the asynchronous reclassification job if none is pending/running."""
    from app.db.session import get_db_connection
    from app.services.segmentation.classifier import fetch_frozen_rules
    ws_id = ws_context["workspace_id"]
    conn = get_db_connection()
    c = conn.cursor()
    
    if _is_reclassify_job_running(conn):
        conn.close()
        raise HTTPException(status_code=409, detail="A reclassification job is already running.")
        
    job_id = str(uuid.uuid4())
    c.execute("INSERT INTO jobs (id, type, status, workspace_id) VALUES (%s, 'reclassify', 'pending', %s)", (job_id, ws_id))
    
    # Generate Frozen Rules snapshot right now to prevent race conditions mid-flight
    frozen_rules = fetch_frozen_rules(conn, ws_id)
    conn.commit()
    conn.close()
    
    # Launch background loop
    background_tasks.add_task(run_reclassify_job_worker, job_id, frozen_rules, ws_id)
    
    return {"status": "accepted", "job_id": job_id}

@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str, ws_context: dict = Depends(auth_deps.require_workspace_access)):
    """Poll job status."""
    from app.db.session import get_db_connection
    ws_id = ws_context["workspace_id"]
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, type, status, processed, errors, started_at, finished_at FROM jobs WHERE id=%s AND workspace_id=%s", (job_id, ws_id))
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
        
    return dict(row)

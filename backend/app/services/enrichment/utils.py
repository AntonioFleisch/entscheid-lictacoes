import logging
import time
import json
import random
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from app.db.session import get_db_connection
from app.services.pncp.client import PNCPClient

logger = logging.getLogger(__name__)

# --- Configuration ---
MAX_CONCURRENT = int(os.getenv("PNCP_ENRICH_MAX_CONCURRENT", 3))
MAX_RPM = int(os.getenv("PNCP_ENRICH_MAX_RPM", 60))
MAX_ATTEMPTS = 8

# --- Helpers ---
def datetime_now_iso():
    return datetime.now().isoformat()

def datetime_add_minutes(m: int):
    return (datetime.now() + timedelta(minutes=m)).isoformat()

def datetime_add_seconds(s: int):
    return (datetime.now() + timedelta(seconds=s)).isoformat()

# --- Logic ---

def extract_items_from_payload(row: Any) -> Optional[List[Dict[str, Any]]]:
    """
    Best-effort extraction of items from stored JSON payloads.
    Returns List of items or None if not found/empty.
    """
    p_json = row['payload_publicacao_json'] if 'payload_publicacao_json' in row.keys() else None
    d_json = row['payload_detalhe_json'] if 'payload_detalhe_json' in row.keys() else None
    
    # Priority 1: Detail Payload (usually more complete)
    # Priority 2: Publication Payload
    payloads = [d_json, p_json]
    
    candidate_keys = ['itens', 'items', 'listaItens', 'itensCompra', 'itensLote', 'lotes', 'lote']
    
    for json_str in payloads:
        if not json_str: continue
        try:
            data = json.loads(json_str)
            for k in candidate_keys:
                val = data.get(k)
                if isinstance(val, list) and len(val) > 0:
                    # Sanity check: does first item have a description?
                    if isinstance(val[0], dict) and ('descricao' in val[0] or 'numeroItem' in val[0]):
                        return val
            
            # Recursive deep search if not found at top level
            found = _find_items_recursive(data)
            if found:
                return found
        except:
            continue
    return None

def _find_items_recursive(data: Any) -> Optional[List[Dict[str, Any]]]:
    if isinstance(data, dict):
        # Look for typical item keys deeper
        for k, v in data.items():
            if k.lower() in ['itens', 'items', 'listaitens'] and isinstance(v, list) and len(v) > 0:
                return v
            res = _find_items_recursive(v)
            if res: return res
    elif isinstance(data, list):
        if len(data) > 0 and isinstance(data[0], dict):
            keys = set(data[0].keys())
            if 'descricao' in keys and ('quantidade' in keys or 'quantidadeItem' in keys):
                return data
        for v in data:
            res = _find_items_recursive(v)
            if res: return res
    return None

# --- Main Pipelines ---

def log_pncp_request(pncp_id: str, endpoint: str, url: str, status_code: Optional[int], duration_ms: int, error: Optional[str] = None):
    """Logs PNCP request to audit table."""
    conn = get_db_connection()
    try:
        conn.execute("""
            INSERT INTO pncp_request_log (pncp_id, endpoint, url, status_code, duration_ms, error)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (pncp_id, endpoint, url, status_code, duration_ms, error))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to log audit record: {e}")
    finally:
        conn.close()

def acquire_lock(pncp_id: str, worker_id: str = "default") -> bool:
    """Acquires a non-transactional lock on items enrichment."""
    conn = get_db_connection()
    now = datetime_now_iso()
    lock_until = datetime_add_minutes(5)
    try:
        res = conn.execute("""
            UPDATE contratacoes
            SET itens_status='FETCHING',
                itens_lock_owner=%s,
                itens_lock_until=%s,
                itens_attempts=itens_attempts+1,
                itens_last_fetch_at=%s,
                itens_updated_at=%s
            WHERE pncp_id=%s
              AND (itens_status IN ('NOT_FETCHED', 'FAILED_TEMP') OR (itens_status = 'FETCHING' AND itens_lock_until < %s))
              AND (itens_next_retry_at IS NULL OR itens_next_retry_at <= %s)
              AND (itens_attempts < %s)
        """, (worker_id, lock_until, now, now, pncp_id, now, now, MAX_ATTEMPTS))
        conn.commit()
        return res.rowcount == 1
    except Exception as e:
        logger.error(f"Lock acquisition (itens) failed for {pncp_id}: {e}")
        return False
    finally:
        conn.close()

def acquire_lock_arquivos(pncp_id: str, worker_id: str = "default") -> bool:
    """Acquires a non-transactional lock on arquivos enrichment."""
    conn = get_db_connection()
    now = datetime_now_iso()
    lock_until = datetime_add_minutes(5)
    try:
        res = conn.execute("""
            UPDATE contratacoes
            SET arquivos_status='FETCHING',
                arquivos_lock_owner=%s,
                arquivos_lock_until=%s,
                arquivos_attempts=COALESCE(arquivos_attempts,0)+1,
                arquivos_last_fetch_at=%s,
                arquivos_updated_at=%s
            WHERE pncp_id=%s
              AND (arquivos_status IN ('NOT_FETCHED', 'FAILED_TEMP') OR (arquivos_status = 'FETCHING' AND arquivos_lock_until < %s))
              AND (arquivos_next_retry_at IS NULL OR arquivos_next_retry_at <= %s)
              AND (COALESCE(arquivos_attempts,0) < %s)
        """, (worker_id, lock_until, now, now, pncp_id, now, now, MAX_ATTEMPTS))
        conn.commit()
        return res.rowcount == 1
    except Exception as e:
        logger.error(f"Lock acquisition (arquivos) failed for {pncp_id}: {e}")
        return False
    finally:
        conn.close()

def release_lock(pncp_id: str, status: str, last_error: Optional[str] = None, next_retry_at: Optional[str] = None):
    """Releases lock and updates status."""
    conn = get_db_connection()
    now = datetime_now_iso()
    try:
        conn.execute("""
            UPDATE contratacoes
            SET itens_status=%s,
                itens_last_error=%s,
                itens_next_retry_at=%s,
                itens_lock_owner=NULL,
                itens_lock_until=NULL,
                itens_updated_at=%s
            WHERE pncp_id=%s
        """, (status, last_error, next_retry_at, now, pncp_id))
        conn.commit()
    except Exception as e:
        logger.error(f"Lock release failed for {pncp_id}: {e}")
    finally:
        conn.close()

def persist_items(pncp_id: str, items: List[Dict[str, Any]]):
    """Atomic persistence for items."""
    conn = get_db_connection()
    preview_items = []
    now = datetime_now_iso()
    for it in items[:5]:
        v_total_raw = it.get("valorTotal") if it.get("valorTotal") is not None else it.get("valorTotalEstimado")
        qtd = it.get("quantidade") if it.get("quantidade") is not None else 0
        v_unit_raw = it.get("valorUnitarioEstimado") if it.get("valorUnitarioEstimado") is not None else it.get("valorUnitario")
        v_unit = float(v_unit_raw) if v_unit_raw is not None else None
        
        if v_total_raw is not None:
            v_total_calc = float(v_total_raw)
        elif v_unit is not None:
            v_total_calc = float(qtd * v_unit)
        else:
            v_total_calc = None

        preview_items.append({
            "descricao": it.get("descricao"),
            "quantidade": qtd,
            "unidade": it.get("unidadeMedida") or it.get("unidade"),
            "valor_total": v_total_calc
        })
    try:
        with conn:
            conn.execute("DELETE FROM licitacao_itens WHERE pncp_id=%s", (pncp_id,))
            if items:
                insert_data = []
                for idx, it in enumerate(items):
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

                    insert_data.append((
                        pncp_id, it.get("numeroItem") or (idx + 1), it.get("descricao"),
                        it.get("unidadeMedida") or it.get("unidade"), qtd,
                        v_unit,
                        v_total,
                        json.dumps(it)
                    ))
                conn.executemany("""
                    INSERT INTO licitacao_itens (pncp_id, item_num, descricao, unidade, quantidade, valor_unit, valor_total, raw_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, insert_data)
            conn.execute("""
                UPDATE contratacoes
                SET itens_count=%s, itens_preview_json=%s, itens_updated_at=%s,
                    itens_status='COMPLETED', itens_last_error=NULL, itens_next_retry_at=NULL,
                    itens_lock_owner=NULL, itens_lock_until=NULL
                WHERE pncp_id=%s
            """, (len(items), json.dumps(preview_items), now, pncp_id))
    except Exception as e:
        logger.error(f"Items persistence failed for {pncp_id}: {e}")
        release_lock(pncp_id, 'FAILED', last_error=f"Persistence Error: {str(e)}")
        raise
    finally:
        conn.close()

def release_lock_arquivos(pncp_id: str, status: str, last_error: Optional[str] = None, next_retry_at: Optional[str] = None):
    """Releases arquivos lock and updates status."""
    conn = get_db_connection()
    now = datetime_now_iso()
    try:
        conn.execute("""
            UPDATE contratacoes
            SET arquivos_status=%s,
                arquivos_last_error=%s,
                arquivos_next_retry_at=%s,
                arquivos_lock_owner=NULL,
                arquivos_lock_until=NULL,
                arquivos_updated_at=%s
            WHERE pncp_id=%s
        """, (status, last_error, next_retry_at, now, pncp_id))
        conn.commit()
    except Exception as e:
        logger.error(f"Arquivos lock release failed for {pncp_id}: {e}")
    finally:
        conn.close()

def persist_arquivos(pncp_id: str, files: List[Dict[str, Any]]):
    """Atomic persistence for arquivos (v2 schema)."""
    conn = get_db_connection()
    now = datetime_now_iso()
    
    # Build preview (top 5)
    preview_items = []
    for f in files[:5]:
        seq_val = f.get("sequencialDocumento")
        if seq_val is None:
            seq_val = f.get("sequencial")
        preview_items.append({
            "titulo": f.get("titulo"),
            "tipo_documento_nome": f.get("tipoDocumentoNome") or f.get("tipo"),
            "url": f.get("url") or f.get("uri")
        })
    
    try:
        with conn:
            conn.execute("DELETE FROM licitacao_arquivos WHERE pncp_id=%s", (pncp_id,))
            if files:
                insert_data = []
                for f in files:
                    seq_val = f.get("sequencialDocumento")
                    if seq_val is None:
                        seq_val = f.get("sequencial")
                    if seq_val is None:
                        continue  # Safety: skip rows without a sequence
                    
                    tipo_doc_id = f.get("tipoDocumentoId")
                    if tipo_doc_id is not None:
                        tipo_doc_id = int(tipo_doc_id)
                    
                    insert_data.append((
                        pncp_id,
                        int(seq_val),
                        f.get("titulo"),
                        tipo_doc_id,
                        f.get("tipoDocumentoNome") or f.get("tipo"),
                        f.get("url") or f.get("uri"),
                        json.dumps(f),
                        now,
                        now
                    ))
                conn.executemany("""
                    INSERT INTO licitacao_arquivos 
                    (pncp_id, doc_seq, titulo, tipo_documento_id, tipo_documento_nome, url, raw_json, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, insert_data)
            conn.execute("""
                UPDATE contratacoes
                SET arquivos_count=%s, 
                    arquivos_preview_json=%s,
                    arquivos_updated_at=%s, 
                    arquivos_status='COMPLETED',
                    arquivos_last_error=NULL, 
                    arquivos_next_retry_at=NULL,
                    arquivos_lock_owner=NULL, 
                    arquivos_lock_until=NULL
                WHERE pncp_id=%s
            """, (len(files), json.dumps(preview_items), now, pncp_id))
    except Exception as e:
        logger.error(f"Arquivos persistence failed for {pncp_id}: {e}")
        release_lock_arquivos(pncp_id, 'FAILED', last_error=f"Persistence Error: {str(e)}")
        raise
    finally:
        conn.close()

def enrich_licitacao_arquivos(pncp_id: str, cnpj: str, ano: str, seq: str) -> Dict[str, Any]:
    """Arquivos enrichment pipeline."""
    # Quick check to avoid locking if already done
    conn = get_db_connection()
    row = conn.execute("SELECT arquivos_status FROM contratacoes WHERE pncp_id=%s", (pncp_id,)).fetchone()
    conn.close()
    if row and row[0] == 'COMPLETED':
        return {"status": "COMPLETED"}

    worker_id = f"enrich-worker-docs-{os.getpid()}"
    if not acquire_lock_arquivos(pncp_id, worker_id):
        return {"status": "SKIPPED_LOCKED"}
    
    # Use sequencial as int (strip leading zeros)
    seq_int = str(int(seq))
    
    client = PNCPClient()
    start_time = time.time()
    try:
        res = client.fetch_compra_arquivos(cnpj, ano, seq_int)
        duration = int((time.time() - start_time) * 1000)
        status = res.get("status")
        log_pncp_request(pncp_id, "get_arquivos", 
                         f"/orgaos/{cnpj}/compras/{ano}/{seq_int}/arquivos", 
                         status_code=res.get("status_code"), 
                         duration_ms=duration, error=res.get("error"))
        if status == "COMPLETED":
            persist_arquivos(pncp_id, res.get("files", []))
            return {"status": "COMPLETED", "count": len(res.get("files", []))}
        elif status == "FAILED_TEMP":
            delay = 60 * (2 ** random.randint(0, 3))
            next_retry = datetime_add_seconds(delay)
            release_lock_arquivos(pncp_id, "FAILED_TEMP", last_error=res.get("error"), next_retry_at=next_retry)
            return {"status": "FAILED_TEMP"}
        else:
            release_lock_arquivos(pncp_id, status, last_error=res.get("error"))
            return {"status": status}
    except Exception as e:
        logger.error(f"Arquivos enrichment crashed for {pncp_id}: {e}")
        release_lock_arquivos(pncp_id, "FAILED", last_error=str(e))
        return {"status": "FAILED", "error": str(e)}

def enrich_licitacao_items(pncp_id: str, cnpj: str, ano: str, seq: str) -> Dict[str, Any]:
    """Itens enrichment pipeline."""
    # Quick check to avoid locking if already done
    conn = get_db_connection()
    row = conn.execute("SELECT itens_status FROM contratacoes WHERE pncp_id=%s", (pncp_id,)).fetchone()
    conn.close()
    if row and row[0] == 'COMPLETED':
        return {"status": "COMPLETED"}

    worker_id = f"enrich-worker-items-{os.getpid()}"
    if not acquire_lock(pncp_id, worker_id):
        return {"status": "SKIPPED_LOCKED"}
    
    # Use sequencial as int (strip leading zeros)
    seq_int = str(int(seq))
    
    client = PNCPClient()
    start_time = time.time()
    try:
        res = client.fetch_compra_itens(cnpj, ano, seq_int)
        duration = int((time.time() - start_time) * 1000)
        status = res.get("status")
        log_pncp_request(pncp_id, "get_items", f"/orgaos/{cnpj}/compras/{ano}/{seq}/itens", 
                         status_code=200 if status == "COMPLETED" else None, 
                         duration_ms=duration, error=res.get("error"))
        if status == "COMPLETED":
            persist_items(pncp_id, res.get("items", []))
            return {"status": "COMPLETED", "count": len(res.get("items", []))}
        elif status == "FAILED_TEMP":
            delay = 60 * (2 ** random.randint(0, 3))
            next_retry = datetime_add_seconds(delay)
            release_lock(pncp_id, "FAILED_TEMP", last_error=res.get("error"), next_retry_at=next_retry)
            return {"status": "FAILED_TEMP"}
        else:
            release_lock(pncp_id, status, last_error=res.get("error"))
            return {"status": status}
    except Exception as e:
        logger.error(f"Items enrichment crashed for {pncp_id}: {e}")
        release_lock(pncp_id, "FAILED", last_error=str(e))
        return {"status": "FAILED", "error": str(e)}



def run_arquivos_backfill(
    limit: int = 50,
    pncp_id: Optional[str] = None,
    dry_run: int = 0,
    per_record_timeout_seconds: float = 12.0,
    debug: int = 1,
    budget_seconds: Optional[int] = None
) -> Dict[str, Any]:
    """
    Robust arquivos backfill logic with strict audit, locking, and time budgeting.
    """
    import time
    from app.db.session import get_db_connection

    start_time_total = time.time()

    if debug:
        logger.info(f"run_arquivos_backfill start | dry_run={dry_run} | pncp_id={pncp_id} | limit={limit} | budget_seconds={budget_seconds}")

    conn = get_db_connection()
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

        count_query = f"SELECT COUNT(*) as cnt FROM licitacoes WHERE {where_clause}"
        c.execute(count_query, params)
        eligible_total = c.fetchone()['cnt']

        if eligible_total == 0 and not pncp_id:
            if debug: logger.info("run_arquivos_backfill done | No eligible records")
            return {
                "eligible_total": 0,
                "selected": 0,
                "picked": 0,
                "reason": "No eligible records"
            }

        query = f"SELECT pncp_id, orgao_cnpj, ano, sequencial FROM licitacoes WHERE {where_clause} LIMIT %s"
        c.execute(query, params + [limit])
        rows = c.fetchall()
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
            "duration_ms": 0,
            "budget_hit": False
        }

        worker_id = f"backfill-arq-{os.getpid()}"
        client = PNCPClient()

        for row in rows:
            record_start_time = time.time()
            
            # Check budget
            if budget_seconds and (record_start_time - start_time_total) >= budget_seconds:
                if debug: logger.info(f"Budget of {budget_seconds}s reached. Stopping arquivos backfill.")
                stats["budget_hit"] = True
                break
                
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

                conn.execute("""
                    INSERT INTO pncp_request_log (pncp_id, endpoint, url, status_code, duration_ms, error)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (pid, "get_arquivos", fetch_url, status_code, duration_fetch, error_msg))
                conn.commit()

                final_status = res_fetch.get("status")

                if final_status == "COMPLETED":
                    raw_files = res_fetch.get("files", [])
                    if debug: logger.info(f"Persist arquivos start for {pid} | {len(raw_files)} files")

                    persist_arquivos(pid, raw_files)
                    
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
        if debug: logger.info(f"run_arquivos_backfill done | selected={selected} picked={stats['picked']} completed={stats['completed']} | Duration: {stats['duration_ms']}ms")

        return stats

    except Exception as e:
        logger.error(f"Critical Backfill arquivos failure: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e), "status": "job_failed"}
    finally:
        conn.close()

def run_itens_backfill(
    limit: int = 1,
    max_records: int = 1, # Used interchangeably
    pncp_id: Optional[str] = None,
    dry_run: int = 0,
    per_record_timeout_seconds: float = 12.0,
    max_pages: int = 20,
    debug: int = 1,
    budget_seconds: Optional[int] = None
) -> Dict[str, Any]:
    """
    Robust items backfill logic with strict audit, locking, and time budgeting.
    """
    import time
    from app.db.session import get_db_connection
    
    start_time_total = time.time()
    actual_limit = max_records if max_records != 1 else limit
    
    if debug:
        logger.info(f"run_itens_backfill start | dry_run={dry_run} | pncp_id={pncp_id} | limit={actual_limit} | budget_seconds={budget_seconds}")

    conn = get_db_connection()
    c = conn.cursor()
    
    try:
        # --- AUTO-RECOVER stuck FETCHING records with expired locks ---
        recovered = conn.execute("""
            UPDATE contratacoes
            SET itens_status = 'FAILED_TEMP',
                itens_last_error = 'AUTO_RECOVER_EXPIRED_LOCK',
                itens_next_retry_at = CURRENT_TIMESTAMP,
                itens_lock_owner = NULL,
                itens_lock_until = NULL
            WHERE itens_status = 'FETCHING'
              AND itens_lock_until IS NOT NULL
              AND itens_lock_until <= CURRENT_TIMESTAMP
        """).rowcount
        conn.commit()
        if recovered > 0 and debug:
            logger.info(f"Auto-recovered {recovered} stuck FETCHING itens records")

        # --- Eligible query ---
        where_parts = [
            "is_valid IS TRUE",
            "status = 'ACTIVE'",
            "itens_status IN ('NOT_FETCHED', 'FAILED_TEMP')"
        ]
        params = []
        
        where_parts.append("(itens_next_retry_at IS NULL OR itens_next_retry_at <= CURRENT_TIMESTAMP)")
        where_parts.append("(itens_lock_until IS NULL OR itens_lock_until <= CURRENT_TIMESTAMP)")

        if pncp_id:
            where_parts = ["pncp_id = %s"]
            params = [pncp_id]

        where_clause = " AND ".join(where_parts)
        
        count_query = f"SELECT COUNT(*) FROM licitacoes WHERE {where_clause}"
        eligible_total = c.execute(count_query, params).fetchone()[0]

        # --- pncp_id diagnostics: capture pre-lock state ---
        pre_lock_state = None
        if pncp_id:
            row_state = c.execute("""
                SELECT pncp_id, itens_status, itens_lock_until, itens_lock_owner,
                       itens_attempts, itens_last_error, itens_next_retry_at
                FROM contratacoes WHERE pncp_id = %s
            """, (pncp_id,)).fetchone()
            if row_state:
                pre_lock_state = dict(row_state)

        if eligible_total == 0 and not pncp_id:
            if debug: logger.info("run_itens_backfill done | No eligible records")
            return {
                "eligible_total": 0,
                "selected": 0,
                "picked": 0,
                "reason": "No eligible records"
            }

        query = f"SELECT pncp_id, orgao_cnpj, ano, sequencial FROM licitacoes WHERE {where_clause} LIMIT %s"
        c.execute(query, params + [actual_limit])
        rows = c.fetchall()
        selected = len(rows)
        processed_sample_ids = [row['pncp_id'] for row in rows[:10]]
        
        if debug:
            logger.info(f"Eligible total: {eligible_total} | Selected {selected} records. Sample: {processed_sample_ids}")

        # DRY RUN FAST PATH
        if dry_run == 1:
            result = {
                "dry_run": True,
                "eligible_total": eligible_total,
                "selected": selected,
                "sample_pncp_ids": processed_sample_ids,
                "auto_recovered": recovered
            }
            if pre_lock_state:
                result["pre_lock_state"] = pre_lock_state
            return result

        if not rows:
            result = {
                "eligible_total": eligible_total,
                "selected": 0,
                "picked": 0,
                "reason": "No eligible records after selection"
            }
            if pncp_id and pre_lock_state:
                # Determine why it's not eligible
                status = pre_lock_state.get("itens_status")
                lock_until = pre_lock_state.get("itens_lock_until")
                reason = "OTHER"
                if lock_until and lock_until > datetime.now().strftime('%Y-%m-%d %H:%M:%S'):
                    reason = "LOCKED_UNTIL_FUTURE"
                elif status not in ('NOT_FETCHED', 'FAILED_TEMP'):
                    reason = "STATUS_NOT_ELIGIBLE"
                result["lock_failure_reason"] = reason
                result["pre_lock_state"] = pre_lock_state
            return result

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
            "duration_ms": 0,
            "budget_hit": False
        }

        # EXECUÇÃO DO FETCH
        worker_id = f"backfill-worker-{os.getpid()}"
        client = PNCPClient()
        
        for row in rows:
            record_start_time = time.time()
            
            # Check budget
            if budget_seconds and (record_start_time - start_time_total) >= budget_seconds:
                if debug: logger.info(f"Budget of {budget_seconds}s reached. Stopping itens backfill.")
                stats["budget_hit"] = True
                break
                
            pid = row['pncp_id']
            cnpj = row['orgao_cnpj']
            ano = row['ano']
            seq = row['sequencial']
            
            # 1) UPDATE condicional para lock (on base table contratacoes) + COMMIT
            res = conn.execute("""
                UPDATE contratacoes
                SET itens_status = 'FETCHING',
                    itens_lock_owner = %s,
                    itens_lock_until = CURRENT_TIMESTAMP + interval '5 minutes',
                    itens_attempts = itens_attempts + 1,
                    itens_last_fetch_at = CURRENT_TIMESTAMP,
                    itens_updated_at = CURRENT_TIMESTAMP
                WHERE pncp_id = %s
                  AND (itens_status IN ('NOT_FETCHED', 'FAILED_TEMP') OR (itens_status = 'FETCHING' AND itens_lock_until <= CURRENT_TIMESTAMP))
                  AND (itens_lock_until IS NULL OR itens_lock_until <= CURRENT_TIMESTAMP)
            """, (worker_id, pid))
            conn.commit()
            
            if res.rowcount != 1:
                stats["skipped_locked"] += 1
                if debug: logger.info(f"Lock skipped for {pid}")
                # If pncp_id mode, add lock failure reason
                if pncp_id and pre_lock_state:
                    status = pre_lock_state.get("itens_status")
                    lock_until = pre_lock_state.get("itens_lock_until")
                    reason = "OTHER"
                    if lock_until and lock_until > datetime.now().strftime('%Y-%m-%d %H:%M:%S'):
                        reason = "LOCKED_UNTIL_FUTURE"
                    elif status not in ('NOT_FETCHED', 'FAILED_TEMP'):
                        reason = "STATUS_NOT_ELIGIBLE"
                    stats["lock_failure_reason"] = reason
                    stats["pre_lock_state"] = pre_lock_state
                continue

            stats["picked"] += 1
            if debug: logger.info(f"Lock acquired for {pid}")

            # 2) GET fetch & 3) Registrar em pncp_request_log
            try:
                fetch_url = f"https://pncp.gov.br/pncp-api/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens"
                if debug: logger.info(f"Fetch start: {fetch_url}")
                
                res_fetch = client.fetch_compra_itens(cnpj, ano, seq, timeout_seconds=per_record_timeout_seconds, max_pages=max_pages)
                
                duration_fetch = int((time.time() - record_start_time) * 1000)
                status_code = res_fetch.get("status_code", 0)
                error_msg = res_fetch.get("error")
                
                # GUARDA de tempo por registro
                elapsed_sec = time.time() - record_start_time
                if elapsed_sec > per_record_timeout_seconds:
                    logger.warning(f"Timeout guard triggered for {pid} ({elapsed_sec:.1f}s)")
                    error_msg = "PER_RECORD_TIMEOUT"
                    status_code = 408
                    res_fetch["status"] = "FAILED_TEMP"

                if debug: logger.info(f"Fetch done for {pid} | Status: {status_code} | Duration: {duration_fetch}ms")
                
                conn.execute("""
                    INSERT INTO pncp_request_log (pncp_id, endpoint, url, status_code, duration_ms, error)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (pid, "get_items", fetch_url, status_code, duration_fetch, error_msg))
                conn.commit()

                final_status = res_fetch.get("status")
                
                if final_status == "COMPLETED" and status_code == 200:
                    raw_items = res_fetch.get("items", [])
                    if debug: logger.info(f"Persist start for {pid}")
                    
                    persist_items(pid, raw_items)
                        
                    if debug: logger.info(f"Persist done for {pid} | Inserts: {len(raw_items)}")
                    stats["completed"] += 1
                
                elif final_status == "FAILED_AUTH":
                    conn.execute("UPDATE contratacoes SET itens_status = 'FAILED_AUTH', itens_lock_owner=NULL, itens_lock_until=NULL WHERE pncp_id = ?", (pid,))
                    conn.commit()
                    stats["failed_auth"] += 1
                elif final_status == "NOT_AVAILABLE":
                    conn.execute("UPDATE contratacoes SET itens_status = 'NOT_AVAILABLE', itens_lock_owner=NULL, itens_lock_until=NULL WHERE pncp_id = ?", (pid,))
                    conn.commit()
                    stats["not_available"] += 1
                else:
                    conn.execute("""
                        UPDATE contratacoes 
                        SET itens_status = 'FAILED_TEMP', 
                            itens_next_retry_at = datetime('now', '+15 minutes'),
                            itens_lock_owner=NULL, 
                            itens_lock_until=NULL, 
                            itens_last_error=? 
                        WHERE pncp_id=?
                    """, (error_msg or f"Status {status_code}", pid))
                    conn.commit()
                    stats["failed_temp"] += 1

                if debug: logger.info(f"Record completed: {pid} -> {final_status}")

            except Exception as e:
                logger.error(f"Error processing {pid} in itens backfill: {e}")
                conn.execute("UPDATE contratacoes SET itens_status = 'FAILED', itens_last_error=?, itens_lock_owner=NULL, itens_lock_until=NULL WHERE pncp_id=?", (str(e), pid))
                conn.commit()
                stats["failed"] += 1

            # Politeness delay
            if actual_limit > 1:
                time.sleep(1.0)
                
        stats["skipped_locked"] = selected - stats["picked"]
        stats["duration_ms"] = int((time.time() - start_time_total) * 1000)
        
        if debug: logger.info(f"run_itens_backfill done | selected={selected} picked={stats['picked']} completed={stats['completed']} | Duration: {stats['duration_ms']}ms")
        return stats

    except Exception as e:
        logger.error(f"Critical Backfill failure: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e), "status": "job_failed"}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Single-record API — canonical, stable, used by Phase B2 and CLI drain
# ---------------------------------------------------------------------------

def enrich_single_itens(pncp_id: str, per_record_timeout_seconds: float = 12.0, debug: int = 0) -> dict:
    """
    Enrich ITENS for exactly one pncp_id.
    Uses the same locking, HTTP client, persistence and status logic as the batch.
    Returns: {pncp_id, status, count, completed, error?, duration_ms}
    """
    from app.db.session import get_db_connection as _get_db_connection

    start_t = time.time()
    conn = _get_db_connection()

    try:
        row = conn.execute(
            "SELECT pncp_id, orgao_cnpj, ano, sequencial, itens_status, itens_lock_until FROM contratacoes WHERE pncp_id=%s",
            (pncp_id,)
        ).fetchone()

        if not row:
            return {"pncp_id": pncp_id, "status": "NOT_FOUND", "completed": False, "duration_ms": 0}

        if row["itens_status"] == "COMPLETED":
            return {"pncp_id": pncp_id, "status": "ALREADY_DONE", "completed": True, "duration_ms": 0}

        worker_id = f"b2-itens-{os.getpid()}"

        # Attempt lock
        res_lock = conn.execute("""
            UPDATE contratacoes
            SET itens_status = 'FETCHING',
                itens_lock_owner = %s,
                itens_lock_until = CURRENT_TIMESTAMP + interval '5 minutes',
                itens_attempts = itens_attempts + 1,
                itens_last_fetch_at = CURRENT_TIMESTAMP,
                itens_updated_at = CURRENT_TIMESTAMP
            WHERE pncp_id = %s
              AND (COALESCE(itens_status,'NOT_FETCHED') IN ('NOT_FETCHED','FAILED_TEMP')
                   OR (itens_status='FETCHING' AND itens_lock_until <= CURRENT_TIMESTAMP))
              AND (itens_lock_until IS NULL OR itens_lock_until <= CURRENT_TIMESTAMP)
        """, (worker_id, pncp_id))
        conn.commit()

        if res_lock.rowcount != 1:
            return {"pncp_id": pncp_id, "status": "SKIPPED_LOCKED", "completed": False,
                    "duration_ms": int((time.time() - start_t) * 1000)}

        cnpj = row["orgao_cnpj"]
        ano = row["ano"]
        seq = str(int(row["sequencial"]))

        client = PNCPClient()
        fetch_url = f"https://pncp.gov.br/pncp-api/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens"

        try:
            res_fetch = client.fetch_compra_itens(cnpj, ano, seq,
                                                   timeout_seconds=per_record_timeout_seconds,
                                                   max_pages=20)
            duration_ms = int((time.time() - start_t) * 1000)
            status_code = res_fetch.get("status_code", 0)
            error_msg = res_fetch.get("error")
            final_status = res_fetch.get("status")

            # Timeout guard
            if (time.time() - start_t) > per_record_timeout_seconds:
                error_msg = "PER_RECORD_TIMEOUT"
                status_code = 408
                final_status = "FAILED_TEMP"

            conn.execute("""
                INSERT INTO pncp_request_log (pncp_id, endpoint, url, status_code, duration_ms, error)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (pncp_id, "get_items", fetch_url, status_code, duration_ms, error_msg))
            conn.commit()

            if final_status == "COMPLETED" and status_code == 200:
                raw_items = res_fetch.get("items", [])
                persist_items(pncp_id, raw_items)
                if debug:
                    logger.info(f"enrich_single_itens OK {pncp_id} | {len(raw_items)} items")
                return {"pncp_id": pncp_id, "status": "COMPLETED", "count": len(raw_items),
                        "completed": True, "duration_ms": duration_ms}
            elif final_status == "FAILED_AUTH":
                conn.execute("UPDATE contratacoes SET itens_status='FAILED_AUTH', itens_lock_owner=NULL, itens_lock_until=NULL WHERE pncp_id=%s", (pncp_id,))
                conn.commit()
                return {"pncp_id": pncp_id, "status": "FAILED_AUTH", "completed": False, "duration_ms": duration_ms}
            elif final_status == "NOT_AVAILABLE":
                conn.execute("UPDATE contratacoes SET itens_status='NOT_AVAILABLE', itens_lock_owner=NULL, itens_lock_until=NULL WHERE pncp_id=%s", (pncp_id,))
                conn.commit()
                return {"pncp_id": pncp_id, "status": "NOT_AVAILABLE", "completed": False, "duration_ms": duration_ms}
            else:
                conn.execute("""
                    UPDATE contratacoes SET itens_status='FAILED_TEMP',
                        itens_next_retry_at=CURRENT_TIMESTAMP + interval '15 minutes',
                        itens_lock_owner=NULL, itens_lock_until=NULL, itens_last_error=%s
                    WHERE pncp_id=%s
                """, (error_msg or f"Status {status_code}", pncp_id))
                conn.commit()
                return {"pncp_id": pncp_id, "status": "FAILED_TEMP", "completed": False,
                        "error": error_msg, "duration_ms": duration_ms}

        except Exception as e:
            logger.error(f"enrich_single_itens error for {pncp_id}: {e}")
            conn.execute("UPDATE contratacoes SET itens_status='FAILED', itens_last_error=%s, itens_lock_owner=NULL, itens_lock_until=NULL WHERE pncp_id=%s",
                         (str(e), pncp_id))
            conn.commit()
            return {"pncp_id": pncp_id, "status": "FAILED", "completed": False,
                    "error": str(e), "duration_ms": int((time.time() - start_t) * 1000)}
    finally:
        conn.close()


def enrich_single_arquivos(pncp_id: str, per_record_timeout_seconds: float = 12.0, debug: int = 0) -> dict:
    """
    Enrich ARQUIVOS for exactly one pncp_id.
    Uses the same locking, HTTP client, persistence and status logic as the batch.
    Returns: {pncp_id, status, count, completed, error?, duration_ms}
    """
    from app.db.session import get_db_connection as _get_db_connection

    start_t = time.time()
    conn = _get_db_connection()

    try:
        row = conn.execute(
            "SELECT pncp_id, orgao_cnpj, ano, sequencial, arquivos_status, arquivos_lock_until FROM contratacoes WHERE pncp_id=%s",
            (pncp_id,)
        ).fetchone()

        if not row:
            return {"pncp_id": pncp_id, "status": "NOT_FOUND", "completed": False, "duration_ms": 0}

        if row["arquivos_status"] == "COMPLETED":
            return {"pncp_id": pncp_id, "status": "ALREADY_DONE", "completed": True, "duration_ms": 0}

        worker_id = f"b2-arq-{os.getpid()}"

        res_lock = conn.execute("""
            UPDATE contratacoes
            SET arquivos_status = 'FETCHING',
                arquivos_lock_owner = %s,
                arquivos_lock_until = CURRENT_TIMESTAMP + interval '5 minutes',
                arquivos_attempts = COALESCE(arquivos_attempts, 0) + 1,
                arquivos_last_fetch_at = CURRENT_TIMESTAMP,
                arquivos_updated_at = CURRENT_TIMESTAMP
            WHERE pncp_id = %s
              AND (COALESCE(arquivos_status,'NOT_FETCHED') IN ('NOT_FETCHED','FAILED_TEMP')
                   OR (arquivos_status='FETCHING' AND arquivos_lock_until <= CURRENT_TIMESTAMP))
              AND (arquivos_lock_until IS NULL OR arquivos_lock_until <= CURRENT_TIMESTAMP)
        """, (worker_id, pncp_id))
        conn.commit()

        if res_lock.rowcount != 1:
            return {"pncp_id": pncp_id, "status": "SKIPPED_LOCKED", "completed": False,
                    "duration_ms": int((time.time() - start_t) * 1000)}

        cnpj = row["orgao_cnpj"]
        ano = row["ano"]
        seq = str(int(row["sequencial"]))

        client = PNCPClient()
        fetch_url = f"https://pncp.gov.br/pncp-api/v1/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos"

        try:
            res_fetch = client.fetch_compra_arquivos(cnpj, ano, seq)
            duration_ms = int((time.time() - start_t) * 1000)
            status_code = res_fetch.get("status_code", 0)
            error_msg = res_fetch.get("error")
            final_status = res_fetch.get("status")

            # Timeout guard
            if (time.time() - start_t) > per_record_timeout_seconds:
                error_msg = "PER_RECORD_TIMEOUT"
                status_code = 408
                final_status = "FAILED_TEMP"

            conn.execute("""
                INSERT INTO pncp_request_log (pncp_id, endpoint, url, status_code, duration_ms, error)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (pncp_id, "get_arquivos", fetch_url, status_code, duration_ms, error_msg))
            conn.commit()

            if final_status == "COMPLETED":
                raw_files = res_fetch.get("files", [])
                persist_arquivos(pncp_id, raw_files)
                if debug:
                    logger.info(f"enrich_single_arquivos OK {pncp_id} | {len(raw_files)} files")
                return {"pncp_id": pncp_id, "status": "COMPLETED", "count": len(raw_files),
                        "completed": True, "duration_ms": duration_ms}
            elif final_status == "FAILED_AUTH":
                conn.execute("UPDATE contratacoes SET arquivos_status='FAILED_AUTH', arquivos_lock_owner=NULL, arquivos_lock_until=NULL WHERE pncp_id=%s", (pncp_id,))
                conn.commit()
                return {"pncp_id": pncp_id, "status": "FAILED_AUTH", "completed": False, "duration_ms": duration_ms}
            elif final_status == "NOT_AVAILABLE":
                conn.execute("UPDATE contratacoes SET arquivos_status='NOT_AVAILABLE', arquivos_lock_owner=NULL, arquivos_lock_until=NULL WHERE pncp_id=%s", (pncp_id,))
                conn.commit()
                return {"pncp_id": pncp_id, "status": "NOT_AVAILABLE", "completed": False, "duration_ms": duration_ms}
            else:
                conn.execute("""
                    UPDATE contratacoes SET arquivos_status='FAILED_TEMP',
                        arquivos_next_retry_at=CURRENT_TIMESTAMP + interval '15 minutes',
                        arquivos_lock_owner=NULL, arquivos_lock_until=NULL, arquivos_last_error=%s
                    WHERE pncp_id=%s
                """, (error_msg or f"Status {status_code}", pncp_id))
                conn.commit()
                return {"pncp_id": pncp_id, "status": "FAILED_TEMP", "completed": False,
                        "error": error_msg, "duration_ms": duration_ms}

        except Exception as e:
            logger.error(f"enrich_single_arquivos error for {pncp_id}: {e}")
            conn.execute("UPDATE contratacoes SET arquivos_status='FAILED', arquivos_last_error=%s, arquivos_lock_owner=NULL, arquivos_lock_until=NULL WHERE pncp_id=%s",
                         (str(e), pncp_id))
            conn.commit()
            return {"pncp_id": pncp_id, "status": "FAILED", "completed": False,
                    "error": str(e), "duration_ms": int((time.time() - start_t) * 1000)}
    finally:
        conn.close()


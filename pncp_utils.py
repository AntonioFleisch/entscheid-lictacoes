import logging
import hashlib
import json
import re
from typing import Dict, Any, List, Optional
from database import get_db_connection
from pncp_client import PNCPClient

logger = logging.getLogger(__name__)
client = PNCPClient()

# --- Identity & Fingerprinting ---

def calculate_fingerprint(item: Dict[str, Any]) -> str:
    """SHA256(orgao_norm + objeto_norm + data_publicacao + valor_total)"""
    orgao = (item.get("orgaoEntidade") or {}).get("razaoSocial", "").strip().lower()
    objeto = (item.get("objetoCompra") or "").strip().lower()
    data = item.get("dataPublicacaoPncp", "").split("T")[0]
    valor = str(item.get("valorTotalEstimado", 0))
    
    raw = f"{orgao}|{objeto}|{data}|{valor}"
    return hashlib.sha256(raw.encode()).hexdigest()

def calculate_json_hash(data: Dict[str, Any]) -> str:
    """Canonical JSON hash"""
    canonical_json = json.dumps(data, sort_keys=True)
    return hashlib.sha256(canonical_json.encode()).hexdigest()

def derive_identity(item: Dict[str, Any], origin_url: str = "") -> Dict[str, str]:
    """
    Derives canonical identity components.
    NEVER invents source_id.
    """
    # 1. Try PNCP ID explicitly if valid format
    # format check: 14 chars - 1 char - 6 chars / 4 chars
    # simple check if contains '/' and '-'
    raw_id = item.get("numeroControlePNCP", "") or item.get("id", "")
    pncp_id = raw_id if ('/' in raw_id and '-' in raw_id) else None
    
    # 2. Source ID
    # If we ingest from PNCP API, source is PNCP
    source = "PNCP"
    source_id = pncp_id # In this context source_id is pncp_id
    
    return {
        "pncp_id": pncp_id,
        "source": source,
        "source_id": source_id,
        "origin_url": origin_url or f"https://pncp.gov.br/app/editais?q={pncp_id}" if pncp_id else None
    }

def build_pncp_edital_url(pncp_id: str, orgao_cnpj: str = None, ano: str = None, sequencial: str = None) -> Optional[str]:
    """
    Builds the canonical PNCP URL for a bidding.
    Format: https://pncp.gov.br/app/editais/{cnpj}/{ano}/{sequencial}
    
    Robustness:
    - Prefer explicit components.
    - Fallback to parsing pncp_id if format matches strictly: ^(\\d{14})-\\d+-(\\d+)/(\\d{4})$
    - Sanitizes inputs (digits only for CNPJ, int for seq/ano).
    - Returns None on error (Exception-safe).
    """
    try:
        # 1. Normalize Inputs
        p_cnpj = None
        p_ano = None
        p_seq = None
        
        # Determine strict or fallback
        if orgao_cnpj and ano and sequencial:
             p_cnpj = str(orgao_cnpj)
             p_ano = str(ano)
             p_seq = str(sequencial)
        elif pncp_id:
             # Fallback Parse: 12345678000199-1-000011/2026
             match = re.match(r'^(\d{14})-\d+-(\d+)/(\d{4})$', str(pncp_id).strip())
             if match:
                 p_cnpj = match.group(1)
                 p_seq = match.group(2)
                 p_ano = match.group(3)
        
        if not (p_cnpj and p_ano and p_seq):
            return None
            
        # 2. Sanitize
        # CNPJ: Digits only
        clean_cnpj = "".join(filter(str.isdigit, p_cnpj))
        if len(clean_cnpj) != 14:
            return None
            
        # Ano: 4 digits integer
        clean_ano_int = int(p_ano)
        if clean_ano_int < 2000 or clean_ano_int > 2100: # Basic sanity
            return None
            
        # Seq: Integer (strips leading ones/zeros)
        clean_seq_int = int(p_seq)
        if clean_seq_int <= 0:
            return None
            
        return f"https://pncp.gov.br/app/editais/{clean_cnpj}/{clean_ano_int}/{clean_seq_int}"
        
    except Exception:
        return None

# --- Ingestion Stages ---

def ingest_staging_list(data_list: List[Dict[str, Any]], request_fingerprint: str):
    """
    Ingests raw list items into staging with deduplication check.
    """
    conn = get_db_connection()
    c = conn.cursor()
    
    for item in data_list:
        # Determine Page/Item Fingerprint to prevent pagination loops duplicating staging
        # Hash of the raw item itself acts as page_fingerprint unique constraint
        raw_json = json.dumps(item, sort_keys=True)
        page_fingerprint = hashlib.sha256(raw_json.encode()).hexdigest()
        
        # Identity derivation for candidate fields
        ident = derive_identity(item)
        
        try:
            c.execute("""
                INSERT INTO staging_licitacoes (
                    candidate_id, source, source_id, origin_url,
                    list_request_fingerprint, page_fingerprint,
                    status, raw_data, raw_data_hash
                ) VALUES (%s, %s, %s, %s, %s, %s, 'NEW', %s, %s)
            """, (
                ident['pncp_id'], ident['source'], ident['source_id'], ident['origin_url'],
                request_fingerprint, page_fingerprint,
                raw_json, page_fingerprint
            ))
        except Exception: # Unique constraint violation -> Update seen
             c.execute("""
                UPDATE staging_licitacoes 
                SET seen_count = seen_count + 1, last_seen_at = CURRENT_TIMESTAMP
                WHERE list_request_fingerprint = %s AND page_fingerprint = %s
             """, (request_fingerprint, page_fingerprint))
             
    conn.commit()
    conn.close()

def reconcile_staging():
    """
    Reconciles NEW staging records to Canonical Licitacoes.
    Strict order: PNCP_ID -> ORIGIN_URL -> Source/ID -> Fingerprint
    """
    conn = get_db_connection()
    c = conn.cursor()
    
    # Iterate NEW items
    c.execute("SELECT * FROM staging_licitacoes WHERE status = 'NEW'")
    staging_items = c.fetchall()
    
    for row in staging_items:
        item = json.loads(row['raw_data'])
        ident = derive_identity(item, row['origin_url'])
        
        canonical_id = None
        is_duplicate = False
        
        # 1. Exact PNCP ID Check
        if ident['pncp_id']:
            c.execute("SELECT canonical_id FROM licitacoes WHERE pncp_id = %s", (ident['pncp_id'],))
            match = c.fetchone()
            if match:
                canonical_id = match['canonical_id']
                is_duplicate = True

        # 2. Exact Origin URL Check
        if not canonical_id and ident['origin_url']:
             c.execute("SELECT canonical_id FROM licitacoes WHERE origin_url = %s", (ident['origin_url'],))
             match = c.fetchone()
             if match:
                 canonical_id = match['canonical_id']
                 is_duplicate = True
                 
        # 3. Insert specific logic (New Record)
        if not canonical_id:
            # Create NEW Canonical
            # define canonical_id
            new_id = ident['pncp_id'] if ident['pncp_id'] else f"{ident['source']}:{ident['source_id']}"
            
            # Extract Normalized Fields
            orgao = (item.get('orgaoEntidade') or {}).get('razaoSocial', 'Unknown')
            objeto = item.get('objetoCompra', '')
            val = item.get('valorTotalEstimado', 0)
            
            # Fingerprint for duplicate detection later
            fg = calculate_fingerprint(item)
            
            try:
                c.execute("""
                    INSERT INTO licitacoes (
                        canonical_id, pncp_id, source, source_id, origin_url,
                        orgao, objeto, valor_total_estimado,
                        data_publicacao, data_inicio_propostas, data_fim_propostas,
                        fingerprint, is_active_record
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                """, (
                    new_id, ident['pncp_id'], ident['source'], ident['source_id'], ident['origin_url'],
                    orgao, objeto, val,
                    item.get('dataPublicacaoPncp'), item.get('dataInicioRecebimentoPropostas'), item.get('dataFimRecebimentoPropostas'),
                    fg
                ))
                canonical_id = new_id
            except Exception as e:
                logger.error(f"Reconciliation Insert Error: {e}")
                # Fallback check if it was race condition
                continue

        # Update Staging
        status = 'DUPLICATE' if is_duplicate else 'ENRICHED' # Technically just reconciled, waiting enrichment
        c.execute("UPDATE staging_licitacoes SET status = %s, matched_canonical_id = %s WHERE id = %s",
                  (status, canonical_id, row['id']))
    
    conn.commit()
    conn.close()

def run_enrichment_cycle(limit=10):
    """
    Enriches Pending items with details from PNCP Client
    """
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("""
        SELECT * FROM licitacoes 
        WHERE enrichment_status IN ('PENDING', 'RETRY') AND is_active_record IS TRUE
        LIMIT %s
    """, (limit,))
    
    targets = c.fetchall()
    
    for row in targets:
        pk = row['canonical_id']
        pncp_id = row['pncp_id']
        
        # Fetch details
        try:
             # Use client to fetch (probe capabilities handled inside client but we assume structure here)
             details = client.fetch_details(pncp_id)
             if not details:
                 c.execute("UPDATE licitacoes SET enrichment_status = 'RETRY', enrichment_attempts = enrichment_attempts + 1 WHERE canonical_id = %s", (pk,))
                 continue
                 
             # Idempotency Check
             new_hash = calculate_json_hash(details)
             if row['payload_hash'] == new_hash:
                 c.execute("UPDATE licitacoes SET enrichment_status = 'COMPLETED', updated_at = CURRENT_TIMESTAMP WHERE canonical_id = %s", (pk,))
                 continue
                 
             # Upsert Details (Items)
             items = client.fetch_items(pncp_id) # Using client fallback/discovery implicitly
             # DELETE existing items for this license (Replace Mode)
             c.execute("DELETE FROM licitacao_itens WHERE licitacao_id = %s", (pk,))
             for i in items:
                 c.execute("""
                    INSERT INTO licitacao_itens (licitacao_id, item_key, numero, descricao, quantidade, valor_unitario, valor_total)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                 """, (
                     pk, str(i.get('numeroItem')), i.get('numeroItem'), i.get('descricao'), 
                     i.get('quantidade'), i.get('valorUnitarioEstimado'), i.get('valorTotal')
                 ))
                 
             # Upsert Docs (Upsert Mode)
             docs = client.fetch_docs(pncp_id)
             for d in docs:
                 d_url = d.get('urlDownload') or 'unknown'
                 c.execute("""
                    INSERT INTO licitacao_documentos (licitacao_id, doc_url, doc_nome, doc_tipo)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT(licitacao_id, doc_url) DO UPDATE SET doc_nome=excluded.doc_nome
                 """, (pk, d_url, d.get('tituloDocumento'), d.get('tipoDocumento')))
 
             c.execute("UPDATE licitacoes SET enrichment_status = 'COMPLETED', payload_hash = %s, updated_at = CURRENT_TIMESTAMP WHERE canonical_id = %s", (new_hash, pk))
             
        except Exception as e:
            logger.error(f"Enrichment Failed for {pk}: {e}")
            c.execute("UPDATE licitacoes SET enrichment_status = 'RETRY', last_error = %s, enrichment_attempts = enrichment_attempts + 1 WHERE canonical_id = %s", (str(e), pk))
            
    conn.commit()
    conn.close()
    
# --- Public Facade (Search) ---

def normalize_for_ui(item: Dict[str, Any], conn=None) -> Dict[str, Any]:
    """
    Normalization Layer: Maps flat DB fields to nested structures expected by the frontend.
    """
    # 1. Location
    if "localizacao" not in item:
        item["localizacao"] = {
            "ufSigla": item.get("uf"),
            "municipioNome": item.get("municipio")
        }
    
    # 2. Values
    v_cents = item.get("valor_estimado_centavos")
    val = None
    if v_cents is not None:
        try:
            # Check if it's a string (potential corruption)
            if isinstance(v_cents, str):
                if 'T' in v_cents:
                    val = None
                else:
                    val = float(v_cents) / 100.0
            else:
                val = float(v_cents) / 100.0
        except (ValueError, TypeError):
            val = None
            # print(f"Error converting valor_estimado_centavos: {v_cents} for item {item.get('pncp_id')}")

    item["valores"] = {
        "estimado": val
    }
        
    # 3. Comprador (Orgao)
    if "comprador" not in item:
        item["comprador"] = {
            "cnpj": item.get("orgao_cnpj"),
            "razaoSocial": item.get("orgao_nome")
        }

    # Workflow Status (v3 Settle - Refined)
    if "workflow_status" not in item and "status" in item:
        item["workflow_status"] = item["status"]

    if "workflow_status" not in item:
        if conn:
            try:
                # Use the new licitacao_workflow table
                pncp_id = item.get('id') or item.get('pncp_id')
                cur = conn.execute("SELECT status FROM licitacao_workflow WHERE pncp_id = %s", (pncp_id,))
                row = cur.fetchone()
                item['workflow_status'] = row['status'] if row else 'ACTIVE'
            except:
                item['workflow_status'] = 'ACTIVE'
        else:
            item['workflow_status'] = 'ACTIVE'

    # 7. PNCP Items Enrichment (Strict Fix)
    itens_count = int(item.get("itens_count") or 0)
    itens_status = item.get("itens_status") or "NOT_FETCHED"
    itens_preview = []
    
    # Rule: If status != 'COMPLETED' -> preview MUST be []
    if itens_status == 'COMPLETED':
        raw_preview = item.get("itens_preview_json")
        if raw_preview:
            try:
                if isinstance(raw_preview, str):
                    itens_preview = json.loads(raw_preview)
                else:
                    itens_preview = raw_preview
            except Exception as e:
                logger.warning(f"Error parsing itens_preview_json for {item.get('pncp_id')}: {e}")
                itens_preview = []
    
    item["itens"] = {
        "count": itens_count,
        "status": itens_status,
        "preview": itens_preview,
        "has_more": itens_count > len(itens_preview),
        "updated_at": item.get("itens_updated_at")
    }

    # 8. PNCP Arquivos (Attachments) Enrichment
    arquivos_count = int(item.get("arquivos_count") or 0)
    arquivos_status = item.get("arquivos_status") or "NOT_FETCHED"
    
    # 8. PNCP Arquivos (Attachments) Enrichment
    arquivos_count = int(item.get("arquivos_count") or 0)
    arquivos_status = item.get("arquivos_status") or "NOT_FETCHED"
    arquivos_preview = []

    if arquivos_status == 'COMPLETED':
        raw_arq_preview = item.get("arquivos_preview_json")
        if raw_arq_preview:
            try:
                if isinstance(raw_arq_preview, str):
                    arquivos_preview = json.loads(raw_arq_preview)
                else:
                    arquivos_preview = raw_arq_preview
            except Exception as e:
                logger.warning(f"Error parsing arquivos_preview_json for {item.get('pncp_id')}: {e}")
                arquivos_preview = []

    item["arquivos"] = {
        "count": arquivos_count,
        "status": arquivos_status,
        "preview": arquivos_preview,
        "has_more": arquivos_count > len(arquivos_preview),
        "updated_at": item.get("arquivos_updated_at")
    }

    # 4. Segment Normalization (v3 Settle Benchmark)
    slug = item.get("segment_id") or item.get("segmento_principal") or "unclassified"
    item["segment_id"] = slug
    
    if "segment_label" not in item:
        if conn:
            try:
                cur = conn.execute("SELECT name FROM segments WHERE slug = %s", (slug,))
                row = cur.fetchone()
                item["segment_label"] = row['name'] if row else ("Sem classificação" if slug == "unclassified" else slug.replace('_', ' ').title())
            except:
                item["segment_label"] = "Sem classificação" if slug == "unclassified" else slug.replace('_', ' ').title()
        else:
            # Fallback labels if no connection
            labels = {
                "almoxarifado_virtual": "Almoxarifado Virtual",
                "kit_escolar": "Kit Escolar",
                "diversos": "Diversos",
                "unclassified": "Sem classificação"
            }
            item["segment_label"] = labels.get(slug, slug.replace('_', ' ').title())

    # 5. ID Normalization (Frontend expects 'id')
    if "id" not in item:
        item["id"] = item.get("pncp_id")
        
    # 6. Compatibility (Frontend expects objetoCompra)
    if "objetoCompra" not in item:
        item["objetoCompra"] = item.get("objeto")

    return item

# --- Public Facade (Search) ---

def search_licitacoes_sql(q=None, uf=None, segmento=None, quick=None, page=1, per_page=10, exclude_ids=None, debug=False, workspace_id=None):
    conn = get_db_connection()
    c = conn.cursor()
    
    # 1. Base Filter Construction (Shared by List and Facets)
    base_where = " WHERE 1=1"
    base_params = []
    
    if workspace_id:
        base_where += " AND l.workspace_id = %s"
        base_params.append(workspace_id)
    
    if exclude_ids:
        # exclude_ids should be a list of strings (pncp_ids)
        placeholders = ','.join(['%s'] * len(exclude_ids))
        base_where += f" AND l.pncp_id NOT IN ({placeholders})"
        base_params.extend(exclude_ids)
    
    if uf:
        base_where += " AND l.uf = %s"
        base_params.append(uf)

    if segmento:
        base_where += " AND l.segment_id = %s"
        base_params.append(segmento)
        
    if q:
        # Use pncp_id instead of id, and ensure objeto exists
        base_where += " AND (l.pncp_id ILIKE %s OR l.objeto ILIKE %s OR l.municipio ILIKE %s)"
        base_params.extend([f"%%{q}%%", f"%%{q}%%", f"%%{q}%%"])

    # 3. Facet Calculation (Over Base set, independent of 'quick' filter)
    # UNIFIED LOGIC: Match counters endpoint exactly
    facet_q = f"""
        SELECT 
            COUNT(CASE WHEN (l.status IS NULL OR l.status != 'IGNORED') 
                        AND DATE(l.first_seen_at) = CURRENT_DATE THEN 1 END) as added_today,
            COUNT(CASE WHEN (l.status IS NULL OR l.status != 'IGNORED')
                        AND l.situacao_nome = 'Divulgada no PNCP'
                        AND l.deadline_at IS NOT NULL
                        AND l.deadline_at >= CURRENT_TIMESTAMP
                        AND l.deadline_at < (CURRENT_TIMESTAMP + interval '7 days') THEN 1 END) as deadline_near,
            COUNT(CASE WHEN l.status = 'IGNORED' THEN 1 END) as ignored
        FROM licitacoes l
        {base_where}
    """
    c.execute(facet_q, base_params)
    facets = dict(c.fetchone())

    # 4. List Logic (Apply Quick Filter on top of Base)
    list_where = base_where
    list_params = list(base_params)

    if quick == 'added_today':
        list_where += """ AND (l.status IS NULL OR l.status != 'IGNORED') 
                          AND DATE(l.first_seen_at) = CURRENT_DATE"""
    elif quick == 'deadline_near':
        # UNIFIED LOGIC: Exact same as counters due_soon
        list_where += """ AND (l.status IS NULL OR l.status != 'IGNORED')
                          AND l.situacao_nome = 'Divulgada no PNCP'
                          AND l.deadline_at IS NOT NULL
                          AND l.deadline_at >= CURRENT_TIMESTAMP
                          AND l.deadline_at < (CURRENT_TIMESTAMP + interval '7 days')"""
    elif quick == 'ignored':
        list_where += " AND l.status = 'IGNORED'"
    else:
        # Default view: Only non-ignored
        list_where += " AND (l.status IS NULL OR l.status != 'IGNORED')"

    # Total count for the CURRENT view
    count_q = f"SELECT COUNT(*) as count FROM licitacoes l {list_where}"
    c.execute(count_q, list_params)
    total = c.fetchone()['count']

    # items query
    offset = (page - 1) * per_page
    items_q = f"""
        SELECT l.*, l.status as workflow_status 
        FROM licitacoes l 
        {list_where} 
        ORDER BY l.first_seen_at DESC, l.pncp_id DESC 
        LIMIT %s OFFSET %s
    """
    list_params.extend([per_page, offset])
    c.execute(items_q, list_params)
    
    items = []
    for row in c.fetchall():
        item = dict(row)
        normalize_for_ui(item, conn=conn)
        items.append(item)
    
    # Debug Logic
    meta = None
    if debug:
        # Check uniqueness in reported items
        ids = [i.get('pncp_id') for i in items]
        unique_ids = len(set(ids))
        
        # Check canonical keys
        canonical_keys = [f"{i.get('orgao_cnpj')}-{i.get('ano')}-{i.get('sequencial')}" for i in items]
        unique_canonical = len(set(canonical_keys))
        
        meta = {
            "rows": len(items),
            "unique_ids": unique_ids,
            "unique_canonical_keys": unique_canonical,
            "duplicate_ids": [id for id in ids if ids.count(id) > 1][:20], # simple list of dupes
            "query_explained": list_where,
            "params": [str(p) for p in list_params]
        }
    
    conn.close()
    return items, total, facets, meta

def update_workflow_status(pncp_id, workspace_id, status):
    """UPSERT workflow status for a bidding for a specific workspace."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO licitacao_workflow (pncp_id, workspace_id, status, updated_at)
        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT(pncp_id, workspace_id) DO UPDATE SET
            status = excluded.status,
            updated_at = CURRENT_TIMESTAMP
    """, (pncp_id, workspace_id, status))
    conn.commit()
    conn.close()

def get_sidebar_stats():
    """Retrieve counts for sidebar filters matching Settle benchmark (Updated)."""
    conn = get_db_connection()
    c = conn.cursor()
    
    # We now fetch facets through the search logic mostly, but keeping this for generic dashboard overview
    # 1. Segment Counts (Only ACTIVE items)
    stats = {
        "segments": {},
        "workflow": {
            "added_today": 0,
            "deadline_near": 0,
            "ignored": 0
        }
    }
    
    # Segment counts for items that are ACTIVE
    c.execute("""
        SELECT l.segment_id, COUNT(*) 
        FROM licitacoes l 
        LEFT JOIN licitacao_workflow w ON w.pncp_id = l.id
        WHERE COALESCE(w.status, 'ACTIVE') = 'ACTIVE'
        GROUP BY l.segment_id
    """)
    for row in c.fetchall():
        stats["segments"][row['segment_id']] = row['count']
        
    # Quick filter counts
    counts_q = """
        SELECT 
            COUNT(CASE WHEN COALESCE(w.status, 'ACTIVE') = 'ACTIVE' AND DATE(COALESCE(l.first_seen_at, l.data_publicacao)) = CURRENT_DATE THEN 1 END) as added_today,
            COUNT(CASE WHEN COALESCE(w.status, 'ACTIVE') = 'ACTIVE' AND DATE(COALESCE(l.deadline_at, l.data_encerramento)) BETWEEN CURRENT_DATE AND (CURRENT_DATE + interval '7 days') THEN 1 END) as deadline_near,
            COUNT(CASE WHEN COALESCE(w.status, 'ACTIVE') = 'IGNORED' THEN 1 END) as ignored
        FROM licitacoes l
        -- NOTE: For this generic dashboard view, we might need organization_id passed in the future.
        -- For now, this is a legacy function. The actual sidebar counts use `get_sidebar_counts`.
        LEFT JOIN licitacao_workflow w ON w.pncp_id = l.id
    """
    c.execute(counts_q)
    res = c.fetchone()
    stats["workflow"]["added_today"] = res['added_today']
    stats["workflow"]["deadline_near"] = res['deadline_near']
    stats["workflow"]["ignored"] = res['ignored']
    
    conn.close()
    return stats

def normalize_valor_estimado_centavos(pub_payload, detail_payload=None) -> Optional[int]:
    """
    Robustly extract and normalize contract value to centavos (integer).
    Prioritizes detail payload over publication payload.
    Discards values that look like dates or are invalid.
    """
    val = None
    
    # Priority 1: Detail Payload
    if detail_payload and isinstance(detail_payload, dict):
        val = detail_payload.get('valorTotalEstimado')
        
    # Priority 2: Publication Payload
    if val is None and pub_payload and isinstance(pub_payload, dict):
        val = pub_payload.get('valorTotalEstimado')
        
    if val is None:
        return None
        
    # Check for corruption (e.g. date strings containing 'T' or '-')
    str_val = str(val)
    if 'T' in str_val or (str_val.count('-') >= 2 and len(str_val) > 8):
        # Looks like a date string (ISO or YYYY-MM-DD)
        return None

    try:
        # Convert to float first to handle string decimals
        f_val = float(val)
        if f_val < 0: return None
        return int(round(f_val * 100))
    except (ValueError, TypeError):
        return None

SEED_MODALIDADES = {
    6:  {"key": "PREGAO",            "label": "Pregão"},
    7:  {"key": "PREGAO",            "label": "Pregão"},
    4:  {"key": "CONCORRENCIA",      "label": "Concorrência"},
    5:  {"key": "CONCORRENCIA",      "label": "Concorrência"},
    9:  {"key": "INEXIGIBILIDADE",   "label": "Inexigibilidade"},
    8:  {"key": "DISPENSA",          "label": "Dispensa"},
    12: {"key": "CREDENCIAMENTO",    "label": "Credenciamento"},
    1:  {"key": "LEILAO",            "label": "Leilão"},
    11: {"key": "QUALIFICACAO",      "label": "Pré-qualificação"}
}

def build_base_where(
    q=None,
    valor_min=None, valor_max=None,
    pub_from=None, pub_to=None,
    prazo_from=None, prazo_to=None,
    expira_em_dias=None,
    capag=None,
    uf=None,
    status_filter='active', # 'active', 'ignored', 'all'
    modalidades=None, # list of keys like ['PREGAO_ELETRONICO', 'OUTRAS']
    organization_id: Optional[str] = None,
    workspace_id: Optional[str] = None
):
    """
    Constructs the common WHERE clause and params for both search and counts.
    status_filter:
      - 'active': only non-ignored items (default)
      - 'ignored': only ignored items
      - 'all': both (for counters)
    """
    # Base Query
    base_query = """
    FROM contratacoes c
    LEFT JOIN orgaos o ON c.orgao_id = o.id
    """
    params = []
    
    ws_id = workspace_id or organization_id  # backward compat
    if ws_id:
        base_query += " LEFT JOIN licitacao_workflow w ON c.pncp_id = w.pncp_id AND w.workspace_id = %s"
        params.append(ws_id)
    else:
        # Fallback if no workspace is passed
        base_query += " LEFT JOIN licitacao_workflow w ON c.pncp_id = w.pncp_id AND w.workspace_id = 'NONE'"
        
    base_query += " WHERE c.is_valid IS TRUE "
    if ws_id:
        base_query += " AND c.workspace_id = %s"
        params.append(ws_id)
    
    # Status Filter
    if status_filter == 'active':
        base_query += " AND (COALESCE(w.status, 'ACTIVE') != 'IGNORED')"
    elif status_filter == 'ignored':
        base_query += " AND COALESCE(w.status, 'ACTIVE') = 'IGNORED'"
    # else 'all': no status filter applied here
    
    # --- FILTERS ---
    
    # 1. Full Text Search
    if q:
        base_query += " AND (c.pncp_id ILIKE %s OR c.objeto ILIKE %s OR c.orgao_nome ILIKE %s)"
        wildcard_q = f"%%{q}%%"
        params.extend([wildcard_q, wildcard_q, wildcard_q])
        
    # 2. Valor
    if valor_min is not None:
        base_query += " AND c.valor_estimado_centavos >= %s"
        params.append(int(valor_min * 100))
        
    if valor_max is not None:
        base_query += " AND c.valor_estimado_centavos <= %s"
        params.append(int(valor_max * 100))
        
    # 3. Dates (Publicacao)
    # Using Postgres DATE cast
    if pub_from:
        base_query += " AND DATE(c.data_publicacao) >= %s"
        params.append(pub_from)
        
    if pub_to:
        base_query += " AND DATE(c.data_publicacao) <= %s"
        params.append(pub_to)
        
    # 4. Deadlines
    if prazo_from:
        base_query += " AND DATE(c.deadline_at) >= %s"
        params.append(prazo_from)
        
    if prazo_to:
        base_query += " AND DATE(c.deadline_at) <= %s"
        params.append(prazo_to)
        
    # 5. Expiring soon
    if expira_em_dias is not None:
        base_query += """
            AND c.deadline_at IS NOT NULL 
            AND DATE(c.deadline_at) BETWEEN CURRENT_DATE AND (CURRENT_DATE + CAST(%s AS interval))
        """
        params.append(f"{expira_em_dias} days")
        
    # 6. CAPAG
    if capag:
        if capag == 'X': 
             base_query += " AND o.capag_nota IS NULL"
        else:
             base_query += " AND o.capag_nota = %s"
             params.append(capag)
 
    # 7. UF
    if uf:
        base_query += " AND (c.uf = %s OR o.uf = %s)"
        params.extend([uf, uf])
        
    # 8. Modalidades
    if modalidades:
        # Resolve 'OUTRAS'
        include_outras = 'OUTRAS' in modalidades
        
        # Build IN clause with matching codes
        seed_codes_in_request = []
        all_seed_codes = list(SEED_MODALIDADES.keys())
        for code, info in SEED_MODALIDADES.items():
            if info["key"] in modalidades:
                seed_codes_in_request.append(code)
                
        or_clauses = []
        if seed_codes_in_request:
            placeholders = ','.join(['%s'] * len(seed_codes_in_request))
            or_clauses.append(f"c.modalidade_codigo IN ({placeholders})")
            params.extend(seed_codes_in_request)
            
        if include_outras:
            or_clauses.append(f"(c.modalidade_codigo IS NULL OR c.modalidade_codigo NOT IN ({','.join(['%s'] * len(all_seed_codes))}))")
            params.extend(all_seed_codes)
            
        if or_clauses:
            base_query += f" AND ({' OR '.join(or_clauses)})"
            
    return base_query, params

def get_sidebar_counts(
    q=None,
    valor_min=None, valor_max=None,
    pub_from=None, pub_to=None,
    prazo_from=None, prazo_to=None,
    expira_em_dias=None,
    capag=None,
    uf=None,
    modalidades=None,
    segmento=None,
    status=None,
    organization_id: Optional[str] = None,
    workspace_id: Optional[str] = None
):
    """
    Returns counts for all segments and 'ignored' bucket dynamically based on search filters.
    Uses 'all' status filter to scan the whole relevant universe.
    """
    conn = get_db_connection()
    c = conn.cursor()
    
    # Build base queries
    # base_query_context: Respects search context filters (q, valor, dates, capag, uf) 
    #   but ignores Segmento/Modalidade/Status for independent lists faceting.
    # base_query_faceted_mods: Respects context + Segmento/Status (the "current scope")
    #   but ignores modalities filter for faceting modalities list.
    # base_query_full: Respects EVERY filter applied (including Segmento, Modalidade, Status).
    
    status_mode = 'ignored' if status == 'ignored' else 'active'
    
    # 0. The search context (global search params)
    base_context, params_context = build_base_where(
        q, valor_min, valor_max, pub_from, pub_to, 
        prazo_from, prazo_to, expira_em_dias, capag, uf,
        status_filter='all', modalidades=None, workspace_id=workspace_id or organization_id
    )
    
    # 1. Fetch active segment mapping (slug -> id)
    c.execute("SELECT id, slug, name FROM segments WHERE is_active IS TRUE")
    segments_config = c.fetchall()
    slug_to_id = {row['slug']: row['id'] for row in segments_config}
    id_to_slug = {row['id']: row['slug'] for row in segments_config}

    # 2. Determine the "Effective Segment Filter" (The Gate)
    # This reflects what the search list actually shows.
    effective_segments_slugs = None
    if status == 'ignored':
        pass # Ignored tab has no gate
    elif segmento:
        effective_segments_slugs = segmento
    else:
        # Default Gate: only classified segments
        effective_segments_slugs = ('diversos', 'kit_escolar', 'almoxarifado_virtual')

    def apply_effective_gate(q_str, q_params):
        if effective_segments_slugs:
            # Map slugs to IDs
            gate_ids = [slug_to_id[s] for s in effective_segments_slugs if s in slug_to_id]
            if not gate_ids:
                # If no mapping found, use a impossible condition to return empty results
                q_str += " AND 1=0"
                return q_str, q_params
                
            placeholders = ','.join(['%s'] * len(gate_ids))
            q_str += f" AND c.segment_id IN ({placeholders})"
            q_params = list(q_params) + list(gate_ids)
        return q_str, q_params

    # 2. Base for Segment Counts (ignores current segment, but respects search context + status)
    # We use status_mode to filter segments list correctly (active or ignored)
    base_for_segments, params_for_segments = build_base_where(
        q, valor_min, valor_max, pub_from, pub_to, 
        prazo_from, prazo_to, expira_em_dias, capag, uf,
        status_filter=status_mode, modalidades=modalidades, workspace_id=workspace_id or organization_id
    )
    
    # 3. Base for Total / Result Specific counts (Respects effective gate + modalities)
    base_full, params_full = build_base_where(
        q, valor_min, valor_max, pub_from, pub_to, 
        prazo_from, prazo_to, expira_em_dias, capag, uf,
        status_filter=status_mode, modalidades=modalidades, workspace_id=workspace_id or organization_id
    )
    base_full, params_full = apply_effective_gate(base_full, params_full)
    
    # 4. Base for Modalities List (Respects effective gate, BUT ignores modalities filter itself)
    base_faceted_mods, params_faceted_mods = build_base_where(
        q, valor_min, valor_max, pub_from, pub_to, 
        prazo_from, prazo_to, expira_em_dias, capag, uf,
        status_filter=status_mode, modalidades=None, organization_id=organization_id, workspace_id=workspace_id or organization_id
    )
    base_faceted_mods, params_faceted_mods = apply_effective_gate(base_faceted_mods, params_faceted_mods)
    
    # slug_map is already used for stats, utilizing our id_to_slug map for counting
    slug_map = {row['slug']: {'id': row['id'], 'slug': row['slug'], 'name': row['name'], 'count': 0} for row in segments_config}

    # 2. Count Active Items Grouped by Segment
    sql_segments = f"""
        SELECT c.segment_id, COUNT(*) as qty
        {base_for_segments}
          AND c.segment_id IS NOT NULL 
          AND c.segment_id != 'unclassified'
        GROUP BY c.segment_id
    """
    c.execute(sql_segments, params_for_segments)
    for row in c.fetchall():
        seg_id = row['segment_id']
        if seg_id in slug_map:
            slug_map[seg_id]['count'] = row['qty']

    # 3. Unclassified count (Respects Search Context + Current Status)

    # 3. Unclassified count (Respects Search Context + Current Status)
    sql_unclass = f"""
        SELECT COUNT(*) as qty 
        {base_for_segments}
          AND (c.segment_id IS NULL OR c.segment_id = 'unclassified')
    """
    unclassified_count = c.execute(sql_unclass, params_for_segments).fetchone()['qty']

    # 4. Ignored count (Global Search Context)
    sql_ignored = f"""
        SELECT COUNT(*) as qty 
        {base_context} AND COALESCE(w.status, 'ACTIVE') = 'IGNORED'
    """
    ignored_count = c.execute(sql_ignored, params_context).fetchone()['qty']

    # 5. Total (FULL match with main results list)
    sql_total = f"SELECT COUNT(*) as qty {base_full}"
    total_count = c.execute(sql_total, params_full).fetchone()['qty']

    # 6. Modalidades count (Faceted by current scope)
    sql_modalidades = f"""
        SELECT c.modalidade_codigo, COUNT(*) as qty
        {base_faceted_mods}
        GROUP BY c.modalidade_codigo
    """
    c.execute(sql_modalidades, params_faceted_mods)
    
    # Initialize mapped modalities to 0
    modalidades_res = []
    modalidades_map = {info["key"]: {"key": info["key"], "label": info["label"], "count": 0} for code, info in SEED_MODALIDADES.items()}
    outras_count = 0
    
    for row in c.fetchall():
        mod_code = row['modalidade_codigo']
        qty = row['qty']
        if mod_code in SEED_MODALIDADES:
            key = SEED_MODALIDADES[mod_code]["key"]
            modalidades_map[key]["count"] += qty
        else:
            outras_count += qty
            
    for key, data in modalidades_map.items():
        modalidades_res.append(data)
        
    modalidades_res.append({"key": "OUTRAS", "label": "Outras (não mapeadas)", "count": outras_count})

    from datetime import datetime, timezone
    as_of = datetime.now(timezone.utc).isoformat()
    
    conn.close()

    return {
        "segments": list(slug_map.values()),
        "sem_classificacao": unclassified_count,
        "ignoradas": ignored_count,
        "modalidades": modalidades_res,
        "total": total_count,
        "as_of": as_of
    }

def get_modalidades_info(workspace_id: Optional[str] = None, organization_id: Optional[str] = None):
    """Returns exact modalities metadata format for the /modalidades endpoint."""
    conn = get_db_connection()
    c = conn.cursor()
    
    ws_id = workspace_id or organization_id
    if ws_id:
        c.execute("SELECT modalidade_codigo, modalidade_nome, count(*) as count FROM contratacoes WHERE workspace_id = %s GROUP BY 1, 2", (ws_id,))
    else:
        c.execute("SELECT modalidade_codigo, modalidade_nome, count(*) as count FROM contratacoes GROUP BY 1, 2")
        
    rows = c.fetchall()
    conn.close()
    
    items = []
    items_map = {}
    
    # Initialize keys
    for code, info in SEED_MODALIDADES.items():
         if info["key"] not in items_map:
             items_map[info["key"]] = {"key": info["key"], "label": info["label"], "codes": [], "count": 0}
         items_map[info["key"]]["codes"].append(code)
         
    unknown_by_code = []
    unknown_by_name = []
    unknown_examples_raw = []
    unknown_total = 0
    
    for r in rows:
        code = r[0]
        name = r[1]
        count = r[2]
        
        if code in SEED_MODALIDADES:
            key = SEED_MODALIDADES[code]["key"]
            items_map[key]["count"] += count
        elif code is not None: # code but not mapped
            unknown_by_code.append({"code": code, "label": f"{name or 'Código'} (não mapeado)", "count": count})
            unknown_total += count
            unknown_examples_raw.append({"codigo": code, "nome": name})
        else: # no code
            unknown_by_name.append({"name": name or "Desconhecido", "count": count})
            unknown_total += count
            unknown_examples_raw.append({"codigo": code, "nome": name})
            
    items = list(items_map.values())
            
    # fetch a few quick examples
    examples = []
    if unknown_total > 0:
        c2 = get_db_connection().cursor()
        for idx, ex in enumerate(unknown_examples_raw[:5]): # only take up to 5 combinations to show examples
            if ws_id:
                c2.execute("SELECT pncp_id, modalidade_codigo, modalidade_nome FROM contratacoes WHERE workspace_id = %s AND modalidade_codigo IS NOT DISTINCT FROM %s AND modalidade_nome IS NOT DISTINCT FROM %s LIMIT 2", 
                           (ws_id, ex['codigo'], ex['nome']))
            else:
                c2.execute("SELECT pncp_id, modalidade_codigo, modalidade_nome FROM contratacoes WHERE modalidade_codigo IS NOT DISTINCT FROM %s AND modalidade_nome IS NOT DISTINCT FROM %s LIMIT 2", 
                           (ex['codigo'], ex['nome']))
            for row in c2.fetchall():
                 examples.append({"pncp_id": row['pncp_id'], "modalidade_codigo": row['modalidade_codigo'], "modalidade_nome": row['modalidade_nome']})
                 if len(examples) >= 5: break
            if len(examples) >= 5: break
        c2.connection.close()
        
    return {
        "items": items,
        "unknown_by_code": unknown_by_code,
        "unknown_by_name": unknown_by_name,
        "unknown_total": unknown_total,
        "examples": examples
    }

def search_licitacoes_advanced(
    q=None,
    valor_min=None, valor_max=None,
    pub_from=None, pub_to=None,
    prazo_from=None, prazo_to=None,
    expira_em_dias=None,
    capag=None,
    segmento=None,
    uf=None,
    status=None,  # 'active' (default) or 'ignored'
    pncp_id=None,
    modalidades=None,
    page=1,
    page_size=20,
    order_by='default',
    organization_id: Optional[str] = None,
    workspace_id: Optional[str] = None
):
    """
    Advanced search with server-side filtering, pagination, and sorting.
    Joins with ORGAOS table for CAPAG filtering.
    """
    import logging
    logger = logging.getLogger("api_logger")
    
    conn = get_db_connection()
    c = conn.cursor()
    
    # Determine status filter mode
    status_mode = 'active'
    if status == 'ignored':
        status_mode = 'ignored'
    
    if pncp_id:
        base_query = """
        FROM contratacoes c
        LEFT JOIN orgaos o ON c.orgao_id = o.id
        """
        params = [pncp_id]
        
        ws_id = workspace_id or organization_id
        if ws_id:
            base_query += " LEFT JOIN licitacao_workflow w ON c.pncp_id = w.pncp_id AND w.workspace_id = %s"
            params.append(ws_id)
        else:
            base_query += " LEFT JOIN licitacao_workflow w ON c.pncp_id = w.pncp_id AND w.workspace_id = 'NONE'"
            
        base_query += " WHERE c.pncp_id = %s" 
        # Note: the param list needs ['org_id', 'pncp_id'] if org_id is present, but we already appended pncp_id.
        # Let's fix the order.
        params = []
        if organization_id:
            params.append(organization_id)
        params.append(pncp_id)
        total = 1
        # Bypass segment gate
    else:
        # Build base query
        base_query, params = build_base_where(
            q, valor_min, valor_max, pub_from, pub_to, 
            prazo_from, prazo_to, expira_em_dias, capag, uf,
            status_filter=status_mode, modalidades=modalidades,
            organization_id=organization_id
        )
    
    # 1. Fetch active segment mapping (slug -> id)
    c.execute("SELECT id, slug, name FROM segments WHERE is_active IS TRUE")
    segments_config = c.fetchall()
    slug_to_id = {row['slug']: row['id'] for row in segments_config}

    if pncp_id:
        pass
    elif status_mode == 'ignored':
        pass 
    else:
        effective_slugs = segmento if segmento else ('diversos', 'kit_escolar', 'almoxarifado_virtual')
        gate_ids = [slug_to_id[s] for s in effective_slugs if s in slug_to_id]
        
        if gate_ids:
            placeholders = ','.join(['%s'] * len(gate_ids))
            base_query += f" AND c.segment_id IN ({placeholders})"
            params.extend(gate_ids)
            gate_type = 'EXPLICIT' if segmento else 'DEFAULT'
        else:
            # If no mapping found, return empty
            base_query += " AND 1=0"
            gate_type = 'EMPTY_MAPPING'
            
        logger.info(f"[SEARCH_ADV] segmento={segmento!r}, gate={gate_type}, gate_ids={gate_ids}")

    # --- COUNT TOTAL ---
    if not pncp_id:
        count_sql = f"SELECT COUNT(*) as count {base_query}"
        c.execute(count_sql, params)
        total = c.fetchone()['count']
    else:
        # total set to 1 above but let's be strict
        c.execute(f"SELECT COUNT(*) as count {base_query}", params)
        total = c.fetchone()['count']
    
    # --- ORDER BY ---
    sort_clause = "ORDER BY c.first_seen_at DESC" # Default fallback
    
    if order_by == 'valor_desc':
        sort_clause = "ORDER BY c.valor_estimado_centavos DESC NULLS LAST"
    elif order_by == 'created_desc' or order_by == 'default':
        sort_clause = "ORDER BY c.first_seen_at DESC"
    elif order_by == 'prazo_asc':
        # NULLS LAST important for deadlines
        sort_clause = "ORDER BY c.deadline_at ASC NULLS LAST"
        
    # --- PAGINATION ---
    limit = page_size
    offset = (page - 1) * page_size
    
    # --- FETCH ITEMS ---
    # We fetch all fields from c, plus capag info from o
    select_sql = f"""
        SELECT c.*, o.capag_nota, o.capag_fonte, o.capag_atualizada_em
        {base_query}
        {sort_clause}
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    
    c.execute(select_sql, params)
    items = []
    for row in c.fetchall():
        item = dict(row)
        # Normalize for Frontend
        normalize_for_ui(item) # uses existing helper
        # Add CAPAG info explicitly if normalize doesn't handle it (it doesn't yet)
        if 'capag_nota' in item:
             if 'comprador' not in item: item['comprador'] = {}
             item['comprador']['capag'] = {
                 'nota': item['capag_nota'],
                 'fonte': item['capag_fonte'],
                 'atualizado_em': item['capag_atualizada_em']
             }
        items.append(item)
        
    conn.close()
    
    meta = {
        "sql_debug": select_sql, # remove in prod?
        "total": total
    }
    
    return items, total, meta

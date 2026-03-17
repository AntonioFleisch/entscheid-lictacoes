from app.db.session import get_db_connection
import logging
import json
import time
import os
import requests
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from app.services.segmentation.classifier import DeterministicClassifier, fetch_frozen_rules, finalize_contract_segment_frozen
from app.services.pncp.utils import build_pncp_edital_url, normalize_valor_estimado_centavos

# Logger Configuration
logger = logging.getLogger("pncp_ingest_job")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Constants
PNCP_BASE_URL = "https://pncp.gov.br/api/consulta/v1"
PNCP_ITEM_BASE = "https://pncp.gov.br/api/pncp/v1"


class PNCPIngestJob:
    def __init__(self):
        self._init_db()

    def _init_db(self):
        """Ensure WAL mode and basic settings."""
        conn = self._get_conn()
        try:
            
            
            
            # Resolve Default Org and its Workspace
            default_slug = os.environ.get("DEFAULT_ORG_SLUG", "default")
            cur = conn.execute("""
                SELECT o.id as org_id, w.id as ws_id 
                FROM organizations o
                LEFT JOIN workspaces w ON w.organization_id = o.id AND w.type = 'organization'
                WHERE o.slug = %s
            """, (default_slug,))
            row = cur.fetchone()
            if row:
                self.default_org_id = row['org_id']
                self.default_workspace_id = row['ws_id']
                logger.info(f"Resolved default org '{default_slug}' (ID: {self.default_org_id}) with workspace {self.default_workspace_id}")
            else:
                self.default_org_id = None
                self.default_workspace_id = None
                logger.warning(f"Default organization '{default_slug}' or its workspace not found. Records will have NULL IDs.")
        finally:
            conn.close()

    def _get_conn(self):
        """Get a PostgreSQL connection from the pool."""
        conn = get_db_connection()
        
        return conn

    # --- LOCKING ---
    def acquire_lock(self, job_name: str, ttl_minutes: int = 30) -> bool:
        """Atomic lock acquisition."""
        conn = self._get_conn()
        try:
            now = datetime.now()
            locked_until = (now + timedelta(minutes=ttl_minutes)).strftime('%Y-%m-%d %H:%M:%S')
            current_time = now.strftime('%Y-%m-%d %H:%M:%S')

            # Try to insert or update ONLY if expired
            cursor = conn.execute("""
                INSERT INTO job_locks (job_name, locked_until, locked_at, locked_by)
                VALUES (%s, %s, %s, 'pncp_ingest_job')
                ON CONFLICT(job_name) DO UPDATE SET
                    locked_until = excluded.locked_until,
                    locked_at = excluded.locked_at
                WHERE job_locks.locked_until < %s
            """, (job_name, locked_until, current_time, current_time))
            
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Lock error: {e}")
            return False
        finally:
            conn.close()

    def release_lock(self, job_name: str):
        conn = self._get_conn()
        try:
            conn.execute("UPDATE job_locks SET locked_until = '1970-01-01 00:00:00' WHERE job_name = %s", (job_name,))
            conn.commit()
        finally:
            conn.close()

    # --- UTILS ---
    def _calculate_hash(self, payload: Dict[str, Any]) -> str:
        s = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(s.encode()).hexdigest()


    def _generate_pncp_deeplink(self, cnpj, ano, seq) -> Optional[str]:
        """Generate deterministic deep link based on user-provided pattern."""
        if not (cnpj and ano and seq):
            return None
        try:
            # cnpj: maintain 14 digits (numeric only)
            clean_cnpj = "".join(filter(str.isdigit, str(cnpj)))
            if len(clean_cnpj) != 14:
                return None
            
            # ano: 4 digits
            clean_ano = str(ano).strip()
            if len(clean_ano) != 4:
                return None
            
            # sequencial: numeric (remove leading zeros)
            clean_seq = str(seq).lstrip('0') or '0'
            
            return f"https://pncp.gov.br/app/editais-{clean_cnpj}-{clean_ano}-{clean_seq}"
        except:
            return None

    def _validate_link(self, url: str) -> Tuple[bool, int, Optional[str]]:
        """Perform a quick HEAD/GET request to validate the link."""
        try:
            # We use a short timeout as requested
            r = requests.head(url, timeout=5, allow_redirects=True)
            status = r.status_code
            if 200 <= status < 400:
                return True, status, None
            
            # Some servers block HEAD, try GET as fallback
            if status == 405:
                r = requests.get(url, timeout=5, stream=True)
                status = r.status_code
                if 200 <= status < 400:
                    return True, status, None
                    
            return False, status, f"HTTP {status}"
        except Exception as e:
            return False, 0, str(e)

    def _extract_structural_fields(self, payload: Dict, pncp_id: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Safely extract CNPJ, Ano, Seq from payload or pncp_id."""
        cnpj = None
        ano = None
        seq = None
        
        # 1. Try payload
        oe = payload.get('orgaoEntidade')
        if isinstance(oe, str):
            try: oe = json.loads(oe) # Handle stringified dicts
            except: oe = {}
        
        if isinstance(oe, dict):
            cnpj = oe.get('cnpj')
            
        ano = payload.get('anoCompra') or payload.get('ano') or payload.get('anoContratacao')
        seq = payload.get('sequencialCompra') or payload.get('sequencial') or payload.get('numeroContratacao')
        
        # 2. Fallback from pncp_id
        if not (cnpj and ano and seq):
            try:
                # Format: CNPJ-1-SEQ/ANO
                parts = pncp_id.split('-')
                if len(parts) >= 3:
                    if not cnpj: cnpj = parts[0]
                    last_parts = parts[-1].split('/')
                    if len(last_parts) == 2:
                        if not seq: seq = last_parts[0]
                        if not ano: ano = last_parts[1]
            except: pass
            
        return cnpj, ano, seq

    # --- PHASE A: DISCOVERY ---
    def run_discovery(self, data_inicial: str, data_final: str, page_size: int = 50, max_pages: int = 100) -> Dict[str, Any]:
        stats = {"pages": 0, "items": 0, "inserted": 0, "updated": 0, "errors": 0}
        new_or_updated_ids: List[str] = []
        
        # 1. Fetch Modalities
        modalities = self._fetch_modalities()
        logger.info(f"Phase A: Starting discovery for {len(modalities)} modalities in window {data_inicial}-{data_final}")

        # Fetch Frozen Rules for Classifier
        conn = self._get_conn()
        try:
            if self.default_org_id:
                frozen_rules = fetch_frozen_rules(conn, self.default_org_id)
            else:
                frozen_rules = []
            classifier = DeterministicClassifier(frozen_rules)
        finally:
            conn.close()

        for mod in modalities:
            mod_code = mod['id']
            # Loop pages
            for page in range(1, max_pages + 1):
                params = {
                    "dataInicial": data_inicial,
                    "dataFinal": data_final,
                    "codigoModalidadeContratacao": mod_code,
                    "pagina": page,
                    "tamanhoPagina": page_size
                }
                
                try:
                    data = self._fetch_publicacao_page(params)
                    items = data.get('data', [])
                    if not items:
                        break # End of pagination for this modality
                    
                    stats["pages"] += 1
                    stats["items"] += len(items)
                    
                    batch_changed = self._persist_phase_a_batch(items, data_inicial, data_final, mod_code, classifier)
                    new_or_updated_ids.extend(batch_changed)
                    stats["inserted"] += len(batch_changed)
                    
                    # Check if last page
                    if page >= data.get('totalPaginas', 0):
                        break
                        
                    # Politeness sleep
                    time.sleep(0.2)
                    
                except Exception as e:
                    logger.error(f"Phase A Error (Mod {mod_code} Page {page}): {e}")
                    stats["errors"] += 1
                    break 

        stats["new_or_updated_ids"] = new_or_updated_ids
        return stats

    def _fetch_modalities(self) -> List[Dict]:
        """Fetch modalities or use fallback."""
        try:
            r = requests.get(f"{PNCP_BASE_URL}/dominios/modalidade-contratacao", timeout=10)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            logger.warning(f"Failed to fetch modalities: {e}")
        
        # Fallback list (Common ones)
        return [{"id": i} for i in range(1, 15)] # 1-14

    def _fetch_publicacao_page(self, params: Dict) -> Dict:
        url = f"{PNCP_BASE_URL}/contratacoes/publicacao"
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def _persist_phase_a_batch(self, items: List[Dict], start: str, end: str, mod_code: int, classifier: DeterministicClassifier) -> List[str]:
        """Upsert a batch and return list of pncp_ids that are new or hash-changed."""
        conn = self._get_conn()
        changed_ids: List[str] = []
        try:
            for item in items:
                pncp_id = item.get('numeroControlePNCP')
                if not pncp_id: continue
                
                payload_hash = self._calculate_hash(item)
                
                # 1. Staging Publicacao (Audit)
                conn.execute("""
                    INSERT INTO staging_publicacao 
                    (window_start, window_end, modalidade_code, pncp_id, payload_hash, payload_json, status)
                    VALUES (%s, %s, %s, %s, %s, %s, 'NEW')
                """, (start, end, mod_code, pncp_id, payload_hash, json.dumps(item)))

                # 2. Upsert Contratacoes (Minimal)
                # Parse Structural Fields for later Enrichment
                orgao_cnpj = item.get('orgaoEntidade', {}).get('cnpj')
                ano = item.get('anoContratacao')
                sequencial = item.get('numeroContratacao') # Often varies, check swagger mapping
                # Fallback struct parsing from pncp_id if needed
                if not (orgao_cnpj and ano and sequencial) and '-' in pncp_id:
                     # ID format: CNPJ-1-SEQ/ANO
                     try:
                        parts = pncp_id.split('-')
                        if len(parts) >= 3:
                             p_cnpj = parts[0]
                             p_rest = parts[-1].split('/')
                             if len(p_rest) == 2:
                                 if not orgao_cnpj: orgao_cnpj = p_cnpj
                                 if not sequencial: sequencial = p_rest[0]
                                 if not ano: ano = p_rest[1]
                     except: pass

                # Determine if hash changed to reset enrichment
                # Check existing hash
                cur = conn.execute("SELECT payload_publicacao_hash FROM contratacoes WHERE pncp_id = %s", (pncp_id,))
                existing = cur.fetchone()
                
                enrich_cols = ""
                enrich_vals_placeholder = ""
                enrich_update = ""
                
                if not existing or existing[0] != payload_hash:
                    # New version -> Reset Enrichment
                    enrich_cols = ", enrichment_status, enrichment_attempts"
                    enrich_vals_placeholder = ", 'PENDING', 0"
                    enrich_update = ", enrichment_status = 'PENDING', enrichment_attempts = 0"
                
                # Canonical URL generation (Phase A)
                canonical_url = build_pncp_edital_url(pncp_id, orgao_cnpj, ano, sequencial)
                
                # Extract Deadline (Phase A)
                deadline_at = None
                deadline_source = None
                deadline_raw = None
                
                # Check listing keys (Prompt B fallback)
                candidates_a = [
                    ('dataEncerramentoProposta', item.get('dataEncerramentoProposta')),
                    ('dataFimRecebimentoPropostas', item.get('dataFimRecebimentoPropostas')),
                    ('dataEncerramento', item.get('dataEncerramento')),
                    ('dataAberturaPropostas', item.get('dataAberturaPropostas')),
                ]
                for key, v in candidates_a:
                    if v:
                        deadline_at = v
                        deadline_source = f"listing_{key}"
                        deadline_raw = str(v)
                        break
                
                # Base Fields Upsert
                # NOTE: We update last_seen_at here. Phase B does NOT update it.
                sql = f"""
                    INSERT INTO contratacoes (
                        pncp_id, orgao_cnpj, ano, sequencial,
                        orgao_nome, modalidade_codigo, modalidade_nome,
                        objeto, situacao_nome, data_publicacao,
                        uf, municipio, valor_estimado_centavos,
                        payload_publicacao_hash, payload_publicacao_json,
                        last_seen_at, url_pncp_detalhe, url_pncp_source, url_pncp_checked_at,
                        deadline_at, deadline_source, deadline_raw,
                        organization_id, workspace_id
                        {enrich_cols}
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s, 'PHASE_A_DISCOVERY', CURRENT_TIMESTAMP, %s, %s, %s, %s, %s {enrich_vals_placeholder})
                    ON CONFLICT(pncp_id) DO UPDATE SET
                        last_seen_at = CURRENT_TIMESTAMP,
                        payload_publicacao_hash = excluded.payload_publicacao_hash,
                        payload_publicacao_json = excluded.payload_publicacao_json,
                        url_pncp_detalhe = COALESCE(excluded.url_pncp_detalhe, contratacoes.url_pncp_detalhe),
                        deadline_at = COALESCE(contratacoes.deadline_at, excluded.deadline_at),
                        deadline_source = COALESCE(contratacoes.deadline_source, excluded.deadline_source),
                        deadline_raw = COALESCE(contratacoes.deadline_raw, excluded.deadline_raw)
                        {enrich_update}
                """
                
                vals = [
                    pncp_id, orgao_cnpj, ano, sequencial,
                    item.get('orgaoEntidade', {}).get('razaoSocial'), 
                    item.get('modalidadeContratacaoInstituida', {}).get('id'),
                    item.get('modalidadeContratacaoInstituida', {}).get('nome'),
                    item.get('objetoCompra'), # Fallback objeto
                    item.get('situacaoCompra', {}).get('nome'),
                    item.get('dataPublicacaoPncp'),
                    item.get('unidadeOrgao', {}).get('ufSigla'), # Note: API struct varies
                    item.get('unidadeOrgao', {}).get('municipioNome'),
                    normalize_valor_estimado_centavos(item),
                    payload_hash, json.dumps(item),
                    canonical_url,
                    deadline_at, deadline_source, deadline_raw,
                    self.default_org_id, self.default_workspace_id
                ]
                
                conn.execute(sql, vals)

                # Track changed record if it was new or payload hash changed
                if not existing or existing[0] != payload_hash:
                    # Also skip if itens and arquivos are already COMPLETED (nothing to enrich)
                    check = conn.execute(
                        "SELECT itens_status, arquivos_status FROM contratacoes WHERE pncp_id=%s",
                        (pncp_id,)
                    ).fetchone()
                    needs_enrich = (
                        not check or
                        check[0] in (None, 'NOT_FETCHED', 'FAILED_TEMP') or
                        check[1] in (None, 'NOT_FETCHED', 'FAILED_TEMP')
                    )
                    if needs_enrich:
                        changed_ids.append(pncp_id)

                # 3. Handle Granular Data (Normalization)
                self._upsert_itens(conn, pncp_id, item.get('itens', []), classifier)
                self._upsert_partes(conn, pncp_id, item)

            conn.commit()
        except Exception as e:
            logger.error(f"Batch persist error: {e}")
            conn.rollback()
        finally:
            conn.close()
        return changed_ids

    def _upsert_itens(self, conn, pncp_id: str, items: List[Dict], classifier: DeterministicClassifier = None):
        """Upsert items into contratacao_itens."""
        for i in items:
            try:
                # Calculate item hash for idempotency if no ID
                item_json = json.dumps(i, sort_keys=True)
                item_hash = hashlib.sha256(item_json.encode()).hexdigest()
                
                item_id = str(i.get('numeroItem') or i.get('id') or '')
                
                v_unit = normalize_valor_estimado_centavos(i)
                v_total = normalize_valor_estimado_centavos(i) # Note: assuming the item payload has valorTotalEstimado or similar

                # Legacy Segment Info (raw PNCP codes)
                seg_cod = str(i.get('materialOuServico') or '')
                seg_nome = i.get('materialOuServicoNome') or ('Serviço' if seg_cod == 'S' else 'Material' if seg_cod == 'M' else 'Outros')

                # Rule-Based Segment Classification v3
                item_text = f"{(i.get('descricao') or '')} {i.get('materialOuServicoNome') or ''}"
                seg_id, _ = classifier.classify(item_text) 
                seg_score = 1.0 if seg_id != 'diversos' else 0.0 # simplified score for items meta
                seg_evidence = "{}" 

                conn.execute("""
                    INSERT INTO contratacao_itens (
                        pncp_id, item_id, item_hash,
                        numero_item, descricao, quantidade, unidade,
                        valor_unitario_centavos, valor_total_centavos,
                        segmento_codigo, segmento_nome,
                        segment_id, segment_score, segment_evidence,
                        payload_json, last_seen_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT(pncp_id, item_hash) DO UPDATE SET
                        last_seen_at = CURRENT_TIMESTAMP,
                        valor_unitario_centavos = excluded.valor_unitario_centavos,
                        valor_total_centavos = excluded.valor_total_centavos,
                        segmento_codigo = excluded.segmento_codigo,
                        segmento_nome = excluded.segmento_nome,
                        segment_id = excluded.segment_id,
                        segment_score = excluded.segment_score,
                        segment_evidence = excluded.segment_evidence,
                        payload_json = excluded.payload_json
                """, (
                    pncp_id, item_id, item_hash,
                    i.get('numeroItem'), i.get('descricao'), i.get('quantidade'), i.get('unidadeMedida'),
                    v_unit, v_total, 
                    seg_cod, seg_nome,
                    seg_id, seg_score, seg_evidence,
                    item_json
                ))
            except Exception as e:
                logger.warning(f"Failed to upsert item for {pncp_id}: {e}")

    def _upsert_partes(self, conn, pncp_id: str, payload: Dict):
        """Extract and upsert participants (Comprador, Entidade, etc)."""
        partes = []
        
        # Comprador
        if 'orgaoEntidade' in payload:
            oe = payload['orgaoEntidade']
            partes.append(('COMPRADOR', oe.get('cnpj'), oe.get('razaoSocial')))
            
        # Unidade
        if 'unidadeOrgao' in payload:
            uo = payload['unidadeOrgao']
            partes.append(('UNIDADE', uo.get('codigoUnidade'), uo.get('nomeUnidade')))

        for papel, cnpj, nome in partes:
            if not cnpj and not nome: continue
            try:
                conn.execute("""
                    INSERT INTO contratacao_partes (pncp_id, papel, cnpj, nome)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT(pncp_id, papel, cnpj) DO UPDATE SET
                        nome = excluded.nome
                """, (pncp_id, papel, str(cnpj or ''), nome))
            except Exception as e:
                logger.warning(f"Failed to upsert parte {papel} for {pncp_id}: {e}")

    # --- PHASE B: ENRICHMENT ---
    def run_enrichment(self, limit: int = 50, backoff_minutes: int = 30) -> Dict[str, int]:
        stats = {"processed": 0, "success": 0, "errors": 0}
        conn = self._get_conn()
        
        try:
            # 1. Select Candidates with Backoff logic
            # Explicitly selecting structural fields for endpoint construction
            cur = conn.execute(f"""
                SELECT pncp_id, orgao_cnpj, ano, sequencial, enrichment_attempts, url_pncp_detalhe
                FROM contratacoes 
                WHERE enrichment_status IN ('PENDING', 'RETRY')
                AND enrichment_attempts < 5
                AND (
                    last_enrichment_attempt IS NULL 
                    OR last_enrichment_attempt < CURRENT_TIMESTAMP - interval '%s minutes'
                )
                LIMIT %s
            """, (backoff_minutes, limit))
            candidates = cur.fetchall()
            
            # Fetch Frozen Rules for current enrichment batch
            if self.default_org_id:
                frozen_rules = fetch_frozen_rules(conn, self.default_org_id)
            else:
                frozen_rules = []
            classifier = DeterministicClassifier(frozen_rules)

            for row in candidates:
                stats["processed"] += 1
                pncp_id = row['pncp_id']
                
                # --- INDEPENDENT URL GENERATION (Phase B Fallback) ---
                current_url = row['url_pncp_detalhe']
                if not current_url or "?q=" in current_url:
                    url_val = build_pncp_edital_url(pncp_id, row['orgao_cnpj'], row['ano'], row['sequencial'])
                    if url_val:
                        conn.execute("""
                            UPDATE contratacoes 
                            SET url_pncp_detalhe = %s, url_pncp_source = 'PHASE_B_INDEPENDENT', url_pncp_checked_at = CURRENT_TIMESTAMP
                            WHERE pncp_id = %s
                        """, (url_val, pncp_id))
                
                try:
                    # Strategy: Structural -> Search Fallback
                    detail = self._fetch_detail_strategy(row)
                    
                    if detail:
                        # Success
                        self._persist_phase_b_success(conn, pncp_id, detail, classifier)
                        stats["success"] += 1
                        time.sleep(0.5) # Politeness
                    else:
                        # Fail
                        self._persist_phase_b_failure(conn, pncp_id, "Detail fetch returned empty or 404")
                        stats["errors"] += 1
                        
                except Exception as e:
                    self._persist_phase_b_failure(conn, pncp_id, str(e))
                    stats["errors"] += 1
            
            conn.commit()  # All or nothing for the batch of status updates ideally, or commit per item
            
        finally:
            conn.close()
            
        return stats

    def _fetch_detail_strategy(self, row: Dict) -> Optional[Dict]:
        """Deterministic strategy: Struct -> Search -> None"""
        
        # Strategy 1: Structural Endpoint
        # /orgaos/{cnpj}/compras/{ano}/{sequencial}
        if row['orgao_cnpj'] and row['ano'] and row['sequencial']:
            # Strip leading zeros just in case, but PNCP often accepts both. 
            # We'll try the provided one first.
            seq = row['sequencial'].lstrip('0') or '0'
            url_variants = [
                f"{PNCP_BASE_URL}/orgaos/{row['orgao_cnpj']}/compras/{row['ano']}/{row['sequencial']}",
                f"{PNCP_BASE_URL}/orgaos/{row['orgao_cnpj']}/compras/{row['ano']}/{seq}"
            ]
            
            for url in url_variants:
                try:
                    r = requests.get(url, timeout=15)
                    if r.status_code == 200:
                        return r.json()
                except Exception as e:
                    logger.warning(f"Struct URL variant failed: {url} | {e}")

        # Strategy 2: Fallback (Search by unique ID)
        # Using the contratacoes/publicacao?numeroControlePNCP filter
        try:
            search_url = f"{PNCP_BASE_URL}/contratacoes/publicacao"
            params = {"numeroControlePNCP": row['pncp_id'], "pagina": 1, "tamanhoPagina": 1}
            r = requests.get(search_url, params=params, timeout=15)
            if r.status_code == 200:
                data = r.json()
                items = data.get('data', [])
                if items:
                    # We found it via search. Note that search payload might be less complete 
                    # than detail payload, but it's a valid fallback.
                    return items[0]
        except Exception as e:
            logger.warning(f"Strategy 2 fallback failed for {row['pncp_id']}: {e}")
        
    def _fetch_itens(self, cnpj: str, ano: str, seq: str) -> List[Dict]:
        """Fetch items from the specialized PNCP items endpoint."""
        items = []
        try:
            url = f"{PNCP_ITEM_BASE}/orgaos/{cnpj}/compras/{ano}/{seq}/itens?pagina=1&tamanhoPagina=100"
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    items = data.get('data', [])
        except Exception as e:
            logger.warning(f"Failed to fetch items for {cnpj}/{ano}/{seq}: {e}")
        return items

    def _persist_phase_b_success(self, conn, pncp_id: str, detail: Dict, classifier: DeterministicClassifier):
        payload_hash = self._calculate_hash(detail)
        
        # 1. Fetch Structural Fields
        cnpj, ano, seq = self._extract_structural_fields(detail, pncp_id)
        
        # Legacy items fetch removed -> Now handled by unified Phase C
        items_payload = [] 
        
        # 2. Classification & Aggregation v3
        objeto = detail.get('objetoCompra') or ""
        item_descriptions = [str(it.get('descricao') or '') for it in items_payload]
        modalidade_nome = detail.get('modalidadeNome') or detail.get('modalidade_nome')
        
        principal_seg, segments_json = finalize_contract_segment_frozen(classifier, objeto, item_descriptions, modalidade_nome)

        sql = """
            UPDATE contratacoes SET 
                payload_detalhe_hash = %s,
                payload_detalhe_json = %s,
                objeto = %s,
                situacao_nome = %s,
                data_publicacao = %s,
                data_abertura = %s,
                data_encerramento = %s,
                deadline_at = %s,
                deadline_source = %s,
                deadline_checked_at = CURRENT_TIMESTAMP,
                valor_estimado_centavos = %s,
                uf = %s,
                municipio = %s,
                url_pncp_detalhe = %s,
                url_pncp_status_code = %s,
                url_pncp_checked_at = CURRENT_TIMESTAMP,
                url_pncp_source = %s,
                url_pncp_error = %s,
                segmento_principal = %s,
                segmentos_json = %s,
                enrichment_status = 'COMPLETED',
                enrichment_attempts = enrichment_attempts + 1,
                last_enrichment_attempt = CURRENT_TIMESTAMP
            WHERE pncp_id = %s
        """

        # Map fields from Detail Payload
        dt_pub = detail.get('dataPublicacaoPncp')
        dt_start = detail.get('dataInicioRecebimentoPropostas') or detail.get('dataAberturaPropostas')
        dt_end = detail.get('dataFimRecebimentoPropostas')
        val_centavos = normalize_valor_estimado_centavos(None, detail)

        # --- LINK GENERATION & VALIDATION ---
        final_url = build_pncp_edital_url(pncp_id, cnpj, ano, seq)
        url_source = 'CANONICAL_BUILDER' if final_url else None
        url_status = None
        url_error = None
        url_checked_at = None
        
        # Verify if generated (optional optimization, user implied trust the format, but validation is good audit)
        # For now, we trust the builder as it follows the strict canonical format.
        # User said: "não depender do sucesso da Phase B" -> implies Phase A should have done it, but here we confirm.
        
        if not final_url:
             url_error = "Could not generate canonical URL from available data"
             # NO FALLBACK to ?q= per strict requirements

        # Robust Deadline Extraction
        # 6. Extract Deadline (Phase B Enrichment) using Prompt A findings
        deadline_at = None
        deadline_source = None
        deadline_raw = None
        
        # Priority 1: dataEncerramentoProposta (Simpler, official field)
        candidates = [
            ('dataEncerramentoProposta', detail.get('dataEncerramentoProposta')),
            ('dataFimRecebimentoPropostas', detail.get('dataFimRecebimentoPropostas')),
            ('dataEncerramento', detail.get('dataEncerramento')),
            ('dataAberturaPropostas', detail.get('dataAberturaPropostas')), # Fallback to Opening
            ('dataAberturaProposta', detail.get('dataAberturaProposta'))
        ]
        
        for key, v in candidates:
            if v:
                deadline_at = v
                deadline_source = f"detail_{key}"
                deadline_raw = str(v)
                break

        if not deadline_at:
             logger.warning(f"No deadline found for {pncp_id} even after Enrichment.")
             
        sql = f"""
            UPDATE contratacoes SET 
                payload_detalhe_json = %s, 
                objeto = %s,
                url_pncp_detalhe = %s,
                url_pncp_status_code = %s,
                url_pncp_checked_at = %s,
                url_pncp_source = %s,
                url_pncp_error = %s,
                situacao_nome = %s,
                data_publicacao = %s,
                data_abertura = %s,
                data_encerramento = %s,
                deadline_at = COALESCE(%s, deadline_at),
                deadline_source = %s,
                deadline_raw = %s,
                valor_estimado_centavos = %s,
                uf = %s,
                municipio = %s,
                orgao_nome = %s,
                modalidade_nome = %s,
                last_seen_at = CURRENT_TIMESTAMP,
                segmento_principal = %s,
                segmentos_json = %s,
                enrichment_status = 'COMPLETED',
                enrichment_attempts = enrichment_attempts + 1,
                last_enrichment_attempt = CURRENT_TIMESTAMP
            WHERE pncp_id = %s
        """ 

        conn.execute(sql, (
            json.dumps(detail),
            detail.get('objetoCompra'),
            final_url, url_status, url_checked_at, url_source, url_error,
            detail.get('situacaoCompraNome') or str(detail.get('situacaoCompraId') or ''),
            dt_pub, dt_start, dt_end,
            deadline_at, deadline_source, deadline_raw,
            val_centavos,
            detail.get('unidadeOrgao', {}).get('ufSigla'),
            detail.get('unidadeOrgao', {}).get('municipioNome'),
            detail.get('unidadeOrgao', {}).get('razaoSocial'),
            detail.get('modalidadeNome'),
            principal_seg,
            segments_json,
            pncp_id
        ))

        # 3. Update Granular Data
        self._upsert_itens(conn, pncp_id, items_payload, classifier)
        self._upsert_partes(conn, pncp_id, detail)

    def _persist_phase_b_failure(self, conn, pncp_id: str, error: str):
        # Check attempts
        cur = conn.execute("SELECT enrichment_attempts FROM contratacoes WHERE pncp_id = %s", (pncp_id,))
        row = cur.fetchone()
        attempts = (row[0] if row else 0) + 1
        
        status = 'RETRY'
        if attempts >= 5:
            status = 'ERROR'
            
        conn.execute("""
            UPDATE contratacoes SET
                enrichment_status = %s,
                enrichment_attempts = %s,
                last_enrichment_attempt = CURRENT_TIMESTAMP,
                last_error = %s
            WHERE pncp_id = %s
        """, (status, attempts, error, pncp_id))

    def run_items_archives_enrichment(self) -> Dict[str, Any]:
        """Phase C: Automated collection of items and archives (Backlog Drain)."""
        import os
        from app.services.enrichment.utils import run_itens_backfill, run_arquivos_backfill

        enrich_drain_enabled = os.getenv("ENRICH_DRAIN_ENABLED", "true").lower() in ("true", "1", "yes")
        budget_seconds = int(os.getenv("ENRICH_DRAIN_BUDGET_SECONDS", "90"))
        itens_batch = int(os.getenv("ENRICH_DRAIN_ITENS_BATCH", "80"))
        arquivos_batch = int(os.getenv("ENRICH_DRAIN_ARQUIVOS_BATCH", "80"))
        per_record_timeout = float(os.getenv("ENRICH_DRAIN_PER_RECORD_TIMEOUT_SECONDS", "12.0"))
        
        if not enrich_drain_enabled:
            logger.info("Phase C skipped: ENRICH_DRAIN_ENABLED is false")
            return {"status": "skipped", "reason": "disabled_by_config"}
            
        logger.info(f"Phase C: Starting drain with budget {budget_seconds}s")
        start_time = time.time()
        
        stats = {
            "itens": {},
            "arquivos": {},
            "budget_hit": False,
            "duration_ms_total": 0
        }

        try:
            # Sub-phase C1: Items
            remaining_budget = budget_seconds
            logger.info(f"Phase C1: Draining items (budget: {remaining_budget}s, batch: {itens_batch})")
            itens_stats = run_itens_backfill(
                limit=itens_batch,
                max_records=itens_batch,
                per_record_timeout_seconds=per_record_timeout,
                budget_seconds=remaining_budget,
                debug=1
            )
            stats["itens"] = itens_stats
            
            # Update remaining budget
            elapsed = time.time() - start_time
            remaining_budget = max(0, int(budget_seconds - elapsed))
            
            # Sub-phase C2: Arquivos
            if remaining_budget > 0:
                logger.info(f"Phase C2: Draining arquivos (budget: {remaining_budget}s, batch: {arquivos_batch})")
                arquivos_stats = run_arquivos_backfill(
                    limit=arquivos_batch,
                    per_record_timeout_seconds=per_record_timeout,
                    budget_seconds=remaining_budget,
                    debug=1
                )
                stats["arquivos"] = arquivos_stats
            else:
                logger.info("Phase C2: Skipped arquivos drain (budget exhausted)")
                stats["budget_hit"] = True
                stats["arquivos"] = {"status": "skipped", "reason": "budget_exhausted"}
                
            # Check if budget was hit during C1 or C2
            if itens_stats.get("budget_hit") or stats["arquivos"].get("budget_hit"):
                stats["budget_hit"] = True
                
        except Exception as e:
            logger.error(f"Phase C drain failed: {e}")
            stats["error"] = str(e)
            
        stats["duration_ms_total"] = int((time.time() - start_time) * 1000)
        return stats

    def run_new_batch_enrichment(self, pncp_ids: List[str]) -> Dict[str, Any]:
        """Phase B2: Immediately enrich itens+arquivos for newly ingested/updated IDs."""
        from app.services.enrichment.utils import enrich_single_itens, enrich_single_arquivos

        enabled = os.getenv("ENRICH_NEW_ENABLED", "true").lower() in ("true", "1", "yes")
        budget = int(os.getenv("ENRICH_NEW_BUDGET_SECONDS", "30"))
        max_records = int(os.getenv("ENRICH_NEW_MAX_RECORDS", "25"))
        timeout = float(os.getenv("ENRICH_NEW_PER_RECORD_TIMEOUT_SECONDS", "12"))

        if not enabled:
            logger.info("Phase B2 skipped: ENRICH_NEW_ENABLED is false")
            return {"status": "skipped", "reason": "disabled"}

        if not pncp_ids:
            return {"status": "skipped", "reason": "no_new_ids", "attempted": 0}

        candidates = pncp_ids[:max_records]
        logger.info(f"Phase B2: Enriching {len(candidates)} new IDs (budget={budget}s, timeout={timeout}s)")

        start_t = time.time()
        stats = {
            "attempted": 0,
            "itens_completed": 0, "itens_failed_temp": 0, "itens_failed": 0, "itens_skipped": 0,
            "arquivos_completed": 0, "arquivos_failed_temp": 0, "arquivos_failed": 0, "arquivos_skipped": 0,
            "budget_hit": False,
            "duration_ms": 0
        }

        for pid in candidates:
            if (time.time() - start_t) >= budget:
                logger.info(f"Phase B2: Budget {budget}s hit after {stats['attempted']} records")
                stats["budget_hit"] = True
                break

            stats["attempted"] += 1

            # Enrich itens
            if (time.time() - start_t) < budget:
                res_i = enrich_single_itens(pid, per_record_timeout_seconds=timeout, debug=0)
                s = res_i.get("status", "")
                if s == "COMPLETED": stats["itens_completed"] += 1
                elif s == "FAILED_TEMP": stats["itens_failed_temp"] += 1
                elif s in ("FAILED", "FAILED_AUTH"): stats["itens_failed"] += 1
                else: stats["itens_skipped"] += 1

            # Enrich arquivos
            if (time.time() - start_t) < budget:
                res_a = enrich_single_arquivos(pid, per_record_timeout_seconds=timeout, debug=0)
                s = res_a.get("status", "")
                if s == "COMPLETED": stats["arquivos_completed"] += 1
                elif s == "FAILED_TEMP": stats["arquivos_failed_temp"] += 1
                elif s in ("FAILED", "FAILED_AUTH"): stats["arquivos_failed"] += 1
                else: stats["arquivos_skipped"] += 1

        stats["duration_ms"] = int((time.time() - start_t) * 1000)
        logger.info(f"Phase B2 done: {stats}")
        return stats

    def run_full_job(self, data_inicial: str, data_final: str):
        job_name = "pncp_ingest_daily"
        if not self.acquire_lock(job_name):
            logger.warning("Job already running (lock held).")
            return {"status": "locked"}
            
        try:
            logger.info("Starting Phase A...")
            stats_a = self.run_discovery(data_inicial, data_final)
            new_ids = stats_a.pop("new_or_updated_ids", [])
            logger.info(f"Phase A Complete: {stats_a} | {len(new_ids)} new/updated IDs")

            logger.info("Starting Phase B (detail enrichment)...")
            stats_b = self.run_enrichment()
            logger.info(f"Phase B Complete: {stats_b}")

            logger.info(f"Starting Phase B2 (immediate new-batch enrichment for {len(new_ids)} IDs)...")
            stats_b2 = self.run_new_batch_enrichment(new_ids)
            logger.info(f"Phase B2 Complete: {stats_b2}")

            logger.info("Starting Phase C (backlog drain)...")
            stats_c = self.run_items_archives_enrichment()
            logger.info(f"Phase C Complete: {stats_c}")

            return {
                "status": "success",
                "phase_a": stats_a,
                "phase_b": stats_b,
                "phase_b2": stats_b2,
                "phase_c": stats_c
            }
        finally:
            self.release_lock(job_name)

if __name__ == "__main__":
    # Test Run
    job = PNCPIngestJob()
    # today = datetime.now().strftime('%Y%m%d')
    # job.run_full_job(today, today)

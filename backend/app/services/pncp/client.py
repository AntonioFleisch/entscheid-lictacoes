import requests
import logging
import time
import random
from typing import Dict, Any, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

class PNCPClient:
    BASE_URL = "https://pncp.gov.br/api/pncp/v1"
    
    def __init__(self, auth_token: Optional[str] = None):
        self.session = requests.Session()
        
        # C3: rate-limit handling (Retries with backoff)
        retry_strategy = Retry(
            total=3,
            backoff_factor=1, # 1, 2, 4s...
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "application/json"
        })
        if auth_token:
            self.session.headers.update({"Authorization": f"Bearer {auth_token}"})
        
        self.capabilities = {
            "details": False,
            "items": False,
            "docs": False,
            "history": False
        }

    def probe_auth(self) -> Dict[str, bool]:
        """
        Probes endpoints to detect capabilities and auth requirements.
        Returns a dict of capabilities found.
        """
        # Test a known public endpoint to see if we get 401/403
        test_url = f"{self.BASE_URL}/contratacoes/publicacao/1" # Generic probe
        try:
            r = self.session.get(test_url, timeout=10)
            if r.status_code in [401, 403]:
                logger.warning("PNCP API requires Authentication.")
                # We could set a flag here
            else:
                 # It might return 404, but that means Auth is likely OK for reads
                 pass
        except Exception as e:
            logger.error(f"Probe failed: {e}")

        # In a real scenario, we would probe specific feature endpoints to toggle capabilities
        # For now, we assume standard capabilities based on the PRD
        self.capabilities = {
            "details": True,
            "items": True,
            "docs": True,
            "history": True
        }
        return self.capabilities

    def fetch_details(self, canonical_id: str) -> Dict[str, Any]:
        """
        Fetches details using dynamic discovery.
        canonical_id expected to be a pncp_id format or we parse it.
        """
        # Logic to parse canonical_id to URL params if necessary
        # For PNCP, usually: /orgaos/{cnpj}/compras/{ano}/{sequencial}
        # We need to robustly handle the ID format: CNPJ-Mod-Seq/Ano
        
        try:
            # format: 83102285000107-1-000623/2025
            parts = canonical_id.split('-')
            if len(parts) >= 3:
                cnpj = parts[0]
                # Modality is part[1] usually
                # Sequencial/Ano is at the end
                last_part = parts[-1] # 000623/2025
                seq_ano = last_part.split('/')
                if len(seq_ano) == 2:
                    sequencial = seq_ano[0]
                    ano = seq_ano[1]
                    
                    url = f"{self.BASE_URL}/orgaos/{cnpj}/compras/{ano}/{sequencial}"
                    
                    r = self.session.get(url, allow_redirects=True)
                    if r.status_code == 200:
                        r.encoding = 'utf-8'
                        return r.json()
                    elif r.status_code == 404:
                         logger.warning(f"Detail not found for {canonical_id}")
                    else:
                         logger.error(f"Error fetching details: {r.status_code}")
            
            return {}
        except Exception as e:
            logger.error(f"Fetch details failed: {e}")
            return {}

    def fetch_compra_itens(self, cnpj: str, ano: str, sequencial: str, timeout_seconds: float = 12.0, max_pages: int = 20) -> Dict[str, Any]:
        """
        Implementation of Part B & J: PNCP Client (Rigid).
        Fetches all items for a bidding, handling pagination and flexible response formats.
        """
        all_items = []
        page = 1
        total_pages = 1
        final_status = "COMPLETED"
        last_error = None
        
        while page <= total_pages and page <= max_pages:
            url = f"https://pncp.gov.br/pncp-api/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens?pagina={page}"
            
            # Retry loop for 5xx/429/Timeout
            max_retries = 2
            attempt = 0
            response = None
            
            while attempt <= max_retries:
                attempt_start = time.time()
                try:
                    # Timeout strict (connect, read)
                    response = self.session.get(url, timeout=(3.0, timeout_seconds), allow_redirects=True)
                    duration = int((time.time() - attempt_start) * 1000)
                    
                    # LOGGING Requirement: persistir metrics (audit)
                    # Note: logging here is to stdout/logs, DB persistence handled by caller or middleware
                    logger.info(f"PNCP REQUEST | URL: {url} | Status: {response.status_code} | Duration: {duration}ms")
                    
                    if response.status_code == 200:
                        break # Success
                    
                    if response.status_code in [401, 403]:
                        return {"status": "FAILED_AUTH", "status_code": response.status_code, "items": [], "error": "Unauthorized/Forbidden"}
                    
                    if response.status_code == 404:
                        return {"status": "NOT_AVAILABLE", "status_code": response.status_code, "items": [], "error": "Not Found"}
                        
                    if response.status_code in [429, 500, 502, 503, 504]:
                        # Retry logic with Backoff + Jitter
                        if attempt < max_retries:
                            base = 2 if response.status_code != 429 else 60
                            # retry_delay = base * (2 ** attempts) + random(0..base)
                            retry_delay = base * (2 ** attempt) + random.uniform(0, base)
                            
                            # Respeitar Retry-After se existir (especialmente para 429)
                            retry_after = response.headers.get("Retry-After")
                            if retry_after and retry_after.isdigit():
                                retry_delay = max(retry_delay, int(retry_after))
                            
                            logger.warning(f"PNCP TEMP ERROR {response.status_code} on {url}. Retrying in {retry_delay:.1f}s... (Attempt {attempt+1}/{max_retries})")
                            time.sleep(retry_delay)
                            attempt += 1
                            continue
                        else:
                            return {"status": "FAILED_TEMP", "status_code": response.status_code, "items": [], "error": f"Max retries reached ({response.status_code})"}
                    
                    # OTHER ERRORS
                    return {"status": "FAILED", "status_code": response.status_code, "items": [], "error": f"HTTP {response.status_code}"}
                    
                except Exception as e:
                    duration = int((time.time() - attempt_start) * 1000)
                    logger.error(f"PNCP TIMEOUT/ERR | URL: {url} | Error: {str(e)} | Duration: {duration}ms")
                    if attempt < max_retries:
                        retry_delay = 2 * (2 ** attempt) + random.uniform(0, 2)
                        time.sleep(retry_delay)
                        attempt += 1
                        continue
                    return {"status": "FAILED_TEMP", "status_code": None, "items": [], "error": str(e)}

            # Se falhou nos retentativas e não deu throw
            if not response or response.status_code != 200:
                 return {"status": "FAILED_TEMP", "status_code": None, "items": [], "error": "Unknown error or timeout after retries"}

            # Process Success Response (200)
            try:
                response.encoding = 'utf-8'
                data = response.json()
                # Accept Acceptance Notes: Flexible parsing (array or object)
                if isinstance(data, list):
                    all_items.extend(data)
                    break # No pagination fields in raw list
                elif isinstance(data, dict):
                    # Expecting something like {"data": [...], "paginas": N}
                    items = data.get("data", [])
                    all_items.extend(items)
                    total_pages = data.get("paginas", 1)
                    if not items or page >= total_pages or page >= max_pages:
                        break
                    page += 1
                else:
                    return {"status": "FAILED", "status_code": 200, "items": [], "error": "Invalid response format"}
            except Exception as e:
                return {"status": "FAILED", "status_code": 200, "items": [], "error": f"JSON Parse Error: {str(e)}"}

        if page > max_pages and page <= total_pages:
             logger.warning(f"Truncated fetching items for {cnpj}/{ano}/{sequencial} at {max_pages} pages")

        return {
            "status": "COMPLETED" if all_items or not last_error else final_status,
            "status_code": 200,
            "items": all_items,
            "count": len(all_items),
            "meta": {"pages_fetched": min(page, max_pages)}
        }

    def fetch_compra_arquivos(self, cnpj: str, ano: str, sequencial: str) -> Dict[str, Any]:
        """
        Fetches all attachments (Arquivos) for a bidding.
        Similar to fetch_compra_itens, handles pagination and retries.
        """
        all_docs = []
        page = 1
        total_pages = 1
        
        while page <= total_pages:
            url = f"https://pncp.gov.br/pncp-api/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos?pagina={page}"
            
            # Use sessions retry logic + manual attempt tracking
            max_retries = 2
            attempt = 0
            response = None
            
            while attempt <= max_retries:
                attempt_start = time.time()
                try:
                    response = self.session.get(url, timeout=10, allow_redirects=True)
                    duration = int((time.time() - attempt_start) * 1000)
                    logger.info(f"PNCP DOCS REQ | URL: {url} | Status: {response.status_code} | Duration: {duration}ms")
                    
                    if response.status_code == 200:
                        break
                    
                    if response.status_code in [401, 403]:
                        return {"status": "FAILED_AUTH", "status_code": response.status_code, "files": [], "error": "Unauthorized"}
                    if response.status_code == 404:
                        return {"status": "NOT_AVAILABLE", "status_code": response.status_code, "files": [], "error": "Not Found"}
                    
                    if response.status_code in [429, 500, 502, 503, 504]:
                        if attempt < max_retries:
                            retry_delay = 2 * (2 ** attempt) + random.uniform(0, 2)
                            time.sleep(retry_delay)
                            attempt += 1
                            continue
                        return {"status": "FAILED_TEMP", "status_code": response.status_code, "files": [], "error": f"Max retries reached ({response.status_code})"}
                    
                    return {"status": "FAILED", "status_code": response.status_code, "files": [], "error": f"HTTP {response.status_code}"}
                    
                except Exception as e:
                    if attempt < max_retries:
                        time.sleep(2)
                        attempt += 1
                        continue
                    return {"status": "FAILED_TEMP", "files": [], "error": str(e)}

            try:
                response.encoding = 'utf-8'
                data = response.json()
                if isinstance(data, list):
                    all_docs.extend(data)
                    break 
                elif isinstance(data, dict):
                    # Flexible check for 'data' (items) or 'value' (arquivos)
                    docs = data.get("value") or data.get("data") or []
                    all_docs.extend(docs)
                    
                    # Pagination logic might differ
                    total_pages = data.get("paginas")
                    if total_pages is None:
                         # For 'value' based responses, it might be a single page or use Count
                         break
                    
                    if not docs or page >= total_pages:
                        break
                    page += 1
                else: break
            except:
                return {"status": "FAILED", "files": [], "error": "JSON Parse Error"}

        return {
            "status": "COMPLETED",
            "status_code": 200,
            "files": all_docs,
            "count": len(all_docs)
        }

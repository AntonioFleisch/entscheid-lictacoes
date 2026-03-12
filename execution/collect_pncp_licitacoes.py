#!/usr/bin/env python3
"""
PNCP Licitações Collection Script

Coleta determinística de licitações do PNCP com paginação controlada,
substituindo workflow n8n sem perda de robustez.

Arquitetura obrigatória:
1. Fonte única de verdade (make_window)
2. Loop de paginação controlado
3. Chamada HTTP sempre do contexto
4. Normalização separada da paginação
5. Agregação pós-loop
6. Envio único para backend

Usage:
    python execution/collect_pncp_licitacoes.py --start 20260101 --end 20260107
    python execution/collect_pncp_licitacoes.py --start 20260101 --end 20260107 --max-pages 10

Environment Variables:
    API_KEY: Authentication token for backend
    BACKEND_URL: Base URL of backend (default: http://localhost:8000)
"""

import os
import sys
import json
import logging
import argparse
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

try:
    import requests
except ImportError:
    print("Error: 'requests' package not found. Install with: pip install requests")
    sys.exit(1)

# Load environment variables
load_dotenv()

# Constants
PNCP_BASE_URL = "https://pncp.gov.br/api/consulta/v1"
PNCP_ENDPOINT = "/contratacoes/atualizacao"
DEFAULT_PAGE_SIZE = 50  # Stable value for results
DEFAULT_MAX_PAGES = 5000  # High limit for long windows
DEFAULT_BACKEND_URL = "http://localhost:8000"
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
INTER_PAGE_DELAY = 0.5  # 500ms between pages
INTER_MODALITY_DELAY = 1.0  # 1s between modalities

# List of all procurement modalities in PNCP
MODALITIES = [
    {"id": 1, "name": "Leilão"},
    {"id": 2, "name": "Diálogo Competitivo"},
    {"id": 3, "name": "Concurso"},
    {"id": 4, "name": "Concorrência - Eletrônica"},
    {"id": 5, "name": "Concorrência - Presencial"},
    {"id": 6, "name": "Pregão - Eletrônico"},
    {"id": 7, "name": "Pregão - Presencial"},
    {"id": 8, "name": "Dispensa de Licitação"},
    {"id": 9, "name": "Inexigibilidade"},
    {"id": 10, "name": "Manifestação de Interesse"},
    {"id": 11, "name": "Pré-qualificação"},
    {"id": 12, "name": "Credenciamento"},
    {"id": 13, "name": "Sistema de Registro de Preços"},
    {"id": 14, "name": "RDC - Regime Diferenciado de Contratações"}
]


class PNCPCollector:
    """PNCP Licitações collector with deterministic pagination."""
    
    def __init__(self, window_start: str, window_end: str, 
                 page_size: int = DEFAULT_PAGE_SIZE,
                 max_pages: int = DEFAULT_MAX_PAGES):
        """
        Initialize collector with immutable context.
        
        Args:
            window_start: Start date (YYYYMMDD)
            window_end: End date (YYYYMMDD)
            page_size: Items per page
            max_pages: Maximum pages to collect
        """
        # 1️⃣ FONTE ÚNICA DE VERDADE - make_window
        # Este objeto é IMUTÁVEL durante toda a execução
        self.context = {
            "run_id": str(uuid.uuid4()),
            "PAGE_SIZE": page_size,
            "MAX_PAGES": max_pages,
            "window_start": window_start,
            "window_end": window_end,
            "pagina": 1  # Somente este campo será incrementado
        }
        
        # Setup logging
        self.log_dir = Path(__file__).parent.parent / ".tmp"
        self.log_dir.mkdir(exist_ok=True)
        
        log_file = self.log_dir / f"pncp_collect_{self.context['run_id']}.log"
        
        self.logger = logging.getLogger(f"PNCPCollector_{self.context['run_id']}")
        self.logger.setLevel(logging.INFO)
        
        # File handler
        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setLevel(logging.INFO)
        
        # Console handler
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        
        self.logger.addHandler(fh)
        self.logger.addHandler(ch)
        
        self.logger.info("="*80)
        self.logger.info("PNCP COLLECTION STARTED")
        self.logger.info(f"Run ID: {self.context['run_id']}")
        self.logger.info(f"Window: {window_start} to {window_end}")
        self.logger.info(f"Page Size: {page_size}, Max Pages: {max_pages}")
        self.logger.info(f"Log file: {log_file}")
        self.logger.info("="*80)
        
        # Storage for collected pages
        self.all_pages_data = []
    
    def _call_pncp_api(self, pagina: int, modality_id: int) -> Optional[Dict[str, Any]]:
        """
        3️⃣ Chamada ao PNCP (HTTP GET)
        
        Args:
            pagina: Current page number
            modality_id: PNCP modality code
            
        Returns:
            API response dict or None on failure
        """
        url = f"{PNCP_BASE_URL}{PNCP_ENDPOINT}"
        
        params = {
            "dataInicial": self.context["window_start"],
            "dataFinal": self.context["window_end"],
            "codigoModalidadeContratacao": modality_id,
            "pagina": pagina,
            "tamanhoPagina": self.context["PAGE_SIZE"]
        }
        
        self.logger.info(f"Calling PNCP (Modality {modality_id}) - Page {pagina}")
        
        for attempt in range(MAX_RETRIES):
            try:
                response = requests.get(
                    url,
                    params=params,
                    timeout=REQUEST_TIMEOUT,
                    headers={"Accept": "application/json"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    items_count = len(data.get('data', []))
                    self.logger.info(f"Modality {modality_id} Page {pagina}: Received {items_count} items")
                    return data
                elif response.status_code == 400:
                    self.logger.warning(f"Modality {modality_id} returned 400 (likely no data or invalid params)")
                    return None
                else:
                    self.logger.warning(
                        f"PNCP API returned status {response.status_code}: {response.text[:200]}"
                    )
                    if attempt < MAX_RETRIES - 1:
                        wait_time = 2 ** attempt
                        time.sleep(wait_time)
                    else:
                        return None
                        
            except requests.exceptions.Timeout:
                self.logger.error(f"Request timeout on page {pagina}")
                if attempt < MAX_RETRIES - 1:
                    wait_time = 2 ** attempt
                    self.logger.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    return None
                    
            except requests.exceptions.RequestException as e:
                self.logger.error(f"Request error: {str(e)}")
                if attempt < MAX_RETRIES - 1:
                    wait_time = 2 ** attempt
                    self.logger.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    return None
        
        return None
    
    def _normalize_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        4️⃣ Normalização da Resposta
        
        Extrai e normaliza campos obrigatórios.
        Campos ausentes → null, nunca lança erro.
        
        Args:
            item: Raw item from PNCP API
            
        Returns:
            Normalized item dict
        """
        def safe_get(obj, *keys):
            """Safely get nested dict value, return None if not found."""
            for key in keys:
                if obj is None or not isinstance(obj, dict):
                    return None
                obj = obj.get(key)
            return obj
        
        normalized = {
            "numeroControlePNCP": item.get("numeroControlePNCP"),
            "objetoCompra": item.get("objetoCompra"),
            
            "comprador": {
                "cnpj": safe_get(item, "comprador", "cnpj"),
                "razaoSocial": safe_get(item, "comprador", "razaoSocial"),
                "esferaId": safe_get(item, "comprador", "esferaId"),
                "poderId": safe_get(item, "comprador", "poderId")
            },
            
            "localizacao": {
                "ufSigla": safe_get(item, "localizacao", "ufSigla"),
                "municipioNome": safe_get(item, "localizacao", "municipioNome"),
                "codigoIbge": safe_get(item, "localizacao", "codigoIbge")
            },
            
            "modalidade": {
                "id": safe_get(item, "modalidade", "id"),
                "nome": safe_get(item, "modalidade", "nome")
            },
            
            "modoDisputa": {
                "id": safe_get(item, "modoDisputa", "id"),
                "nome": safe_get(item, "modoDisputa", "nome")
            },
            
            "amparoLegal": {
                "codigo": safe_get(item, "amparoLegal", "codigo"),
                "nome": safe_get(item, "amparoLegal", "nome")
            },
            
            "valores": {
                "estimado": safe_get(item, "valores", "estimado"),
                "homologado": safe_get(item, "valores", "homologado"),
                "srp": safe_get(item, "valores", "srp")
            },
            
            "datas": {
                "publicacaoPncp": safe_get(item, "datas", "publicacaoPncp"),
                "aberturaProposta": safe_get(item, "datas", "aberturaProposta"),
                "encerramentoProposta": safe_get(item, "datas", "encerramentoProposta"),
                "atualizacaoGlobal": safe_get(item, "datas", "atualizacaoGlobal")
            },
            
            "situacao": {
                "id": safe_get(item, "situacao", "id"),
                "nome": safe_get(item, "situacao", "nome")
            },
            
            "links": {
                "sistemaOrigem": safe_get(item, "links", "sistemaOrigem"),
                "processoEletronico": safe_get(item, "links", "processoEletronico")
            }
        }
        
        return normalized
    
    def _normalize_page(self, page_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Normalize all items from a page.
        
        Args:
            page_data: Raw page response from PNCP API
            
        Returns:
            List of normalized items
        """
        items = page_data.get('data', [])
        normalized_items = []
        
        for item in items:
            try:
                normalized = self._normalize_item(item)
                normalized_items.append(normalized)
            except Exception as e:
                # Nunca falhar por erro de normalização
                self.logger.warning(f"Failed to normalize item: {str(e)}")
                self.logger.debug(f"Problematic item: {json.dumps(item, indent=2)}")
                continue
        
        return normalized_items
    
    def collect(self) -> List[Dict[str, Any]]:
        """
        2️⃣ Loop de Paginação por Modalidade
        """
        self.logger.info("Starting multi-modality collection loop")
        
        for modality in MODALITIES:
            m_id = modality["id"]
            m_name = modality["name"]
            
            self.logger.info(f"--- Processing Modality: {m_name} (ID: {m_id}) ---")
            
            pagina = 1
            max_p = self.context["MAX_PAGES"]
            
            while pagina <= max_p:
                page_data = self._call_pncp_api(pagina, m_id)
                
                if page_data is None:
                    break
                
                # Dynamic update of pages for THIS modality
                if pagina == 1:
                    total_p = page_data.get('totalPaginas', 1)
                    total_r = page_data.get('totalRegistros', 0)
                    self.logger.info(f"Modality {m_id}: {total_r} records available in {total_p} pages")
                    max_p = min(total_p, self.context["MAX_PAGES"])
                
                normalized_items = self._normalize_page(page_data)
                self.all_pages_data.extend(normalized_items)
                
                pagina += 1
                if pagina <= max_p:
                    time.sleep(INTER_PAGE_DELAY)
            
            self.logger.info(f"Modality {m_id} finished. Total items so far: {len(self.all_pages_data)}")
            time.sleep(INTER_MODALITY_DELAY)
        
        self.logger.info("="*80)
        self.logger.info(f"ALL MODALITIES COMPLETED. Total items collected: {len(self.all_pages_data)}")
        self.logger.info("="*80)
        
        return self.all_pages_data
        
        # 5️⃣ Agregação pós-loop
        self.logger.info("="*80)
        self.logger.info("PAGINATION COMPLETED")
        self.logger.info(f"Total pages collected: {pagina - 1}")
        self.logger.info(f"Total items collected: {len(self.all_pages_data)}")
        self.logger.info("="*80)
        
        return self.all_pages_data
    
    def save_normalized_data(self) -> Path:
        """
        Save normalized data to file for audit and potential retry.
        
        Returns:
            Path to saved file
        """
        normalized_file = self.log_dir / f"pncp_normalized_{self.context['run_id']}.json"
        
        payload = {
            "run_id": self.context["run_id"],
            "window": {
                "start": self.context["window_start"],
                "end": self.context["window_end"]
            },
            "items": self.all_pages_data
        }
        
        with open(normalized_file, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Normalized data saved: {normalized_file}")
        return normalized_file
    
    def send_to_backend(self, api_key: str, backend_url: str, batch_size: int = 500) -> bool:
        """
        6️⃣ Envio para Backend em Lotes (Batched)
        """
        url = f"{backend_url}/ingest/pncp/batch"
        total_items = len(self.all_pages_data)
        
        self.logger.info(f"Sending {total_items} items in batches of {batch_size}...")
        
        for i in range(0, total_items, batch_size):
            batch = self.all_pages_data[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total_items + batch_size - 1) // batch_size
            
            headers = {
                "X-API-Key": api_key,
                "Idempotency-Key": f"pncp:{self.context['run_id']}:batch:{batch_num}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "run_id": self.context["run_id"],
                "source": "pncp_collector_agent",
                "window": {
                    "start": self.context["window_start"],
                    "end": self.context["window_end"]
                },
                "items": batch
            }
            
            self.logger.info(f"Batch {batch_num}/{total_batches}: Sending {len(batch)} items...")
            
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
                if response.status_code == 200:
                    self.logger.info(f"Batch {batch_num} success.")
                else:
                    self.logger.error(f"Batch {batch_num} failed ({response.status_code})")
                    return False
            except Exception as e:
                self.logger.error(f"Batch {batch_num} error: {str(e)}")
                return False
                
        return True


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description='Collect PNCP licitações with deterministic pagination'
    )
    parser.add_argument(
        '--start',
        help='Window start date (YYYYMMDD). Defaults to yesterday if not provided.'
    )
    parser.add_argument(
        '--end',
        help='Window end date (YYYYMMDD). Defaults to today if not provided.'
    )
    parser.add_argument(
        '--page-size',
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help=f'Items per page (default: {DEFAULT_PAGE_SIZE})'
    )
    parser.add_argument(
        '--max-pages',
        type=int,
        default=DEFAULT_MAX_PAGES,
        help=f'Maximum pages to collect (default: {DEFAULT_MAX_PAGES})'
    )
    parser.add_argument(
        '--days',
        type=int,
        help='Collect data for the last N days (overrides --start/--end)'
    )
    parser.add_argument(
        '--skip-backend',
        action='store_true',
        help='Skip backend ingestion (only collect and save)'
    )
    
    args = parser.parse_args()
    
    # Handle dynamic dates
    if args.days:
        from datetime import timedelta
        args.end = datetime.now().strftime('%Y%m%d')
        args.start = (datetime.now() - timedelta(days=args.days)).strftime('%Y%m%d')
    else:
        if not args.start:
            from datetime import timedelta
            args.start = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
        if not args.end:
            args.end = datetime.now().strftime('%Y%m%d')
    
    # Validate date format
    try:
        datetime.strptime(args.start, '%Y%m%d')
        datetime.strptime(args.end, '%Y%m%d')
    except ValueError:
        print("Error: Dates must be in YYYYMMDD format")
        return 1
    
    # Load config
    api_key = os.getenv('ADMIN_API_KEY') or os.getenv('API_KEY')
    backend_url = os.getenv('BACKEND_URL', DEFAULT_BACKEND_URL)
    
    if not args.skip_backend and not api_key:
        print("Error: ADMIN_API_KEY not found in environment. Set it in .env or use --skip-backend")
        return 1
    
    try:
        # Initialize collector with immutable context
        collector = PNCPCollector(
            window_start=args.start,
            window_end=args.end,
            page_size=args.page_size,
            max_pages=args.max_pages
        )
        
        # Collect data (deterministic pagination loop)
        items = collector.collect()
        
        if not items:
            collector.logger.warning("No items collected")
            return 1
        
        # Save normalized data
        normalized_file = collector.save_normalized_data()
        
        # Send to backend (unless skipped)
        if not args.skip_backend:
            success = collector.send_to_backend(api_key, backend_url)
            if not success:
                collector.logger.error("Backend ingestion failed")
                collector.logger.info(f"Data saved in: {normalized_file}")
                return 1
        else:
            collector.logger.info("Backend ingestion skipped (--skip-backend)")
            collector.logger.info(f"Data saved in: {normalized_file}")
        
        collector.logger.info("="*80)
        collector.logger.info("✓ COLLECTION COMPLETED SUCCESSFULLY")
        collector.logger.info("="*80)
        
        return 0
        
    except Exception as e:
        print(f"Fatal error: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

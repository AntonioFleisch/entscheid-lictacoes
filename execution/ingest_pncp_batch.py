#!/usr/bin/env python3
"""
PNCP Batch Ingestion Script

Ingests PNCP (Portal Nacional de Contratações Públicas) data into the system
via the batch ingestion endpoint.

Usage:
    python execution/ingest_pncp_batch.py <input_file.json>
    python execution/ingest_pncp_batch.py --stdin < data.json

Environment Variables:
    API_KEY: Authentication token for the ingestion endpoint
    API_URL: Base URL of the FastAPI backend (default: http://localhost:8000)
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
from dotenv import load_dotenv

try:
    import requests
except ImportError:
    print("Error: 'requests' package not found. Install with: pip install requests")
    sys.exit(1)

# Load environment variables
load_dotenv()

# Setup logging
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_dir = Path(__file__).parent.parent / ".tmp"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"ingest_pncp_{timestamp}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def load_config() -> Dict[str, Any]:
    """Load configuration from environment variables."""
    api_key = os.getenv('ADMIN_API_KEY') or os.getenv('API_KEY')
    if not api_key:
        raise ValueError("ADMIN_API_KEY not found in environment variables. Check your .env file.")
    
    config = {
        'api_key': api_key,
        'api_url': os.getenv('API_URL', 'http://localhost:8000'),
        'batch_size': int(os.getenv('BATCH_SIZE', '100')),
        'max_retries': int(os.getenv('MAX_RETRIES', '3')),
    }
    return config


def validate_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Validate and filter PNCP items."""
    valid_items = []
    
    for idx, item in enumerate(items):
        # Check required fields
        if not item.get('numeroControlePNCP'):
            logger.warning(f"Item {idx}: Missing numeroControlePNCP, skipping")
            continue
        
        if not item.get('objetoCompra'):
            logger.warning(f"Item {idx}: Missing objetoCompra, skipping")
            continue
        
        valid_items.append(item)
    
    logger.info(f"Validated {len(valid_items)}/{len(items)} items")
    return valid_items


def ingest_batch(items: List[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
    """Send batch ingestion request to API."""
    url = f"{config['api_url']}/ingest/pncp/batch"
    headers = {
        'X-API-Key': config['api_key'],
        'Content-Type': 'application/json'
    }
    payload = {'items': items}
    
    for attempt in range(config['max_retries']):
        try:
            logger.info(f"Sending batch request (attempt {attempt + 1}/{config['max_retries']})")
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Success: {result}")
                return result
            elif response.status_code == 401:
                logger.error("Authentication failed. Check API_KEY in .env")
                raise ValueError("Invalid API key")
            elif response.status_code == 422:
                logger.error(f"Validation error: {response.json()}")
                return {'status': 'error', 'detail': response.json()}
            else:
                logger.warning(f"Request failed with status {response.status_code}: {response.text}")
                if attempt < config['max_retries'] - 1:
                    import time
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue
                else:
                    raise Exception(f"Failed after {config['max_retries']} attempts")
                    
        except requests.exceptions.ConnectionError:
            logger.error("Connection failed. Is the backend running?")
            if attempt < config['max_retries'] - 1:
                import time
                wait_time = 2 ** attempt
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                raise
        except requests.exceptions.Timeout:
            logger.error("Request timed out")
            if attempt < config['max_retries'] - 1:
                import time
                wait_time = 2 ** attempt
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                raise


def chunk_items(items: List[Dict[str, Any]], chunk_size: int) -> List[List[Dict[str, Any]]]:
    """Split items into chunks."""
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(description='Ingest PNCP data in batch')
    parser.add_argument('input_file', nargs='?', help='Input JSON file (or use --stdin)')
    parser.add_argument('--stdin', action='store_true', help='Read from stdin')
    args = parser.parse_args()
    
    try:
        logger.info("Starting PNCP batch ingestion")
        
        # Load configuration
        config = load_config()
        logger.info(f"Configuration loaded. API URL: {config['api_url']}")
        
        # Load input data
        if args.stdin:
            logger.info("Reading from stdin")
            data = json.load(sys.stdin)
        elif args.input_file:
            logger.info(f"Reading from file: {args.input_file}")
            with open(args.input_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            parser.print_help()
            return 1
        
        # Extract items
        if isinstance(data, dict) and 'items' in data:
            items = data['items']
        elif isinstance(data, list):
            items = data
        else:
            raise ValueError("Input must be a list or dict with 'items' key")
        
        logger.info(f"Loaded {len(items)} items")
        
        # Validate items
        valid_items = validate_items(items)
        if not valid_items:
            logger.error("No valid items to ingest")
            return 1
        
        # Process in chunks
        chunks = chunk_items(valid_items, config['batch_size'])
        logger.info(f"Processing {len(chunks)} batch(es)")
        
        total_created = 0
        total_updated = 0
        total_failed = 0
        
        for idx, chunk in enumerate(chunks, 1):
            logger.info(f"Processing batch {idx}/{len(chunks)} ({len(chunk)} items)")
            result = ingest_batch(chunk, config)
            
            if result.get('status') == 'success':
                total_created += result.get('created', 0)
                total_updated += result.get('updated', 0)
                total_failed += result.get('failed', 0)
        
        # Summary
        logger.info("=" * 60)
        logger.info("INGESTION SUMMARY")
        logger.info(f"Total items processed: {len(valid_items)}")
        logger.info(f"Created: {total_created}")
        logger.info(f"Updated: {total_updated}")
        logger.info(f"Failed: {total_failed}")
        logger.info(f"Log file: {log_file}")
        logger.info("=" * 60)
        
        return 0
        
    except Exception as e:
        logger.error(f"Execution failed: {str(e)}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

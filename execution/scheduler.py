#!/usr/bin/env python3
"""
PNCP Automation Scheduler

Runs the PNCP collection and ingestion process every hour.
Ensures that new licitações are automatically added to the database.
Executes directly without HTTP requests or external API keys.

Usage:
    python execution/scheduler.py
"""

import time
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Add project root to sys.path so we can import backend logic directly
root_dir = Path(__file__).parent.parent.absolute()
sys.path.append(str(root_dir))

from pncp_ingest_job import PNCPIngestJob

# Load Env
load_dotenv()

# Configuration
INTERVAL_SECONDS = 3600  # 1 hour

def run_collection():
    """Execute the collection job natively (No HTTP, no API Keys)."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] Triggering internal ingestion job...")
    
    try:
        # Instantiating the job class directly (it connects to sqlite naturally)
        job = PNCPIngestJob()
        
        # Determine window
        data_inicial = datetime.now().strftime('%Y%m%d')
        data_final = datetime.now().strftime('%Y%m%d')
        
        print(f"[{timestamp}] - Running Full Job (Phase A + B)...")
        results = job.run_full_job(data_inicial, data_final)
        
        print(f"[{timestamp}] ✓ Job Output:", results)
        
    except Exception as e:
        print(f"[{timestamp}] ✗ Critical error triggering job: {str(e)}")

def main():
    """Main scheduler loop."""
    print("="*80)
    print("PNCP AUTOMATION SCHEDULER (LOCAL INTERNAL MODE)")
    print(f"Interval: {INTERVAL_SECONDS // 60} minutes")
    print("Target: Direct Python Execution (No HTTP)")
    print("="*80)
    print("Press Ctrl+C to stop.")
    
    # Run once immediately on start
    run_collection()
    
    try:
        while True:
            # Calculate time until next run
            print(f"Next run in {INTERVAL_SECONDS // 60} minutes...")
            time.sleep(INTERVAL_SECONDS)
            run_collection()
            
    except KeyboardInterrupt:
        print("\nScheduler stopped by user.")
        return 0
    except Exception as e:
        print(f"Fatal scheduler error: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())

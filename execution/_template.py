#!/usr/bin/env python3
"""
Example execution script template.

This script demonstrates the structure for deterministic execution scripts.
All scripts in execution/ should:
1. Have clear inputs (args, env vars, or config)
2. Handle errors gracefully
3. Log important steps
4. Return clear outputs
5. Be testable and reliable
"""

import os
import sys
import logging
from typing import Dict, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config() -> Dict[str, Any]:
    """Load configuration from environment variables."""
    config = {
        'example_var': os.getenv('EXAMPLE_VAR', 'default_value'),
    }
    return config


def main():
    """Main execution function."""
    try:
        logger.info("Starting execution script")
        
        # Load configuration
        config = load_config()
        logger.info(f"Loaded configuration: {config}")
        
        # Your deterministic logic here
        # Example: process data, call APIs, write files, etc.
        
        logger.info("Execution completed successfully")
        return 0
        
    except Exception as e:
        logger.error(f"Execution failed: {str(e)}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

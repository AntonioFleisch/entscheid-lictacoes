#!/usr/bin/env python3
"""
Configuration Validation Script

Validates that the 3-layer architecture is properly configured.
"""

import os
import sys
from pathlib import Path

def check_directory(path: Path, name: str) -> bool:
    """Check if directory exists."""
    if path.exists() and path.is_dir():
        print(f"✓ {name}: {path}")
        return True
    else:
        print(f"✗ {name}: NOT FOUND - {path}")
        return False

def check_file(path: Path, name: str, required: bool = True) -> bool:
    """Check if file exists."""
    if path.exists() and path.is_file():
        print(f"✓ {name}: {path}")
        return True
    else:
        marker = "✗" if required else "⚠"
        status = "REQUIRED" if required else "OPTIONAL"
        print(f"{marker} {name}: {status} - {path}")
        return not required

def main():
    """Validate configuration."""
    print("="*80)
    print("3-LAYER ARCHITECTURE CONFIGURATION VALIDATION")
    print("="*80)
    print()
    
    project_root = Path(__file__).parent.parent
    all_checks = []
    
    # Check directories
    print("📁 DIRECTORIES")
    print("-" * 80)
    all_checks.append(check_directory(project_root / "directives", "Directives"))
    all_checks.append(check_directory(project_root / "execution", "Execution"))
    all_checks.append(check_directory(project_root / ".tmp", "Temporary"))
    print()
    
    # Check core files
    print("📄 CORE FILES")
    print("-" * 80)
    all_checks.append(check_file(project_root / "AGENTS.md", "Architecture Doc"))
    all_checks.append(check_file(project_root / "SETUP.md", "Setup Guide"))
    all_checks.append(check_file(project_root / ".gitignore", ".gitignore"))
    all_checks.append(check_file(project_root / ".env.example", ".env.example"))
    all_checks.append(check_file(project_root / ".env", ".env", required=False))
    all_checks.append(check_file(project_root / "requirements.txt", "requirements.txt"))
    print()
    
    # Check directives
    print("📋 DIRECTIVES (Layer 1)")
    print("-" * 80)
    all_checks.append(check_file(project_root / "directives" / "README.md", "Directives README"))
    all_checks.append(check_file(project_root / "directives" / "_template.md", "Directive Template"))
    all_checks.append(check_file(project_root / "directives" / "collect_pncp_licitacoes.md", "PNCP Collection Directive"))
    all_checks.append(check_file(project_root / "directives" / "ingest_pncp_data.md", "PNCP Ingestion Directive"))
    print()
    
    # Check execution scripts
    print("⚙️  EXECUTION SCRIPTS (Layer 3)")
    print("-" * 80)
    all_checks.append(check_file(project_root / "execution" / "README.md", "Execution README"))
    all_checks.append(check_file(project_root / "execution" / "_template.py", "Script Template"))
    all_checks.append(check_file(project_root / "execution" / "collect_pncp_licitacoes.py", "PNCP Collector"))
    all_checks.append(check_file(project_root / "execution" / "ingest_pncp_batch.py", "PNCP Batch Ingestion"))
    print()
    
    # Check Python dependencies
    print("🐍 PYTHON DEPENDENCIES")
    print("-" * 80)
    try:
        import requests
        print("✓ requests: installed")
        all_checks.append(True)
    except ImportError:
        print("✗ requests: NOT INSTALLED - run 'pip install requests'")
        all_checks.append(False)
    
    try:
        import dotenv
        print("✓ python-dotenv: installed")
        all_checks.append(True)
    except ImportError:
        print("✗ python-dotenv: NOT INSTALLED - run 'pip install python-dotenv'")
        all_checks.append(False)
    print()
    
    # Check environment configuration
    print("🔧 ENVIRONMENT CONFIGURATION")
    print("-" * 80)
    env_file = project_root / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)
        
        api_key = os.getenv('API_KEY')
        if api_key:
            print(f"✓ API_KEY: configured (length: {len(api_key)})")
            all_checks.append(True)
        else:
            print("⚠ API_KEY: not set in .env (required for backend ingestion)")
            all_checks.append(True)  # Not critical for validation
        
        backend_url = os.getenv('BACKEND_URL', 'http://localhost:8000')
        print(f"✓ BACKEND_URL: {backend_url}")
    else:
        print("⚠ .env file not found - copy .env.example to .env")
        all_checks.append(True)  # Not critical for validation
    print()
    
    # Summary
    print("="*80)
    if all(all_checks):
        print("✅ CONFIGURATION VALID - All checks passed!")
        print()
        print("Next steps:")
        print("1. Install dependencies: pip install -r requirements.txt")
        print("2. Configure .env: cp .env.example .env (and edit)")
        print("3. Test PNCP collection: python execution/collect_pncp_licitacoes.py --help")
        print()
        print("See QUICKSTART_PNCP.md for usage examples.")
        return 0
    else:
        print("❌ CONFIGURATION INCOMPLETE - Some checks failed")
        print()
        print("Please review the errors above and:")
        print("1. Create missing directories/files")
        print("2. Install missing dependencies: pip install -r requirements.txt")
        print("3. Configure .env file")
        return 1

if __name__ == "__main__":
    sys.exit(main())

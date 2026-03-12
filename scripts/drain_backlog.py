#!/usr/bin/env python3
"""
CLI: Full backlog drain for itens and arquivos.

Runs until eligible_total == 0 (or max-minutes is reached).
Uses the same locking, persistence and status logic as the batch functions.

Usage:
    # Drain everything (recommended)
    python -m scripts.drain_backlog --mode both --batch-itens 200 --batch-arquivos 200 --per-record-timeout 12 --max-minutes 0

    # Items only
    python -m scripts.drain_backlog --mode itens --batch-itens 300 --max-minutes 0

    # Arquivos only
    python -m scripts.drain_backlog --mode arquivos --batch-arquivos 300 --max-minutes 0
"""
import argparse
import sys
import time
import os

# Allow running directly from hello_api/ root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

from enrichment_utils import run_itens_backfill, run_arquivos_backfill


def fmt(stats: dict) -> str:
    return (
        f"eligible={stats.get('eligible_total','?')} "
        f"selected={stats.get('selected','?')} "
        f"picked={stats.get('picked','?')} "
        f"completed={stats.get('completed','?')} "
        f"failed_temp={stats.get('failed_temp','?')} "
        f"failed_auth={stats.get('failed_auth','?')} "
        f"not_available={stats.get('not_available','?')} "
        f"failed={stats.get('failed','?')} "
        f"skipped_locked={stats.get('skipped_locked','?')} "
        f"duration_ms={stats.get('duration_ms','?')}"
    )


def drain(args):
    mode = args.mode
    batch_itens = args.batch_itens
    batch_arquivos = args.batch_arquivos
    timeout = args.per_record_timeout
    max_minutes = args.max_minutes
    sleep_ms = args.sleep_ms / 1000.0

    start_wall = time.time()
    max_seconds = max_minutes * 60 if max_minutes > 0 else float("inf")

    totals = {
        "itens_batches": 0, "itens_completed": 0, "itens_failed_temp": 0,
        "itens_failed_auth": 0, "itens_not_available": 0, "itens_failed": 0,
        "arquivos_batches": 0, "arquivos_completed": 0, "arquivos_failed_temp": 0,
        "arquivos_failed_auth": 0, "arquivos_not_available": 0, "arquivos_failed": 0,
    }

    iteration = 0
    print(f"\n{'='*70}")
    print(f"  PNCP Backlog Drain | mode={mode} | batch_itens={batch_itens} | batch_arquivos={batch_arquivos}")
    print(f"  max_minutes={'∞' if max_minutes == 0 else max_minutes} | per_record_timeout={timeout}s")
    print(f"{'='*70}\n")

    while True:
        iteration += 1
        elapsed = time.time() - start_wall

        if elapsed >= max_seconds:
            print(f"\n⏱  Time limit reached ({max_minutes} min). Stopping.")
            break

        remaining_budget = int(max_seconds - elapsed) if max_seconds != float("inf") else None
        itens_done = True
        arquivos_done = True

        # --- ITENS ---
        if mode in ("itens", "both"):
            print(f"[{iteration}] Itens batch (limit={batch_itens}) ...", end=" ", flush=True)
            stats_i = run_itens_backfill(
                limit=batch_itens,
                max_records=batch_itens,
                per_record_timeout_seconds=timeout,
                budget_seconds=remaining_budget,
                debug=0,
            )
            totals["itens_batches"] += 1
            totals["itens_completed"] += stats_i.get("completed", 0)
            totals["itens_failed_temp"] += stats_i.get("failed_temp", 0)
            totals["itens_failed_auth"] += stats_i.get("failed_auth", 0)
            totals["itens_not_available"] += stats_i.get("not_available", 0)
            totals["itens_failed"] += stats_i.get("failed", 0)
            print(f"\n    ITENS  → {fmt(stats_i)}")
            if stats_i.get("eligible_total", 1) > 0:
                itens_done = False

        # --- ARQUIVOS ---
        if mode in ("arquivos", "both"):
            print(f"[{iteration}] Arquivos batch (limit={batch_arquivos}) ...", end=" ", flush=True)
            stats_a = run_arquivos_backfill(
                limit=batch_arquivos,
                per_record_timeout_seconds=timeout,
                budget_seconds=remaining_budget,
                debug=0,
            )
            totals["arquivos_batches"] += 1
            totals["arquivos_completed"] += stats_a.get("completed", 0)
            totals["arquivos_failed_temp"] += stats_a.get("failed_temp", 0)
            totals["arquivos_failed_auth"] += stats_a.get("failed_auth", 0)
            totals["arquivos_not_available"] += stats_a.get("not_available", 0)
            totals["arquivos_failed"] += stats_a.get("failed", 0)
            print(f"\n    ARQUIVOS → {fmt(stats_a)}")
            if stats_a.get("eligible_total", 1) > 0:
                arquivos_done = False

        # Check done
        if mode == "itens" and itens_done:
            print(f"\n✅  Itens backlog fully drained.")
            break
        elif mode == "arquivos" and arquivos_done:
            print(f"\n✅  Arquivos backlog fully drained.")
            break
        elif mode == "both" and itens_done and arquivos_done:
            print(f"\n✅  Both backlogs fully drained.")
            break

        # Sleep between batches
        if sleep_ms > 0:
            time.sleep(sleep_ms)

    total_elapsed = time.time() - start_wall
    print(f"\n{'='*70}")
    print(f"  TOTALS  |  elapsed={total_elapsed:.1f}s")
    if mode in ("itens", "both"):
        print(f"  ITENS   | batches={totals['itens_batches']} completed={totals['itens_completed']} "
              f"failed_temp={totals['itens_failed_temp']} failed_auth={totals['itens_failed_auth']} "
              f"not_available={totals['itens_not_available']} failed={totals['itens_failed']}")
    if mode in ("arquivos", "both"):
        print(f"  ARQUIVOS| batches={totals['arquivos_batches']} completed={totals['arquivos_completed']} "
              f"failed_temp={totals['arquivos_failed_temp']} failed_auth={totals['arquivos_failed_auth']} "
              f"not_available={totals['arquivos_not_available']} failed={totals['arquivos_failed']}")
    print(f"{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Drain PNCP itens/arquivos backlog until empty or time limit reached."
    )
    parser.add_argument("--mode", choices=["itens", "arquivos", "both"], default="both",
                        help="Which backlog to drain (default: both)")
    parser.add_argument("--batch-itens", type=int, default=200,
                        help="Batch size for itens per iteration (default: 200)")
    parser.add_argument("--batch-arquivos", type=int, default=200,
                        help="Batch size for arquivos per iteration (default: 200)")
    parser.add_argument("--per-record-timeout", type=float, default=12.0,
                        help="Per-record HTTP timeout in seconds (default: 12)")
    parser.add_argument("--max-minutes", type=int, default=60,
                        help="Max runtime in minutes. 0 = unlimited (default: 60)")
    parser.add_argument("--sleep-ms", type=int, default=200,
                        help="Sleep between batches in milliseconds (default: 200)")
    args = parser.parse_args()
    drain(args)


if __name__ == "__main__":
    main()

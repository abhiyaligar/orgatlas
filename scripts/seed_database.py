#!/usr/bin/env python
import argparse
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_path = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.ingestion.seed import seed_database
from app.ingestion.verify import verify_demo_graph


def main():
    parser = argparse.ArgumentParser(description="OrgAtlas FalkorDB Seed and Verification Tool")
    parser.add_argument("--dry-run", action="store_true", help="Validate fixtures and print generated Cypher queries without executing")
    parser.add_argument("--verify-only", action="store_true", help="Run verification checks against existing graph without reseeding")

    args = parser.parse_args()

    if args.verify_only:
        print("Running verification checks on current graph...")
        try:
            res = verify_demo_graph()
            print("Verification results:", res)
            if not res["verified"]:
                sys.exit(1)
        except Exception as e:
            print(f"Verification failed with error: {e}")
            sys.exit(1)
        return

    print(f"Starting seed process (dry-run: {args.dry_run})...")
    res = seed_database(dry_run=args.dry_run)
    print("Seed result:", res)


if __name__ == "__main__":
    main()

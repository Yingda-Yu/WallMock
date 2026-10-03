"""Validate a storefront contract bundle.

Usage:
  python scripts/validate_storefront_contract.py --bundle <path> [--json]

Exits with code 0 if valid, 1 if invalid.
"""
import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.bundle_validator import validate_contract_bundle


def main():
    parser = argparse.ArgumentParser(
        description="Validate a WallMock storefront contract bundle."
    )
    parser.add_argument(
        "--bundle", required=True,
        help="Path to the contract bundle directory.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output machine-readable JSON report.",
    )
    args = parser.parse_args()

    report = validate_contract_bundle(args.bundle)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        if report.valid:
            print("Bundle VALID")
        else:
            print("Bundle INVALID")
        print(f"  Errors: {len(report.errors)}")
        for err in report.errors:
            print(f"    - {err}")
        if report.warnings:
            print(f"  Warnings: {len(report.warnings)}")
            for w in report.warnings:
                print(f"    - {w}")
        if report.info:
            print("  Info:")
            for k, v in sorted(report.info.items()):
                print(f"    {k}: {v}")

    sys.exit(0 if report.valid else 1)


if __name__ == "__main__":
    main()

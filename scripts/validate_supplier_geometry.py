"""
CLI for validating a supplier geometry package.

Usage:
    python scripts/validate_supplier_geometry.py <package_dir> [--json]

Exit codes:
    0 — package is valid
    1 — package is invalid
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path for imports
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent
sys.path.insert(0, str(_project_root))

from core.supplier_geometry import validate_supplier_geometry_package


def main():
    parser = argparse.ArgumentParser(
        description="Validate a supplier geometry package."
    )
    parser.add_argument(
        "package_dir",
        help="Path to the supplier geometry package directory.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output validation result as JSON.",
    )
    args = parser.parse_args()

    result = validate_supplier_geometry_package(args.package_dir)

    if args.json:
        output = {
            "valid": result.valid,
            "errors": result.errors,
            "warnings": result.warnings,
            "package_id": result.package.package_id if result.package else None,
            "target_template_id": (
                result.package.target_template_id if result.package else None
            ),
        }
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        pkg_dir = Path(args.package_dir).resolve()
        print(f"Validating: {pkg_dir}")
        print()

        if result.valid:
            print("RESULT: VALID")
            if result.package:
                print(f"  Package ID:     {result.package.package_id}")
                print(f"  Supplier:       {result.package.supplier_id}")
                print(f"  Device:         {result.package.device_id}")
                print(f"  Case type:      {result.package.case_type}")
                print(f"  Revision:       {result.package.revision}")
                print(f"  Target template:{result.package.target_template_id}")
                print(f"  Reviewed by:    {result.package.verified_by}")
        else:
            print("RESULT: INVALID")
            print()
            print(f"Errors ({len(result.errors)}):")
            for err in result.errors:
                print(f"  - {err}")

        if result.warnings:
            print()
            print(f"Warnings ({len(result.warnings)}):")
            for warn in result.warnings:
                print(f"  - {warn}")

    sys.exit(0 if result.valid else 1)


if __name__ == "__main__":
    main()

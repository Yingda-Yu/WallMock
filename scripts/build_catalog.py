#!/usr/bin/env python3
"""
CLI entry point for WallMock catalog builds.

Usage:
    python scripts/build_catalog.py --plan <plan.json> --out dist/catalog --mode preview --json

Exit codes:
    0 - build succeeded
    1 - build failed (validation error, render error, etc.)
"""
import argparse
import json
import sys
from pathlib import Path

# Add the repo root to the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.catalog_build_plan import load_catalog_build_plan, CatalogValidationError
from core.catalog_builder import CatalogBuilder


def main():
    parser = argparse.ArgumentParser(
        description="Build a WallMock catalog from a build plan."
    )
    parser.add_argument(
        "--plan",
        required=True,
        help="Path to the build plan JSON file.",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output directory for the build.",
    )
    parser.add_argument(
        "--mode",
        choices=["preview", "publish"],
        default=None,
        help="Override build mode (preview or publish). If not set, uses mode from plan.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output build report as JSON to stdout.",
    )
    parser.add_argument(
        "--templates-root",
        default=None,
        help="Root directory for case templates (default: assets/case_templates).",
    )
    parser.add_argument(
        "--designs-root",
        default=None,
        help="Directory containing design artwork files (default: tests/fixtures/artworks).",
    )
    parser.add_argument(
        "--device-registry",
        default=None,
        help="Path to device registry JSON (default: catalog/device_registry.v1.json).",
    )

    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent

    # Resolve paths
    templates_root = args.templates_root or str(repo_root / "assets" / "case_templates")
    designs_root = args.designs_root or str(repo_root / "tests" / "fixtures" / "artworks")
    device_registry = args.device_registry or str(repo_root / "catalog" / "device_registry.v1.json")

    # Load build plan
    try:
        plan = load_catalog_build_plan(
            args.plan,
            templates_root=templates_root,
            validate_templates_exist=True,
        )
    except CatalogValidationError as e:
        print(f"ERROR: Invalid build plan: {e}", file=sys.stderr)
        if args.json:
            print(json.dumps({
                "success": False,
                "errors": [str(e)],
                "output_dir": args.out,
            }, indent=2))
        sys.exit(1)

    # Override mode if specified
    if args.mode and args.mode != plan.mode:
        # We need to create a new plan with the overridden mode
        from dataclasses import replace
        plan = replace(plan, mode=args.mode)

    # Build the catalog
    builder = CatalogBuilder(
        templates_root=templates_root,
        designs_root=designs_root,
        device_registry_path=device_registry,
    )

    report = builder.build(plan, args.out)

    # Output report
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"Build {'succeeded' if report.success else 'FAILED'}")
        print(f"  Mode: {report.mode}")
        print(f"  Total assets: {report.total_assets}")
        print(f"  Generated: {report.generated}")
        print(f"  Skipped (unchanged): {report.skipped_unchanged}")
        print(f"  Skipped (publish gate): {report.skipped_publish_gate}")
        if report.errors:
            print(f"  Errors: {len(report.errors)}")
            for err in report.errors:
                print(f"    - {err}")
        print(f"  Output: {report.output_dir}")
        if report.bundle_path:
            print(f"  Bundle: {report.bundle_path}")
            print(f"  Bundle valid: {report.bundle_valid}")
        print(f"  Duration: {report.build_duration_seconds:.2f}s")

    sys.exit(0 if report.success else 1)


if __name__ == "__main__":
    main()

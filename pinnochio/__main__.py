#!/usr/bin/env python

import argparse
import sys

from pinnochio.core import (
    check_all_dependencies_are_pinned_above,
    check_all_groups_are_sorted,
    check_group_overlaps_match,
    check_no_overlap_between_core_deps_and_groups,
    load_uv_dependencies,
    save_toml_document,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lint UV dependencies in pyproject.toml"
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Automatically fix issues where possible",
    )
    args = parser.parse_args()

    try:
        groups, doc = load_uv_dependencies()
    except FileNotFoundError:
        print("Error: pyproject.toml not found in current directory")
        return 1
    except Exception as e:
        print(f"Error loading pyproject.toml: {e}")
        return 1

    checks = [
        check_all_dependencies_are_pinned_above,
        check_all_groups_are_sorted,
        check_group_overlaps_match,
        check_no_overlap_between_core_deps_and_groups,
    ]

    issues_found = []
    all_issues_fixed = True

    for check in checks:
        result, was_fixed = check(groups, doc, fix=args.fix)
        if result:
            issues_found.append(result)
            if not was_fixed:
                all_issues_fixed = False

    if args.fix and any(issues_found):
        save_toml_document(doc)
        print("Changes have been written to pyproject.toml")

        # Return 0 only if all issues were actually fixed
        if all_issues_fixed:
            return 0
        else:
            print("Some issues could not be automatically fixed.")
            return 1

    return 1 if any(issues_found) else 0


if __name__ == "__main__":
    sys.exit(main())

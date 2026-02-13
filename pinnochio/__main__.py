#!/usr/bin/env python

import argparse
import sys

import tomlkit.exceptions

from pinnochio.core import (
    CheckStatus,
    check_all_groups_are_sorted,
    check_group_overlaps_match,
    check_no_overlap_between_core_deps_and_groups,
    check_upper_bounds,
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

    error_raised = False
    try:
        groups, doc, config = load_uv_dependencies()
    except FileNotFoundError:
        print(
            "Error: pyproject.toml not found in current directory",
            file=sys.stderr,
        )
        error_raised = True
    except tomlkit.exceptions.TOMLKitError as e:
        print(
            "Error: Malformed pyproject.toml file",
            file=sys.stderr,
        )
        print(
            f"  {e}",
            file=sys.stderr,
        )
        error_raised = True
    except KeyError as e:
        print(
            f"Error: {e}",
            file=sys.stderr,
        )
        error_raised = True
    except ValueError as e:
        print(
            f"Error: {e}",
            file=sys.stderr,
        )
        error_raised = True

    if error_raised:
        return 1

    checks = [
        check_upper_bounds,
        check_all_groups_are_sorted,
        check_group_overlaps_match,
        check_no_overlap_between_core_deps_and_groups,
    ]

    results = []
    for check in checks:
        result = check(groups, doc, config, fix=args.fix)
        results.append(result)

    # Check if any issues were found or fixed
    has_issues = any(r.has_issues for r in results)
    all_fixed = all(
        r.status in (CheckStatus.PASSED, CheckStatus.FIXED) for r in results
    )

    if args.fix and has_issues:
        save_toml_document(doc)
        print("Changes have been written to pyproject.toml")

        # Return 0 only if all issues were actually fixed
        if all_fixed:
            return 0
        else:
            print("Some issues could not be automatically fixed.")
            return 1

    return 0 if not has_issues else 1


if __name__ == "__main__":
    sys.exit(main())

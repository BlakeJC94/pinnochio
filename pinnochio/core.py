#!/usr/bin/env python

import re
from collections import defaultdict
from itertools import combinations, product
from pathlib import Path
from typing import Callable, TypeAlias, cast

import tomlkit
from tomlkit.items import Array, Table

DependencyGroups: TypeAlias = dict[str, list[str]]


def load_uv_dependencies() -> tuple[DependencyGroups, tomlkit.TOMLDocument]:
    """Load dependencies and return both the parsed groups and the raw TOML
    document.
    """
    pyproject_path = Path("pyproject.toml")
    with open(pyproject_path, "rb") as f:
        content = f.read()

    doc = tomlkit.parse(content.decode())

    # Extract dependencies with proper type casting
    project_table = cast(Table, doc["project"])
    dependencies = cast(Array, project_table["dependencies"])

    dependency_groups_table = cast(Table, doc["dependency-groups"])
    dev_deps = cast(Array, dependency_groups_table["dev"])

    optional_deps_table = cast(Table, project_table["optional-dependencies"])

    groups = {
        "dependencies": [str(dep) for dep in dependencies],
        "dev": [str(dep) for dep in dev_deps],
        **{
            k: [str(dep) for dep in cast(Array, v)]
            for k, v in optional_deps_table.items()
        },
    }

    return groups, doc


def save_toml_document(doc: tomlkit.TOMLDocument) -> None:
    """Save the TOML document back to pyproject.toml."""
    pyproject_path = Path("pyproject.toml")
    with open(pyproject_path, "w") as f:
        f.write(tomlkit.dumps(doc))


def check_all_dependencies_are_pinned_above(
    groups: DependencyGroups, doc: tomlkit.TOMLDocument, fix: bool = False
) -> tuple[DependencyGroups, bool]:
    """All deps must be pinned from below and above."""
    unpinned = defaultdict(list)

    for group_name, group in groups.items():
        for pin in group:
            if ">" in pin and "<" not in pin:
                unpinned[group_name].append(pin)

    if unpinned:
        print("Warning! The following dependencies aren't pinned from above")
        for group_name, group in unpinned.items():
            print(f"{group_name}:")
            for pin in sorted(group):
                print(f"  {pin}")
        print("")

        if fix:
            print("Fixing: Adding upper bounds to unpinned dependencies...")
            for group_name, pins in unpinned.items():
                _fix_dependencies_in_group(
                    doc, group_name, pins, _add_upper_bound
                )
            print("Fixed: Upper bounds have been added where possible.")
            print("")
            return dict(unpinned), True  # Issues found but fixed

    return dict(unpinned), False  # Issues found but not fixed (or no issues)


def check_all_groups_are_sorted(
    groups: DependencyGroups, doc: tomlkit.TOMLDocument, fix: bool = False
) -> tuple[DependencyGroups, bool]:
    """All groups should be sorted."""
    unsorted = {}

    for group_name, group in groups.items():
        if group != sorted(group):
            unsorted[group_name] = group

    if unsorted:
        print("Warning: The following dependency groups aren't sorted:")
        for group_name in unsorted:
            print(f"  {group_name}")
        print("")

        if fix:
            print("Fixing: Sorting dependency groups...")
            for group_name in unsorted:
                if group_name == "dependencies":
                    # Create a new sorted array to preserve tomlkit formatting
                    project_table = cast(Table, doc["project"])
                    current_deps = cast(Array, project_table["dependencies"])
                    sorted_deps = tomlkit.array()
                    sorted_deps.multiline(True)
                    for dep in sorted([str(d) for d in current_deps]):
                        sorted_deps.append(dep)
                    project_table["dependencies"] = sorted_deps
                elif group_name == "dev":
                    dependency_groups_table = cast(
                        Table, doc["dependency-groups"]
                    )
                    current_deps = cast(Array, dependency_groups_table["dev"])
                    sorted_deps = tomlkit.array()
                    sorted_deps.multiline(True)
                    for dep in sorted([str(d) for d in current_deps]):
                        sorted_deps.append(dep)
                    dependency_groups_table["dev"] = sorted_deps
                else:
                    project_table = cast(Table, doc["project"])
                    optional_deps_table = cast(
                        Table, project_table["optional-dependencies"]
                    )
                    current_deps = cast(Array, optional_deps_table[group_name])
                    sorted_deps = tomlkit.array()
                    sorted_deps.multiline(True)
                    for dep in sorted([str(d) for d in current_deps]):
                        sorted_deps.append(dep)
                    optional_deps_table[group_name] = sorted_deps
            print("Fixed: Dependency groups have been sorted.")
            print("")
            return unsorted, True  # Issues found but fixed

    return unsorted, False  # Issues found but not fixed (or no issues)


def check_group_overlaps_match(
    groups: DependencyGroups, doc: tomlkit.TOMLDocument, fix: bool = False
) -> tuple[DependencyGroups, bool]:
    """Overlap between groups => Pin should be the same."""
    drift = defaultdict(list)

    for group_name_a, group_name_b in combinations(groups, 2):
        for pin_a, pin_b in product(
            groups[group_name_a],
            groups[group_name_b],
        ):
            dep_a, _ = split_pin(pin_a)
            dep_b, _ = split_pin(pin_b)
            if dep_a == dep_b and pin_a != pin_b:
                drift[group_name_a].append(pin_a)
                drift[group_name_b].append(pin_b)

    if drift:
        print("The following dependencies have drifted:")
        for group_name, group in drift.items():
            print(f"{group_name}:")
            for pin in sorted(group):
                print(f"  {pin}")
        print("")

        if fix:
            print("Note: Automatic fixing of version drift is not implemented.")
            print(
                "Please manually align the versions of the dependencies "
                "listed above."
            )
            print("")

    return dict(drift), False  # Issues found but cannot be automatically fixed


def _fix_dependencies_in_group(
    doc: tomlkit.TOMLDocument,
    group_name: str,
    pins_to_fix: list[str],
    fix_function: Callable[[str], str],
) -> None:
    """Apply a fix function to specific dependencies in a group."""
    # Get current dependencies based on group location
    if group_name == "dependencies":
        project_table = cast(Table, doc["project"])
        current_deps_array = cast(Array, project_table["dependencies"])
        current_deps = [str(dep) for dep in current_deps_array]
        target_location = project_table
        target_key = "dependencies"
    elif group_name == "dev":
        dependency_groups_table = cast(Table, doc["dependency-groups"])
        current_deps_array = cast(Array, dependency_groups_table["dev"])
        current_deps = [str(dep) for dep in current_deps_array]
        target_location = dependency_groups_table
        target_key = "dev"
    else:
        project_table = cast(Table, doc["project"])
        optional_deps_table = cast(
            Table, project_table["optional-dependencies"]
        )
        current_deps_array = cast(Array, optional_deps_table[group_name])
        current_deps = [str(dep) for dep in current_deps_array]
        target_location = optional_deps_table
        target_key = group_name

    # Apply fixes
    fixed_deps = tomlkit.array()
    fixed_deps.multiline(True)
    for dep in current_deps:
        if dep in pins_to_fix:
            try:
                fixed_dep = fix_function(dep)
                fixed_deps.append(fixed_dep)
                print(f"  Fixed: {dep} -> {fixed_dep}")
            except Exception as e:
                print(f"  Could not fix {dep}: {e}")
                fixed_deps.append(dep)
        else:
            fixed_deps.append(dep)

    # Update the document
    target_location[target_key] = fixed_deps


def _add_upper_bound(pin: str) -> str:
    """Add upper bound to a dependency pin that only has a lower bound.

    Converts 'package>=x.y.z' to 'package>=x.y.z,<x+1' where x is the major
    version.
    """
    package_name, version_constraint = split_pin(pin)

    # Check if it already has an upper bound
    if "<" in version_constraint:
        return pin

    # Extract version from >=x.y.z pattern
    version_match = re.search(r">=(\d+)\.(\d+)\.(\d+)", version_constraint)
    if not version_match:
        raise ValueError(
            f"Cannot parse version constraint: {version_constraint}"
        )

    major, minor, patch = version_match.groups()

    return (
        f"{package_name}>={major}.{minor}.{patch},<{major}.{int(minor) + 1}.0"
    )


def split_pin(pin: str) -> tuple[str, str]:
    """Split a dependency pin into package name and version constraint."""
    m = re.search(r"^[^><=]+", pin)
    if not m:
        raise ValueError(f"Bad pin: {pin}")
    return pin[: m.end()], pin[m.end() :]


def check_no_overlap_between_core_deps_and_groups(  # noqa
    groups: DependencyGroups, doc: tomlkit.TOMLDocument, fix: bool = False
) -> tuple[DependencyGroups, bool]:
    """No overlap between dependencies and groups."""
    redundant_pins = defaultdict(list)

    for core_pin in groups["dependencies"]:
        core_dep, _ = split_pin(core_pin)
        for group_name, group in groups.items():
            if group_name == "dependencies":
                continue
            for pin in group:
                dep, _ = split_pin(pin)
                if core_dep == dep:
                    redundant_pins[group_name].append(pin)

    if redundant_pins:
        print("The following dependencies are redundant:")
        for group_name, group in redundant_pins.items():
            print(f"{group_name}:")
            for pin in sorted(group):
                print(f"  {pin}")
        print("")

        if fix:
            print("Fixing: Removing redundant dependencies...")
            for group_name, pins in redundant_pins.items():
                if group_name == "dev":
                    dependency_groups_table = cast(
                        Table, doc["dependency-groups"]
                    )
                    current_deps_array = cast(
                        Array, dependency_groups_table["dev"]
                    )
                    current_deps = [str(dep) for dep in current_deps_array]
                    filtered_deps = tomlkit.array()
                    filtered_deps.multiline(True)
                    for dep in current_deps:
                        if dep not in pins:
                            filtered_deps.append(dep)
                    dependency_groups_table["dev"] = filtered_deps
                else:
                    project_table = cast(Table, doc["project"])
                    optional_deps_table = cast(
                        Table, project_table["optional-dependencies"]
                    )
                    current_deps_array = cast(
                        Array, optional_deps_table[group_name]
                    )
                    current_deps = [str(dep) for dep in current_deps_array]
                    filtered_deps = tomlkit.array()
                    filtered_deps.multiline(True)
                    for dep in current_deps:
                        if dep not in pins:
                            filtered_deps.append(dep)
                    optional_deps_table[group_name] = filtered_deps
            print("Fixed: Redundant dependencies have been removed.")
            print("")
            return dict(redundant_pins), True  # Issues found but fixed

    return dict(
        redundant_pins
    ), False  # Issues found but not fixed (or no issues)

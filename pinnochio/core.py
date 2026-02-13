#!/usr/bin/env python

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from itertools import combinations, product
from pathlib import Path
from typing import Callable, TypeAlias, cast

import tomlkit
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version
from tomlkit.items import Array, Table

from pinnochio.config import Config, PinningStrategy, load_config

DependencyGroups: TypeAlias = dict[str, list[str]]


class CheckStatus(Enum):
    """Status of a dependency check."""

    PASSED = "passed"
    FAILED = "failed"
    FIXED = "fixed"


@dataclass
class CheckResult:
    """Result of a dependency check.

    Attributes:
        status: Whether the check passed, failed, or was fixed
        issues: Dictionary mapping group names to lists of problematic
            dependencies
    """

    status: CheckStatus
    issues: dict[str, list[str]]

    @property
    def has_issues(self) -> bool:
        """Returns True if any issues were found."""
        return bool(self.issues)


def load_uv_dependencies() -> tuple[DependencyGroups, tomlkit.TOMLDocument, Config]:
    """Load dependencies and config from pyproject.toml.

    Returns:
        Tuple of (dependency groups, TOML document, config)

    Raises:
        FileNotFoundError: If pyproject.toml is not found
        tomlkit.exceptions.TOMLKitError: If pyproject.toml is malformed
        KeyError: If required sections are missing from pyproject.toml
    """
    pyproject_path = Path("pyproject.toml")
    with open(pyproject_path, "rb") as f:
        content = f.read()

    doc = tomlkit.parse(content.decode())

    # Extract dependencies with proper error handling
    if "project" not in doc:
        raise KeyError("Missing [project] section in pyproject.toml")

    project_table = cast(Table, doc["project"])

    if "dependencies" not in project_table:
        raise KeyError("Missing [project.dependencies] in pyproject.toml")

    dependencies = cast(Array, project_table["dependencies"])

    if "dependency-groups" not in doc:
        raise KeyError("Missing [dependency-groups] section in pyproject.toml")

    dependency_groups_table = cast(Table, doc["dependency-groups"])

    if "dev" not in dependency_groups_table:
        raise KeyError("Missing [dependency-groups.dev] in pyproject.toml")

    dev_deps = cast(Array, dependency_groups_table["dev"])

    # Optional dependencies are optional
    optional_deps_table = cast(Table, project_table.get("optional-dependencies", {}))

    groups = {
        "dependencies": [str(dep) for dep in dependencies],
        "dev": [str(dep) for dep in dev_deps],
        **{
            k: [str(dep) for dep in cast(Array, v)]
            for k, v in optional_deps_table.items()
        },
    }

    config = load_config(doc)

    return groups, doc, config


def save_toml_document(doc: tomlkit.TOMLDocument) -> None:
    """Save the TOML document back to pyproject.toml."""
    pyproject_path = Path("pyproject.toml")
    with open(pyproject_path, "w") as f:
        f.write(tomlkit.dumps(doc))


def get_dependency_array(doc: tomlkit.TOMLDocument, group_name: str) -> Array:
    """Get the Array object for a dependency group.

    Args:
        doc: The TOML document
        group_name: Name of the dependency group ('dependencies', 'dev', or
            optional-dependencies name)

    Returns:
        The Array object containing the dependencies
    """
    if group_name == "dependencies":
        project_table = cast(Table, doc["project"])
        return cast(Array, project_table["dependencies"])
    elif group_name == "dev":
        dependency_groups_table = cast(Table, doc["dependency-groups"])
        return cast(Array, dependency_groups_table["dev"])
    else:
        project_table = cast(Table, doc["project"])
        optional_deps_table = cast(Table, project_table["optional-dependencies"])
        return cast(Array, optional_deps_table[group_name])


def set_dependency_array(
    doc: tomlkit.TOMLDocument, group_name: str, array: Array
) -> None:
    """Set the Array object for a dependency group.

    Args:
        doc: The TOML document
        group_name: Name of the dependency group
        array: The new Array to set
    """
    if group_name == "dependencies":
        project_table = cast(Table, doc["project"])
        project_table["dependencies"] = array
    elif group_name == "dev":
        dependency_groups_table = cast(Table, doc["dependency-groups"])
        dependency_groups_table["dev"] = array
    else:
        project_table = cast(Table, doc["project"])
        optional_deps_table = cast(Table, project_table["optional-dependencies"])
        optional_deps_table[group_name] = array


def update_dependencies_in_group(
    doc: tomlkit.TOMLDocument,
    group_name: str,
    transform_fn: Callable[[list[str]], list[str]],
) -> None:
    """Apply a transformation function to dependencies in a group.

    Args:
        doc: The TOML document
        group_name: Name of the dependency group
        transform_fn: Function that takes a list of dependencies and returns
            transformed list
    """
    current_deps_array = get_dependency_array(doc, group_name)
    current_deps = [str(dep) for dep in current_deps_array]

    # Apply transformation
    transformed_deps = transform_fn(current_deps)

    # Create new array with formatting preserved
    new_array = tomlkit.array()
    new_array.multiline(True)
    for dep in transformed_deps:
        new_array.append(dep)

    set_dependency_array(doc, group_name, new_array)


def check_upper_bounds(
    groups: DependencyGroups,
    doc: tomlkit.TOMLDocument,
    config: Config,
    fix: bool = False,
) -> CheckResult:
    """Check that all dependencies have upper version bounds.

    Args:
        groups: Dictionary of dependency groups
        doc: The TOML document
        config: Configuration with pinning strategy
        fix: Whether to automatically fix issues

    Returns:
        CheckResult with status and any issues found
    """
    unpinned = defaultdict(list)

    for group_name, group in groups.items():
        for pin in group:
            # Check if has lower bound but no upper bound
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
                # Use lambda to pass config to _add_upper_bound
                def fix_fn(deps: list[str]) -> list[str]:
                    return [
                        _add_upper_bound(dep, config) if dep in pins else dep
                        for dep in deps
                    ]

                try:
                    update_dependencies_in_group(doc, group_name, fix_fn)
                    for pin in pins:
                        try:
                            fixed = _add_upper_bound(pin, config)
                            print(f"  Fixed: {pin} -> {fixed}")
                        except Exception as e:
                            print(f"  Could not fix {pin}: {e}")
                except Exception as e:
                    print(f"  Error fixing group {group_name}: {e}")

            print("Fixed: Upper bounds have been added where possible.")
            print("")
            return CheckResult(status=CheckStatus.FIXED, issues=dict(unpinned))

        return CheckResult(status=CheckStatus.FAILED, issues=dict(unpinned))

    return CheckResult(status=CheckStatus.PASSED, issues={})


def check_all_groups_are_sorted(
    groups: DependencyGroups,
    doc: tomlkit.TOMLDocument,
    config: Config,
    fix: bool = False,
) -> CheckResult:
    """Check that all dependency groups are alphabetically sorted.

    Args:
        groups: Dictionary of dependency groups
        doc: The TOML document
        config: Configuration (unused but kept for consistency)
        fix: Whether to automatically fix issues

    Returns:
        CheckResult with status and any issues found
    """
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
                update_dependencies_in_group(doc, group_name, sorted)
            print("Fixed: Dependency groups have been sorted.")
            print("")
            return CheckResult(status=CheckStatus.FIXED, issues=unsorted)

        return CheckResult(status=CheckStatus.FAILED, issues=unsorted)

    return CheckResult(status=CheckStatus.PASSED, issues={})


def check_group_overlaps_match(
    groups: DependencyGroups,
    doc: tomlkit.TOMLDocument,
    config: Config,
    fix: bool = False,
) -> CheckResult:
    """Check that dependencies appearing in multiple groups have matching
    versions.

    Args:
        groups: Dictionary of dependency groups
        doc: The TOML document
        config: Configuration (unused but kept for consistency)
        fix: Whether to automatically fix issues

    Returns:
        CheckResult with status and any issues found
    """
    drift = defaultdict(list)

    for group_name_a, group_name_b in combinations(groups, 2):
        for pin_a, pin_b in product(
            groups[group_name_a],
            groups[group_name_b],
        ):
            try:
                dep_a, _ = split_pin(pin_a)
                dep_b, _ = split_pin(pin_b)
                if dep_a == dep_b and pin_a != pin_b:
                    drift[group_name_a].append(pin_a)
                    drift[group_name_b].append(pin_b)
            except InvalidRequirement:
                # Skip malformed requirements
                continue

    if drift:
        print("The following dependencies have drifted:")
        for group_name, group in drift.items():
            print(f"{group_name}:")
            for pin in sorted(set(group)):
                print(f"  {pin}")
        print("")

        if fix:
            print("Note: Automatic fixing of version drift is not implemented.")
            print(
                "Please manually align the versions of the dependencies listed above."
            )
            print("")

        return CheckResult(status=CheckStatus.FAILED, issues=dict(drift))

    return CheckResult(status=CheckStatus.PASSED, issues={})


def split_pin(pin: str) -> tuple[str, SpecifierSet]:
    """Split a dependency pin into package name and version specifiers.

    Args:
        pin: A dependency specification (e.g., 'package>=1.0.0' or
            'package[extra]>=1.0.0')

    Returns:
        Tuple of (package_name, specifier_set)

    Raises:
        InvalidRequirement: If the pin is malformed
    """
    try:
        req = Requirement(pin)
        return req.name, req.specifier
    except InvalidRequirement as e:
        raise InvalidRequirement(f"Invalid dependency pin '{pin}': {e}") from e


def _add_upper_bound(pin: str, config: Config) -> str:
    """Add upper bound to a dependency pin based on pinning strategy.

    Args:
        pin: A dependency specification (e.g., 'package>=1.0.0')
        config: Configuration specifying the pinning strategy

    Returns:
        Dependency pin with upper bound added

    Raises:
        ValueError: If the pin cannot be parsed or doesn't have a lower bound
    """
    package_name, specifiers = split_pin(pin)

    # Check if it already has an upper bound
    if any(spec.operator in ("<", "<=") for spec in specifiers):
        return pin

    # Find the >= specifier
    lower_bound = None
    lower_version = None
    for spec in specifiers:
        if spec.operator == ">=":
            lower_bound = spec.version
            lower_version = Version(spec.version)
            break

    if not lower_version:
        raise ValueError(f"Cannot add upper bound: no '>=' specifier found in '{pin}'")

    # Calculate upper bound based on strategy
    if config.pinning_strategy == PinningStrategy.MAJOR:
        upper_version = f"{lower_version.major + 1}.0.0"
    elif config.pinning_strategy == PinningStrategy.MINOR:
        upper_version = f"{lower_version.major}.{lower_version.minor + 1}.0"
    elif config.pinning_strategy == PinningStrategy.PATCH:
        upper_version = (
            f"{lower_version.major}.{lower_version.minor}.{lower_version.micro + 1}"
        )
    else:
        raise ValueError(f"Unknown pinning strategy: {config.pinning_strategy}")

    # Reconstruct the pin with extras if present
    try:
        req = Requirement(pin)
        extras_str = f"[{','.join(sorted(req.extras))}]" if req.extras else ""
        return f"{package_name}{extras_str}>={lower_bound},<{upper_version}"
    except InvalidRequirement:
        # Fallback for simple cases
        return f"{package_name}>={lower_bound},<{upper_version}"


def check_no_overlap_between_core_deps_and_groups(
    groups: DependencyGroups,
    doc: tomlkit.TOMLDocument,
    config: Config,
    fix: bool = False,
) -> CheckResult:
    """Check that dependencies in core don't overlap with other groups.

    Args:
        groups: Dictionary of dependency groups
        doc: The TOML document
        config: Configuration (unused but kept for consistency)
        fix: Whether to automatically fix issues

    Returns:
        CheckResult with status and any issues found
    """
    redundant_pins = defaultdict(list)

    for core_pin in groups["dependencies"]:
        try:
            core_dep, _ = split_pin(core_pin)
            for group_name, group in groups.items():
                if group_name == "dependencies":
                    continue
                for pin in group:
                    try:
                        dep, _ = split_pin(pin)
                        if core_dep == dep:
                            redundant_pins[group_name].append(pin)
                    except InvalidRequirement:
                        continue
        except InvalidRequirement:
            continue

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
                update_dependencies_in_group(
                    doc,
                    group_name,
                    lambda deps: [dep for dep in deps if dep not in pins],
                )
            print("Fixed: Redundant dependencies have been removed.")
            print("")
            return CheckResult(status=CheckStatus.FIXED, issues=dict(redundant_pins))

        return CheckResult(status=CheckStatus.FAILED, issues=dict(redundant_pins))

    return CheckResult(status=CheckStatus.PASSED, issues={})

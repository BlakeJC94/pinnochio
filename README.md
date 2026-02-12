# Pinnochio

A dependency linter for Python projects using UV and `pyproject.toml`. Pinnochio
helps prevent accidental dependency upgrades that break APIs by enforcing best
practices for version pinning.

## Features

* **Upper Bound Enforcement**: Ensures all dependencies have upper version
  bounds (e.g., `>=2.25.0,<2.26.0`) to prevent breaking changes
* **Automatic Sorting**: Keeps dependency groups alphabetically sorted for
  consistency
* **Version Drift Detection**: Identifies when the same package has different
  version constraints across dependency groups
* **Redundancy Checks**: Detects dependencies duplicated between core
  dependencies and optional groups
* **Auto-fix Support**: Automatically fixes many common issues with the `--fix`
  flag

## Installation

```bash
uv tool install pinnochio
# Or pipx install pinnochio
```

## Usage

Run in your project directory:

```bash
# Check for issues
pinnochio

# Check and automatically fix issues
pinnochio --fix
```

### Example Output

```text
Warning! The following dependencies aren't pinned from above
dependencies:
  requests>=2.25.0
  numpy>=1.20.0

Warning: The following dependency groups aren't sorted:
  dev
```

## Checks Performed

1. **Upper Bound Pinning**: Dependencies with only lower bounds (e.g.,
  `>=1.0.0`) are flagged and can be auto-fixed to include upper bounds (e.g.,
  `>=1.0.0,<1.1.0`)

2. **Dependency Sorting**: All dependency groups must be alphabetically sorted

3. **Version Consistency**: The same package must have identical version
   constraints across all dependency groups

4. **No Redundancy**: Dependencies in the core `dependencies` list should not be
   duplicated in `optional-dependencies` or `dev` groups

## Pre-commit Hook

Coming soon: Pinnochio will be available as a pre-commit hook to enforce
dependency hygiene in your CI/CD pipeline.

## Requirements

* Python >=3.11
* `pyproject.toml` with UV-style dependency groups

## License

MIT

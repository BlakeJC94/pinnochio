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

# Override pinning strategy for this run
pinnochio --fix --pinning-strategy minor
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

With `--fix`, pinnochio will automatically add upper bounds:

```text
Fixing: Adding upper bounds to unpinned dependencies...
  Fixed: requests>=2.25.0 -> requests>=2.25.0,<3.0.0
  Fixed: numpy>=1.20.0 -> numpy>=1.20.0,<2.0.0
Fixed: Upper bounds have been added where possible.

Fixing: Sorting dependency groups...
Fixed: Dependency groups have been sorted.

Changes have been written to pyproject.toml
```

## Configuration

Pinnochio can be configured via the `[tool.pinnochio]` section in your
`pyproject.toml`:

```toml
[tool.pinnochio]
pinning-strategy = "major"  # Default: "major"
```

### Pinning Strategies

The `pinning-strategy` option controls how upper bounds are added to
dependencies. You can set it in your config file or override it with the
`--pinning-strategy` CLI flag:

- **`"major"`** (default): Allows minor and patch updates within the same major
  version
  - Example: `>=1.2.3` becomes `>=1.2.3,<2.0.0`
  - Follows semantic versioning: breaking changes at major version boundaries
  - Recommended for most projects

- **`"minor"`**: Only allows patch updates within the same minor version
  - Example: `>=1.2.3` becomes `>=1.2.3,<1.3.0`
  - More restrictive, useful for projects requiring high stability
  - Prevents feature additions that might affect behavior

- **`"patch"`**: No automatic updates, only the exact patch version
  - Example: `>=1.2.3` becomes `>=1.2.3,<1.2.4`
  - Most restrictive, useful for critical production systems
  - Requires manual version bumps for any updates

**Note:** The `--pinning-strategy` CLI flag always takes precedence over the
config file setting.

## Checks Performed

1. **Upper Bound Pinning**: Dependencies with only lower bounds (e.g.,
  `>=1.0.0`) are flagged and can be auto-fixed to include upper bounds based on
  your configured pinning strategy

2. **Dependency Sorting**: All dependency groups must be alphabetically sorted

3. **Version Consistency**: The same package must have identical version
   constraints across all dependency groups

4. **No Redundancy**: Dependencies in the core `dependencies` list should not be
   duplicated in `optional-dependencies` or `dev` groups

## Pre-commit Hook

Add pinnochio to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/BlakeJC94/pinnochio
    rev: v0.1.0  # Use the latest version
    hooks:
      - id: pinnochio
```

This will run `pinnochio` automatically whenever you commit changes to
`pyproject.toml`. If issues are found, the commit will be blocked until they're
fixed.

To automatically fix issues during pre-commit, you can pass the `--fix` flag:

```yaml
repos:
  - repo: https://github.com/anomalyco/pinnochio
    rev: v0.1.0
    hooks:
      - id: pinnochio
        args: [--fix]
```

## Requirements

* Python >=3.11
* `pyproject.toml` with UV-style dependency groups

## License

MIT

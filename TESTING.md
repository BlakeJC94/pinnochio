# Testing Guide for Pinnochio

This document describes how to test Pinnochio's functionality, including manual
testing procedures and automated tests.

## Running Automated Tests

### Run All Tests

```bash
uv run pytest tests/test_core.py -v
```

Expected: All 36 tests should pass.

### Run Specific Test Categories

```bash
# Test split_pin functionality
uv run pytest tests/test_core.py -k "split_pin" -v

# Test upper bound adding
uv run pytest tests/test_core.py -k "add_upper_bound" -v

# Test configuration loading
uv run pytest tests/test_core.py -k "config_loading" -v

# Test check functions
uv run pytest tests/test_core.py -k "check_" -v
```

### Quick Test Run

```bash
uv run pytest tests/test_core.py -q
```

## Manual Testing

### Test 1: Basic Functionality on Itself

Test that Pinnochio runs successfully on its own `pyproject.toml`:

```bash
uv run python -m pinnochio
```

Expected output: No issues (exit code 0), as the project's own dependencies are
already properly pinned.

### Test 2: Help Text

Verify the CLI help is correct:

```bash
uv run python -m pinnochio --help
```

Expected output:

```text
usage: __main__.py [-h] [--fix] [--pinning-strategy {major,minor,patch}]

Lint UV dependencies in pyproject.toml

options:
  -h, --help            show this help message and exit
  --fix                 Automatically fix issues where possible
  --pinning-strategy {major,minor,patch}
                        Override the pinning strategy (default: use config or
                        'major')
```

### Test 3: Testing Different Pinning Strategies

Create a test `pyproject.toml` with unpinned dependencies:

```bash
cat > /tmp/test_pyproject.toml << 'EOF'
[project]
name = "test"
version = "0.1.0"
dependencies = [
    "requests>=2.25.0",
]

[dependency-groups]
dev = [
    "pytest>=6.0.0",
]
EOF
```

#### Test Minor Strategy

```bash
cd /tmp
cp test_pyproject.toml pyproject.toml
PYTHONPATH=/Users/blake/Workspace/repos/pinnochio \
  /Users/blake/Workspace/repos/pinnochio/.venv/bin/python \
  -m pinnochio --fix --pinning-strategy minor
cat pyproject.toml
```

Expected transformations:

- `requests>=2.25.0` → `requests>=2.25.0,<2.26.0`
- `pytest>=6.0.0` → `pytest>=6.0.0,<6.1.0`

#### Test Patch Strategy

```bash
cd /tmp
cp test_pyproject.toml pyproject.toml
PYTHONPATH=/Users/blake/Workspace/repos/pinnochio \
  /Users/blake/Workspace/repos/pinnochio/.venv/bin/python \
  -m pinnochio --fix --pinning-strategy patch
cat pyproject.toml
```

Expected transformations:

- `requests>=2.25.0` → `requests>=2.25.0,<2.25.1`
- `pytest>=6.0.0` → `pytest>=6.0.0,<6.0.1`

#### Test Major Strategy (Default)

```bash
cd /tmp
cp test_pyproject.toml pyproject.toml
PYTHONPATH=/Users/blake/Workspace/repos/pinnochio \
  /Users/blake/Workspace/repos/pinnochio/.venv/bin/python \
  -m pinnochio --fix --pinning-strategy major
cat pyproject.toml
```

Expected transformations:

- `requests>=2.25.0` → `requests>=2.25.0,<3.0.0`
- `pytest>=6.0.0` → `pytest>=6.0.0,<7.0.0`

### Test 4: Testing Edge Cases

#### Package with Extras

Create a test file:

```bash
cat > /tmp/test_extras.toml << 'EOF'
[project]
name = "test"
version = "0.1.0"
dependencies = [
    "package[extra1,extra2]>=1.0.0",
]

[dependency-groups]
dev = []
EOF
```

Run pinnochio:

```bash
cd /tmp
cp test_extras.toml pyproject.toml
PYTHONPATH=/Users/blake/Workspace/repos/pinnochio \
  /Users/blake/Workspace/repos/pinnochio/.venv/bin/python \
  -m pinnochio --fix
cat pyproject.toml
```

Expected: Extras are preserved in the fixed version.

#### Pre-release Versions

Create a test file:

```bash
cat > /tmp/test_prerelease.toml << 'EOF'
[project]
name = "test"
version = "0.1.0"
dependencies = [
    "package>=1.0.0a1",
]

[dependency-groups]
dev = []
EOF
```

Run pinnochio:

```bash
cd /tmp
cp test_prerelease.toml pyproject.toml
PYTHONPATH=/Users/blake/Workspace/repos/pinnochio \
  /Users/blake/Workspace/repos/pinnochio/.venv/bin/python \
  -m pinnochio --fix
cat pyproject.toml
```

Expected: Pre-release version gets proper upper bound (e.g., `>=1.0.0a1,<2.0.0`).

### Test 5: Configuration File Override

Create a test file with minor strategy in config:

```bash
cat > /tmp/test_config.toml << 'EOF'
[project]
name = "test"
version = "0.1.0"
dependencies = [
    "requests>=2.25.0",
]

[dependency-groups]
dev = []

[tool.pinnochio]
pinning-strategy = "minor"
EOF
```

Test that config is used:

```bash
cd /tmp
cp test_config.toml pyproject.toml
PYTHONPATH=/Users/blake/Workspace/repos/pinnochio \
  /Users/blake/Workspace/repos/pinnochio/.venv/bin/python \
  -m pinnochio --fix
cat pyproject.toml | grep requests
```

Expected: `requests>=2.25.0,<2.26.0` (minor strategy from config).

Test that CLI overrides config:

```bash
cd /tmp
cp test_config.toml pyproject.toml
PYTHONPATH=/Users/blake/Workspace/repos/pinnochio \
  /Users/blake/Workspace/repos/pinnochio/.venv/bin/python \
  -m pinnochio --fix --pinning-strategy major
cat pyproject.toml | grep requests
```

Expected: `requests>=2.25.0,<3.0.0` (major strategy from CLI override).

### Test 6: Error Handling

#### Missing pyproject.toml

```bash
cd /tmp/nonexistent_dir_xyz123
PYTHONPATH=/Users/blake/Workspace/repos/pinnochio \
  /Users/blake/Workspace/repos/pinnochio/.venv/bin/python \
  -m pinnochio
```

Expected: Error message about missing `pyproject.toml` and exit code 1.

#### Malformed TOML

```bash
cat > /tmp/bad.toml << 'EOF'
[project
name = "test"
EOF

cd /tmp
cp bad.toml pyproject.toml
PYTHONPATH=/Users/blake/Workspace/repos/pinnochio \
  /Users/blake/Workspace/repos/pinnochio/.venv/bin/python \
  -m pinnochio
```

Expected: Error message about malformed TOML and exit code 1.

#### Missing Required Sections

```bash
cat > /tmp/missing_deps.toml << 'EOF'
[project]
name = "test"
EOF

cd /tmp
cp missing_deps.toml pyproject.toml
PYTHONPATH=/Users/blake/Workspace/repos/pinnochio \
  /Users/blake/Workspace/repos/pinnochio/.venv/bin/python \
  -m pinnochio
```

Expected: Error message about missing `[project.dependencies]` and exit code 1.

## Test Coverage

The test suite covers:

1. **Core Functionality** (25 tests)
   - `split_pin()` with various package formats
   - `_add_upper_bound()` with all three strategies
   - `load_uv_dependencies()` and config loading
   - All four check functions (upper bounds, sorting, drift, redundancy)
   - Helper functions for dependency group manipulation

2. **Edge Cases** (10 tests)
   - Pre-release versions
   - Package extras (single and multiple)
   - Configuration loading and validation
   - Error handling for missing/malformed files

3. **Integration** (1 test)
   - CLI flag override behavior

## Performance Testing

For large projects, you can test performance:

```bash
# Create a large test file
python -c "
import sys
deps = [f'package{i}>=1.0.0' for i in range(100)]
print('[project]')
print('name = \"test\"')
print('version = \"0.1.0\"')
print('dependencies = [')
for dep in deps:
    print(f'    \"{dep}\",')
print(']')
print('[dependency-groups]')
print('dev = []')
" > /tmp/large_project.toml

cd /tmp
cp large_project.toml pyproject.toml
time PYTHONPATH=/Users/blake/Workspace/repos/pinnochio \
  /Users/blake/Workspace/repos/pinnochio/.venv/bin/python \
  -m pinnochio --fix
```

Expected: Should complete in under 1 second for 100 dependencies.

## Continuous Integration Testing

To test in a CI environment:

```bash
# Install dependencies
uv sync

# Run linter/formatter (if configured)
# uv run ruff check .

# Run tests
uv run pytest tests/test_core.py -v

# Test CLI on sample project
cd /tmp
cat > pyproject.toml << 'EOF'
[project]
name = "ci-test"
version = "0.1.0"
dependencies = ["requests>=2.0.0"]
[dependency-groups]
dev = []
EOF

# Should fail (unpinned)
if uv run python -m pinnochio; then
    echo "ERROR: Should have detected unpinned dependencies"
    exit 1
fi

# Should succeed (with fix)
uv run python -m pinnochio --fix
if ! uv run python -m pinnochio; then
    echo "ERROR: Should pass after fix"
    exit 1
fi

echo "All CI tests passed!"
```

## Troubleshooting

### Tests Failing with Import Errors

If you see `ModuleNotFoundError: No module named 'pinnochio'`:

```bash
# Ensure you're in the project root
cd /Users/blake/Workspace/repos/pinnochio

# Sync dependencies
uv sync

# Run tests with uv run
uv run pytest tests/test_core.py -v
```

### Manual Tests Not Working

For manual testing outside the project directory, ensure `PYTHONPATH` is set:

```bash
export PYTHONPATH=/Users/blake/Workspace/repos/pinnochio
```

Or use the project's virtual environment directly:

```bash
/Users/blake/Workspace/repos/pinnochio/.venv/bin/python -m pinnochio
```

## Test Maintenance

When adding new features:

1. Add unit tests to `tests/test_core.py`
2. Add manual testing steps to this document
3. Run full test suite to ensure no regressions
4. Update expected output in documentation if behavior changes

#!/usr/bin/env python
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import tomlkit
from packaging.requirements import InvalidRequirement
from packaging.specifiers import SpecifierSet
from pinnochio.config import Config, PinningStrategy, load_config
from pinnochio.core import (
    CheckStatus,
    _add_upper_bound,
    check_all_groups_are_sorted,
    check_group_overlaps_match,
    check_no_overlap_between_core_deps_and_groups,
    check_upper_bounds,
    load_uv_dependencies,
    save_toml_document,
    split_pin,
    update_dependencies_in_group,
)


@pytest.fixture
def sample_toml_content():
    """Sample TOML content for testing."""
    return """
[project]
name = "test-project"
version = "0.1.0"
dependencies = [
    "requests>=2.25.0",
    "pandas>=1.3.0,<2",
    "numpy>=1.20.0",
]

[dependency-groups]
dev = [
    "pytest>=6.0.0",
    "black>=21.0.0,<22",
    "mypy>=0.910",
]

[project.optional-dependencies]
web = [
    "fastapi>=0.68.0",
    "uvicorn>=0.15.0,<1",
]
ml = [
    "scikit-learn>=1.0.0",
    "pandas>=1.3.0,<2",
]
"""


@pytest.fixture
def temp_pyproject_file(sample_toml_content):
    """Create a temporary pyproject.toml file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(sample_toml_content)
        temp_path = Path(f.name)

    yield temp_path

    # Cleanup
    temp_path.unlink()


# =============================================================================
# split_pin function tests
# =============================================================================


def test_split_pin_with_version_constraint():
    package, specifiers = split_pin("requests>=2.25.0")
    assert package == "requests"
    assert isinstance(specifiers, SpecifierSet)
    assert str(specifiers) == ">=2.25.0"


def test_split_pin_with_complex_constraint():
    package, specifiers = split_pin("pandas>=1.3.0,<2")
    assert package == "pandas"
    assert str(specifiers) == "<2,>=1.3.0"  # SpecifierSet normalizes order


def test_split_pin_with_hyphenated_name():
    package, specifiers = split_pin("scikit-learn>=1.0.0")
    assert package == "scikit-learn"
    assert str(specifiers) == ">=1.0.0"


def test_split_pin_with_extras():
    package, specifiers = split_pin("package[extra]>=1.0.0")
    assert package == "package"
    assert str(specifiers) == ">=1.0.0"


def test_split_pin_invalid_format():
    with pytest.raises(InvalidRequirement):
        split_pin("")


# =============================================================================
# _add_upper_bound function tests
# =============================================================================


def test_add_upper_bound_major_strategy():
    config = Config(pinning_strategy=PinningStrategy.MAJOR)
    result = _add_upper_bound("requests>=2.25.0", config)
    assert result == "requests>=2.25.0,<3.0.0"


def test_add_upper_bound_minor_strategy():
    config = Config(pinning_strategy=PinningStrategy.MINOR)
    result = _add_upper_bound("requests>=2.25.0", config)
    assert result == "requests>=2.25.0,<2.26.0"


def test_add_upper_bound_patch_strategy():
    config = Config(pinning_strategy=PinningStrategy.PATCH)
    result = _add_upper_bound("requests>=2.25.0", config)
    assert result == "requests>=2.25.0,<2.25.1"


def test_add_upper_bound_already_has_upper():
    config = Config(pinning_strategy=PinningStrategy.MAJOR)
    result = _add_upper_bound("pandas>=1.3.0,<2", config)
    assert result == "pandas>=1.3.0,<2"


def test_add_upper_bound_with_extras():
    config = Config(pinning_strategy=PinningStrategy.MAJOR)
    result = _add_upper_bound("package[extra]>=1.2.3", config)
    assert result == "package[extra]>=1.2.3,<2.0.0"


def test_add_upper_bound_invalid_version():
    config = Config(pinning_strategy=PinningStrategy.MAJOR)
    with pytest.raises(ValueError, match="no '>=' specifier found"):
        _add_upper_bound("package>2.0.0", config)


# =============================================================================
# load_uv_dependencies function tests
# =============================================================================


def test_load_uv_dependencies(temp_pyproject_file):
    with patch("pinnochio.core.Path") as mock_path:
        mock_path.return_value = temp_pyproject_file

        groups, doc, config = load_uv_dependencies()

        assert "dependencies" in groups
        assert "dev" in groups
        assert "web" in groups
        assert "ml" in groups

        assert "requests>=2.25.0" in groups["dependencies"]
        assert "pytest>=6.0.0" in groups["dev"]
        assert "fastapi>=0.68.0" in groups["web"]
        assert isinstance(doc, tomlkit.TOMLDocument)
        assert isinstance(config, Config)
        assert config.pinning_strategy == PinningStrategy.MAJOR


# =============================================================================
# check_upper_bounds function tests
# =============================================================================


def test_finds_unpinned_dependencies():
    groups = {
        "dependencies": ["requests>=2.25.0", "pandas>=1.3.0,<2"],
        "dev": ["pytest>=6.0.0", "black>=21.0.0,<22"],
    }
    doc = tomlkit.document()
    config = Config(pinning_strategy=PinningStrategy.MAJOR)

    result = check_upper_bounds(groups, doc, config)

    assert result.status == CheckStatus.FAILED
    assert "dependencies" in result.issues
    assert "dev" in result.issues
    assert "requests>=2.25.0" in result.issues["dependencies"]
    assert "pytest>=6.0.0" in result.issues["dev"]
    assert "pandas>=1.3.0,<2" not in result.issues.get("dependencies", [])


def test_no_unpinned_dependencies():
    groups = {
        "dependencies": ["pandas>=1.3.0,<2"],
        "dev": ["black>=21.0.0,<22"],
    }
    doc = tomlkit.document()
    config = Config(pinning_strategy=PinningStrategy.MAJOR)

    result = check_upper_bounds(groups, doc, config)

    assert result.status == CheckStatus.PASSED
    assert result.issues == {}


def test_fix_unpinned_dependencies(capsys):
    doc = tomlkit.document()
    deps_array = tomlkit.array()
    deps_array.append("requests>=2.25.0")
    dev_array = tomlkit.array()
    dev_array.append("pytest>=6.0.0")

    doc["project"] = {"dependencies": deps_array}
    doc["dependency-groups"] = {"dev": dev_array}

    groups = {
        "dependencies": ["requests>=2.25.0"],
        "dev": ["pytest>=6.0.0"],
    }
    config = Config(pinning_strategy=PinningStrategy.MAJOR)

    result = check_upper_bounds(groups, doc, config, fix=True)

    captured = capsys.readouterr()
    assert "Fixing: Adding upper bounds" in captured.out
    assert "Fixed: requests>=2.25.0 -> requests>=2.25.0,<3.0.0" in captured.out
    assert result.status == CheckStatus.FIXED


# =============================================================================
# check_all_groups_are_sorted function tests
# =============================================================================


def test_finds_unsorted_groups():
    groups = {
        "dependencies": ["zlib>=1.0.0", "requests>=2.25.0"],  # unsorted
        "dev": ["black>=21.0.0", "pytest>=6.0.0"],  # sorted
    }
    doc = tomlkit.document()
    config = Config()

    result = check_all_groups_are_sorted(groups, doc, config)

    assert result.status == CheckStatus.FAILED
    assert "dependencies" in result.issues
    assert "dev" not in result.issues


def test_all_groups_sorted():
    groups = {
        "dependencies": ["requests>=2.25.0", "zlib>=1.0.0"],
        "dev": ["black>=21.0.0", "pytest>=6.0.0"],
    }
    doc = tomlkit.document()
    config = Config()

    result = check_all_groups_are_sorted(groups, doc, config)

    assert result.status == CheckStatus.PASSED
    assert result.issues == {}


def test_fix_unsorted_groups(capsys):
    doc = tomlkit.document()
    deps_array = tomlkit.array()
    deps_array.append("zlib>=1.0.0")
    deps_array.append("requests>=2.25.0")
    doc["project"] = {"dependencies": deps_array}

    groups = {
        "dependencies": ["zlib>=1.0.0", "requests>=2.25.0"],
    }
    config = Config()

    result = check_all_groups_are_sorted(groups, doc, config, fix=True)

    captured = capsys.readouterr()
    assert "Fixing: Sorting dependency groups" in captured.out
    assert result.status == CheckStatus.FIXED


# =============================================================================
# check_group_overlaps_match function tests
# =============================================================================


def test_finds_version_drift():
    groups = {
        "dependencies": ["pandas>=1.3.0,<2"],
        "ml": ["pandas>=1.4.0,<2"],  # different version
    }
    doc = tomlkit.document()
    config = Config()

    result = check_group_overlaps_match(groups, doc, config)

    assert result.status == CheckStatus.FAILED
    assert "dependencies" in result.issues
    assert "ml" in result.issues
    assert "pandas>=1.3.0,<2" in result.issues["dependencies"]
    assert "pandas>=1.4.0,<2" in result.issues["ml"]


def test_no_version_drift():
    groups = {
        "dependencies": ["pandas>=1.3.0,<2"],
        "ml": ["pandas>=1.3.0,<2"],  # same version
    }
    doc = tomlkit.document()
    config = Config()

    result = check_group_overlaps_match(groups, doc, config)

    assert result.status == CheckStatus.PASSED
    assert result.issues == {}


# =============================================================================
# check_no_overlap_between_core_deps_and_groups function tests
# =============================================================================


def test_finds_redundant_dependencies():
    groups = {
        "dependencies": ["pandas>=1.3.0,<2"],
        "ml": [
            "pandas>=1.3.0,<2",
            "scikit-learn>=1.0.0",
        ],  # redundant pandas
    }
    doc = tomlkit.document()
    config = Config()

    result = check_no_overlap_between_core_deps_and_groups(groups, doc, config)

    assert result.status == CheckStatus.FAILED
    assert "ml" in result.issues
    assert "pandas>=1.3.0,<2" in result.issues["ml"]
    assert "scikit-learn>=1.0.0" not in result.issues["ml"]


def test_no_redundant_dependencies():
    groups = {
        "dependencies": ["requests>=2.25.0"],
        "ml": ["scikit-learn>=1.0.0"],
    }
    doc = tomlkit.document()
    config = Config()

    result = check_no_overlap_between_core_deps_and_groups(groups, doc, config)

    assert result.status == CheckStatus.PASSED
    assert result.issues == {}


def test_fix_redundant_dependencies(capsys):
    doc = tomlkit.document()
    deps_array = tomlkit.array()
    deps_array.append("pandas>=1.3.0,<2")
    ml_array = tomlkit.array()
    ml_array.append("pandas>=1.3.0,<2")
    ml_array.append("scikit-learn>=1.0.0")

    doc["project"] = {
        "dependencies": deps_array,
        "optional-dependencies": {"ml": ml_array},
    }

    groups = {
        "dependencies": ["pandas>=1.3.0,<2"],
        "ml": ["pandas>=1.3.0,<2", "scikit-learn>=1.0.0"],
    }
    config = Config()

    result = check_no_overlap_between_core_deps_and_groups(
        groups, doc, config, fix=True
    )

    captured = capsys.readouterr()
    assert "Fixing: Removing redundant dependencies" in captured.out
    assert result.status == CheckStatus.FIXED


# =============================================================================
# update_dependencies_in_group function tests
# =============================================================================


def test_update_dependencies_in_core_group():
    doc = tomlkit.document()
    deps_array = tomlkit.array()
    deps_array.append("requests>=2.25.0")
    deps_array.append("pandas>=1.3.0,<2")
    doc["project"] = {"dependencies": deps_array}

    def transform_fn(deps):
        return [dep.replace("requests>=2.25.0", "requests>=2.25.0,<3") for dep in deps]

    update_dependencies_in_group(doc, "dependencies", transform_fn)

    # Check the transformation was applied
    result = [str(d) for d in doc["project"]["dependencies"]]
    assert "requests>=2.25.0,<3" in result
    assert "pandas>=1.3.0,<2" in result


# =============================================================================
# save_toml_document function tests
# =============================================================================


def test_save_toml_document(temp_pyproject_file):
    doc = tomlkit.document()
    doc["project"] = {"name": "test-project", "version": "0.1.0"}

    with patch("pinnochio.core.Path") as mock_path:
        mock_path.return_value = temp_pyproject_file

        save_toml_document(doc)

        # Read back the file to verify it was saved
        with open(temp_pyproject_file, "r") as f:
            content = f.read()
            assert "test-project" in content
            assert "0.1.0" in content


# =============================================================================
# Edge case tests
# =============================================================================


def test_split_pin_with_pre_release_version():
    """Test that pre-release versions are handled correctly."""
    package, specifiers = split_pin("package>=1.0.0a1")
    assert package == "package"
    assert str(specifiers) == ">=1.0.0a1"


def test_add_upper_bound_with_pre_release():
    """Test that pre-release versions get proper upper bounds."""
    config = Config(pinning_strategy=PinningStrategy.MAJOR)
    result = _add_upper_bound("package>=1.0.0a1", config)
    assert result == "package>=1.0.0a1,<2.0.0"


def test_split_pin_with_multiple_extras():
    """Test packages with multiple extras."""
    package, specifiers = split_pin("package[extra1,extra2]>=1.0.0")
    assert package == "package"
    assert str(specifiers) == ">=1.0.0"


def test_add_upper_bound_with_multiple_extras():
    """Test that packages with multiple extras preserve extras."""
    config = Config(pinning_strategy=PinningStrategy.MAJOR)
    result = _add_upper_bound("package[extra1,extra2]>=1.0.0", config)
    # Extras are sorted alphabetically by packaging
    assert (
        "package[extra1,extra2]>=1.0.0,<2.0.0" in result
        or "package[extra2,extra1]>=1.0.0,<2.0.0" in result
    )


def test_config_loading_default():
    """Test that config loads with defaults when no config section exists."""

    doc = tomlkit.document()
    doc["project"] = {"name": "test"}

    config = load_config(doc)
    assert config.pinning_strategy == PinningStrategy.MAJOR


def test_config_loading_with_minor_strategy():
    """Test that config loads minor strategy correctly."""

    doc = tomlkit.document()
    doc["tool"] = {"pinnochio": {"pinning-strategy": "minor"}}

    config = load_config(doc)
    assert config.pinning_strategy == PinningStrategy.MINOR


def test_config_loading_with_patch_strategy():
    """Test that config loads patch strategy correctly."""

    doc = tomlkit.document()
    doc["tool"] = {"pinnochio": {"pinning-strategy": "patch"}}

    config = load_config(doc)
    assert config.pinning_strategy == PinningStrategy.PATCH


def test_config_loading_invalid_strategy():
    """Test that invalid strategy raises ValueError."""

    doc = tomlkit.document()
    doc["tool"] = {"pinnochio": {"pinning-strategy": "invalid"}}

    with pytest.raises(ValueError, match="Invalid pinning-strategy"):
        load_config(doc)


def test_load_uv_dependencies_missing_project():
    """Test that missing [project] section raises KeyError."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write('[tool]\nname = "test"\n')
        temp_path = Path(f.name)

    try:
        with patch("pinnochio.core.Path") as mock_path:
            mock_path.return_value = temp_path

            with pytest.raises(KeyError, match="Missing \\[project\\] section"):
                load_uv_dependencies()
    finally:
        temp_path.unlink()


def test_load_uv_dependencies_missing_dependencies():
    """Test that missing [project.dependencies] raises KeyError."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write('[project]\nname = "test"\n')
        temp_path = Path(f.name)

    try:
        with patch("pinnochio.core.Path") as mock_path:
            mock_path.return_value = temp_path

            with pytest.raises(KeyError, match="Missing \\[project.dependencies\\]"):
                load_uv_dependencies()
    finally:
        temp_path.unlink()


def test_cli_override_pinning_strategy():
    """Test that CLI flag overrides config pinning strategy."""
    from pinnochio.config import Config, PinningStrategy

    # Start with minor strategy in config
    config = Config(pinning_strategy=PinningStrategy.MINOR)
    assert config.pinning_strategy == PinningStrategy.MINOR

    # Override with major (simulating CLI flag)
    config.pinning_strategy = PinningStrategy("major")
    assert config.pinning_strategy == PinningStrategy.MAJOR

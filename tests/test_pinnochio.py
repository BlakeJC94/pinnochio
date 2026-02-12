#!/usr/bin/env python

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import tomlkit

from scripts.pinnochio import (
    _add_upper_bound,
    _fix_dependencies_in_group,
    check_all_dependencies_are_pinned_above,
    check_all_groups_are_sorted,
    check_group_overlaps_match,
    check_no_overlap_between_core_deps_and_groups,
    load_uv_dependencies,
    save_toml_document,
    split_pin,
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
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".toml", delete=False
    ) as f:
        f.write(sample_toml_content)
        temp_path = Path(f.name)

    yield temp_path

    # Cleanup
    temp_path.unlink()


# =============================================================================
# split_pin function tests
# =============================================================================


def test_split_pin_with_version_constraint():
    package, constraint = split_pin("requests>=2.25.0")
    assert package == "requests"
    assert constraint == ">=2.25.0"


def test_split_pin_with_complex_constraint():
    package, constraint = split_pin("pandas>=1.3.0,<2")
    assert package == "pandas"
    assert constraint == ">=1.3.0,<2"


def test_split_pin_with_hyphenated_name():
    package, constraint = split_pin("scikit-learn>=1.0.0")
    assert package == "scikit-learn"
    assert constraint == ">=1.0.0"


def test_split_pin_invalid_format():
    with pytest.raises(ValueError, match="Bad pin"):
        split_pin("")


# =============================================================================
# _add_upper_bound function tests
# =============================================================================


def test_add_upper_bound_simple():
    result = _add_upper_bound("requests>=2.25.0")
    assert result == "requests>=2.25.0,<2.26.0"


def test_add_upper_bound_already_has_upper():
    result = _add_upper_bound("pandas>=1.3.0,<2")
    assert result == "pandas>=1.3.0,<2"


def test_add_upper_bound_major_version_increment():
    result = _add_upper_bound("numpy>=1.20.3")
    assert result == "numpy>=1.20.3,<1.21.0"


def test_add_upper_bound_double_digit_major():
    result = _add_upper_bound("package>=12.5.1")
    assert result == "package>=12.5.1,<12.6.0"


def test_add_upper_bound_invalid_version():
    with pytest.raises(ValueError, match="Cannot parse version constraint"):
        _add_upper_bound("package>2.0.0")


# =============================================================================
# load_uv_dependencies function tests
# =============================================================================


def test_load_uv_dependencies(temp_pyproject_file):
    with patch("scripts.pinnochio.Path") as mock_path:
        mock_path.return_value = temp_pyproject_file

        groups, doc = load_uv_dependencies()

        assert "dependencies" in groups
        assert "dev" in groups
        assert "web" in groups
        assert "ml" in groups

        assert "requests>=2.25.0" in groups["dependencies"]
        assert "pytest>=6.0.0" in groups["dev"]
        assert "fastapi>=0.68.0" in groups["web"]
        assert isinstance(doc, tomlkit.TOMLDocument)


# =============================================================================
# check_all_dependencies_are_pinned_above function tests
# =============================================================================


def test_finds_unpinned_dependencies():
    groups = {
        "dependencies": ["requests>=2.25.0", "pandas>=1.3.0,<2"],
        "dev": ["pytest>=6.0.0", "black>=21.0.0,<22"],
    }
    doc = tomlkit.document()

    result, was_fixed = check_all_dependencies_are_pinned_above(groups, doc)

    assert "dependencies" in result
    assert "dev" in result
    assert "requests>=2.25.0" in result["dependencies"]
    assert "pytest>=6.0.0" in result["dev"]
    assert "pandas>=1.3.0,<2" not in result["dependencies"]


def test_no_unpinned_dependencies():
    groups = {
        "dependencies": ["pandas>=1.3.0,<2"],
        "dev": ["black>=21.0.0,<22"],
    }
    doc = tomlkit.document()

    result, was_fixed = check_all_dependencies_are_pinned_above(groups, doc)

    assert result == {}


def test_fix_unpinned_dependencies(capsys):
    doc = tomlkit.document()
    doc["project"] = {"dependencies": tomlkit.array(["requests>=2.25.0"])}
    doc["dependency-groups"] = {"dev": tomlkit.array(["pytest>=6.0.0"])}

    groups = {
        "dependencies": ["requests>=2.25.0"],
        "dev": ["pytest>=6.0.0"],
    }

    _ = check_all_dependencies_are_pinned_above(groups, doc, fix=True)

    captured = capsys.readouterr()
    assert "Fixing: Adding upper bounds" in captured.out
    assert (
        "Fixed: requests>=2.25.0 -> requests>=2.25.0,<2.26.0" in captured.out
    )
    assert doc["project"]["dependencies"][0] == "requests>=2.25.0,<2.26.0"


# =============================================================================
# check_all_groups_are_sorted function tests
# =============================================================================


def test_finds_unsorted_groups():
    groups = {
        "dependencies": ["zlib>=1.0.0", "requests>=2.25.0"],  # unsorted
        "dev": ["black>=21.0.0", "pytest>=6.0.0"],  # sorted
    }
    doc = tomlkit.document()

    result, was_fixed = check_all_groups_are_sorted(groups, doc)

    assert "dependencies" in result
    assert "dev" not in result


def test_all_groups_sorted():
    groups = {
        "dependencies": ["requests>=2.25.0", "zlib>=1.0.0"],
        "dev": ["black>=21.0.0", "pytest>=6.0.0"],
    }
    doc = tomlkit.document()

    result, was_fixed = check_all_groups_are_sorted(groups, doc)

    assert result == {}


def test_fix_unsorted_groups(capsys):
    doc = tomlkit.document()
    doc["project"] = {
        "dependencies": tomlkit.array(["zlib>=1.0.0", "requests>=2.25.0"])
    }

    groups = {
        "dependencies": ["zlib>=1.0.0", "requests>=2.25.0"],
    }

    _ = check_all_groups_are_sorted(groups, doc, fix=True)

    captured = capsys.readouterr()
    assert "Fixing: Sorting dependency groups" in captured.out
    assert doc["project"]["dependencies"][0] == "requests>=2.25.0"
    assert doc["project"]["dependencies"][1] == "zlib>=1.0.0"


# =============================================================================
# check_group_overlaps_match function tests
# =============================================================================


def test_finds_version_drift():
    groups = {
        "dependencies": ["pandas>=1.3.0,<2"],
        "ml": ["pandas>=1.4.0,<2"],  # different version
    }
    doc = tomlkit.document()

    result, was_fixed = check_group_overlaps_match(groups, doc)

    assert "dependencies" in result
    assert "ml" in result
    assert "pandas>=1.3.0,<2" in result["dependencies"]
    assert "pandas>=1.4.0,<2" in result["ml"]


def test_no_version_drift():
    groups = {
        "dependencies": ["pandas>=1.3.0,<2"],
        "ml": ["pandas>=1.3.0,<2"],  # same version
    }
    doc = tomlkit.document()

    result, was_fixed = check_group_overlaps_match(groups, doc)

    assert result == {}


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

    result, was_dixed = check_no_overlap_between_core_deps_and_groups(
        groups, doc
    )

    assert "ml" in result
    assert "pandas>=1.3.0,<2" in result["ml"]
    assert "scikit-learn>=1.0.0" not in result["ml"]


def test_no_redundant_dependencies():
    groups = {
        "dependencies": ["requests>=2.25.0"],
        "ml": ["scikit-learn>=1.0.0"],
    }
    doc = tomlkit.document()

    result, was_fixed = check_no_overlap_between_core_deps_and_groups(
        groups, doc
    )

    assert result == {}


def test_fix_redundant_dependencies(capsys):
    doc = tomlkit.document()
    doc["project"] = {
        "dependencies": tomlkit.array(["pandas>=1.3.0,<2"]),
        "optional-dependencies": {
            "ml": tomlkit.array(["pandas>=1.3.0,<2", "scikit-learn>=1.0.0"])
        },
    }

    groups = {
        "dependencies": ["pandas>=1.3.0,<2"],
        "ml": ["pandas>=1.3.0,<2", "scikit-learn>=1.0.0"],
    }

    check_no_overlap_between_core_deps_and_groups(groups, doc, fix=True)

    captured = capsys.readouterr()
    assert "Fixing: Removing redundant dependencies" in captured.out

    ml_deps = list(doc["project"]["optional-dependencies"]["ml"])
    assert "pandas>=1.3.0,<2" not in ml_deps
    assert "scikit-learn>=1.0.0" in ml_deps


# =============================================================================
# _fix_dependencies_in_group function tests
# =============================================================================


def test_fix_dependencies_in_core_group(capsys):
    doc = tomlkit.document()
    doc["project"] = {
        "dependencies": tomlkit.array(["requests>=2.25.0", "pandas>=1.3.0,<2"])
    }

    def mock_fix_function(pin):
        if pin == "requests>=2.25.0":
            return "requests>=2.25.0,<3"
        return pin

    _fix_dependencies_in_group(
        doc, "dependencies", ["requests>=2.25.0"], mock_fix_function
    )

    captured = capsys.readouterr()
    assert "Fixed: requests>=2.25.0 -> requests>=2.25.0,<3" in captured.out
    assert doc["project"]["dependencies"][0] == "requests>=2.25.0,<3"
    assert doc["project"]["dependencies"][1] == "pandas>=1.3.0,<2"


def test_fix_dependencies_handles_exceptions(capsys):
    doc = tomlkit.document()
    doc["project"] = {"dependencies": tomlkit.array(["bad-package"])}

    def failing_fix_function(pin):
        raise ValueError("Cannot fix this")

    _fix_dependencies_in_group(
        doc, "dependencies", ["bad-package"], failing_fix_function
    )

    captured = capsys.readouterr()
    assert "Could not fix bad-package: Cannot fix this" in captured.out
    assert doc["project"]["dependencies"][0] == "bad-package"


# =============================================================================
# save_toml_document function tests
# =============================================================================


def test_save_toml_document(temp_pyproject_file):
    doc = tomlkit.document()
    doc["project"] = {"name": "test-project", "version": "0.1.0"}

    with patch("scripts.pinnochio.Path") as mock_path:
        mock_path.return_value = temp_pyproject_file

        save_toml_document(doc)

        # Read back the file to verify it was saved
        with open(temp_pyproject_file, "r") as f:
            content = f.read()
            assert "test-project" in content
            assert "0.1.0" in content


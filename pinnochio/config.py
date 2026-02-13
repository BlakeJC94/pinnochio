#!/usr/bin/env python

from dataclasses import dataclass
from enum import Enum

import tomlkit
from tomlkit.items import Table


class PinningStrategy(Enum):
    """Strategy for adding upper bounds to version constraints."""

    MAJOR = "major"  # >=1.2.3 -> >=1.2.3,<2.0.0
    MINOR = "minor"  # >=1.2.3 -> >=1.2.3,<1.3.0
    PATCH = "patch"  # >=1.2.3 -> >=1.2.3,<1.2.4


@dataclass
class Config:
    """Configuration for pinnochio."""

    pinning_strategy: PinningStrategy = PinningStrategy.MAJOR


def load_config(doc: tomlkit.TOMLDocument) -> Config:
    """Load configuration from pyproject.toml.

    Args:
        doc: The parsed TOML document

    Returns:
        Config object with settings from [tool.pinnochio] or defaults

    Raises:
        ValueError: If configuration values are invalid
    """
    # Return defaults if no config section exists
    if "tool" not in doc or "pinnochio" not in doc["tool"]:
        return Config()

    tool_table = doc["tool"]
    config_table = tool_table["pinnochio"]

    if not isinstance(config_table, Table):
        raise ValueError("[tool.pinnochio] must be a table in pyproject.toml")

    # Extract pinning strategy
    pinning_strategy = PinningStrategy.MAJOR
    if "pinning-strategy" in config_table:
        strategy_str = str(config_table["pinning-strategy"])
        try:
            pinning_strategy = PinningStrategy(strategy_str)
        except ValueError:
            valid_values = [s.value for s in PinningStrategy]
            raise ValueError(
                f"Invalid pinning-strategy '{strategy_str}'. "
                f"Must be one of: {', '.join(valid_values)}"
            ) from None

    return Config(pinning_strategy=pinning_strategy)

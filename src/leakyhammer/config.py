"""Loading and validating the YAML configs that describe sweeps."""

from pathlib import Path
from typing import Any, Dict, List, Set, Tuple, Union

import yaml


def load_yaml_config(
    config: Union[str, Path], config_dir: Path, allowed_keys: Set[str]
) -> Tuple[str, Dict[str, Any]]:
    """Reads a sweep config and returns its name and contents.

    "config" is a name looked up as "<config_dir>/<name>.yaml", or a path to a
    YAML file. The name is the file's stem. Raises "FileNotFoundError" if the
    file does not exist and "ValueError" for unknown top-level keys, so a
    misspelled option fails instead of being silently ignored.
    """
    path = Path(config)
    if not path.suffix:
        path = config_dir / f"{config}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"No sweep config at {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping of options")
    unknown = set(raw) - allowed_keys
    if unknown:
        raise ValueError(f"{path}: unknown key(s) {sorted(unknown)}")
    return path.stem, raw


def parse_overrides(pairs: List[str]) -> Dict[str, Any]:
    """Parses "key=value" strings; values are read as YAML scalars."""
    overrides: Dict[str, Any] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep:
            raise ValueError(f"Expected key=value, got '{pair}'")
        overrides[key] = yaml.safe_load(value)
    return overrides

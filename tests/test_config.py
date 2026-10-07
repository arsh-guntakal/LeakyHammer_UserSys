"""Sweep config loading and defense variants."""

from pathlib import Path

import pytest

from leakyhammer import config
from leakyhammer.defenses import Variant, parse_variant


def _write(tmp_path: Path, text: str) -> Path:
    """Writes a YAML file and returns its path."""
    path = tmp_path / "c.yaml"
    path.write_text(text)
    return path


@pytest.mark.unit
def test_load_by_path_returns_stem_and_contents(tmp_path: Path) -> None:
    """A config given by path is named after its file."""
    name, raw = config.load_yaml_config(
        _write(tmp_path, "variants: []\nmsg_bytes: 5"),
        tmp_path,
        {"variants", "msg_bytes"},
    )
    assert (name, raw["msg_bytes"]) == ("c", 5)


@pytest.mark.unit
def test_load_by_name_looks_in_the_config_dir(tmp_path: Path) -> None:
    """A bare name resolves to "<dir>/<name>.yaml"."""
    (tmp_path / "quick.yaml").write_text("variants: []")
    name, _ = config.load_yaml_config("quick", tmp_path, {"variants"})
    assert name == "quick"


@pytest.mark.unit
def test_load_rejects_missing_unknown_and_non_mapping(tmp_path: Path) -> None:
    """Missing files, misspelled keys, and non-mappings all fail loudly."""
    with pytest.raises(FileNotFoundError):
        config.load_yaml_config("nope", tmp_path, set())
    with pytest.raises(ValueError, match="unknown key"):
        config.load_yaml_config(
            _write(tmp_path, "bogus: 1"), tmp_path, {"variants"}
        )
    with pytest.raises(ValueError, match="mapping"):
        config.load_yaml_config(_write(tmp_path, "- a"), tmp_path, set())


@pytest.mark.unit
def test_parse_overrides_reads_yaml_scalars() -> None:
    """--set values become ints/strings as YAML would read them."""
    assert config.parse_overrides(["threshold=62", "grouping=random"]) == {
        "threshold": 62,
        "grouping": "random",
    }
    with pytest.raises(ValueError, match="key=value"):
        config.parse_overrides(["oops"])


@pytest.mark.unit
def test_variant_names_and_labels_include_overrides() -> None:
    """Variants are distinguishable in file names and in tables."""
    plain = Variant("rfm")
    tuned = parse_variant({"defense": "dream", "overrides": {"threshold": 62}})
    assert (plain.name, plain.label) == ("rfm", "rfm")
    assert (tuned.name, tuned.label) == (
        "dream_threshold62",
        "dream[threshold=62]",
    )
    assert tuned.spec.name == "dream"


@pytest.mark.unit
def test_parse_variant_rejects_bad_entries() -> None:
    """Non-mappings, unknown keys/defenses, and overrides on plugin-less
    defenses are rejected; extra keys are allowed only when declared."""
    with pytest.raises(ValueError, match="'defense' key"):
        parse_variant("rfm")
    with pytest.raises(ValueError, match="Unknown variant key"):
        parse_variant({"defense": "rfm", "noise_rates": [1]})
    assert parse_variant(
        {"defense": "rfm", "noise_rates": [1]}, {"noise_rates"}
    )
    with pytest.raises(ValueError, match="Unknown defense"):
        parse_variant({"defense": "nope"})
    with pytest.raises(ValueError, match="takes no overrides"):
        parse_variant({"defense": "prac", "overrides": {"a": 1}})

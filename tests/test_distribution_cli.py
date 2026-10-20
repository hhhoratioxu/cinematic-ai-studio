import json
from pathlib import Path

import pytest

from cinema import main
from install_skill import install
from validate_distribution import validate


def test_distribution_metadata_full_example_and_links():
    assert validate(Path(__file__).resolve().parents[1])["sample_seconds"] == 180


@pytest.mark.parametrize("command", [["doctor"], ["providers"], ["schema", "plan"], ["schema", "character"]])
def test_offline_cli_entry_points(command, capsys):
    assert main(command) == 0
    assert isinstance(json.loads(capsys.readouterr().out), dict)


def test_estimate_cli_never_pays_or_invents_rates(capsys):
    root = Path(__file__).resolve().parents[1]
    assert main(["estimate", "--plan", str(root / "assets/episode01.plan.json")]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["target_seconds"] == 180
    assert report["all_attempts_and_configured_fallbacks_ceiling_usd"] is None
    assert len(report["capability_checks"]) == 30


def test_install_is_self_contained_and_does_not_overwrite(tmp_path):
    dest = install(tmp_path / "skills/cinematic-ai-studio")
    assert (dest / "scripts/cinema.py").is_file()
    assert (dest / "assets/episode01.plan.json").is_file()
    assert validate(dest)["valid"]
    assert not list(dest.rglob("*.pyc"))
    with pytest.raises(FileExistsError):
        install(dest)

from __future__ import annotations

import shutil

import pytest
import yaml
from conftest import ROOT

from job_alert.config import ConfigError, load_config


@pytest.mark.parametrize("timeout", ["nan", "inf", "-inf", 0, -1])
def test_link_validation_timeout_must_be_finite_and_positive(tmp_path, timeout):
    config_path = tmp_path / "config.yaml"
    shutil.copy(ROOT / "config.yaml", config_path)
    config = yaml.safe_load(config_path.read_text())
    config["link_validation"]["timeout_seconds"] = timeout
    config_path.write_text(yaml.safe_dump(config))

    with pytest.raises(ConfigError, match="finite positive number"):
        load_config(config_path)

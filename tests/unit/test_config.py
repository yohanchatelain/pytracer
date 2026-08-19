import pytest

from pytracer._errors import ConfigError
from pytracer.config.loader import CONFIG_FILENAME, load_config, write_default_config
from pytracer.config.schema import PytracerConfig, config_from_dict


def test_defaults_are_valid():
    config = PytracerConfig()
    config.validate()
    assert config.trace.plugins == ["numpy"]
    assert config.analysis.alignment == "callsite"


def test_load_without_file_returns_defaults(tmp_path):
    config = load_config(tmp_path)
    assert config.trace.instrumentation == "hybrid"


def test_init_roundtrip(tmp_path):
    path = write_default_config(tmp_path)
    assert path.name == CONFIG_FILENAME
    config = load_config(tmp_path)
    config.validate()
    with pytest.raises(ConfigError, match="already exists"):
        write_default_config(tmp_path)


def test_unknown_section_rejected():
    with pytest.raises(ConfigError, match="unknown section"):
        config_from_dict({"tracing": {}})


def test_unknown_key_rejected():
    with pytest.raises(ConfigError, match="unknown key"):
        config_from_dict({"trace": {"modules": ["numpy"]}})


def test_invalid_enum_rejected():
    with pytest.raises(ConfigError, match="alignment"):
        config_from_dict({"analysis": {"alignment": "magic"}})


def test_invalid_toml_reported(tmp_path):
    (tmp_path / CONFIG_FILENAME).write_text("not [valid toml")
    with pytest.raises(ConfigError, match="invalid TOML"):
        load_config(tmp_path)


def test_perturb_env_templating_valid():
    config = config_from_dict(
        {"perturb": {"env": {"VFC_BACKENDS": "mca --seed={run_index}"}}}
    )
    assert config.perturb.env["VFC_BACKENDS"].format(run_index=3, run_id="x") == \
        "mca --seed=3"


def test_perturb_env_bad_template_rejected():
    with pytest.raises(ConfigError, match="perturb.env"):
        config_from_dict({"perturb": {"env": {"X": "seed={unknown_var}"}}})


def test_perturb_env_non_string_rejected():
    with pytest.raises(ConfigError, match="perturb.env"):
        config_from_dict({"perturb": {"env": {"X": 5}}})

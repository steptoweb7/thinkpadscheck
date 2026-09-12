import textwrap

from olx_bot.config import load_config


def test_load_config_reads_yaml(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        textwrap.dedent(
            """
            max_price: 1500
            gmail:
              address: "a@gmail.com"
            """
        )
    )
    config = load_config(str(config_path))
    assert config["max_price"] == 1500
    assert config["gmail"]["address"] == "a@gmail.com"


def test_load_config_merges_tracked_settings_with_local_secrets(tmp_path):
    """settings.yaml (tracked in git, no secrets) carries the tunable
    knobs -- filter_url, max_price, ssd_deal, etc. -- so a `git pull`
    alone changes bot behavior. config.yaml (gitignored) only needs the
    Gmail credentials; the two get merged at load time."""
    (tmp_path / "settings.yaml").write_text(
        textwrap.dedent(
            """
            max_price: 1800
            ssd_deal:
              max_price: 800
              min_ssd_gb: 512
            """
        )
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        textwrap.dedent(
            """
            gmail:
              address: "a@gmail.com"
              app_password: "pw"
              to: "a@gmail.com"
            """
        )
    )
    config = load_config(str(config_path))
    assert config["max_price"] == 1800
    assert config["ssd_deal"]["min_ssd_gb"] == 512
    assert config["gmail"]["address"] == "a@gmail.com"


def test_local_secrets_file_can_override_tracked_settings(tmp_path):
    """A value present in both files -- e.g. someone testing a different
    max_price locally -- lets the local (gitignored) file win, so nothing
    forces every override through git."""
    (tmp_path / "settings.yaml").write_text("max_price: 1800\n")
    config_path = tmp_path / "config.yaml"
    config_path.write_text("max_price: 2500\ngmail:\n  address: a@gmail.com\n")

    config = load_config(str(config_path))
    assert config["max_price"] == 2500

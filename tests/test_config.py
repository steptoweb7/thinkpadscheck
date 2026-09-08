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

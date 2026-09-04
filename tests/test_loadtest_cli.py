from qe_platform.loadtest import cli


def test_cli_rejects_invalid_config(tmp_path, capsys):
    path = tmp_path / "bad.yaml"
    path.write_text("target_url: nope\n", encoding="utf-8")
    assert cli.main([str(path)]) == 2
    assert "configuration error" in capsys.readouterr().err.lower()

from src.report_generator import _plain_text


def test_plain_text_preserves_project_name_hyphen() -> None:
    markdown = "# Weekly\n\n- Zycus - Titan S2P Implementation: AMBER\n"

    text = _plain_text(markdown)

    assert "* Zycus - Titan S2P Implementation: AMBER" in text

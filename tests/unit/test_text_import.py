"""Tests for the text decklist parser."""

from auto_goldfish.decklist.text_import import parse_decklist


class TestParseDecklist:
    def test_basic_format(self):
        text = "1 Sol Ring\n1 Island\n1 Swamp"
        result = parse_decklist(text)
        assert len(result) == 3
        assert result[0] == (1, "Sol Ring", False)
        assert result[1] == (1, "Island", False)

    def test_quantity_x_format(self):
        text = "2x Lightning Bolt\n3X Island"
        result = parse_decklist(text)
        assert result[0] == (2, "Lightning Bolt", False)
        assert result[1] == (3, "Island", False)

    def test_no_quantity_defaults_to_1(self):
        text = "Sol Ring\nIsland"
        result = parse_decklist(text)
        assert result[0] == (1, "Sol Ring", False)
        assert result[1] == (1, "Island", False)

    def test_cmdr_tag(self):
        text = "1 Vren, the Relentless *CMDR*"
        result = parse_decklist(text)
        assert result[0] == (1, "Vren, the Relentless", True)

    def test_commander_section_header(self):
        text = "// Commander\n1 Vren, the Relentless\n\n// Creatures\n1 Sol Ring"
        result = parse_decklist(text)
        assert result[0] == (1, "Vren, the Relentless", True)
        assert result[1] == (1, "Sol Ring", False)

    def test_blank_lines_ignored(self):
        text = "1 Sol Ring\n\n\n1 Island"
        result = parse_decklist(text)
        assert len(result) == 2

    def test_section_headers_ignored(self):
        text = "// Lands\n1 Island\n// Ramp\n1 Sol Ring"
        result = parse_decklist(text)
        assert len(result) == 2
        assert result[0] == (1, "Island", False)
        assert result[1] == (1, "Sol Ring", False)

    def test_empty_input(self):
        assert parse_decklist("") == []
        assert parse_decklist("   \n  \n") == []

    def test_whitespace_handling(self):
        text = "  1   Sol Ring  \n  2x  Island  "
        result = parse_decklist(text)
        assert result[0] == (1, "Sol Ring", False)
        assert result[1] == (2, "Island", False)

    def test_double_faced_card_name(self):
        text = "1 Agadeem's Awakening // Agadeem, the Undercrypt"
        result = parse_decklist(text)
        assert result[0] == (1, "Agadeem's Awakening // Agadeem, the Undercrypt", False)

    def test_commanders_section_variant(self):
        text = "// Commanders\n1 Tymna the Weaver\n1 Thrasios, Triton Hero"
        result = parse_decklist(text)
        assert result[0][2] is True
        assert result[1][2] is True

    def test_mixed_formats(self):
        text = """// Commander
1 Vren, the Relentless

// Ramp
1x Sol Ring
Arcane Signet

// Lands
36 Island"""
        result = parse_decklist(text)
        assert len(result) == 4
        assert result[0] == (1, "Vren, the Relentless", True)
        assert result[1] == (1, "Sol Ring", False)
        assert result[2] == (1, "Arcane Signet", False)
        assert result[3] == (36, "Island", False)

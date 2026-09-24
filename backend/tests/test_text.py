from app.core.text import clean_marketplace_text


def test_html_entities_become_the_characters_they_stand_for():
    assert clean_marketplace_text("Dzi\u0119kujemy za zam&oacute;wienie") == "Dzi\u0119kujemy za zam\u00f3wienie"
    assert clean_marketplace_text("&quot;Serce&quot; &amp; \u201eDrzewo&rdquo;") == '"Serce" & \u201eDrzewo\u201d'
    assert clean_marketplace_text("a &ndash; b &hellip; &#39;x&#39;") == "a \u2013 b \u2026 'x'"


def test_it_decodes_once_so_a_typed_entity_stays_what_was_typed():
    assert clean_marketplace_text("&amp;lt;b&amp;gt;") == "&lt;b&gt;"


def test_invisible_characters_and_no_break_spaces_are_removed():
    assert clean_marketplace_text("Dzie\u0144 dobry&zwnj;,\u200b nice&nbsp;day\ufeff") == "Dzie\u0144 dobry, nice day"


def test_line_breaks_stay_and_the_ends_are_trimmed():
    assert clean_marketplace_text("  Cze\u015b\u0107,\n\nMonika \n") == "Cze\u015b\u0107,\n\nMonika"


def test_plain_text_is_left_as_it_is():
    text = "Dobrze dzi\u0119kuj\u0119! 5 < 6 i 7 > 6, R&D"

    assert clean_marketplace_text(text) == text


def test_only_invisible_text_is_empty():
    assert clean_marketplace_text("\u200c\u00a0 ") == ""

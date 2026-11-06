"""The menu and settings metrics the reference panels set (spec: stage pass, step 5)."""

import pytest

ui = pytest.importorskip("encoregui.ui")  # GTK: skipped where gi is missing


def _rule(selector: str) -> str:
    start = ui.CSS.index(selector + " {")
    return ui.CSS[start : ui.CSS.index("}", start)]


def test_eyebrows_are_11px_uppercase_and_tracked():
    assert ui.eyebrow("Background") == "BACKGROUND"
    for selector in (".section", ".panel-title"):
        rule = _rule(selector)
        assert "font-size: 11px" in rule
        assert "letter-spacing: 0.08em" in rule


def test_rows_are_36px_tall():
    assert ui.ROW_PX == 36
    assert "min-height: 28px" in _rule("button.item")  # + 4 px padding above and below
    assert "min-height: 36px" in _rule(".panel-row")


def test_separators_are_8_percent_white():
    assert "rgba(255,255,255,0.08)" in _rule(".hsep")


def test_swatches_are_18px_rounds_with_a_light_ring():
    assert ui.SWATCH_PX == 18
    rule = _rule("button.swatch")
    assert "padding: 0" in rule
    assert "border-radius: 999px" in rule
    assert 0.3 <= ui.SWATCH_RING_ALPHA <= 0.6  # the 1 px light ring the swatch draws


def test_slider_values_use_tabular_figures():
    assert 'font-feature-settings: "tnum"' in _rule(".value")

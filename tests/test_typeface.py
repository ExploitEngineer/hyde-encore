from encorelib.typeface import (
    ALIASES,
    DISPLAY_FONTS,
    Face,
    face_for,
    mono_partner,
    nearest_weight,
    pango_string,
    primary_family,
    role_for,
    serif_partner,
)

HAVE = {
    "SF Pro Display": {(400, False), (700, False)},
    "Inter": {(w, False) for w in range(100, 1000, 100)} | {(400, True)},
    "Instrument Serif": {(400, False)},
    "Newsreader": {(400, False), (700, False)},
    "JetBrainsMono Nerd Font": {(400, False)},
    "Alfa Slab One": {(400, False)},
}


def _roles(style: str, on_block: bool = False) -> list[str]:
    return [role_for(style, f"track:{i}", j, on_block) for i in range(40) for j in range(10)]


def test_line_is_bold_only():
    assert set(_roles("line")) == {"heavy"}


def test_stack_and_visual_mix_heavy_serif_and_medium_about_half_quarter_quarter():
    for style in ("stack", "visual"):
        roles = _roles(style)
        assert 0.42 < roles.count("heavy") / len(roles) < 0.58
        assert 0.18 < roles.count("serif") / len(roles) < 0.32
        assert 0.18 < roles.count("medium") / len(roles) < 0.32


def test_the_word_on_the_highlight_block_is_never_heavy():
    assert set(_roles("visual", on_block=True)) <= {"medium", "serif"}


def test_the_same_word_keeps_its_face():
    assert role_for("stack", "k", 3, False) == role_for("stack", "k", 3, False)


def test_constellation_is_semibold_with_one_serif_word_in_four():
    roles = _roles("constellation")
    assert set(roles) == {"semibold", "serif"}
    assert 0.18 < roles.count("serif") / len(roles) < 0.32


def test_nearest_weight_prefers_the_closest_then_the_heavier():
    assert nearest_weight(600, {400, 700}) == 700
    assert nearest_weight(500, {400, 700}) == 400
    assert nearest_weight(500, {400, 600}) == 600
    assert nearest_weight(700, {400}) == 400
    assert nearest_weight(700, set()) == 700


def test_faces_use_only_what_the_family_ships():
    assert face_for("heavy", "SF Pro Display", HAVE) == Face("SF Pro Display", 700, False)
    assert face_for("semibold", "SF Pro Display", HAVE) == Face("SF Pro Display", 700, False)
    assert face_for("semibold", "Inter", HAVE) == Face("Inter", 600, False)
    assert face_for("medium", "SF Pro Display", HAVE) == Face("SF Pro Display", 400, False)
    assert face_for("medium", "Inter", HAVE) == Face("Inter", 400, False)
    # a one-weight family is never set in a synthetic bold
    assert face_for("heavy", "Alfa Slab One", HAVE) == Face("Alfa Slab One", 400, False)
    assert face_for("serif", "Inter", HAVE) == Face("Instrument Serif", 400, True)
    assert face_for("mono", "Inter", HAVE) == Face("JetBrainsMono Nerd Font", 400, False)


def test_faces_unknown_family_falls_back_to_an_installed_one():
    assert primary_family("Futura", HAVE) == "SF Pro Display"
    assert primary_family("SF Pro Display, Inter, sans-serif", HAVE) == "SF Pro Display"
    assert primary_family("Cantarell, Inter", HAVE) == "Inter"
    assert primary_family("Inter", {}) == "Inter"  # nothing known: trust the name


def test_partners_fall_back_in_order():
    assert serif_partner(HAVE) == "Instrument Serif"
    assert serif_partner({"Newsreader": {(400, False)}}) == "Newsreader"
    assert serif_partner({}) == "Serif"
    assert mono_partner(HAVE) == "JetBrainsMono Nerd Font"
    assert mono_partner({"Maple Mono": {(400, False)}}) == "Maple Mono"
    assert mono_partner({}) == "Monospace"


def test_pango_string_names_weight_and_slant():
    assert pango_string(Face("SF Pro Display", 700, False)) == "SF Pro Display Bold"
    assert pango_string(Face("Inter", 600, False)) == "Inter Semi-Bold"
    assert pango_string(Face("Inter", 400, False)) == "Inter Normal"
    assert pango_string(Face("Instrument Serif", 400, True)) == "Instrument Serif Normal Italic"


def test_display_fonts_and_their_reference_names():
    assert DISPLAY_FONTS == (
        "SF Pro Display",
        "Inter",
        "Newsreader",
        "Instrument Serif",
        "Alfa Slab One",
        "Electrolize",
        "Anurati",
        "JetBrainsMono Nerd Font",
        "Maple Mono",
    )
    assert ALIASES == {"Newsreader": "New York", "Instrument Serif": "Didot"}


def test_menu_fonts_show_the_family_in_use():
    from encorelib.typeface import menu_fonts

    shown = ["SF Pro Display", "Inter"]
    assert menu_fonts(shown, "Inter") == shown
    # an installed family set outside the menu (from the CLI) joins the list
    assert menu_fonts(shown, "Noto Sans") == ["SF Pro Display", "Inter", "Noto Sans"]

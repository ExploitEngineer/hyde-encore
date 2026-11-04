from encorelib.colors import DEFAULT_ACCENT, scheme
from encorelib.palette import contrast_ratio

VIVID = {"1xa8": "D4407A", "2xa8": "E8A0C0", "3xa8": "4A90D9", "pry1": "1A1014", "txt1": "FFFFFF"}
GREY = {"1xa8": "D6D6D6", "2xa8": "D6D6D6", "3xa8": "D6D6D6", "pry1": "121316", "txt1": "FFFFFF"}
THEME = {"1xa8": "4FB89A", "2xa8": "2E7D6B", "pry1": "0F1A17", "txt1": "FFFFFF"}


def hue(hex_color):
    import colorsys

    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)[0] * 360


def test_vivid_cover_drives_the_accent():
    s = scheme(VIVID, THEME)
    assert s.source == "cover"
    assert abs(hue(s.accent) - hue("D4407A")) < 3  # same hue, lightened only to stay readable
    assert contrast_ratio(s.accent, "101014") >= 4.5


def test_grey_cover_falls_back_to_the_theme():
    s = scheme(GREY, THEME)
    assert s.source == "theme"
    assert abs(hue(s.accent) - hue("4FB89A")) < 8


def test_grey_cover_and_no_theme_uses_the_default():
    s = scheme(GREY, {})
    assert s.source == "default" and s.accent == DEFAULT_ACCENT


def test_text_on_the_highlight_is_readable():
    for palette in (VIVID, GREY, {"1xa8": "F5E26B"}):
        s = scheme(palette, {})
        assert contrast_ratio(s.on_highlight, s.highlight) >= 4.5, s


def test_highlight_is_a_saturated_mid_tone():
    import colorsys

    r, g, b = (int(scheme(VIVID, {}).highlight[i : i + 2], 16) / 255 for i in (0, 2, 4))
    _, lightness, saturation = colorsys.rgb_to_hls(r, g, b)
    assert 0.3 <= lightness <= 0.6 and saturation >= 0.45


def test_second_hue_differs_from_the_accent():
    s = scheme(VIVID, {})
    gap = abs(hue(s.accent) - hue(s.accent2)) % 360
    assert min(gap, 360 - gap) >= 25


def test_lyric_and_secondary_are_light_tints_readable_on_dark():
    s = scheme(VIVID, {})
    assert contrast_ratio(s.lyric, "101014") >= 7
    assert contrast_ratio(s.secondary, "101014") >= 3
    assert s.lyric != "FFFFFF"  # tinted by the cover, like the reference look


def test_resolve_defaults_to_the_scheme():
    from encorelib.colors import resolve

    s = scheme(VIVID, {})
    r = resolve(s, {}, "")
    assert (r.sung, r.highlight, r.column_sung) == (s.accent, s.highlight, s.accent)
    assert (r.lyric, r.secondary, r.on_highlight) == (s.lyric, s.secondary, s.on_highlight)


def test_resolve_color_override_drives_sung_words_and_the_block():
    from encorelib.colors import resolve

    r = resolve(scheme(VIVID, {}), {}, "#FF0000")
    assert r.sung == r.column_sung == r.highlight == "FF0000"
    assert contrast_ratio(r.on_highlight, r.highlight) >= 4.0


def test_resolve_look_colors_win():
    from encorelib.colors import resolve

    look = {"highlight_color": "#00FF00", "lyric_color": "#ABCDEF", "secondary_color": "#123456"}
    r = resolve(scheme(VIVID, {}), look, "#FF0000")
    assert r.highlight == r.column_sung == "00FF00"  # the Highlight picker beats `color`
    assert r.sung == "FF0000"  # line fill keeps the `color` override
    assert (r.lyric, r.secondary) == ("ABCDEF", "123456")


def test_scheme_contrast_holds_across_hues():
    import colorsys

    for i in range(36):
        for lightness in (0.2, 0.5, 0.85):
            rgb = colorsys.hls_to_rgb(i / 36, lightness, 0.8)
            color = "".join(f"{round(c * 255):02X}" for c in rgb)
            s = scheme({"1xa8": color}, {})
            assert contrast_ratio(s.accent, "101014") >= 4.5, color
            assert contrast_ratio(s.on_highlight, s.highlight) >= 4.5, color


# a real wallbash ramp from a pink cover: muted by design, lightest shade first
PINK_RAMP = {
    f"1xa{i + 1}": c
    for i, c in enumerate(
        ["FFCCEE", "F0AAD9", "E69ACC", "C27AAA", "A3658F", "8F577C", "7D4B6C", "6B3A5B", "522944"]
    )
}


def chroma(hex_color):
    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return max(r, g, b) - min(r, g, b)


def test_muted_ramp_gives_a_vivid_accent_of_its_hue():
    s = scheme(PINK_RAMP, {})
    assert s.source == "cover"
    assert chroma(s.accent) >= 0.45  # not the pastel FFCCEE (chroma 0.2)
    assert abs(hue(s.accent) - hue("E69ACC")) < 6
    assert contrast_ratio(s.accent, "101014") >= 4.5


def test_barely_tinted_grey_falls_back_to_the_theme():
    tinted_grey = {f"1xa{i}": c for i, c in enumerate(["B0B0C8", "9898AC", "707080"], 1)}
    s = scheme(tinted_grey, THEME)
    assert s.source == "theme"

from pathlib import Path

from paths import FIXTURES

from encorelib.config import EncoreConfig, load_config

HOME = {"HOME": "/home/u"}


def test_defaults_with_empty_env(tmp_path):
    cfg = load_config(env=HOME, env_file=tmp_path / "missing")
    assert cfg == EncoreConfig(
        lyrics_dirs=(Path("/home/u/.local/share/lyrics"), Path("/home/u/Music/Lyrics"))
    )
    assert cfg.enable is False
    assert cfg.lrclib is True
    assert cfg.spicy_key == ""


def test_xdg_data_home_respected(tmp_path):
    cfg = load_config(env={**HOME, "XDG_DATA_HOME": "/d"}, env_file=tmp_path / "missing")
    assert cfg.lyrics_dirs[0] == Path("/d/lyrics")


def test_env_file_is_read(tmp_path):
    f = tmp_path / "config"
    f.write_text('# comment\nexport ENCORE_LYRICS_SPICY_KEY="abc"\nexport ENCORE_ENABLE=1\n')
    cfg = load_config(env=HOME, env_file=f)
    assert cfg.spicy_key == "abc"
    assert cfg.enable is True


def test_process_env_overrides_file(tmp_path):
    f = tmp_path / "config"
    f.write_text('export ENCORE_LYRICS_SPICY_KEY="file"\n')
    cfg = load_config(env={**HOME, "ENCORE_LYRICS_SPICY_KEY": "env"}, env_file=f)
    assert cfg.spicy_key == "env"


def test_spicy_alias_env(tmp_path):
    cfg = load_config(env={**HOME, "SPICY_LYRICS_SECRET_KEY": "k"}, env_file=tmp_path / "x")
    assert cfg.spicy_key == "k"


def test_bad_boolean_falls_back(tmp_path):
    cfg = load_config(env={**HOME, "ENCORE_LYRICS_LRCLIB": "maybe"}, env_file=tmp_path / "x")
    assert cfg.lrclib is True


def test_false_boolean(tmp_path):
    cfg = load_config(env={**HOME, "ENCORE_LYRICS_LRCLIB": "false"}, env_file=tmp_path / "x")
    assert cfg.lrclib is False


def test_players_comma_list(tmp_path):
    cfg = load_config(env={**HOME, "ENCORE_PLAYERS": "spotify, mpv"}, env_file=tmp_path / "x")
    assert cfg.players == ("spotify", "mpv")


def test_players_shell_array_from_hyde(tmp_path):
    f = tmp_path / "config"
    f.write_text('export ENCORE_PLAYERS=("spotify" "firefox")\n')
    cfg = load_config(env=HOME, env_file=f)
    assert cfg.players == ("spotify", "firefox")


def test_lyrics_dirs_are_added_before_defaults(tmp_path):
    cfg = load_config(env={**HOME, "ENCORE_LYRICS_DIRS": "/a:/b"}, env_file=tmp_path / "x")
    assert cfg.lyrics_dirs == (
        Path("/a"),
        Path("/b"),
        Path("/home/u/.local/share/lyrics"),
        Path("/home/u/Music/Lyrics"),
    )


def test_real_hyde_config_lua_output():
    """tests/fixtures/hyde_config.env was produced by HyDE's config.lua."""
    cfg = load_config(env=HOME, env_file=FIXTURES / "hyde_config.env")
    assert cfg.enable is True
    assert cfg.players == ("spotify", "firefox")
    assert cfg.spicy_key == "sl_sk_x"
    assert cfg.lrclib is False
    assert cfg.hyprlock_color == "#CAAAF0"
    assert cfg.lyrics_dirs[:2] == (Path("/a b"), Path("/c"))


def test_hyprlock_colors(tmp_path):
    env = {**HOME, "ENCORE_HYPRLOCK_COLOR": "#ff0000", "ENCORE_HYPRLOCK_DIM": "#ffffff80"}
    cfg = load_config(env=env, env_file=tmp_path / "x")
    assert (cfg.hyprlock_color, cfg.hyprlock_dim) == ("#ff0000", "#ffffff80")


def test_overlay_defaults(tmp_path):
    cfg = load_config(env=HOME, env_file=tmp_path / "missing")
    assert cfg.overlay_enable is False
    assert cfg.overlay_position == "bottom"
    assert cfg.overlay_margin == 120
    assert cfg.overlay_font == "SF Pro Display, Inter, Cantarell, sans-serif"
    assert cfg.overlay_size == 30
    assert cfg.overlay_next_line is True
    assert cfg.overlay_color == ""
    assert cfg.overlay_monitor == ""


def test_overlay_env_names(tmp_path):
    env = {
        **HOME,
        "ENCORE_OVERLAY_ENABLE": "1",
        "ENCORE_OVERLAY_POSITION": "top",
        "ENCORE_OVERLAY_MARGIN": "64",
        "ENCORE_OVERLAY_FONT": '"Inter"',
        "ENCORE_OVERLAY_SIZE": "40",
        "ENCORE_OVERLAY_NEXT_LINE": "false",
        "ENCORE_OVERLAY_COLOR": "#AABBCC",
        "ENCORE_OVERLAY_MONITOR": "eDP-1",
    }
    cfg = load_config(env=env, env_file=tmp_path / "x")
    assert cfg.overlay_enable is True
    assert cfg.overlay_position == "top"
    assert cfg.overlay_margin == 64
    assert cfg.overlay_font == "Inter"
    assert cfg.overlay_size == 40
    assert cfg.overlay_next_line is False
    assert cfg.overlay_color == "#AABBCC"
    assert cfg.overlay_monitor == "eDP-1"


def test_overlay_bad_values_fall_back(tmp_path):
    env = {**HOME, "ENCORE_OVERLAY_MARGIN": "wide", "ENCORE_OVERLAY_POSITION": "left"}
    cfg = load_config(env=env, env_file=tmp_path / "x")
    assert cfg.overlay_margin == 120
    assert cfg.overlay_position == "bottom"


def test_overlay_style(tmp_path):
    assert load_config(env=HOME, env_file=tmp_path / "x").overlay_style == "line"
    env = {**HOME, "ENCORE_OVERLAY_STYLE": "Constellation"}
    assert load_config(env=env, env_file=tmp_path / "x").overlay_style == "constellation"
    env = {**HOME, "ENCORE_OVERLAY_STYLE": "wave"}
    assert load_config(env=env, env_file=tmp_path / "x").overlay_style == "line"


def test_overlay_style_accepts_every_style(tmp_path):
    for style in ("line", "stack", "constellation", "visual"):
        env = {**HOME, "ENCORE_OVERLAY_STYLE": style}
        assert load_config(env=env, env_file=tmp_path / "x").overlay_style == style
    env = {**HOME, "ENCORE_OVERLAY_STYLE": "nope"}
    assert load_config(env=env, env_file=tmp_path / "x").overlay_style == "line"

from encorelib.service import surface_log


def test_surface_log_lives_in_the_cache(tmp_path):
    env = {"XDG_CACHE_HOME": str(tmp_path / "cache")}
    path = surface_log("overlay", env)
    assert path == tmp_path / "cache" / "hyde" / "encore" / "logs" / "overlay.log"
    assert path.parent.is_dir()


def test_surface_log_defaults_to_home(tmp_path):
    env = {"HOME": str(tmp_path)}
    assert surface_log("glow", env) == tmp_path / ".cache" / "hyde" / "encore" / "logs" / "glow.log"

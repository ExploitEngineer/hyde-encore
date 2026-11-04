"""State published on $XDG_RUNTIME_DIR/hyde/encore.sock as JSON lines.

Clients compute the live position as position + (now - ts) * rate while
status is "playing"; ts is time.monotonic(), shared across processes.
"""

from __future__ import annotations

import html
import json
import socket
from pathlib import Path

from .clock import PlaybackClock
from .model import Lyrics
from .palette import pick_accent
from .providers import TrackInfo, track_key
from .timing import Cursor, locate
from .words import split_words, word_spans

PROTOCOL_VERSION = 1


def build_state(
    status: str,
    track: TrackInfo | None,
    art: Path | None,
    lyrics: Lyrics | None,
    clock: PlaybackClock,
    palette: dict[str, str],
) -> dict:
    position, ts = clock.anchor()
    line = nxt = gap = None
    if lyrics is not None and lyrics.sync != "none":
        cursor = locate(lyrics, clock.position())
        if cursor.line >= 0:
            ln = lyrics.lines[cursor.line]
            line = {
                "index": cursor.line,
                "start": ln.start,
                "end": ln.end,
                "text": ln.text,
                "words": [{"text": w.text, "start": w.start, "end": w.end} for w in ln.words],
            }
        upcoming = next(
            (i for i in range(cursor.after + 1, len(lyrics.lines)) if lyrics.lines[i].text.strip()),
            None,
        )
        if upcoming is not None:
            nxt = lyrics.lines[upcoming].text
            if line is None:
                gap = {"after": cursor.after, "until": lyrics.lines[upcoming].start}
    return {
        "v": PROTOCOL_VERSION,
        "ts": ts,
        "status": status,
        "player": track.player if track else None,
        "track": (
            {
                "key": track_key(track),
                "title": track.title,
                "artist": track.artist,
                "album": track.album,
                "length": track.length,
                "art": str(art) if art else None,
            }
            if track
            else None
        ),
        "lyrics": (
            {
                "sync": lyrics.sync,
                "source": lyrics.source,
                "credit": lyrics.credit,
                # every line once, for clients that show the whole song
                "lines": [{"start": ln.start, "text": ln.text} for ln in lyrics.lines],
            }
            if lyrics is not None
            else None
        ),
        "position": position,
        "rate": clock.rate,
        "line": line,
        "next": nxt,
        "gap": gap,
        "palette": palette,
    }


def _span(color: str, text: str) -> str:
    color = color if color.startswith("#") else f"#{color}"
    if len(color) == 9:
        alpha = round(int(color[7:9], 16) * 100 / 255)
        return f'<span foreground="{color[:7]}" fgalpha="{alpha}%">{text}</span>'
    return f'<span foreground="{color}">{text}</span>'


def hyprlock_markup(lyrics: Lyrics | None, cursor: Cursor, accent: str, dim: str) -> str:
    """Pango markup of the current line, sung words in accent, the rest dim."""
    if lyrics is None or cursor.line < 0:
        return ""
    line = lyrics.lines[cursor.line]
    text = line.text.strip()
    words = [w.text for w in line.words] if line.words else split_words(text)
    if not words:
        return ""
    # cut the source text after the sung word, so CJK lines keep no spaces
    cut = word_spans(text, words)[cursor.word][1] if cursor.word >= 0 else 0
    sung, rest = text[:cut].rstrip(), text[cut:].lstrip()
    gap = " " if text[cut : cut + 1].isspace() else ""

    def esc(part: str) -> str:
        return html.escape(part, quote=False)

    if sung and rest:
        return _span(accent, esc(sung)) + gap + _span(dim, esc(rest))
    if sung:
        return _span(accent, esc(sung))
    return _span(dim, esc(rest))


def encode(state: dict) -> bytes:
    return (json.dumps(state, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


class StateServer:
    """Broadcasts the latest state to every connected client."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.sock: socket.socket | None = None
        self.clients: list[socket.socket] = []
        self.last: bytes | None = None

    def start(self) -> socket.socket:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                probe.connect(str(self.path))
            except OSError:
                self.path.unlink(missing_ok=True)
            else:
                raise RuntimeError(f"encore already running on {self.path}")
            finally:
                probe.close()
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(str(self.path))
        self.sock.listen(8)
        self.sock.setblocking(False)
        return self.sock

    def accept(self) -> None:
        try:
            client, _ = self.sock.accept()
        except BlockingIOError:
            return
        client.setblocking(False)
        if self.last is not None and not self._send(client, self.last):
            return
        self.clients.append(client)

    def _send(self, client: socket.socket, data: bytes) -> bool:
        try:
            client.sendall(data)
            return True
        except OSError:
            client.close()
            return False

    def broadcast(self, state: dict) -> None:
        self.last = encode(state)
        self.clients = [c for c in self.clients if self._send(c, self.last)]

    def close(self) -> None:
        for client in self.clients:
            client.close()
        self.clients = []
        if self.sock is not None:
            self.sock.close()
            self.sock = None
            self.path.unlink(missing_ok=True)


def read_state(path: Path, timeout: float = 0.3) -> dict | None:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(str(path))
            line = s.makefile("rb").readline()
        return json.loads(line) if line else None
    except (OSError, ValueError):
        return None


DIM_ALPHA = "66"  # unsung words at 40% opacity


def hyprlock_colors(cfg, palette: dict[str, str]) -> tuple[str, str]:
    """(sung, unsung) colors for the hyprlock line.

    Config wins. Otherwise sung words take the most vivid palette accent that
    is readable on the dark lock screen, and unsung words are soft white.
    """
    accent = cfg.hyprlock_color or "#" + pick_accent(palette)
    dim = cfg.hyprlock_dim or "#FFFFFF" + DIM_ALPHA
    return accent, dim


def hyprlock_track(track: TrackInfo | None) -> str:
    """Title and artist on two lines, escaped for hyprlock's Pango labels."""
    if track is None:
        return ""
    title = html.escape(track.title, quote=False)
    artist = html.escape(track.artist, quote=False)
    return f"{title}\n{artist}\n"

"""Player profiles (name + avatar) and the 20 built-in avatars, drawn here as SVG."""
import json
import threading
import uuid

# (background, body colour, body shape, eyes, mouth, extra)
AVATARS = [
    ("#ffd6e0", "#ff5c8a", "round", "big", "smile", "bow"),
    ("#d6f5ff", "#2bb3f0", "blob", "one", "grin", "antenna"),
    ("#e6ffd6", "#5ccb3b", "frog", "big", "wide", "none"),
    ("#fff2cc", "#ffb400", "cat", "happy", "cat", "whiskers"),
    ("#ecdcff", "#8f5cff", "ghost", "big", "o", "none"),
    ("#ffe1cc", "#ff7a29", "bear", "dots", "smile", "none"),
    ("#d9fff4", "#14c4a0", "square", "visor", "flat", "antenna"),
    ("#ffe0f5", "#e94fc1", "round", "lashes", "smile", "crown"),
    ("#e0ecff", "#3d6bff", "blob", "big", "teeth", "horns"),
    ("#f8ffcc", "#a8d600", "round", "three", "wide", "none"),
    ("#ffd9d9", "#ff3b3b", "devil", "angry", "grin", "horns"),
    ("#d6fffb", "#00bfc9", "cat", "big", "cat", "none"),
    ("#fdeccf", "#c9833d", "bear", "happy", "o", "hat"),
    ("#efe0ff", "#b46cff", "square", "big", "teeth", "crown"),
    ("#dcffe5", "#2fd06d", "ghost", "dots", "smile", "bow"),
    ("#fff0d6", "#ff9f1c", "frog", "big", "tongue", "none"),
    ("#e3f2ff", "#5aa9ff", "round", "glasses", "smile", "none"),
    ("#ffe5ec", "#ff6f91", "bear", "big", "tongue", "bow"),
    ("#e9ffd1", "#7ed321", "blob", "three", "o", "antenna"),
    ("#fff5d1", "#ffcc00", "square", "lashes", "grin", "hat"),
]
COUNT = len(AVATARS)


def _darker(hex_colour, f=0.7):
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % (int(r * f), int(g * f), int(b * f))


def _body(shape, c, d):
    o = f'fill="{c}" stroke="{d}" stroke-width="3"'
    if shape == "round":
        return f'<circle cx="50" cy="56" r="32" {o}/>'
    if shape == "blob":
        return f'<path d="M20 62 C16 34 36 22 52 24 C74 26 86 40 82 62 C80 82 64 88 50 88 C32 88 22 80 20 62Z" {o}/>'
    if shape == "square":
        return f'<rect x="20" y="26" width="60" height="60" rx="14" {o}/>'
    if shape == "ghost":
        return (f'<path d="M20 88 L20 52 C20 32 34 22 50 22 C66 22 80 32 80 52 L80 88 L70 80 L60 88 '
                f'L50 80 L40 88 L30 80Z" {o}/>')
    if shape == "cat":
        return (f'<path d="M22 40 L24 14 L42 30 L58 30 L76 14 L78 40 C84 56 80 86 50 86 C20 86 16 56 22 40Z" {o}/>'
                f'<path d="M28 22 L30 32 L36 28Z M72 22 L70 32 L64 28Z" fill="#ffffff88"/>')
    if shape == "bear":
        return (f'<circle cx="26" cy="32" r="11" {o}/><circle cx="74" cy="32" r="11" {o}/>'
                f'<circle cx="26" cy="32" r="5" fill="#ffffff88"/><circle cx="74" cy="32" r="5" fill="#ffffff88"/>'
                f'<circle cx="50" cy="58" r="30" {o}/><ellipse cx="50" cy="70" rx="14" ry="10" fill="#ffffff66"/>')
    if shape == "frog":
        return (f'<circle cx="32" cy="34" r="13" {o}/><circle cx="68" cy="34" r="13" {o}/>'
                f'<ellipse cx="50" cy="62" rx="34" ry="26" {o}/>')
    if shape == "devil":
        return f'<path d="M50 26 C72 26 82 42 80 60 C78 80 64 88 50 88 C36 88 22 80 20 60 C18 42 28 26 50 26Z" {o}/>'
    raise ValueError(shape)


def _eyes(kind, shape):
    y = 34 if shape == "frog" else 50
    w = '<circle cx="{x}" cy="{y}" r="{r}" fill="#fff" stroke="#222" stroke-width="2"/>'
    p = '<circle cx="{x}" cy="{y}" r="{r}" fill="#222"/>'
    shine = '<circle cx="{x}" cy="{y}" r="1.6" fill="#fff"/>'
    xs = (32, 68) if shape == "frog" else (38, 62)
    if kind == "big":
        return "".join(w.format(x=x, y=y, r=9) + p.format(x=x + 1, y=y + 1, r=4.5) + shine.format(x=x + 2.5, y=y - 1)
                       for x in xs)
    if kind == "one":
        return w.format(x=50, y=y - 2, r=13) + p.format(x=51, y=y - 1, r=6) + shine.format(x=54, y=y - 4)
    if kind == "dots":
        return "".join(p.format(x=x, y=y, r=4) for x in xs)
    if kind == "happy":
        return "".join(f'<path d="M{x - 7} {y + 2} Q{x} {y - 8} {x + 7} {y + 2}" fill="none" stroke="#222" '
                       f'stroke-width="3.5" stroke-linecap="round"/>' for x in xs)
    if kind == "visor":
        return (f'<rect x="28" y="{y - 8}" width="44" height="15" rx="7" fill="#1f2937"/>'
                f'<rect x="33" y="{y - 4}" width="12" height="6" rx="3" fill="#5eead4"/>'
                f'<rect x="55" y="{y - 4}" width="12" height="6" rx="3" fill="#5eead4"/>')
    if kind == "lashes":
        out = ""
        for x in xs:
            out += w.format(x=x, y=y, r=7) + p.format(x=x, y=y + 1, r=3.5)
            out += (f'<path d="M{x - 7} {y - 5} L{x - 10} {y - 10} M{x} {y - 7} L{x} {y - 12} '
                    f'M{x + 7} {y - 5} L{x + 10} {y - 10}" stroke="#222" stroke-width="2" stroke-linecap="round"/>')
        return out
    if kind == "three":
        return "".join(w.format(x=x, y=yy, r=6) + p.format(x=x, y=yy + 1, r=3)
                       for x, yy in ((36, y + 2), (50, y - 6), (64, y + 2)))
    if kind == "angry":
        out = "".join(w.format(x=x, y=y, r=7) + p.format(x=x, y=y + 1, r=3.5) for x in xs)
        return out + ('<path d="M29 40 L45 46 M71 40 L55 46" stroke="#222" stroke-width="3.5" '
                      'stroke-linecap="round"/>')
    if kind == "glasses":
        out = "".join(w.format(x=x, y=y, r=9) + p.format(x=x, y=y + 1, r=3.5) for x in xs)
        return out + (f'<circle cx="38" cy="{y}" r="11" fill="none" stroke="#222" stroke-width="3"/>'
                      f'<circle cx="62" cy="{y}" r="11" fill="none" stroke="#222" stroke-width="3"/>'
                      f'<path d="M49 {y} L51 {y}" stroke="#222" stroke-width="3"/>')
    raise ValueError(kind)


def _mouth(kind, shape):
    y = 64 if shape != "frog" else 68
    s = 'fill="none" stroke="#222" stroke-width="3.5" stroke-linecap="round"'
    if kind == "smile":
        return f'<path d="M40 {y} Q50 {y + 10} 60 {y}" {s}/>'
    if kind == "grin":
        return f'<path d="M36 {y - 2} Q50 {y + 16} 64 {y - 2}Z" fill="#7a1f2b" stroke="#222" stroke-width="3"/>'
    if kind == "wide":
        return f'<path d="M30 {y} Q50 {y + 14} 70 {y}" {s}/>'
    if kind == "o":
        return f'<ellipse cx="50" cy="{y + 3}" rx="6" ry="7" fill="#7a1f2b" stroke="#222" stroke-width="3"/>'
    if kind == "flat":
        return f'<path d="M40 {y + 2} L60 {y + 2}" {s}/>'
    if kind == "cat":
        return f'<path d="M40 {y} Q45 {y + 6} 50 {y} Q55 {y + 6} 60 {y}" {s}/><path d="M47 {y - 4} L53 {y - 4} L50 {y - 1}Z" fill="#ff7aa2"/>'
    if kind == "teeth":
        return (f'<path d="M36 {y - 2} Q50 {y + 14} 64 {y - 2}Z" fill="#7a1f2b" stroke="#222" stroke-width="3"/>'
                f'<path d="M42 {y} L45 {y + 5} L48 {y + 1} M52 {y + 1} L55 {y + 5} L58 {y}" fill="#fff" '
                f'stroke="#fff" stroke-width="1"/>')
    if kind == "tongue":
        return (f'<path d="M38 {y} Q50 {y + 12} 62 {y}" {s}/>'
                f'<path d="M46 {y + 5} Q50 {y + 15} 54 {y + 5}" fill="#ff7aa2" stroke="#222" stroke-width="2"/>')
    raise ValueError(kind)


def _extra(kind, c, d):
    if kind == "none":
        return ""
    if kind == "bow":
        return ('<path d="M50 24 L36 15 L36 33Z M50 24 L64 15 L64 33Z" fill="#ff2d6f" stroke="#a3123f" '
                'stroke-width="2"/><circle cx="50" cy="24" r="4" fill="#ff2d6f" stroke="#a3123f" stroke-width="2"/>')
    if kind == "antenna":
        return (f'<path d="M50 26 L50 10" stroke="{d}" stroke-width="3"/>'
                '<circle cx="50" cy="9" r="5" fill="#ffe14d" stroke="#222" stroke-width="2"/>')
    if kind == "crown":
        return ('<path d="M34 28 L36 12 L44 20 L50 8 L56 20 L64 12 L66 28Z" fill="#ffd400" stroke="#b38f00" '
                'stroke-width="2"/><circle cx="50" cy="20" r="2.5" fill="#ff3b6b"/>')
    if kind == "horns":
        return (f'<path d="M30 34 Q22 22 26 10 Q32 22 40 28Z" fill="#fff4e0" stroke="{d}" stroke-width="2"/>'
                f'<path d="M70 34 Q78 22 74 10 Q68 22 60 28Z" fill="#fff4e0" stroke="{d}" stroke-width="2"/>')
    if kind == "hat":
        return ('<rect x="30" y="24" width="40" height="6" rx="3" fill="#333"/>'
                '<rect x="37" y="6" width="26" height="20" rx="3" fill="#333"/>'
                '<rect x="37" y="18" width="26" height="4" fill="#e63946"/>')
    if kind == "whiskers":
        return ('<path d="M22 62 L36 64 M22 70 L36 68 M78 62 L64 64 M78 70 L64 68" stroke="#222" '
                'stroke-width="2" stroke-linecap="round"/>')
    raise ValueError(kind)


ANON_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            '<rect width="100" height="100" rx="22" fill="#4a4744"/>'
            '<path d="M28 86 L74 86 L74 78 L67 73 C69 59 73 47 69 35 C65 23 55 16 44 16 L41 9 L35 17 '
            'C28 21 22 31 20 42 L17 52 C17 57 22 59 27 57 L35 51 C39 51 43 49 46 46 C44 57 37 63 33 71 '
            'L30 78Z" fill="#a8a6a3" stroke="#6b6966" stroke-width="2.5" stroke-linejoin="round"/>'
            '<circle cx="40" cy="31" r="3" fill="#4a4744"/>'
            '<path d="M24 78 L78 78" stroke="#6b6966" stroke-width="2.5"/></svg>')


def avatar_svg(n):
    if n == "anon":
        return ANON_SVG
    n = int(n)
    if not 0 <= n < COUNT:
        raise ValueError("Unknown avatar")
    bg, c, shape, eyes, mouth, extra = AVATARS[n]
    d = _darker(c)
    cheeks = ('<circle cx="30" cy="64" r="5" fill="#ff8fab" opacity=".55"/>'
              '<circle cx="70" cy="64" r="5" fill="#ff8fab" opacity=".55"/>') if shape not in ("square", "frog") else ""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            f'<rect width="100" height="100" rx="22" fill="{bg}"/>'
            f'{_body(shape, c, d)}{cheeks}{_eyes(eyes, shape)}{_mouth(mouth, shape)}{_extra(extra, c, d)}</svg>')


class Players:
    """Players saved in data/players.json as [{id, name, avatar}]."""

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()

    def all(self):
        try:
            data = json.loads(self.path.read_text())
            return [p for p in data if isinstance(p, dict) and "id" in p]
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def get(self, player_id):
        return next((p for p in self.all() if p["id"] == player_id), None)

    def create(self, name, avatar):
        name = (name or "").strip()[:30]
        if not name:
            raise ValueError("Type a name for the player")
        avatar = int(avatar)
        if not 0 <= avatar < COUNT:
            raise ValueError("Pick an avatar")
        with self.lock:
            players = self.all()
            if any(p["name"].lower() == name.lower() for p in players):
                raise ValueError(f"There's already a player called {name}")
            p = {"id": uuid.uuid4().hex[:10], "name": name, "avatar": avatar}
            players.append(p)
            self._write(players)
            return p

    def update(self, player_id, name=None, avatar=None):
        with self.lock:
            players = self.all()
            p = next((x for x in players if x["id"] == player_id), None)
            if p is None:
                raise ValueError("Player not found")
            if name is not None:
                name = name.strip()[:30]
                if not name:
                    raise ValueError("Type a name for the player")
                if any(x["name"].lower() == name.lower() and x["id"] != player_id for x in players):
                    raise ValueError(f"There's already a player called {name}")
                p["name"] = name
            if avatar is not None:
                avatar = int(avatar)
                if not 0 <= avatar < COUNT:
                    raise ValueError("Pick an avatar")
                p["avatar"] = avatar
            self._write(players)
            return p

    def _write(self, players):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(players, indent=1))
        tmp.replace(self.path)

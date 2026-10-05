#!/usr/bin/env python3
"""Install a curated US English font set for CachyOS, Pop!_OS, and other Linuxes.

The fonts/ directory next to this script is what a USB stick should carry.
./install.sh copies those files into place. --download rebuilds them.

A re-run replaces ~/.local/share/fonts/us-english and the three us-english
fontconfig files. It does not remove distro packages or application fonts.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOME = Path.home()
# Finished faces shipped in this folder, so a USB copy can install offline.
BUNDLED = ROOT / "fonts"
# Extra coding faces. Installed only with --coding.
BUNDLED_CODING = ROOT / "fonts-coding"
DEST = HOME / ".local" / "share" / "fonts" / "us-english"
CONF_DIR = HOME / ".config" / "fontconfig" / "conf.d"
CACHE = HOME / ".cache" / "us-font-cleanup"
DOWNLOADS = CACHE / "downloads"
STAGE = CACHE / "stage"

FONTSOURCE = "https://cdn.jsdelivr.net/fontsource/fonts/{fid}@latest/{subset}-{weight}-{style}.ttf"
UA = "us-font-cleanup"

# (fontsource id, folder, subsets to try, weights, styles)
# styles: "normal" or "italic". Missing italic files are skipped.
FONTSOURCE_FAMILIES: list[tuple[str, str, list[str], list[int], list[str]]] = [
    # Word / Pages text faces
    ("eb-garamond", "document", ["latin-ext"], [400, 500, 600, 700], ["normal", "italic"]),
    ("libre-baskerville", "document", ["latin-ext"], [400, 700], ["normal", "italic"]),
    ("libre-caslon-text", "document", ["latin-ext"], [400, 700], ["normal", "italic"]),
    ("libre-franklin", "document", ["latin-ext"], [400, 700], ["normal", "italic"]),
    ("carlito", "document", ["latin-ext", "latin"], [400, 700], ["normal", "italic"]),
    ("caladea", "document", ["latin-ext", "latin"], [400, 700], ["normal", "italic"]),
    ("gelasio", "document", ["latin-ext", "latin"], [400, 700], ["normal", "italic"]),
    ("league-spartan", "document", ["latin-ext"], [400, 700], ["normal"]),
    ("philosopher", "document", ["latin-ext", "latin"], [400, 700], ["normal", "italic"]),
    ("gfs-didot", "document", ["latin-ext", "latin"], [400], ["normal"]),
    ("inter", "document", ["latin-ext"], [400, 600, 700], ["normal", "italic"]),
    ("source-sans-3", "document", ["latin-ext"], [400, 600, 700], ["normal", "italic"]),
    ("source-serif-4", "document", ["latin-ext"], [400, 600, 700], ["normal", "italic"]),
    ("source-code-pro", "mono", ["latin-ext"], [400, 500, 700], ["normal", "italic"]),
    ("nunito-sans", "document", ["latin-ext"], [400, 700], ["normal", "italic"]),
    ("open-sans", "document", ["latin-ext"], [400, 700], ["normal", "italic"]),
    ("roboto", "document", ["latin-ext"], [400, 700], ["normal", "italic"]),
    ("roboto-mono", "mono", ["latin-ext"], [400, 500, 700], ["normal", "italic"]),
    ("lato", "document", ["latin-ext"], [400, 700], ["normal", "italic"]),
    ("montserrat", "document", ["latin-ext"], [400, 700], ["normal", "italic"]),
    ("merriweather", "document", ["latin-ext"], [400, 700], ["normal", "italic"]),
    ("lora", "document", ["latin-ext"], [400, 700], ["normal", "italic"]),
    ("literata", "document", ["latin-ext"], [400, 700], ["normal", "italic"]),
    ("pt-sans", "document", ["latin-ext"], [400, 700], ["normal", "italic"]),
    ("pt-serif", "document", ["latin-ext"], [400, 700], ["normal", "italic"]),
    ("pt-mono", "mono", ["latin-ext", "latin"], [400], ["normal"]),
    ("caveat", "document", ["latin-ext"], [400, 700], ["normal"]),
    ("ibm-plex-sans", "document", ["latin-ext"], [400, 700], ["normal", "italic"]),
    ("ibm-plex-serif", "document", ["latin-ext"], [400, 700], ["normal", "italic"]),
    ("ibm-plex-mono", "mono", ["latin-ext"], [400, 500, 700], ["normal", "italic"]),
    # Metric stand-ins used by LibreOffice for older Word faces
    ("agdasima", "document", ["latin-ext"], [400, 700], ["normal"]),
    ("bacasime-antique", "document", ["latin-ext"], [400], ["normal"]),
    ("belanosima", "document", ["latin-ext"], [400, 600, 700], ["normal"]),
    ("caprasimo", "document", ["latin-ext"], [400], ["normal"]),
    ("lunasima", "document", ["latin-ext"], [400, 700], ["normal"]),
    ("lumanosimo", "document", ["latin-ext"], [400], ["normal"]),
    ("lugrasimo", "document", ["latin-ext"], [400], ["normal"]),
    # Coding
    ("cascadia-code", "mono", ["latin-ext"], [400, 600, 700], ["normal", "italic"]),
    ("cascadia-mono", "mono", ["latin-ext", "latin"], [400, 600, 700], ["normal", "italic"]),
    ("fira-code", "mono", ["latin-ext"], [400, 500, 700], ["normal", "italic"]),
    # Ubuntu Sans (the newer family). Classic Ubuntu comes from the zip below.
    ("ubuntu-sans", "ubuntu", ["latin-ext"], [400, 500, 700], ["normal", "italic"]),
    ("ubuntu-sans-mono", "ubuntu", ["latin-ext"], [400, 500, 700], ["normal", "italic"]),
    # Broad Latin / Greek / Cyrillic. Noto Sans and Tibetan are merged below.
    ("noto-serif", "document", ["latin-ext"], [400, 700], ["normal", "italic"]),
    ("noto-sans-mono", "mono", ["latin-ext"], [400, 700], ["normal"]),
    ("noto-sans-symbols", "symbols", ["symbols"], [400], ["normal"]),
    ("noto-sans-symbols-2", "symbols", ["symbols"], [400], ["normal"]),
    ("stix-two-text", "document", ["latin-ext"], [400, 700], ["normal", "italic"]),
    ("stix-two-math", "symbols", ["latin", "latin-ext", "math"], [400], ["normal"]),
]

# Living scripts merged into the single family "Noto Sans".
# Historic scripts are omitted. A missing italic file is normal.
# Tibetan has no Noto Sans package; it is merged into Noto Serif instead.
NOTO_SANS_PARTS: list[tuple[str, str]] = [
    ("noto-sans", "latin"),
    ("noto-sans", "latin-ext"),
    ("noto-sans", "vietnamese"),
    ("noto-sans", "greek"),
    ("noto-sans", "greek-ext"),
    ("noto-sans", "cyrillic"),
    ("noto-sans", "cyrillic-ext"),
    ("noto-sans-arabic", "arabic"),
    ("noto-sans-hebrew", "hebrew"),
    ("noto-sans-devanagari", "devanagari"),
    ("noto-sans-bengali", "bengali"),
    ("noto-sans-gurmukhi", "gurmukhi"),
    ("noto-sans-gujarati", "gujarati"),
    ("noto-sans-oriya", "oriya"),
    ("noto-sans-tamil", "tamil"),
    ("noto-sans-telugu", "telugu"),
    ("noto-sans-kannada", "kannada"),
    ("noto-sans-malayalam", "malayalam"),
    ("noto-sans-sinhala", "sinhala"),
    ("noto-sans-thai", "thai"),
    ("noto-sans-lao", "lao"),
    ("noto-sans-khmer", "khmer"),
    ("noto-sans-myanmar", "myanmar"),
    ("noto-sans-armenian", "armenian"),
    ("noto-sans-georgian", "georgian"),
    ("noto-sans-ethiopic", "ethiopic"),
    ("noto-sans-cherokee", "cherokee"),
    ("noto-sans-canadian-aboriginal", "canadian-aboriginal"),
    ("noto-sans-adlam", "adlam"),
    ("noto-sans-thaana", "thaana"),
    ("noto-sans-nko", "nko"),
    ("noto-sans-vai", "vai"),
    ("noto-sans-ol-chiki", "ol-chiki"),
    ("noto-sans-tifinagh", "tifinagh"),
    ("noto-sans-syriac", "syriac"),
]
NOTO_SERIF_EXTRA: list[tuple[str, str]] = [
    ("noto-serif-tibetan", "tibetan"),
]
NOTO_MERGE_WEIGHTS = [400, 700]
NOTO_MERGE_STYLES = ["normal", "italic"]

# fontsource static files keep the thin/light instance in the family name.
# The weight class and the outlines are already the file we asked for.
CANONICAL_FAMILY = {
    "eb-garamond": "EB Garamond",
    "libre-baskerville": "Libre Baskerville",
    "libre-caslon-text": "Libre Caslon Text",
    "libre-franklin": "Libre Franklin",
    "carlito": "Carlito",
    "caladea": "Caladea",
    "gelasio": "Gelasio",
    "league-spartan": "League Spartan",
    "philosopher": "Philosopher",
    "gfs-didot": "GFS Didot",
    "inter": "Inter",
    "source-sans-3": "Source Sans 3",
    "source-serif-4": "Source Serif 4",
    "source-code-pro": "Source Code Pro",
    "nunito-sans": "Nunito Sans",
    "open-sans": "Open Sans",
    "roboto": "Roboto",
    "roboto-mono": "Roboto Mono",
    "lato": "Lato",
    "montserrat": "Montserrat",
    "merriweather": "Merriweather",
    "lora": "Lora",
    "literata": "Literata",
    "pt-sans": "PT Sans",
    "pt-serif": "PT Serif",
    "pt-mono": "PT Mono",
    "caveat": "Caveat",
    "ibm-plex-sans": "IBM Plex Sans",
    "ibm-plex-serif": "IBM Plex Serif",
    "ibm-plex-mono": "IBM Plex Mono",
    "agdasima": "Agdasima",
    "bacasime-antique": "Bacasime Antique",
    "belanosima": "Belanosima",
    "caprasimo": "Caprasimo",
    "lunasima": "Lunasima",
    "lumanosimo": "Lumanosimo",
    "lugrasimo": "Lugrasimo",
    "cascadia-code": "Cascadia Code",
    "cascadia-mono": "Cascadia Mono",
    "fira-code": "Fira Code",
    "ubuntu-sans": "Ubuntu Sans",
    "ubuntu-sans-mono": "Ubuntu Sans Mono",
    "noto-sans": "Noto Sans",
    "noto-serif": "Noto Serif",
    "noto-sans-mono": "Noto Sans Mono",
    "noto-sans-symbols": "Noto Sans Symbols",
    "noto-sans-symbols-2": "Noto Sans Symbols 2",
    "stix-two-text": "STIX Two Text",
    "stix-two-math": "STIX Two Math",
    "inconsolata": "Inconsolata",
    "victor-mono": "Victor Mono",
    "intel-one-mono": "Intel One Mono",
    "iosevka": "Iosevka",
    "space-mono": "Space Mono",
    "anonymous-pro": "Anonymous Pro",
    "dm-mono": "DM Mono",
    "red-hat-mono": "Red Hat Mono",
    "overpass-mono": "Overpass Mono",
    "geist-mono": "Geist Mono",
    "commit-mono": "Commit Mono",
    "cousine": "Cousine",
    "fira-mono": "Fira Mono",
    "monaspace-neon": "Monaspace Neon",
    "monaspace-argon": "Monaspace Argon",
    "monaspace-xenon": "Monaspace Xenon",
    "monaspace-radon": "Monaspace Radon",
    "monaspace-krypton": "Monaspace Krypton",
}

# Opt-in coding faces. The default install already has JetBrains Mono,
# Cascadia, Fira Code, Hack, Source Code Pro, and the other mono faces above.
# (fontsource id, weights, styles, menu name)
CODING_FAMILIES: list[tuple[str, list[int], list[str], str]] = [
    ("inconsolata", [400, 700], ["normal"], "Inconsolata"),
    ("victor-mono", [400, 500, 700], ["normal", "italic"], "Victor Mono"),
    ("intel-one-mono", [400, 500, 700], ["normal", "italic"], "Intel One Mono"),
    ("iosevka", [400, 500, 700], ["normal", "italic"], "Iosevka"),
    ("space-mono", [400, 700], ["normal", "italic"], "Space Mono"),
    ("anonymous-pro", [400, 700], ["normal", "italic"], "Anonymous Pro"),
    ("dm-mono", [400, 500], ["normal", "italic"], "DM Mono"),
    ("red-hat-mono", [400, 500, 700], ["normal", "italic"], "Red Hat Mono"),
    ("overpass-mono", [400, 700], ["normal"], "Overpass Mono"),
    ("geist-mono", [400, 500, 700], ["normal", "italic"], "Geist Mono"),
    ("commit-mono", [400, 500, 700], ["normal", "italic"], "Commit Mono"),
    ("cousine", [400, 700], ["normal", "italic"], "Cousine"),
    ("fira-mono", [400, 500, 700], ["normal"], "Fira Mono"),
    ("monaspace-neon", [400, 500, 700], ["normal", "italic"], "Monaspace Neon"),
    ("monaspace-argon", [400, 500, 700], ["normal", "italic"], "Monaspace Argon"),
    ("monaspace-xenon", [400, 500, 700], ["normal", "italic"], "Monaspace Xenon"),
    ("monaspace-radon", [400, 500, 700], ["normal", "italic"], "Monaspace Radon"),
    ("monaspace-krypton", [400, 500, 700], ["normal", "italic"], "Monaspace Krypton"),
]
JULIA_MONO_URL = "https://github.com/cormullion/juliamono/releases/download/v0.63.2/JuliaMono-ttf.zip"
JULIA_MONO_FILES = {
    "JuliaMono-Regular.ttf": "Regular",
    "JuliaMono-RegularItalic.ttf": "Italic",
    "JuliaMono-Medium.ttf": "Medium",
    "JuliaMono-MediumItalic.ttf": "Medium Italic",
    "JuliaMono-Bold.ttf": "Bold",
    "JuliaMono-BoldItalic.ttf": "Bold Italic",
}

FONTSOURCE_FILE = re.compile(
    r"^(?P<fid>.+)-(?P<subset>latin-ext|latin|hebrew|arabic|devanagari|thai|symbols|emoji|math)"
    r"-(?P<weight>\d+)-(?P<style>normal|italic)\.ttf$"
)

# Familiar menu name -> open family that should also answer to it.
# Applied only when the familiar name is not already installed for real.
MENU_NAMES: list[tuple[str, str]] = [
    ("Garamond", "EB Garamond"),
    ("Apple Garamond", "EB Garamond"),
    ("ITC Garamond", "EB Garamond"),
    ("Calibri", "Carlito"),
    ("Cambria", "Caladea"),
    ("Georgia", "Gelasio"),
    ("Segoe UI", "Selawik"),
    ("Aptos", "Carlito"),
    ("Helvetica", "TeX Gyre Heros"),
    ("Helvetica Neue", "TeX Gyre Heros"),
    ("Helvetica Narrow", "TeX Gyre Heros Cn"),
    ("Arial Narrow", "TeX Gyre Heros Cn"),
    ("Gill Sans", "Gillius ADF No2"),
    ("Gill Sans MT", "Gillius ADF No2"),
    ("Didot", "GFS Didot"),
    ("Baskerville", "Libre Baskerville"),
    ("Baskerville Old Face", "Bacasime Antique"),
    ("Lucida Grande", "Lunasima"),
    ("Futura", "League Spartan"),
    ("Optima", "Philosopher"),
    ("Century Gothic", "TeX Gyre Adventor"),
    ("SF Pro", "Inter"),
    ("San Francisco", "Inter"),
    ("New York", "Source Serif 4"),
    ("Avenir", "Nunito Sans"),
    ("Avenir Next", "Nunito Sans"),
]

# LeelUIsl.ttf does not contain "leelaw" or "leela", so match "leelui" too.
MS_SKIP = re.compile(
    r"(malgun|ebrima|gadugi|leelaw|leelui|leela|seguiemj|seguihis)",
    re.IGNORECASE,
)

OLD_USER_DIRS = [
    "Apple",
    "EB Garamond",
    "Hack",
    "ms-fonts",
    "Nerd-fonts",
    "Noto",
    "ubuntu",
]

# Path rules, not family names. D050000L and StandardSymbolsPS stay available.
# Applied only when TeX Gyre is installed, so a machine without it keeps URW.
URW_GLOBS = [
    "/usr/share/fonts/gsfonts/Nimbus*",
    "/usr/share/fonts/gsfonts/C059*",
    "/usr/share/fonts/gsfonts/P052*",
    "/usr/share/fonts/gsfonts/Z003*",
    "/usr/share/fonts/gsfonts/URW*",
    "/usr/share/fonts/opentype/urw-base35/Nimbus*",
    "/usr/share/fonts/opentype/urw-base35/C059*",
    "/usr/share/fonts/opentype/urw-base35/P052*",
    "/usr/share/fonts/opentype/urw-base35/Z003*",
    "/usr/share/fonts/opentype/urw-base35/URW*",
    "/usr/share/fonts/truetype/urw-base35/Nimbus*",
    "/usr/share/fonts/truetype/urw-base35/C059*",
    "/usr/share/fonts/truetype/urw-base35/P052*",
    "/usr/share/fonts/truetype/urw-base35/Z003*",
    "/usr/share/fonts/truetype/urw-base35/URW*",
]


def log(msg: str) -> None:
    print(msg, flush=True)


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)


def require_tools(download: bool = False) -> None:
    needed = ["fc-cache", "fc-list", "fc-match", "fc-query"]
    if download:
        needed.insert(0, "curl")
    missing = [tool for tool in needed if shutil.which(tool) is None]
    if missing:
        sys.exit("Missing required tools: " + ", ".join(missing))


def file_head(path: Path) -> bytes:
    try:
        return path.read_bytes()[:8]
    except OSError:
        return b""


def is_font(path: Path) -> bool:
    return file_head(path)[:4] in {b"\x00\x01\x00\x00", b"OTTO", b"ttcf", b"true"}


def payload_ok(path: Path) -> bool:
    if path.stat().st_size < 500:
        return False
    head = file_head(path)
    name = path.name.lower()
    if name.endswith((".ttf", ".otf", ".ttc")):
        return is_font(path)
    if name.endswith(".zip"):
        return head.startswith(b"PK")
    if name.endswith(".deb"):
        return head.startswith(b"!<arch>")
    if name.endswith(".gz") or name.endswith(".tgz"):
        return head.startswith(b"\x1f\x8b")
    if name.endswith(".xz"):
        return head.startswith(b"\xfd7zXZ")
    if name.endswith(".bz2"):
        return head.startswith(b"BZh")
    return True


def _checksum(data: bytes) -> int:
    pad = (4 - len(data) % 4) % 4
    buf = data + b"\x00" * pad
    total = 0
    for i in range(0, len(buf), 4):
        total = (total + int.from_bytes(buf[i:i + 4], "big")) & 0xFFFFFFFF
    return total


def _encode_name(platform: int, text: str) -> bytes:
    if platform == 1:
        return text.encode("mac_roman")
    return text.encode("utf-16-be")


def _rebuild_name_table(table: bytes, mapping: dict[int, str]) -> bytes:
    import struct

    fmt, count, _string_offset = struct.unpack_from(">HHH", table, 0)
    if fmt != 0:
        raise ValueError(f"unsupported name table format {fmt}")
    string_offset = _string_offset
    records = []
    for i in range(count):
        plat, enc, lang, name_id, length, offset = struct.unpack_from(">HHHHHH", table, 6 + i * 12)
        raw = table[string_offset + offset:string_offset + offset + length]
        if name_id in mapping:
            raw = _encode_name(plat, mapping[name_id])
        records.append((plat, enc, lang, name_id, raw))
    strings = bytearray()
    rec_bytes = bytearray()
    for plat, enc, lang, name_id, raw in records:
        rec_bytes += struct.pack(">HHHHHH", plat, enc, lang, name_id, len(raw), len(strings))
        strings += raw
    header = struct.pack(">HHH", 0, count, 6 + len(rec_bytes))
    return header + bytes(rec_bytes) + bytes(strings)


def rewrite_ttf_names(path: Path, mapping: dict[int, str]) -> None:
    """Replace family and style names. Outlines and weight class stay as they are."""
    import struct

    blob = path.read_bytes()
    if blob[:4] not in (b"\x00\x01\x00\x00", b"true", b"typ1", b"OTTO"):
        raise ValueError(path.name)
    num_tables = struct.unpack_from(">H", blob, 4)[0]
    records = []
    for i in range(num_tables):
        tag, _check, offset, length = struct.unpack_from(">4sIII", blob, 12 + i * 16)
        data = bytearray(blob[offset:offset + length])
        if tag == b"name":
            data = bytearray(_rebuild_name_table(bytes(data), mapping))
        records.append({"tag": tag, "data": data})
    for rec in records:
        if rec["tag"] == b"head":
            rec["data"][8:12] = b"\x00\x00\x00\x00"
    cursor = 12 + num_tables * 16
    placed = []
    for rec in records:
        if cursor % 4:
            cursor += 4 - (cursor % 4)
        rec["offset"] = cursor
        rec["checksum"] = _checksum(bytes(rec["data"]))
        placed.append((cursor, bytes(rec["data"])))
        cursor += len(rec["data"])
    out = bytearray(cursor)
    out[:12] = blob[:12]
    for i, rec in enumerate(records):
        struct.pack_into(
            ">4sIII", out, 12 + i * 16,
            rec["tag"], rec["checksum"], rec["offset"], len(rec["data"]),
        )
    for offset, data in placed:
        out[offset:offset + len(data)] = data
    adjustment = (0xB1B0AFBA - _checksum(bytes(out))) & 0xFFFFFFFF
    for rec in records:
        if rec["tag"] == b"head":
            struct.pack_into(">I", out, rec["offset"] + 8, adjustment)
            break
    tmp = path.with_name(path.name + ".namefix")
    tmp.write_bytes(out)
    tmp.replace(path)


def style_label(weight: int, style: str) -> str:
    italic = style == "italic"
    labels = {
        400: ("Regular", "Italic"),
        500: ("Medium", "Medium Italic"),
        600: ("SemiBold", "SemiBold Italic"),
        700: ("Bold", "Bold Italic"),
    }
    if weight in labels:
        return labels[weight][1 if italic else 0]
    return "Bold Italic" if italic and weight >= 700 else "Bold" if weight >= 700 else "Italic" if italic else "Regular"


def ps_name(family: str, style: str) -> str:
    def token(text: str) -> str:
        return "".join(ch for ch in text if ch.isalnum())
    return f"{token(family)}-{token(style)}"


def rewrite_ubuntu_medium() -> None:
    """Ubuntu 0.83's Medium face is labeled Ubuntu Light / Bold in the Windows name table."""
    path = STAGE / "ubuntu" / "Ubuntu-M.ttf"
    if not path.is_file():
        return
    mapping = {
        1: "Ubuntu",
        2: "Medium",
        4: "Ubuntu Medium",
        6: "Ubuntu-Medium",
        16: "Ubuntu",
        17: "Medium",
    }
    try:
        rewrite_ttf_names(path, mapping)
    except Exception as exc:
        log(f"  warn  name fix failed for Ubuntu-M.ttf: {exc}")


def rewrite_jetbrains_names() -> None:
    """One menu name. The archive also publishes a short NFM family and a Medium family."""
    styles = {
        "JetBrainsMonoNerdFontMono-Regular.ttf": "Regular",
        "JetBrainsMonoNerdFontMono-Italic.ttf": "Italic",
        "JetBrainsMonoNerdFontMono-Medium.ttf": "Medium",
        "JetBrainsMonoNerdFontMono-MediumItalic.ttf": "Medium Italic",
        "JetBrainsMonoNerdFontMono-Bold.ttf": "Bold",
        "JetBrainsMonoNerdFontMono-BoldItalic.ttf": "Bold Italic",
    }
    family = "JetBrainsMono Nerd Font Mono"
    folder = STAGE / "mono"
    if not folder.is_dir():
        return
    for name, style in styles.items():
        path = folder / name
        if not path.is_file():
            continue
        mapping = {
            1: family,
            2: style,
            4: f"{family} {style}",
            6: ps_name(family, style),
            16: family,
            17: style,
            21: family,
            22: style,
        }
        try:
            rewrite_ttf_names(path, mapping)
        except Exception as exc:
            log(f"  warn  name fix failed for {name}: {exc}")


def rewrite_staged_fontsource_names() -> None:
    count = 0
    for path in STAGE.rglob("*.ttf"):
        match = FONTSOURCE_FILE.match(path.name)
        if match is None:
            continue
        family = CANONICAL_FAMILY.get(match.group("fid"))
        if family is None:
            log(f"  warn  no family name for {path.name}")
            continue
        style = style_label(int(match.group("weight")), match.group("style"))
        mapping = {
            1: family,
            2: style,
            4: f"{family} {style}",
            6: ps_name(family, style),
            16: family,
            17: style,
            21: family,
            22: style,
        }
        try:
            rewrite_ttf_names(path, mapping)
        except Exception as exc:
            log(f"  warn  name fix failed for {path.name}: {exc}")
            continue
        count += 1
    log(f"  names {count} fontsource files")


def curl(url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and payload_ok(dest):
        return True
    dest.unlink(missing_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    proc = subprocess.run(
        [
            "curl", "-sS", "-L", "--retry", "3", "--retry-delay", "2",
            "-A", UA, "-o", str(tmp), "-w", "%{http_code}", url,
        ],
        text=True,
        capture_output=True,
    )
    status = (proc.stdout or "").strip()
    # A missing italic file is normal. Keep network failures visible.
    if proc.returncode != 0 and status != "404":
        err = (proc.stderr or "").strip()
        if err:
            log(f"  warn  download: {err}")
    if proc.returncode != 0 or status != "200" or not tmp.exists() or not payload_ok(tmp):
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(dest)
    return True


def fontsource_url(fid: str, subset: str, weight: int, style: str) -> str:
    return FONTSOURCE.format(fid=fid, subset=subset, weight=weight, style=style)


def latin_family(subsets: list[str]) -> bool:
    return bool(subsets) and all(subset in ("latin", "latin-ext") for subset in subsets)


def has_english_letters(path: Path) -> bool:
    from fontTools.ttLib import TTFont

    font = TTFont(path, lazy=True)
    cmap = None
    for table in font["cmap"].tables:
        if table.platformID == 3 and table.platEncID == 1:
            cmap = table.cmap
            break
    if cmap is None:
        cmap = font.getBestCmap() or {}
    return all(ord(ch) in cmap for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")


def merge_rank(path: Path) -> tuple[int, str]:
    """Latin alphabet first, accents second, every other cut after that."""
    name = path.name
    if "-latin-ext-" in name:
        return (1, name)
    if "-latin-" in name:
        return (0, name)
    return (2, name)


def merge_into(parts: list[Path], dest: Path) -> None:
    """Join cuts of one face. The latin file stays first so its name and letters win."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(parts, key=merge_rank)
    if len(ordered) == 1:
        if ordered[0].resolve() != dest.resolve():
            shutil.copy2(ordered[0], dest)
        return
    from fontTools.merge import Merger
    from fontTools.ttLib import TTFont

    # Ethiopic, Thaana, and Canadian Aboriginal ship vertical-layout tables.
    # fontTools cannot merge those, and a word processor does not need them.
    with tempfile.TemporaryDirectory(prefix="usfont-merge-") as tmp:
        tmp_path = Path(tmp)
        cleaned: list[Path] = []
        for index, path in enumerate(ordered):
            font = TTFont(path)
            dropped = [tag for tag in ("vhea", "vmtx", "VORG") if tag in font]
            if not dropped:
                font.close()
                cleaned.append(path)
                continue
            for tag in dropped:
                del font[tag]
            out = tmp_path / f"{index}.ttf"
            font.save(out)
            cleaned.append(out)
        merged = Merger().merge([str(path) for path in cleaned])
        tmp_out = dest.with_name(dest.name + ".merge")
        merged.save(str(tmp_out))
        tmp_out.replace(dest)


def cover_vertical_metrics(path: Path) -> None:
    """Grow the line box so a taller script is not clipped by the latin metrics."""
    from fontTools.ttLib import TTFont

    font = TTFont(path)
    if "glyf" not in font:
        font.close()
        return
    ymax = 0
    ymin = 0
    for glyph in font["glyf"].glyphs.values():
        try:
            y0, y1 = glyph.yMin, glyph.yMax
        except AttributeError:
            continue
        ymax = max(ymax, y1)
        ymin = min(ymin, y0)
    hhea = font["hhea"]
    os2 = font["OS/2"]
    hhea.ascent = max(hhea.ascent, ymax)
    hhea.descent = min(hhea.descent, ymin)
    os2.sTypoAscender = max(os2.sTypoAscender, ymax)
    os2.sTypoDescender = min(os2.sTypoDescender, ymin)
    os2.usWinAscent = max(os2.usWinAscent, ymax)
    os2.usWinDescent = max(os2.usWinDescent, -ymin)
    font.save(path)


def cached_font(fid: str, subset: str, weight: int, style: str) -> Path | None:
    path = DOWNLOADS / "fontsource" / f"{fid}-{subset}-{weight}-{style}.ttf"
    if path.is_file() and is_font(path):
        return path
    return None


def queue_fontsource(downloads: dict[Path, str], fid: str, subset: str, weight: int, style: str) -> None:
    cache = DOWNLOADS / "fontsource" / f"{fid}-{subset}-{weight}-{style}.ttf"
    downloads[cache] = fontsource_url(fid, subset, weight, style)


def install_noto_sans(failures: list[str]) -> None:
    """One menu row. Script packages are renamed onto Noto Sans by the merger."""
    dest_dir = STAGE / "document"
    dest_dir.mkdir(parents=True, exist_ok=True)
    made = 0
    for weight in NOTO_MERGE_WEIGHTS:
        for style in NOTO_MERGE_STYLES:
            parts = []
            for fid, subset in NOTO_SANS_PARTS:
                path = cached_font(fid, subset, weight, style)
                if path is not None:
                    parts.append(path)
            if not parts:
                continue
            dest = dest_dir / f"noto-sans-latin-{weight}-{style}.ttf"
            core = [path for path in parts if "-latin-" in path.name or "-latin-ext-" in path.name]
            try:
                merge_into(parts, dest)
            except Exception as exc:
                log(f"  warn  Noto Sans merge failed for {weight} {style}: {exc}")
                if not core:
                    continue
                try:
                    merge_into(core, dest)
                except Exception as inner:
                    log(f"  warn  Noto Sans latin merge failed for {weight} {style}: {inner}")
                    continue
            if is_font(dest) and has_english_letters(dest):
                try:
                    cover_vertical_metrics(dest)
                except Exception as exc:
                    log(f"  warn  Noto Sans metrics left as merged for {weight} {style}: {exc}")
                made += 1
            else:
                dest.unlink(missing_ok=True)
                log(f"  warn  Noto Sans {weight} {style} has no English alphabet")
    present = [
        subset for fid, subset in NOTO_SANS_PARTS
        if cached_font(fid, subset, 400, "normal") is not None
    ]
    if made == 0:
        failures.append("noto-sans")
        log("  miss  noto-sans")
    else:
        log(f"  ok    noto-sans ({made} faces, {len(present)} scripts)")


def install_noto_serif_tibetan() -> None:
    """Tibetan is published as Noto Serif Tibetan. Fold it into Noto Serif."""
    folded = 0
    for weight in NOTO_MERGE_WEIGHTS:
        for style in NOTO_MERGE_STYLES:
            dest = STAGE / "document" / f"noto-serif-latin-{weight}-{style}.ttf"
            extras = []
            for fid, subset in NOTO_SERIF_EXTRA:
                path = cached_font(fid, subset, weight, style)
                if path is not None:
                    extras.append(path)
            if not dest.is_file() or not extras:
                continue
            backup = dest.with_name(dest.name + ".latin")
            shutil.copy2(dest, backup)
            try:
                merge_into([backup, *extras], dest)
                cover_vertical_metrics(dest)
            except Exception as exc:
                log(f"  warn  Tibetan merge failed for Noto Serif {weight} {style}: {exc}")
                shutil.copy2(backup, dest)
                backup.unlink(missing_ok=True)
                continue
            if not has_english_letters(dest):
                log(f"  warn  Noto Serif {weight} {style} lost the English alphabet")
                shutil.copy2(backup, dest)
                backup.unlink(missing_ok=True)
                continue
            backup.unlink(missing_ok=True)
            folded += 1
    if folded:
        log(f"  ok    noto-serif tibetan ({folded})")


def install_fontsource(failures: list[str]) -> None:
    # latin-ext is the accent cut only. It has no A–Z, so a preview of the
    # font name comes out as garbage. Merge it with the latin cut.
    downloads: dict[Path, str] = {}
    latin_specs = []
    other_specs = []
    for spec in FONTSOURCE_FAMILIES:
        fid, _folder, subsets, weights, styles = spec
        if latin_family(subsets):
            latin_specs.append(spec)
            for weight in weights:
                for style in styles:
                    for subset in ("latin", "latin-ext"):
                        queue_fontsource(downloads, fid, subset, weight, style)
        else:
            other_specs.append(spec)
    for fid, subset in NOTO_SANS_PARTS + NOTO_SERIF_EXTRA:
        for weight in NOTO_MERGE_WEIGHTS:
            for style in NOTO_MERGE_STYLES:
                queue_fontsource(downloads, fid, subset, weight, style)
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(curl, url, cache) for cache, url in downloads.items()]
        for fut in futures:
            fut.result()

    for fid, folder, _subsets, weights, styles in latin_specs:
        dest_dir = STAGE / folder
        dest_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        for weight in weights:
            for style in styles:
                parts = []
                for subset in ("latin", "latin-ext"):
                    cache = DOWNLOADS / "fontsource" / f"{fid}-{subset}-{weight}-{style}.ttf"
                    if cache.is_file() and is_font(cache):
                        parts.append(cache)
                if not parts:
                    continue
                dest = dest_dir / f"{fid}-latin-{weight}-{style}.ttf"
                try:
                    merge_into(parts, dest)
                except Exception as exc:
                    log(f"  warn  merge failed for {fid} {weight} {style}: {exc}")
                    basic = [path for path in parts if "-latin-ext-" not in path.name]
                    shutil.copy2(basic[0] if basic else parts[0], dest)
                if is_font(dest) and has_english_letters(dest):
                    count += 1
                else:
                    dest.unlink(missing_ok=True)
                    log(f"  warn  {fid} {weight} {style} has no English alphabet")
        if count == 0:
            failures.append(fid)
            log(f"  miss  {fid}")
        else:
            log(f"  ok    {fid} ({count})")

    install_noto_sans(failures)
    install_noto_serif_tibetan()

    for fid, folder, subsets, weights, styles in other_specs:
        chosen: str | None = None
        for subset in subsets:
            probe = DOWNLOADS / "fontsource" / f"{fid}-{subset}-{weights[0]}-{styles[0]}.ttf"
            url = fontsource_url(fid, subset, weights[0], styles[0])
            if curl(url, probe) and is_font(probe):
                chosen = subset
                break
            probe.unlink(missing_ok=True)
        if chosen is None:
            failures.append(fid)
            log(f"  miss  {fid}")
            continue
        dest_dir = STAGE / folder
        dest_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        probe = DOWNLOADS / "fontsource" / f"{fid}-{chosen}-{weights[0]}-{styles[0]}.ttf"
        shutil.copy2(probe, dest_dir / probe.name)
        count += 1
        pending: list[tuple[str, Path]] = []
        for weight in weights:
            for style in styles:
                if weight == weights[0] and style == styles[0]:
                    continue
                cache = DOWNLOADS / "fontsource" / f"{fid}-{chosen}-{weight}-{style}.ttf"
                url = fontsource_url(fid, chosen, weight, style)
                pending.append((url, cache))
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {pool.submit(curl, url, cache): cache for url, cache in pending}
            for fut in as_completed(futures):
                cache = futures[fut]
                if fut.result() and is_font(cache):
                    shutil.copy2(cache, dest_dir / cache.name)
                    count += 1
        if count == 0:
            failures.append(fid)
            log(f"  miss  {fid}")
        else:
            log(f"  ok    {fid} ({count})")


def extract_fonts(archive: Path, dest: Path, pred) -> int:
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    name = archive.name.lower()
    if name.endswith(".zip") or zipfile.is_zipfile(archive):
        try:
            zf_ctx = zipfile.ZipFile(archive)
        except zipfile.BadZipFile:
            return 0
        with zf_ctx as zf:
            for info in zf.infolist():
                base = Path(info.filename).name
                if not pred(base):
                    continue
                target = dest / base
                with zf.open(info) as src, target.open("wb") as out:
                    shutil.copyfileobj(src, out)
                if is_font(target):
                    count += 1
                else:
                    target.unlink(missing_ok=True)
        return count
    if name.endswith(".tar.xz") or name.endswith(".tar.gz") or name.endswith(".tar.bz2") or name.endswith(".tgz"):
        with tarfile.open(archive) as tf:
            for member in tf.getmembers():
                base = Path(member.name).name
                if not member.isfile() or not pred(base):
                    continue
                src = tf.extractfile(member)
                if src is None:
                    continue
                target = dest / base
                with target.open("wb") as out:
                    shutil.copyfileobj(src, out)
                if is_font(target):
                    count += 1
                else:
                    target.unlink(missing_ok=True)
        return count
    return 0


def extract_deb(deb: Path, dest: Path, pred) -> int:
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="usfont-deb-") as tmp:
        tmp_path = Path(tmp)
        extractor = "bsdtar" if shutil.which("bsdtar") else None
        if extractor:
            proc = run([extractor, "-xf", str(deb), "-C", str(tmp_path)])
            if proc.returncode != 0:
                return 0
        elif shutil.which("ar"):
            proc = run(["ar", "x", str(deb)], cwd=tmp_path)
            if proc.returncode != 0:
                return 0
        else:
            log("  skip  deb extract (need bsdtar or ar)")
            return 0
        data = next(tmp_path.glob("data.tar*"), None)
        if data is None:
            return 0
        inner = tmp_path / "inner"
        inner.mkdir()
        proc = run(["tar", "-xf", str(data), "-C", str(inner)])
        if proc.returncode != 0:
            log(f"  warn  could not unpack {data.name}: {proc.stderr.strip()}")
            return 0
        count = 0
        for path in inner.rglob("*"):
            if path.is_file() and pred(path.name) and is_font(path):
                shutil.copy2(path, dest / path.name)
                count += 1
        return count


def install_archives(failures: list[str]) -> dict[str, bool]:
    flags = {"liberation": False, "ubuntu": False, "dejavu": False, "hack": False,
             "jetbrains": False, "symbols": False, "texgyre": False, "gillius": False,
             "cjk": False, "selawik": False, "notomath": False, "emoji": False}
    dest_mono = STAGE / "mono"
    dest_doc = STAGE / "document"
    dest_sym = STAGE / "symbols"
    dest_fb = STAGE / "fallback"
    dest_ub = STAGE / "ubuntu"

    # fonts-liberation2 is an empty transitional package. The faces are in fonts-liberation.
    deb = DOWNLOADS / "fonts-liberation_2.1.5-3_all.deb"
    url = "https://deb.debian.org/debian/pool/main/f/fonts-liberation/fonts-liberation_2.1.5-3_all.deb"
    n = extract_deb(deb, dest_doc, lambda name: name.lower().endswith(".ttf")) if curl(url, deb) else 0
    source = "deb"
    if n == 0:
        for folder in (
            Path("/usr/share/fonts/liberation"),
            Path("/usr/share/fonts/truetype/liberation"),
            Path("/usr/share/fonts/truetype/liberation2"),
        ):
            n = copy_font_dir(folder, dest_doc)
            if n:
                source = str(folder)
                break
    flags["liberation"] = n > 0
    if flags["liberation"]:
        log(f"  ok    liberation ({n}, {source})")
    else:
        failures.append("liberation")
        log("  miss  liberation")

    ub = DOWNLOADS / "ubuntu-font-family-0.83.zip"
    if curl("https://assets.ubuntu.com/v1/0cef8205-ubuntu-font-family-0.83.zip", ub):
        def keep_ubuntu(name: str) -> bool:
            if not name.lower().endswith((".ttf", ".otf")):
                return False
            stem = Path(name).stem.lower()
            return stem in {
                "ubuntu-r", "ubuntu-b", "ubuntu-i", "ubuntu-bi", "ubuntu-m",
                "ubuntu-c", "ubuntu-ri",
                "ubuntumono-r", "ubuntumono-b", "ubuntumono-ri", "ubuntumono-bi",
            }
        n = extract_fonts(ub, dest_ub, keep_ubuntu)
        flags["ubuntu"] = n > 0
        log(f"  {'ok' if n else 'miss'}  ubuntu ({n})")
    else:
        failures.append("ubuntu")
        log("  miss  ubuntu")

    dejavu = DOWNLOADS / "dejavu-fonts-ttf-2.37.tar.bz2"
    if curl("https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.tar.bz2", dejavu):
        keep = {
            "DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans-Oblique.ttf", "DejaVuSans-BoldOblique.ttf",
            "DejaVuSerif.ttf", "DejaVuSerif-Bold.ttf", "DejaVuSerif-Italic.ttf", "DejaVuSerif-BoldItalic.ttf",
            "DejaVuSansMono.ttf", "DejaVuSansMono-Bold.ttf", "DejaVuSansMono-Oblique.ttf", "DejaVuSansMono-BoldOblique.ttf",
        }
        n = extract_fonts(dejavu, dest_doc, lambda name: name in keep)
        flags["dejavu"] = n > 0
        log(f"  {'ok' if n else 'miss'}  dejavu ({n})")
    else:
        failures.append("dejavu")
        log("  miss  dejavu")

    hack = DOWNLOADS / "Hack-v3.003-ttf.zip"
    if curl("https://github.com/source-foundry/Hack/releases/download/v3.003/Hack-v3.003-ttf.zip", hack):
        n = extract_fonts(hack, dest_mono, lambda name: name.lower().endswith(".ttf") and "hack-" in name.lower())
        flags["hack"] = n > 0
        log(f"  {'ok' if n else 'miss'}  hack ({n})")
    else:
        failures.append("hack")
        log("  miss  hack")

    jb = DOWNLOADS / "JetBrainsMono.tar.xz"
    if curl("https://github.com/ryanoasis/nerd-fonts/releases/latest/download/JetBrainsMono.tar.xz", jb):
        keep = {
            "JetBrainsMonoNerdFontMono-Regular.ttf",
            "JetBrainsMonoNerdFontMono-Italic.ttf",
            "JetBrainsMonoNerdFontMono-Medium.ttf",
            "JetBrainsMonoNerdFontMono-MediumItalic.ttf",
            "JetBrainsMonoNerdFontMono-Bold.ttf",
            "JetBrainsMonoNerdFontMono-BoldItalic.ttf",
        }
        n = extract_fonts(jb, dest_mono, lambda name: name in keep)
        flags["jetbrains"] = n > 0
        log(f"  {'ok' if n else 'miss'}  jetbrains mono nerd ({n})")
    else:
        failures.append("jetbrains-mono-nerd")
        log("  miss  jetbrains mono nerd")

    sym = DOWNLOADS / "NerdFontsSymbolsOnly.tar.xz"
    if curl("https://github.com/ryanoasis/nerd-fonts/releases/latest/download/NerdFontsSymbolsOnly.tar.xz", sym):
        n = extract_fonts(sym, dest_sym, lambda name: name == "SymbolsNerdFont-Regular.ttf")
        flags["symbols"] = n > 0
        log(f"  {'ok' if n else 'miss'}  nerd symbols ({n})")
    else:
        failures.append("nerd-symbols")
        log("  miss  nerd symbols")

    sel = DOWNLOADS / "Selawik_Release.zip"
    if curl("https://github.com/Microsoft/Selawik/releases/download/1.01/Selawik_Release.zip", sel):
        def keep_sel(name: str) -> bool:
            # selawk.ttf, selawkb.ttf, selawksb.ttf. Light faces are left out.
            return Path(name).name.lower() in {"selawk.ttf", "selawkb.ttf"}
        n = extract_fonts(sel, dest_doc, keep_sel)
        flags["selawik"] = n > 0
        log(f"  {'ok' if n else 'miss'}  selawik ({n})")
    else:
        failures.append("selawik")
        log("  miss  selawik")

    math = DOWNLOADS / "NotoSansMath-Regular.ttf"
    math_url = "https://github.com/google/fonts/raw/main/ofl/notosansmath/NotoSansMath-Regular.ttf"
    if curl(math_url, math) and is_font(math):
        dest_sym.mkdir(parents=True, exist_ok=True)
        shutil.copy2(math, dest_sym / math.name)
        flags["notomath"] = True
        log("  ok    noto sans math")
    else:
        failures.append("noto-sans-math")
        log("  miss  noto sans math")

    tex_urls = [
        "https://mirrors.mit.edu/CTAN/fonts/tex-gyre.zip",
        "https://mirror.ctan.org/fonts/tex-gyre.zip",
        "https://ctan.org/tex-archive/fonts/tex-gyre.zip",
    ]
    tex = DOWNLOADS / "tex-gyre.zip"
    if not (tex.exists() and tex.stat().st_size > 100000):
        for url in tex_urls:
            if curl(url, tex):
                break
    if tex.exists():
        n = extract_fonts(tex, dest_doc, lambda name: name.lower().endswith(".otf"))
        flags["texgyre"] = n > 0
        log(f"  {'ok' if n else 'miss'}  tex gyre ({n})")
    if not flags["texgyre"]:
        failures.append("tex-gyre")
        copied = copy_gsfonts(dest_doc)
        log(f"  {'ok' if copied else 'miss'}  urw fallback from gsfonts ({copied})")

    gill_urls = [
        "https://mirrors.mit.edu/CTAN/fonts/gillius.zip",
        "https://mirrors.ctan.org/fonts/gillius.zip",
    ]
    gill = DOWNLOADS / "gillius.zip"
    if not (gill.exists() and gill.stat().st_size > 10000):
        for url in gill_urls:
            if curl(url, gill):
                break
    if gill.exists():
        keep_gill = {
            "GilliusADFNo2-Regular.otf",
            "GilliusADFNo2-Bold.otf",
            "GilliusADFNo2-Italic.otf",
            "GilliusADFNo2-BoldItalic.otf",
        }
        n = extract_fonts(gill, dest_doc, lambda name: name in keep_gill)
        flags["gillius"] = n > 0
        log(f"  {'ok' if n else 'miss'}  gillius ({n})")
    else:
        failures.append("gillius")
        log("  miss  gillius")

    cjk = DOWNLOADS / "08_NotoSansCJKsc.zip"
    cjk_url = "https://github.com/notofonts/noto-cjk/releases/download/Sans2.004/08_NotoSansCJKsc.zip"
    if curl(cjk_url, cjk):
        n = extract_fonts(
            cjk,
            dest_fb,
            lambda name: bool(re.search(r"-Regular\.|-Bold\.(otf|ttf|ttc)$", name, re.I))
            and "Mono" not in name,
        )
        flags["cjk"] = n > 0
        log(f"  {'ok' if n else 'miss'}  noto sans cjk sc ({n})")
    else:
        failures.append("noto-cjk")
        log("  miss  noto sans cjk sc")

    copied = copy_symbol_ps(dest_sym)
    if copied:
        log(f"  ok    standard symbols ({copied})")

    # Bitmap Noto Color Emoji. fontconfig records its cmap; the COLR build from
    # fontsource leaves U+1F600 out of the charset, so Word cannot fall back to it.
    emoji_deb = DOWNLOADS / "fonts-noto-color-emoji_2.051-1_all.deb"
    emoji_url = "https://deb.debian.org/debian/pool/main/f/fonts-noto-color-emoji/fonts-noto-color-emoji_2.051-1_all.deb"
    n = 0
    if curl(emoji_url, emoji_deb):
        n = extract_deb(emoji_deb, dest_sym, lambda name: name == "NotoColorEmoji.ttf")
    if n == 0:
        for folder in (Path("/usr/share/fonts/noto"), Path("/usr/share/fonts/truetype/noto")):
            hit = folder / "NotoColorEmoji.ttf"
            if hit.is_file() and is_font(hit):
                dest_sym.mkdir(parents=True, exist_ok=True)
                shutil.copy2(hit, dest_sym / hit.name)
                n = 1
                break
    flags["emoji"] = n > 0
    if flags["emoji"]:
        log(f"  ok    noto color emoji ({n})")
    else:
        failures.append("noto-color-emoji")
        log("  miss  noto color emoji")
    return flags


def copy_font_dir(src: Path, dest: Path) -> int:
    if not src.is_dir():
        return 0
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for path in src.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".ttf", ".otf", ".ttc"} and is_font(path):
            shutil.copy2(path, dest / path.name)
            n += 1
    return n


def copy_gsfonts(dest: Path) -> int:
    src = Path("/usr/share/fonts/gsfonts")
    if not src.is_dir():
        return 0
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for path in src.iterdir():
        if path.suffix.lower() in {".otf", ".ttf"} and is_font(path):
            shutil.copy2(path, dest / path.name)
            n += 1
    return n


def copy_symbol_ps(dest: Path) -> int:
    src = Path("/usr/share/fonts/gsfonts")
    if not src.is_dir():
        return 0
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for path in src.iterdir():
        if path.name in {"StandardSymbolsPS.otf", "D050000L.otf"}:
            shutil.copy2(path, dest / path.name)
            n += 1
    return n


def install_local_microsoft(skip_cascadia: bool) -> int:
    src = ROOT / "ms-fonts"
    if not src.is_dir():
        log("  skip  local Microsoft fonts (no ./ms-fonts directory)")
        return 0
    log("  note  copying Microsoft fonts from ./ms-fonts")
    log("        Those files stay on this machine. They are licensed with Windows")
    log("        or Microsoft 365. Do not give that folder to someone who lacks a license.")
    dest = STAGE / "microsoft"
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for path in sorted(src.iterdir()):
        if path.suffix.lower() not in {".ttf", ".otf", ".ttc"}:
            continue
        if MS_SKIP.search(path.name):
            continue
        if skip_cascadia and "cascadia" in path.name.lower():
            continue
        if not is_font(path):
            continue
        shutil.copy2(path, dest / path.name)
        n += 1
    log(f"  ok    microsoft ({n}, non-English UI fonts left out)")
    return n


def install_dropin(folder_name: str) -> int:
    """Copy fonts from a folder next to this script. Names and files are kept."""
    src = ROOT / folder_name
    if not src.is_dir():
        return 0
    dest_root = STAGE / folder_name
    n = 0
    for path in sorted(src.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() not in {".ttf", ".otf", ".ttc"}:
            continue
        rel = path.relative_to(src)
        if not is_font(path):
            log(f"  skip  {folder_name}/{rel} (not a font)")
            continue
        target = dest_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        log(f"  add   {folder_name}/{rel}")
        n += 1
    if n:
        log(f"  ok    {folder_name} ({n})")
    return n


def install_private() -> int:
    return install_dropin("private")


# --- Fonts you add later ----------------------------------------------------
# Drop .ttf, .otf, or .ttc files into the additions directory next to this
# script. The next run copies them as they are. uninstall.sh does not delete
# that directory. private/ is the same mechanism and still works.


def install_additions() -> int:
    return install_dropin("additions")


def install_corefonts(have_arial: bool, accept: bool) -> None:
    if have_arial:
        log("  skip  classic core-font download (Arial is already included from ms-fonts/)")
        return
    if not accept:
        log("  skip  classic Microsoft core fonts")
        log("        Arial, Times New Roman, Verdana, Georgia, Courier New, Trebuchet MS,")
        log("        Comic Sans MS, Impact, Andale Mono, and Webdings were left out.")
        log("        License: https://sourceforge.net/projects/corefonts/ (Microsoft EULA).")
        return
    log("  note  downloading classic Microsoft core fonts under the core fonts EULA")
    log("        https://sourceforge.net/projects/corefonts/")
    extractor = "cabextract" if shutil.which("cabextract") else ("7z" if shutil.which("7z") else None)
    if extractor is None:
        log("  skip  core fonts (install cabextract or 7z, then re-run)")
        return
    names = [
        "andale32.exe", "arial32.exe", "arialb32.exe", "comic32.exe", "courie32.exe",
        "georgi32.exe", "impact32.exe", "times32.exe", "trebuc32.exe", "verdan32.exe", "webdin32.exe",
    ]
    dest = STAGE / "microsoft"
    dest.mkdir(parents=True, exist_ok=True)
    got = 0
    for name in names:
        exe = DOWNLOADS / "corefonts" / name
        url = "https://downloads.sourceforge.net/project/corefonts/the%20fonts/final/" + name
        if not curl(url, exe):
            log(f"  miss  {name}")
            continue
        with tempfile.TemporaryDirectory(prefix="usfont-cab-") as tmp:
            if extractor == "cabextract":
                proc = run(["cabextract", "-q", "-L", "-d", tmp, str(exe)])
            else:
                proc = run(["7z", "x", f"-o{tmp}", str(exe)])
            if proc.returncode != 0:
                log(f"  miss  {name} (extract)")
                continue
            for path in Path(tmp).rglob("*"):
                if path.is_file() and path.suffix.lower() in {".ttf", ".otf"} and is_font(path):
                    shutil.copy2(path, dest / path.name.lower())
                    got += 1
    log(f"  ok    core fonts ({got})")


def families_in(directory: Path) -> set[str]:
    found: set[str] = set()
    if not directory.exists():
        return found
    for path in directory.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".ttf", ".otf", ".ttc"}:
            continue
        proc = run(["fc-query", "--format", "%{family}\n", str(path)])
        if proc.returncode != 0:
            continue
        for line in proc.stdout.splitlines():
            for part in line.split(","):
                name = part.strip()
                if name:
                    found.add(name)
    return found


def write_config(installed: set[str], texgyre: bool) -> None:
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("60-us-english-aliases.conf", "61-us-english-menu.conf"):
        shutil.copy2(ROOT / "fontconfig" / name, CONF_DIR / name)

    lines = [
        '<?xml version="1.0"?>',
        '<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">',
        "<fontconfig>",
        "  <!-- Familiar menu names for open fonts, written by install.py. -->",
    ]
    used_subs: set[str] = set()
    for familiar, substitute in MENU_NAMES:
        if familiar in installed or substitute not in installed:
            continue
        if substitute in used_subs and familiar in {"San Francisco", "Helvetica Neue", "Avenir Next", "Apple Garamond", "ITC Garamond", "Gill Sans MT"}:
            # Still add the extra name; used_subs only tracks the substitute once for logging.
            pass
        lines.append("  <match target=\"scan\">")
        lines.append("    <test name=\"family\" compare=\"eq\">")
        lines.append(f"      <string>{substitute}</string>")
        lines.append("    </test>")
        lines.append("    <edit name=\"family\" mode=\"prepend\" binding=\"strong\">")
        lines.append(f"      <string>{familiar}</string>")
        lines.append("    </edit>")
        lines.append("  </match>")
        used_subs.add(substitute)
        log(f"  name  {familiar}  ->  {substitute}")

    if texgyre:
        lines.append("  <!-- URW duplicates of TeX Gyre. The dingbat faces in that folder stay. -->")
        lines.append("  <selectfont><rejectfont>")
        for pattern in URW_GLOBS:
            lines.append(f"    <glob>{pattern}</glob>")
        lines.append("  </rejectfont></selectfont>")
    lines.append("</fontconfig>")
    (CONF_DIR / "62-us-english-names.conf").write_text("\n".join(lines) + "\n", encoding="utf-8")


def backup_old_user_fonts() -> Path | None:
    """Move only the old personal folders this project used to install.

    A directory added later, by the user or by another program, stays put.
    """
    root = HOME / ".local" / "share" / "fonts"
    present = [root / name for name in OLD_USER_DIRS if (root / name).exists()]
    if not present:
        return None
    backup = HOME / ".local" / "share" / "fonts-backup-20261005"
    n = 2
    while backup.exists():
        backup = HOME / ".local" / "share" / f"fonts-backup-20261005-{n}"
        n += 1
    backup.mkdir(parents=True)
    for path in present:
        shutil.move(str(path), str(backup / path.name))
    return backup


def publish() -> None:
    # Only the curated tree is replaced. Distro and application fonts stay.
    if DEST.name != "us-english" or DEST.parent.name != "fonts":
        raise SystemExit(f"refusing to replace {DEST}")
    DEST.parent.mkdir(parents=True, exist_ok=True)
    if DEST.exists():
        shutil.rmtree(DEST)
    shutil.copytree(STAGE, DEST)


def fc_match(pattern: str) -> str:
    proc = run(["fc-match", "-f", "%{family}", pattern])
    return proc.stdout.strip()


def first_family(pattern: str) -> str:
    got = fc_match(pattern)
    return got.split(",")[0].strip()


def match_file(pattern: str) -> str:
    proc = run(["fc-match", "-f", "%{file}", pattern])
    return proc.stdout.strip()


def charset_has(charset: str, codepoint: int) -> bool:
    for part in charset.split():
        if "-" in part:
            start, end = part.split("-", 1)
            try:
                if int(start, 16) <= codepoint <= int(end, 16):
                    return True
            except ValueError:
                continue
            continue
        try:
            if int(part, 16) == codepoint:
                return True
        except ValueError:
            continue
    return False


def file_charset(path: Path) -> str:
    if not path.is_file():
        return ""
    proc = run(["fc-query", "--format", "%{charset}", str(path)])
    if proc.returncode != 0:
        return ""
    return proc.stdout


def file_has_codepoint(path: Path, codepoint: int) -> bool:
    return charset_has(file_charset(path), codepoint)


def file_has_alphabet(path: Path) -> bool:
    charset = file_charset(path)
    return all(charset_has(charset, ord(ch)) for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")


PRESERVE_FILES = [
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/Vera.ttf",
    "/usr/share/fonts/gsfonts/D050000L.otf",
    "/usr/share/projectM/fonts/Vera.ttf",
    "/usr/share/calibre/fonts/calibreSymbols.otf",
    "/usr/lib/libreoffice/share/fonts/truetype/opens___.ttf",
    "/usr/share/wine/fonts/tahoma.ttf",
    "/usr/share/imlib2/data/fonts/cinema.ttf",
    "/usr/share/sddm/themes/maya/fonts/OpenSans_CondLight.ttf",
]


def preservation_stamp() -> dict[str, tuple[int, int] | int]:
    """Size and time of distro and application fonts this run must not touch."""
    stamp: dict[str, tuple[int, int] | int] = {}
    for text in PRESERVE_FILES:
        path = Path(text)
        if path.is_file():
            st = path.stat()
            stamp[text] = (st.st_size, st.st_mtime_ns)
    noto = Path("/usr/share/fonts/noto")
    if noto.is_dir():
        stamp["/usr/share/fonts/noto"] = sum(1 for path in noto.rglob("*") if path.is_file())
    return stamp


def verify(failures: list[str], preserved: dict[str, tuple[int, int] | int] | None = None) -> int:
    log("")
    log("Checking the font list")
    families = sorted({
        line.split(",")[0].strip()
        for line in run(["fc-list", ":", "family"]).stdout.splitlines()
        if line.strip()
    })
    log(f"  families in the menu: {len(families)}")
    banned = (
        "Noto Sans Adlam",
        "Noto Sans Arabic",
        "Noto Sans Hebrew",
        "Noto Sans Hebrew Thin",
        "Noto Sans Devanagari",
        "Noto Sans Bengali",
        "Noto Sans Tamil",
        "Noto Sans Khmer",
        "Noto Sans Thai",
        "Noto Sans Ethiopic",
        "Noto Serif Tibetan",
        "MesloLGL Nerd Font",
        "WenQuanYi Zen Hei",
        "FantasqueSansM Nerd Font",
        "League Spartan Thin",
        "Montserrat Thin",
        "Libre Franklin Thin",
        "Fira Code Light",
        "Source Code Pro ExtraLight",
        "Source Sans 3 ExtraLight",
        "Nunito Sans 12pt ExtraLight 12pt",
        "Merriweather Light 18pt",
        "IBM Plex Mono Medium",
        "Belanosima SemiBold",
        "Leelawadee UI",
        "Gillius ADF Cond",
        "Gillius ADF No2 Cond",
    )
    bad = [name for name in banned if name in families]
    if bad:
        log("  still listed: " + ", ".join(bad))
    wanted = {
        "Arial": ("Arial", "Liberation Sans"),
        "Times New Roman": ("Times New Roman", "Liberation Serif"),
        "Calibri": ("Calibri", "Carlito"),
        "Cambria": ("Cambria", "Caladea"),
        "Garamond": ("Garamond", "EB Garamond"),
        "Helvetica": ("Helvetica", "TeX Gyre Heros"),
        "Futura": ("Futura", "League Spartan"),
        "Avenir": ("Avenir", "Nunito Sans"),
        "Gill Sans": ("Gill Sans", "Gillius ADF No2"),
        "Ubuntu": ("Ubuntu",),
        "Fira Code": ("Fira Code",),
        "JetBrainsMono Nerd Font Mono": ("JetBrainsMono Nerd Font Mono",),
        "Noto Sans": ("Noto Sans",),
        "Noto Sans CJK SC": ("Noto Sans CJK SC",),
        "Noto Color Emoji": ("Noto Color Emoji",),
    }
    problems = 0
    for request, ok_names in wanted.items():
        got = first_family(request)
        mark = "ok" if got in ok_names else "??"
        if mark != "ok":
            problems += 1
        log(f"  {mark:4} {request} -> {got}")
    lib_path = DEST / "document" / "LiberationSans-Regular.ttf"
    if lib_path.is_file():
        log(f"  ok   Liberation Sans file: {lib_path}")
    else:
        problems += 1
        log("  ??   Liberation Sans was not copied into the user font set")
    alphabet_gaps = []
    for label, rel in (
        ("Caladea", "document/caladea-latin-400-normal.ttf"),
        ("Carlito", "document/carlito-latin-400-normal.ttf"),
        ("EB Garamond", "document/eb-garamond-latin-400-normal.ttf"),
        ("Libre Baskerville", "document/libre-baskerville-latin-400-normal.ttf"),
        ("Nunito Sans", "document/nunito-sans-latin-400-normal.ttf"),
        ("League Spartan", "document/league-spartan-latin-400-normal.ttf"),
        ("Agdasima", "document/agdasima-latin-400-normal.ttf"),
    ):
        path = DEST / rel
        if not path.is_file() or not file_has_alphabet(path):
            alphabet_gaps.append(label)
    if alphabet_gaps:
        problems += 1
        log("  ??   missing the English alphabet: " + ", ".join(alphabet_gaps))
    else:
        log("  ok   stand-in fonts include the English alphabet")
    sans = DEST / "document" / "noto-sans-latin-400-normal.ttf"
    serif = DEST / "document" / "noto-serif-latin-400-normal.ttf"
    for label, pack, codepoint in (
        ("Bengali", sans, 0x0985),
        ("Tamil", sans, 0x0B85),
        ("Khmer", sans, 0x1780),
        ("Arabic", sans, 0x0627),
        ("Hebrew", sans, 0x05D0),
        ("Devanagari", sans, 0x0905),
        ("Thai", sans, 0x0E01),
        ("Ethiopic", sans, 0x1200),
        ("Adlam", sans, 0x1E900),
        ("Tibetan", serif, 0x0F40),
        ("CJK", DEST / "fallback" / "NotoSansCJKsc-Regular.otf", 0x4E00),
    ):
        packed = file_has_codepoint(pack, codepoint)
        matched = Path(match_file(f":charset={codepoint:04x}"))
        draws = file_has_codepoint(matched, codepoint)
        mark = "ok" if packed and draws else "??"
        if mark != "ok":
            problems += 1
        log(f"  {mark:4} {label} pack={packed} draws={draws} ({matched.name})")
    if (DEST / "coding" / "inconsolata-latin-400-normal.ttf").is_file():
        for request in (
            "Inconsolata",
            "Victor Mono",
            "Intel One Mono",
            "Iosevka",
            "Geist Mono",
            "Commit Mono",
            "Fira Mono",
            "JuliaMono",
            "Monaspace Neon",
            "Monaspace Argon",
            "Monaspace Xenon",
            "Monaspace Radon",
            "Monaspace Krypton",
        ):
            got = first_family(request)
            mark = "ok" if got == request else "??"
            if mark != "ok":
                problems += 1
            log(f"  {mark:4} {request} -> {got}")
        if not file_has_alphabet(DEST / "coding" / "iosevka-latin-400-normal.ttf"):
            problems += 1
            log("  ??   Iosevka is missing the English alphabet")
    for label, charset in (("emoji", "1f600"), ("powerline", "e0b0")):
        got = first_family(f":charset={charset}")
        log(f"  draw  {label} -> {got}")
    if failures:
        log("  downloads that failed: " + ", ".join(failures))
        problems += 1
    # LibreOffice loads OpenSymbol from its own folder, which fc-list does not scan.
    # preservation_stamp checks that file is still on disk.
    for name in ("DejaVu Sans",):
        if name not in families:
            problems += 1
            log(f"  ??   {name} dropped out of the menu")
    if preserved:
        changed = []
        for key, before in preserved.items():
            if key == "/usr/share/fonts/noto":
                noto = Path(key)
                after = sum(1 for path in noto.rglob("*") if path.is_file()) if noto.is_dir() else 0
                if after != before:
                    changed.append(key)
                continue
            path = Path(key)
            if not path.is_file():
                changed.append(key)
                continue
            st = path.stat()
            if (st.st_size, st.st_mtime_ns) != before:
                changed.append(key)
        if changed:
            problems += 1
            log("  ??   distro or application fonts changed: " + ", ".join(changed))
        else:
            log("  ok   distro and application font files are unchanged")
    if bad or problems:
        return 1
    return 0


def bundled_ready() -> bool:
    needed = (
        BUNDLED / "document" / "LiberationSans-Regular.ttf",
        BUNDLED / "document" / "noto-sans-latin-400-normal.ttf",
        BUNDLED / "fallback" / "NotoSansCJKsc-Regular.otf",
    )
    return all(path.is_file() for path in needed)


def install_coding_families(failures: list[str]) -> None:
    """Download the opt-in coding faces into STAGE/coding."""
    downloads: dict[Path, str] = {}
    for fid, weights, styles, _family in CODING_FAMILIES:
        for weight in weights:
            for style in styles:
                for subset in ("latin", "latin-ext"):
                    queue_fontsource(downloads, fid, subset, weight, style)
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(curl, url, cache) for cache, url in downloads.items()]
        for fut in futures:
            fut.result()
    dest_dir = STAGE / "coding"
    dest_dir.mkdir(parents=True, exist_ok=True)
    for fid, weights, styles, _family in CODING_FAMILIES:
        count = 0
        for weight in weights:
            for style in styles:
                parts = []
                for subset in ("latin", "latin-ext"):
                    cache = DOWNLOADS / "fontsource" / f"{fid}-{subset}-{weight}-{style}.ttf"
                    if cache.is_file() and is_font(cache):
                        parts.append(cache)
                if not parts:
                    continue
                dest = dest_dir / f"{fid}-latin-{weight}-{style}.ttf"
                try:
                    merge_into(parts, dest)
                except Exception as exc:
                    log(f"  warn  merge failed for {fid} {weight} {style}: {exc}")
                    basic = [path for path in parts if "-latin-ext-" not in path.name]
                    shutil.copy2(basic[0] if basic else parts[0], dest)
                if is_font(dest) and has_english_letters(dest):
                    count += 1
                else:
                    dest.unlink(missing_ok=True)
                    log(f"  warn  {fid} {weight} {style} has no English alphabet")
        if count == 0:
            failures.append(fid)
            log(f"  miss  {fid}")
        else:
            log(f"  ok    {fid} ({count})")
    install_julia_mono(failures)
    rewrite_staged_fontsource_names()


def install_julia_mono(failures: list[str]) -> None:
    """JuliaMono publishes one zip. Medium's Windows name would otherwise be its own family."""
    archive = DOWNLOADS / "JuliaMono-ttf-v0.63.2.zip"
    if not curl(JULIA_MONO_URL, archive):
        failures.append("juliamono")
        log("  miss  juliamono")
        return
    dest_dir = STAGE / "coding"
    dest_dir.mkdir(parents=True, exist_ok=True)
    family = "JuliaMono"
    count = 0
    with zipfile.ZipFile(archive) as zf:
        members = {Path(name).name: name for name in zf.namelist()}
        for filename, style in JULIA_MONO_FILES.items():
            member = members.get(filename)
            if member is None:
                continue
            target = dest_dir / filename
            target.write_bytes(zf.read(member))
            if not is_font(target):
                target.unlink(missing_ok=True)
                continue
            mapping = {
                1: family,
                2: style,
                4: f"{family} {style}",
                6: ps_name(family, style),
                16: family,
                17: style,
                21: family,
                22: style,
            }
            try:
                rewrite_ttf_names(target, mapping)
            except Exception as exc:
                log(f"  warn  name fix failed for {filename}: {exc}")
            count += 1
    if count == 0:
        failures.append("juliamono")
        log("  miss  juliamono")
    else:
        log(f"  ok    juliamono ({count})")


def coding_ready() -> bool:
    needed = (
        BUNDLED_CODING / "inconsolata-latin-400-normal.ttf",
        BUNDLED_CODING / "iosevka-latin-400-normal.ttf",
        BUNDLED_CODING / "JuliaMono-Regular.ttf",
    )
    return all(path.is_file() for path in needed)


def install_coding_bundled() -> int:
    dest_dir = STAGE / "coding"
    dest_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for path in BUNDLED_CODING.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".ttf", ".otf", ".ttc"} or not is_font(path):
            continue
        shutil.copy2(path, dest_dir / path.name)
        count += 1
    log(f"  ok    coding fonts from this folder ({count})")
    return count


def save_coding_bundle() -> None:
    src = STAGE / "coding"
    if not src.is_dir():
        return
    if BUNDLED_CODING.exists():
        shutil.rmtree(BUNDLED_CODING)
    shutil.copytree(src, BUNDLED_CODING)
    log(f"Updated the coding fonts shipped in {BUNDLED_CODING}")


def install_bundled() -> int:
    """Copy the faces stored next to this script. No download."""
    count = 0
    for path in BUNDLED.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".ttf", ".otf", ".ttc"} or not is_font(path):
            continue
        dest = STAGE / path.relative_to(BUNDLED)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        count += 1
    log(f"  ok    fonts from this folder ({count})")
    return count


def save_bundle() -> None:
    """Keep fonts/ in step with a fresh download, for the next USB copy."""
    if BUNDLED.exists():
        shutil.rmtree(BUNDLED)

    def ignore(directory: str, names: list[str]) -> set[str]:
        if Path(directory) == STAGE and "coding" in names:
            return {"coding"}
        return set()

    shutil.copytree(STAGE, BUNDLED, ignore=ignore)
    log(f"Updated the fonts shipped in {BUNDLED}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the US English font set into ~/.local/share/fonts")
    parser.add_argument(
        "--accept-mscorefonts-eula",
        action="store_true",
        help="Accepted by default. Kept so an older command still works.",
    )
    parser.add_argument(
        "--skip-mscorefonts",
        action="store_true",
        help="Do not download the classic Microsoft core fonts.",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download and rebuild the fonts, then refresh the fonts folder in this package.",
    )
    parser.add_argument(
        "--coding",
        action="store_true",
        help="Also install the extra coding fonts in fonts-coding/.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Accept the core fonts EULA and install the extra coding fonts.",
    )
    args = parser.parse_args()
    if args.all:
        args.coding = True
        args.accept_mscorefonts_eula = True
    if args.all and args.skip_mscorefonts:
        log("  note  --skip-mscorefonts overrides --all for the classic core fonts")
    use_bundle = bundled_ready() and not args.download
    need_download = (not use_bundle) or (args.coding and not coding_ready())
    require_tools(download=need_download)
    preserved = preservation_stamp()
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    DOWNLOADS.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    if use_bundle:
        log("Installing the fonts shipped in this folder")
        install_bundled()
        have_cascadia = any((STAGE / "mono").glob("cascadia-code*"))
        install_local_microsoft(skip_cascadia=have_cascadia)
        install_private()
        install_additions()
        if args.coding:
            if coding_ready():
                install_coding_bundled()
            else:
                log("Downloading extra coding fonts")
                install_coding_families(failures)
                save_coding_bundle()
        flags = {"texgyre": any(path.name.lower().startswith("texgyre") for path in STAGE.rglob("*") if path.is_file())}
    else:
        if not args.download and not bundled_ready():
            log("The fonts folder in this package is missing, so the faces will be downloaded.")
        log("Downloading open fonts")
        install_fontsource(failures)
        if args.coding:
            log("Downloading extra coding fonts")
            install_coding_families(failures)
        rewrite_staged_fontsource_names()
        flags = install_archives(failures)
        rewrite_ubuntu_medium()
        rewrite_jetbrains_names()
        install_local_microsoft(skip_cascadia="cascadia-code" not in failures)
        install_private()
        install_additions()
    ms_dir = STAGE / "microsoft"
    have_arial = ms_dir.is_dir() and any(p.name.lower() == "arial.ttf" for p in ms_dir.iterdir())
    if use_bundle and have_arial:
        pass
    else:
        install_corefonts(have_arial, not args.skip_mscorefonts)
    if not use_bundle:
        save_bundle()
        if args.coding:
            save_coding_bundle()

    log("Writing fontconfig")
    installed = families_in(STAGE)
    write_config(installed, flags["texgyre"])

    backup = backup_old_user_fonts()
    publish()
    log("Refreshing the font cache")
    proc = run(["fc-cache", "-f"])
    if proc.returncode != 0:
        log(proc.stderr.strip())
        return 1
    code = verify(failures, preserved)
    log("")
    log(f"Installed into {DEST}")
    log("Distro packages and application font folders were left in place.")
    log("Only the us-english font folder and its three fontconfig files were replaced.")
    if backup:
        log(f"Previous ~/.local/share/fonts folders were moved to {backup}")
    if code == 0 and not failures:
        log("Font check passed.")
    elif code == 0:
        log("Core names resolve. Some optional downloads failed; see the list above.")
    else:
        log("Font check found gaps. See the list above.")
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)

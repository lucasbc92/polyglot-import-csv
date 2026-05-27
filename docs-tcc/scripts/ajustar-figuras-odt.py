"""
Scale embedded images in an ODT so they fit ABNT A4 text area.

Pandoc often writes draw:frame sizes in points matching pixel dimensions (e.g. 2474pt
wide), which overflows the page. This script caps width/height and preserves aspect ratio.
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

# A4 with margins 3cm left + 2cm right => ~16cm text width; cap height for one page.
MAX_WIDTH_CM = 16.0
MAX_HEIGHT_CM = 20.0
CM_PER_PT = 2.54 / 72.0


def _parse_length(value: str) -> tuple[float, str]:
    value = value.strip()
    if value.endswith("cm"):
        return float(value[:-2]), "cm"
    if value.endswith("pt"):
        return float(value[:-2]) * CM_PER_PT, "cm"
    if value.endswith("in"):
        return float(value[:-2]) * 2.54, "cm"
    if value.endswith("mm"):
        return float(value[:-2]) / 10.0, "cm"
    # bare number treated as pt (Pandoc default for ODT)
    return float(value) * CM_PER_PT, "cm"


def _format_cm(cm: float) -> str:
    return f"{cm:.2f}cm"


def _scale_frame(match: re.Match[str]) -> str:
    prefix, width_raw, height_raw, suffix = match.groups()
    w_cm, _ = _parse_length(width_raw)
    h_cm, _ = _parse_length(height_raw)
    if w_cm <= 0 or h_cm <= 0:
        return match.group(0)
    scale = 1.0
    if w_cm > MAX_WIDTH_CM:
        scale = min(scale, MAX_WIDTH_CM / w_cm)
    if h_cm > MAX_HEIGHT_CM:
        scale = min(scale, MAX_HEIGHT_CM / h_cm)
    if scale >= 1.0:
        return match.group(0)
    new_w = w_cm * scale
    new_h = h_cm * scale
    return f'{prefix}svg:width="{_format_cm(new_w)}" svg:height="{_format_cm(new_h)}"{suffix}'


_FRAME_RE = re.compile(
    r'(<draw:frame\b[^>]*?)svg:width="([^"]+)"\s+svg:height="([^"]+)"([^>]*>)'
)


def patch_content_xml(xml: str) -> tuple[str, int]:
    count = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal count
        out = _scale_frame(m)
        if out != m.group(0):
            count += 1
        return out

    return _FRAME_RE.sub(repl, xml), count


def patch_odt(path: Path, *, in_place: bool = True) -> int:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)

    with zipfile.ZipFile(path, "r") as zin:
        names = zin.namelist()
        files = {n: zin.read(n) for n in names}

    xml = files["content.xml"].decode("utf-8")
    patched, n = patch_content_xml(xml)
    if n == 0:
        return 0
    files["content.xml"] = patched.encode("utf-8")

    out_path = path if in_place else path.with_stem(path.stem + "-scaled")
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name in names:
            zout.writestr(name, files[name])
    tmp.replace(out_path)
    return n


def main() -> int:
    parser = argparse.ArgumentParser(description="Scale ODT figures to fit A4 text area.")
    parser.add_argument(
        "odt",
        nargs="*",
        type=Path,
        help="ODT file(s) to patch (default: report ODT in docs-tcc/)",
    )
    args = parser.parse_args()
    docs = Path(__file__).resolve().parents[1]
    paths = args.odt or [docs / "LucasBuenoCesario-PolyglotImportCSV-Report-TCC1.odt"]
    total = 0
    for p in paths:
        n = patch_odt(p)
        print(f"{p.name}: scaled {n} figure(s)")
        total += n
    return 0 if total >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())

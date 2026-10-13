"""Cut the fonts the card embeds down to the glyphs it uses.

Run it once, and again if the card starts using new characters:

    pip install fonttools brotli
    python scripts/subset_fonts.py SRC_DIR

SRC_DIR holds the source fonts, all under the SIL Open Font License:
Outfit[wght].ttf, Inter[opsz,wght].ttf and Inter-Italic[opsz,wght].ttf from
github.com/google/fonts, and JetBrainsMono-Regular.ttf from
github.com/JetBrains/JetBrainsMono.

It writes one small woff2 per weight to assets/fonts/, plus metrics.json with
each glyph's advance width, which build_card.py uses to measure and wrap text
without any third-party packages.
"""

import argparse
import json
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "fonts"

UNICODES = [
    *range(0x20, 0x7F),
    0xA0, 0xB0, 0xB7, 0xD7, 0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D,
    0x2022, 0x2026, 0x2116, 0x2192, 0x2197, 0x25CF,
]

# name: (source file, variable axes to pin, OpenType features to keep)
FONTS = {
    "outfit-700": ("Outfit[wght].ttf", {"wght": 700}, ["kern"]),
    "inter-400": ("Inter[opsz,wght].ttf", {"wght": 400, "opsz": 14}, []),
    "inter-600": ("Inter[opsz,wght].ttf", {"wght": 600, "opsz": 14}, []),
    "inter-300i": ("Inter-Italic[opsz,wght].ttf", {"wght": 300, "opsz": 18}, []),
    "mono-400": ("JetBrainsMono-Regular.ttf", {}, []),
}


def build(src_dir):
    OUT.mkdir(parents=True, exist_ok=True)
    metrics = {}
    for name, (source, axes, features) in FONTS.items():
        font = TTFont(src_dir / source)
        if axes:
            font = instancer.instantiateVariableFont(font, axes)
        options = subset.Options()
        options.flavor = "woff2"
        options.layout_features = features
        options.hinting = False
        options.desubroutinize = True
        options.name_IDs = []
        subsetter = subset.Subsetter(options)
        subsetter.populate(unicodes=UNICODES)
        subsetter.subset(font)
        font.flavor = "woff2"
        font.save(OUT / f"{name}.woff2")

        cmap, hmtx = font.getBestCmap(), font["hmtx"].metrics
        metrics[name] = {
            "upm": font["head"].unitsPerEm,
            "adv": {chr(code): hmtx[glyph][0] for code, glyph in sorted(cmap.items())},
        }
        print(f"{name}: {(OUT / f'{name}.woff2').stat().st_size} bytes")
    (OUT / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("src_dir", type=Path)
    build(parser.parse_args().src_dir)

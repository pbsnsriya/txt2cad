"""WCAG 2 contrast check for the design tokens.

    python contrast.py tokens.json
    python contrast.py tokens.dark.json

Checks every [foreground, background, kind] triple in the file's "pairs" list. Kinds: normal text needs 4.5:1, "ui" parts (borders of
inputs, focus rings) need 3:1. Exits 1 if any pair fails, so it can gate CI.
"""
import json
import sys

NEEDS = {"normal": 4.5, "large": 3.0, "ui": 3.0}


def luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lin = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def ratio(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def main(path: str) -> int:
    tokens = json.load(open(path, encoding="utf-8"))
    colours = tokens["color"]
    failures = 0
    for fg, bg, *kind in tokens["pairs"]:
        need = NEEDS[kind[0] if kind else "normal"]
        got = ratio(colours[fg], colours[bg])
        ok = got >= need
        failures += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {got:5.2f}:1  need {need}  {fg} on {bg}")
    print(f"\n  {len(tokens['pairs'])} pairs, {failures} failing")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))

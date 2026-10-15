"""Render generated SVG to PNG/PDF; requires the optional preview extra and Cairo."""
import argparse
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
if __package__:
    from .validation import parse_svg
else:
    from validation import parse_svg


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("svg", type=Path)
    parser.add_argument("--png", type=Path)
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--width", type=int, default=1500)
    args = parser.parse_args()
    if not args.png and not args.pdf:
        parser.error("Provide --png and/or --pdf")
    if args.width < 1:
        parser.error("--width must be positive")
    try:
        import cairosvg
        content=ET.tostring(parse_svg(args.svg.read_text(encoding="utf-8")))
        for target in (args.png, args.pdf):
            if target:
                target.parent.mkdir(parents=True, exist_ok=True)
        if args.png:
            cairosvg.svg2png(bytestring=content, write_to=str(args.png), output_width=args.width)
        if args.pdf:
            cairosvg.svg2pdf(bytestring=content, write_to=str(args.pdf))
    except (ImportError, OSError, ValueError) as error:
        print(f"ERROR: SVG preview requires the preview extra and the platform Cairo runtime. {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())

#!/usr/bin/env python3
"""svg_to_pdf.py -- put the SVG sheet onto a real drafting sheet size.

    python3 svg_to_pdf.py sheet.svg sheet.pdf [--size A1]

Tries cairosvg first, then rsvg-convert, then inkscape. If none is present it
says so and exits non-zero rather than silently producing nothing -- a missing
PDF is easy to miss otherwise.

Sheet sizes are in PostScript points (1/72 in), landscape.
"""

import argparse
import os
import shutil
import subprocess
import sys

SIZES = {
    "A4": (842, 595),
    "A3": (1191, 842),
    "A2": (1684, 1191),
    "A1": (2384, 1684),
    "A0": (3370, 2384),
    "ANSI_B": (1224, 792),
    "ANSI_C": (1584, 1224),
    "ANSI_D": (2448, 1584),
    "ANSI_E": (3168, 2448),
}


# cairosvg's output_width/output_height are CSS pixels at 96 dpi, but a PDF page
# is measured in PostScript points at 72 dpi. Passing points straight in yields a
# page 0.75x the intended size -- an "A1" sheet that is really about A2. Convert.
PX_PER_PT = 96.0 / 72.0


def convert(svg_path, pdf_path, size="A1"):
    w, h = SIZES.get(size.upper(), SIZES["A1"])
    try:
        import cairosvg
        cairosvg.svg2pdf(url=svg_path, write_to=pdf_path,
                         output_width=w * PX_PER_PT, output_height=h * PX_PER_PT)
        return pdf_path
    except ImportError:
        pass

    if shutil.which("rsvg-convert"):
        # librsvg takes an explicit page size in real units, which sidesteps the
        # pixel/point question entirely.
        subprocess.check_call(["rsvg-convert", "-f", "pdf",
                               "--page-width=%dpt" % w, "--page-height=%dpt" % h,
                               "--keep-aspect-ratio",
                               "-o", pdf_path, svg_path])
        return pdf_path
    if shutil.which("inkscape"):
        subprocess.check_call(["inkscape", svg_path, "--export-type=pdf",
                               "--export-filename=" + pdf_path,
                               "--export-width=%d" % int(w * PX_PER_PT)])
        return pdf_path

    sys.stderr.write(
        "No SVG->PDF backend found. Install one of:\n"
        "  pip install cairosvg --break-system-packages\n"
        "  apt-get install -y librsvg2-bin\n")
    raise SystemExit(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("svg")
    ap.add_argument("pdf", nargs="?")
    ap.add_argument("--size", default="A1",
                    help="one of: " + ", ".join(sorted(SIZES)))
    a = ap.parse_args()
    out = a.pdf or os.path.splitext(a.svg)[0] + ".pdf"
    convert(a.svg, out, a.size)
    print("wrote %s (%s landscape)" % (out, a.size.upper()))


if __name__ == "__main__":
    main()

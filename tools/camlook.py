#!/usr/bin/env python3
"""Blick auf das Board per USB-Webcam: aufnehmen, aufhellen, auf das Panel zuschneiden.

Der Ausschnitt (Standard: Bildmitte) laesst sich per Argument in Prozent angeben,
z.B. `camlook.py 20 30 80 95` fuer links/oben/rechts/unten in Prozent.

Ausgabe: /root/.hermes/cache/scratch/camlook.jpg (zugeschnitten, aufgehellt)
         /root/.hermes/cache/scratch/camlook_full.jpg (ganzes Bild, aufgehellt)
"""

import glob
import os
import statistics
import subprocess
import sys

from PIL import Image, ImageEnhance, ImageOps

DEV = os.environ.get("CAM", "/dev/video0")
OUT = "/root/.hermes/cache/scratch"
TMP = os.path.join(OUT, "camlook_seq")


def capture(frames=25, size="1920x1080"):
    for old in glob.glob(TMP + "*.jpg"):
        os.remove(old)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-f", "v4l2", "-input_format", "mjpeg", "-video_size", size,
           "-i", DEV, "-frames:v", str(frames), "-q:v", "2",
           TMP + "%03d.jpg"]
    subprocess.run(cmd, check=True)
    files = sorted(glob.glob(TMP + "*.jpg"))
    if not files:
        raise SystemExit("keine Aufnahme entstanden")
    return files[-1]


def main():
    args = [float(a) / 100.0 for a in sys.argv[1:5]] or [0.25, 0.30, 0.80, 0.95]
    left, top, right, bottom = args
    path = capture()
    img = Image.open(path).convert("RGB")
    print("Aufnahme:", path, img.size)

    small = img.resize((160, 90))
    lum = [0.299 * r + 0.587 * g + 0.114 * b for r, g, b in list(small.getdata())]
    print("Helligkeit: min=%.0f mittel=%.0f max=%.0f"
          % (min(lum), statistics.mean(lum), max(lum)))

    w, h = img.size
    crop = img.crop((int(w * left), int(h * top), int(w * right), int(h * bottom)))
    crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
    ImageOps.autocontrast(crop, cutoff=0).save(os.path.join(OUT, "camlook.jpg"), quality=92)
    ImageEnhance.Brightness(ImageOps.autocontrast(img, cutoff=1)).enhance(1.6).save(
        os.path.join(OUT, "camlook_full.jpg"), quality=92)
    print("geschrieben:", os.path.join(OUT, "camlook.jpg"))
    print("geschrieben:", os.path.join(OUT, "camlook_full.jpg"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

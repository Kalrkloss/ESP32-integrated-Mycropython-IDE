#!/usr/bin/env python3
"""Read the panel from a webcam frame as text.

The agent cannot look at images, so the frame is reduced to a brightness map (and a
colour map) that can be read as characters: that shows whether the glass is black,
uniform, or has visible content.
"""
import glob
import sys

from PIL import Image

path = sys.argv[1] if len(sys.argv) > 1 else sorted(glob.glob("/tmp/cam*.jpg"))[-1]
image = Image.open(path).convert("RGB")
small = image.resize((56, 30))
pixels = list(small.getdata())

lut = " .:-=+*#%@"
lines_bright = []
lines_colour = []
for row in range(small.height):
    bright = ""
    colour = ""
    for column in range(small.width):
        r, g, b = pixels[row * small.width + column]
        luma = (r * 30 + g * 59 + b * 11) // 100
        bright += lut[min(9, luma * 10 // 256)]
        if max(r, g, b) - min(r, g, b) < 18:
            colour += "." if luma < 40 else "o"          # grey/black or white
        elif r >= g and r >= b:
            colour += "R"
        elif g >= r and g >= b:
            colour += "G"
        else:
            colour += "B"
    lines_bright.append(bright)
    lines_colour.append(colour)

print("frame:", path, image.size)
print()
print("brightness map ( .:-=+*#%@ ):")
for line in lines_bright:
    print("  " + line)
print()
print("colour map (R/G/B = hue, o = light grey, . = dark):")
for line in lines_colour:
    print("  " + line)
print()
flat = image.convert("L")
histogram = flat.histogram()
total = sum(histogram)
print("luma: mean %.1f, dark(<32) %.1f%%, bright(>192) %.1f%%"
      % (sum(i * n for i, n in enumerate(histogram)) / total,
         100.0 * sum(histogram[:32]) / total,
         100.0 * sum(histogram[192:]) / total))

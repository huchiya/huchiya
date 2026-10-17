"""Generate a simple FileMind .ico (folder + sparkle motif) using Pillow."""
from PIL import Image, ImageDraw
import os

SIZE = 256
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# Rounded background
radius = 56
d.rounded_rectangle([8, 8, SIZE - 8, SIZE - 8], radius=radius, fill=(79, 70, 229, 255))

# Folder body
def _rounded_rect(x0, y0, x1, y1, r):
    d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=(255, 255, 255, 255))

# Back tab
d.polygon([(70, 78), (70, 120), (110, 120), (120, 92), (200, 92), (200, 78)], fill=(226, 226, 250, 255))
# Front folder
_rounded_rect(60, 92, 205, 170, 26)

# Sparkle (four-point star) inside
cx, cy = 132, 130
r_out, r_in = 46, 12
star = [(cx, cy - r_out), (cx + r_in, cy - r_in), (cx + r_out, cy),
        (cx + r_in, cy + r_in), (cx, cy + r_out), (cx - r_in, cy + r_in),
        (cx - r_out, cy), (cx - r_in, cy - r_in)]
d.polygon(star, fill=(79, 70, 229, 255))

# Save ICO with multiple sizes
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "filemind.ico")
img.save(out, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("saved:", out)

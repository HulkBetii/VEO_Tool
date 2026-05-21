"""
Generate app_icon.png + app_icon.ico from Stitch V3 - Clean Circuit design.

Render pipeline: 4x supersample -> LANCZOS downsample for crisp edges.
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

FINAL = 512
SUPER = 4
S = FINAL * SUPER
REF = 340
MARGIN_PX = 40
OUTER_SIZE = 340
SCALE = S / REF


def px(v):
    """Scale a Stitch-source pixel value to super-canvas."""
    return int(round(v * SCALE))


BG = (8, 12, 37)
WHITE = (255, 255, 255)
CYAN_400 = (34, 211, 238)
CYAN_GLOW = (0, 227, 253)
PURPLE_500 = (168, 85, 247)
PURPLE_GLOW = (172, 138, 255)

img = Image.new("RGBA", (S, S), BG + (255,))

cx0 = px(MARGIN_PX)
cy0 = px(MARGIN_PX)
cx1 = S - px(MARGIN_PX)
cy1 = S - px(MARGIN_PX)
outer_radius = px(40)
border_w = px(2)

grad = np.zeros((S, S, 4), dtype=np.uint8)
ys, xs = np.mgrid[0:S, 0:S]
t = np.clip((xs + (S - ys)) / (2 * S), 0, 1)
for i, (a, b) in enumerate(zip(PURPLE_500, CYAN_400)):
    grad[..., i] = (a * (1 - t) + b * t).astype(np.uint8)
grad[..., 3] = 255
grad_img = Image.fromarray(grad, "RGBA")

ring_mask = Image.new("L", (S, S), 0)
rm = ImageDraw.Draw(ring_mask)
rm.rounded_rectangle([cx0, cy0, cx1, cy1], radius=outer_radius, fill=255)
inner_radius = px(38.4)
inner_inset = border_w
rm.rounded_rectangle(
    [cx0 + inner_inset, cy0 + inner_inset, cx1 - inner_inset, cy1 - inner_inset],
    radius=inner_radius,
    fill=0,
)
grad_ring = Image.new("RGBA", (S, S), (0, 0, 0, 0))
grad_ring.paste(grad_img, (0, 0), ring_mask)
img = Image.alpha_composite(img, grad_ring)

inner_rect = [cx0 + border_w, cy0 + border_w, cx1 - border_w, cy1 - border_w]
ir = ImageDraw.Draw(img)
ir.rounded_rectangle(inner_rect, radius=inner_radius, fill=BG + (255,))

bracket_origin_x = cx0
bracket_origin_y = cy0
bracket_area = cx1 - cx0
br_size = px(96)
br_margin = px(24)
br_stroke = px(4)
br_radius = px(32)
brackets_layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
bdraw = ImageDraw.Draw(brackets_layer)
CYAN_RGBA = CYAN_400 + (255,)


def draw_bracket(corner):
    """L-shaped corner bracket with rounded outside corner."""
    if corner == "tl":
        x0 = bracket_origin_x + br_margin
        y0 = bracket_origin_y + br_margin
    else:
        x0 = bracket_origin_x + bracket_area - br_margin - br_size
        y0 = bracket_origin_y + bracket_area - br_margin - br_size

    x1 = x0 + br_size - 1
    y1 = y0 + br_size - 1
    if corner == "tl":
        bdraw.rectangle([(x0 + br_radius, y0), (x1, y0 + br_stroke)], fill=CYAN_RGBA)
        bdraw.rectangle([(x0, y0 + br_radius), (x0 + br_stroke, y1)], fill=CYAN_RGBA)
        bdraw.arc([(x0, y0), (x0 + 2 * br_radius, y0 + 2 * br_radius)], start=180, end=270, fill=CYAN_RGBA, width=br_stroke)
        return None

    bdraw.rectangle([(x0, y1 - br_stroke), (x1 - br_radius, y1)], fill=CYAN_RGBA)
    bdraw.rectangle([(x1 - br_stroke, y0), (x1, y1 - br_radius)], fill=CYAN_RGBA)
    bdraw.arc([(x1 - 2 * br_radius, y1 - 2 * br_radius), (x1, y1)], start=0, end=90, fill=CYAN_RGBA, width=br_stroke)
    return None


draw_bracket("tl")
draw_bracket("br")

br_glow_alpha = brackets_layer.split()[-1].filter(ImageFilter.GaussianBlur(px(20)))
br_glow = Image.new("RGBA", (S, S), CYAN_GLOW + (0,))
br_glow.putalpha(br_glow_alpha.point(lambda v: min(255, int(v * 0.7))))
img = Image.alpha_composite(img, br_glow)
img = Image.alpha_composite(img, brackets_layer)

btn_size = px(192)
btn_radius = px(24)
btn = Image.new("RGBA", (btn_size, btn_size), (0, 0, 0, 0))
bd = ImageDraw.Draw(btn)
bd.rounded_rectangle([(0, 0), (btn_size - 1, btn_size - 1)], radius=btn_radius, fill=WHITE + (255,))

icon_size = px(128)
tr_w = int(icon_size * 0.7)
tr_h = int(icon_size * 0.78)
tr_cx = btn_size // 2 + px(4)
tr_cy = btn_size // 2
triangle = [
    (tr_cx - tr_w // 2, tr_cy - tr_h // 2),
    (tr_cx - tr_w // 2, tr_cy + tr_h // 2),
    (tr_cx + tr_w // 2, tr_cy),
]
bd.polygon(triangle, fill=BG + (255,))

btn_rot = btn.rotate(-12, resample=Image.BICUBIC, expand=True)
btn_alpha = btn_rot.split()[-1]
white_glow_alpha = btn_alpha.filter(ImageFilter.GaussianBlur(px(22)))
white_glow = Image.new("RGBA", btn_rot.size, WHITE + (0,))
white_glow.putalpha(white_glow_alpha.point(lambda v: int(v * 0.45)))
cyan_glow_alpha = btn_alpha.filter(ImageFilter.GaussianBlur(px(32)))
cyan_glow = Image.new("RGBA", btn_rot.size, CYAN_GLOW + (0,))
cyan_glow.putalpha(cyan_glow_alpha.point(lambda v: int(v * 0.35)))

bx = (S - btn_rot.width) // 2
by = (S - btn_rot.height) // 2
glow_canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))
glow_canvas.paste(cyan_glow, (bx, by), cyan_glow)
glow_canvas.paste(white_glow, (bx, by), white_glow)
img = Image.alpha_composite(img, glow_canvas)
img.paste(btn_rot, (bx, by), btn_rot)

final = img.resize((FINAL, FINAL), resample=Image.LANCZOS)
root = Path(__file__).resolve().parent.parent
out_png = root / "config" / "app_icon.png"
out_ico = root / "config" / "app_icon.ico"
out_png.parent.mkdir(parents=True, exist_ok=True)
final.save(out_png, "PNG")
print(f"Saved: {out_png}")
ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
final.save(out_ico, format="ICO", sizes=ico_sizes)
print(f"Saved: {out_ico} (sizes: {ico_sizes})")

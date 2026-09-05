"""Generate PNG favicon and touch icon for LEHAR brand.

Run once after editing assets/logo.svg:
    py generate_logo.py
"""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"

def draw_lehar_icon(size):
    scale = 4
    img_size = size * scale
    img = Image.new("RGBA", (img_size, img_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Background circle
    draw.ellipse([4 * scale, 4 * scale, (size - 4) * scale, (size - 4) * scale], 
                 fill=(17, 20, 24, 255), outline=(38, 42, 48, 255), width=int(2.5 * scale))
    
    def to_pt(x, y):
        return (x / 200.0 * img_size, y / 200.0 * img_size)
        
    def cubic_bezier(p0, p1, p2, p3, steps=100):
        pts = []
        for i in range(steps + 1):
            t = i / steps
            x = (1-t)**3 * p0[0] + 3*(1-t)**2 * t * p1[0] + 3*(1-t) * t**2 * p2[0] + t**3 * p3[0]
            y = (1-t)**3 * p0[1] + 3*(1-t)**2 * t * p1[1] + 3*(1-t) * t**2 * p2[1] + t**3 * p3[1]
            pts.append((x, y))
        return pts

    c1 = cubic_bezier(to_pt(124, 76), to_pt(118, 52), to_pt(94, 48), to_pt(80, 66))
    c2 = cubic_bezier(to_pt(80, 66), to_pt(66, 84), to_pt(72, 116), to_pt(56, 140))
    c3 = cubic_bezier(to_pt(56, 140), to_pt(47, 154), to_pt(32, 147), to_pt(36, 132))
    c4 = cubic_bezier(to_pt(36, 132), to_pt(40, 118), to_pt(58, 128), to_pt(86, 136))
    c5 = cubic_bezier(to_pt(86, 136), to_pt(114, 144), to_pt(144, 140), to_pt(156, 122))

    full_curve = c1 + c2[1:] + c3[1:] + c4[1:] + c5[1:]
    line_w = max(2, int(13 / 200.0 * img_size))
    
    for i in range(len(full_curve) - 1):
        draw.line([full_curve[i], full_curve[i+1]], fill=(217, 4, 41, 255), width=line_w)

    for pt in full_curve:
        r = line_w / 2
        draw.ellipse([pt[0] - r, pt[1] - r, pt[0] + r, pt[1] + r], fill=(235, 30, 65, 255))

    return img.resize((size, size), Image.Resampling.LANCZOS)

def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    fav = draw_lehar_icon(32)
    fav.save(ASSETS / "favicon-32.png")
    touch = draw_lehar_icon(180)
    touch.save(ASSETS / "apple-touch-icon.png")
    print("Generated LEHAR brand assets successfully:")
    for p in sorted(ASSETS.glob("*.png")):
        print(f"  {p.name} ({p.stat().st_size} bytes)")

if __name__ == "__main__":
    main()

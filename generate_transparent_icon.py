"""
Generates a minimalist high-resolution application icon with a 100% transparent background.
Exports to ICO (multi-resolution 16 to 256) and PNG (256x256 and 512x512).
"""

from pathlib import Path
from PIL import Image, ImageDraw


def generate_transparent_icon(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    # Render at 1024x1024 for supersampled anti-aliasing, then downsample with Lanczos
    render_size = 1024
    img_large = Image.new("RGBA", (render_size, render_size), (0, 0, 0, 0))

    # 7 bars forming an iconic audio wave with modern gradient
    bars_data = [
        (0.20, 0.32, 0.055, (0, 242, 254), (0, 160, 255)),   # Cyan to Azure
        (0.30, 0.52, 0.055, (0, 220, 255), (30, 130, 255)),  # Electric blue
        (0.40, 0.74, 0.055, (0, 195, 255), (75, 95, 255)),   # Azure to Blue
        (0.50, 0.90, 0.060, (0, 230, 255), (130, 30, 255)),  # Center pulse (Cyan to Violet)
        (0.60, 0.74, 0.055, (75, 95, 255), (155, 45, 255)),  # Violet
        (0.70, 0.52, 0.055, (120, 75, 255), (185, 35, 240)), # Purple
        (0.80, 0.32, 0.055, (160, 50, 240), (215, 25, 220)), # Magenta
    ]

    center_y = render_size / 2.0

    for x_rat, h_rat, w_rat, c_start, c_end in bars_data:
        cx = x_rat * render_size
        bar_w = int(w_rat * render_size)
        bar_h = int(h_rat * render_size)
        radius = bar_w // 2

        top = int(center_y - (bar_h / 2.0))
        left = int(cx - radius)

        # Draw smooth rounded pill on high-res canvas
        bar_img = Image.new("RGBA", (bar_w, bar_h), (0, 0, 0, 0))
        b_draw = ImageDraw.Draw(bar_img)
        b_draw.rounded_rectangle([0, 0, bar_w - 1, bar_h - 1], radius=radius, fill=(255, 255, 255, 255))

        # Color with vertical gradient and subtle top lighting
        for y_idx in range(bar_h):
            t = y_idx / max(1.0, float(bar_h - 1))
            # Smooth ease
            t_smooth = t * t * (3.0 - 2.0 * t)
            r = int(c_start[0] * (1.0 - t_smooth) + c_end[0] * t_smooth)
            g = int(c_start[1] * (1.0 - t_smooth) + c_end[1] * t_smooth)
            b = int(c_start[2] * (1.0 - t_smooth) + c_end[2] * t_smooth)

            # Add subtle top highlight (glassy feel)
            if y_idx < radius * 2:
                hl = (1.0 - (y_idx / (radius * 2))) * 0.22
                r = min(255, int(r + (255 - r) * hl))
                g = min(255, int(g + (255 - g) * hl))
                b = min(255, int(b + (255 - b) * hl))

            for x_idx in range(bar_w):
                p = bar_img.getpixel((x_idx, y_idx))
                if p[3] > 0:
                    bar_img.putpixel((x_idx, y_idx), (r, g, b, p[3]))

        img_large.paste(bar_img, (left, top), bar_img)

    # Downsample to 512x512 with high quality Lanczos filter for crisp anti-aliased curves
    img_512 = img_large.resize((512, 512), Image.Resampling.LANCZOS)

    # Save 512x512 PNG
    png_path_512 = output_dir / "app_icon.png"
    img_512.save(png_path_512, format="PNG")

    # Save ICO with all Windows standard resolutions (from 16 to 256)
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    ico_path = output_dir / "app_icon.ico"
    img_512.save(ico_path, format="ICO", sizes=sizes)

    print(f"[Icon] Generated transparent minimalist icons at {output_dir}")
    return ico_path, png_path_512


if __name__ == "__main__":
    assets_dir = Path(__file__).resolve().parent / "assets"
    generate_transparent_icon(assets_dir)

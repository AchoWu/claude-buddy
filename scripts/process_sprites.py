"""
Process cute_girl sprites: resize to 128x128, map animations to BUDDY states.
One-time script, run once to generate sprite files.
"""
import sys
from pathlib import Path
from PIL import Image

SRC_DIR = Path(r"C:\Users\29441\Downloads\cutegirlfiles\png")
DST_DIR = Path(__file__).parent.parent / "assets" / "sprites" / "characters" / "cute_girl"
DST_DIR.mkdir(parents=True, exist_ok=True)

TARGET_SIZE = 128

# Animation mapping: buddy_state -> (source_anim_name, frame_indices_1based)
MAPPING = {
    "idle":      ("Idle",  [1, 5, 9, 13]),
    "walk":      ("Walk",  [1, 6, 11, 16]),
    "work":      ("Run",   [1, 6, 11, 16]),
    "talk":      ("Jump",  [1, 8, 15]),
    "sleep":     ("Dead",  [1, 2, 3]),
    "celebrate": ("Jump",  [5, 12, 19, 26]),
}


def resize_to_square(img: Image.Image, size: int) -> Image.Image:
    """Resize image to fit within size×size, centered on transparent background."""
    # Calculate scale to fit
    w, h = img.size
    scale = min(size / w, size / h)
    new_w = int(w * scale)
    new_h = int(h * scale)

    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # Center on transparent canvas
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    offset_x = (size - new_w) // 2
    offset_y = (size - new_h) // 2
    canvas.paste(resized, (offset_x, offset_y), resized)
    return canvas


def process():
    total = 0
    for state, (anim_name, frames) in MAPPING.items():
        for i, frame_num in enumerate(frames):
            src_file = SRC_DIR / f"{anim_name} ({frame_num}).png"
            dst_file = DST_DIR / f"{state}_{i}.png"

            if not src_file.exists():
                print(f"  WARNING: {src_file} not found, skipping")
                continue

            img = Image.open(src_file).convert("RGBA")
            processed = resize_to_square(img, TARGET_SIZE)
            processed.save(dst_file, "PNG")
            total += 1
            print(f"  {state}_{i}.png <- {anim_name} ({frame_num}).png  [{img.size} -> {TARGET_SIZE}x{TARGET_SIZE}]")

    print(f"\nDone! {total} sprites saved to {DST_DIR}")


if __name__ == "__main__":
    process()

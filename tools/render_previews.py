# Render previews headlessly, without opening a window.
#
#   python tools/render_previews.py            # all designs
#   python tools/render_previews.py FIRE       # just one
#
# For every design it replays one full loop at 30 fps in a virtual
# display, saves the stills each README links to, and cuts the
# preview.gif the repository page shows.

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import importlib.util
from pathlib import Path

import numpy as np
import pygame
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
FPS = 30
GIF_EVERY = 4          # one gif frame every 4 simulated frames
GIF_WIDTH = 540

# folder -> script, the stills each README wants, in order
DESIGNS = {
    "LIGHTHOUSE": ("lighthouse.py", [("01_beam.png", 2.6), ("02_flash.png", 8.05), ("03_sea.png", 12.4)]),
    "FIRE": ("fire.py", [("01_ignite.png", 2.0), ("02_blaze.png", 9.4), ("03_coals.png", 20.0)]),
    "SOLAR-ECLIPSE": ("solar_eclipse.py", [("01_crescent.png", 6.5), ("02_totality.png", 11.0), ("03_diamond_ring.png", 14.8)]),
    "FIREFLY-FIELD": ("firefly_field.py", [("01_field.png", 4.7), ("02_wave.png", 9.1), ("03_night.png", 15.3)]),
    "THE-ANGLER": ("angler.py", [("01_lure.png", 3.5), ("02_lurk.png", 12.0), ("03_strike.png", 14.72)]),
}


def load(design, script):
    path = ROOT / design / script
    spec = importlib.util.spec_from_file_location(design.lower().replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def compose(mod, canvas, t, screen, small):
    # the same picture the window shows: art, glow, and the writing
    art, info, count = canvas.draw(t)
    screen.fill((0, 0, 0))
    screen.blit(art, (0, 0))
    screen.blit(mod.glow_layer(mod.blur(art, 4, 5), 0.75), (0, 0), special_flags=pygame.BLEND_ADD)
    screen.blit(mod.glow_layer(mod.blur(art, 8, 22), 0.45), (0, 0), special_flags=pygame.BLEND_ADD)
    y = mod.H - 70
    screen.blit(small.render(mod.SIGN, True, (120, 112, 128)), (64, y - 26))
    screen.blit(small.render(mod.hud(info), True, mod.DIM), (64, y))
    screen.blit(small.render(f"letters {count:05,d}", True, mod.DIM), (64, y + 26))
    tt = small.render(f"{'●' if int(t * 2) % 2 == 0 else ' '} t {t:05.2f}s", True, mod.AMBER)
    screen.blit(tt, (mod.W - 64 - tt.get_width(), 30))
    return info


def render(design):
    script, stills = DESIGNS[design]
    mod = load(design, script)
    out = ROOT / design / "images"
    out.mkdir(exist_ok=True)
    pygame.init()
    screen = pygame.Surface((mod.W, mod.H))
    small = pygame.font.SysFont(mod.MONO, 17)
    canvas = mod.Canvas(mod.glyphs())

    steps = int(mod.LOOP * FPS)
    gif_frames = []
    todo = {int(t * FPS): name for name, t in stills}
    print(f"{design}: {steps} frames ...", flush=True)
    for i in range(steps):
        t = (i + 1) / FPS
        info = compose(mod, canvas, t, screen, small)
        if i + 1 in todo:
            name = todo[i + 1]
            pygame.image.save(screen, str(out / name))
            print(f"  still {name}  (t={t:.2f}s)", flush=True)
        if (i + 1) % GIF_EVERY == 0:
            frame = pygame.surfarray.array3d(screen).transpose(1, 0, 2)
            img = Image.fromarray(frame.astype(np.uint8))
            k = GIF_WIDTH / mod.W
            img = img.resize((GIF_WIDTH, int(mod.H * k)), Image.LANCZOS)
            gif_frames.append(img)
    pygame.quit()

    gif = out / "preview.gif"
    pal = gif_frames[0].quantize(colors=64, method=Image.MEDIANCUT)
    qframes = [f.quantize(palette=pal, dither=Image.FLOYDSTEINBERG) for f in gif_frames]
    qframes[0].save(gif, save_all=True, append_images=qframes[1:],
                    duration=1000 * GIF_EVERY / FPS, loop=0, optimize=True)
    print(f"  preview.gif  ({len(qframes)} frames, {gif.stat().st_size // 1024} KB)", flush=True)


def main():
    wanted = sys.argv[1:] or list(DESIGNS)
    for design in wanted:
        if design not in DESIGNS:
            sys.exit(f"unknown design: {design}")
        render(design)


if __name__ == "__main__":
    main()

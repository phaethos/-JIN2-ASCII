# Firefly Field
# phaethos, 2026. Free to use for personal projects, see LICENSE.txt.
#
#   pip install -r requirements.txt
#   python firefly_field.py
#
# Some of the fireflies flash together, a wave of light crossing the
# field, the way real colonies of synchronous fireflies do. The rest
# keep their own time.
#
# Space pause, R restart, S screenshot, Esc quit

import sys
import time
from pathlib import Path

import numpy as np
import pygame

TAU = np.pi * 2
LOOP = 26.0          # length of one run (s)
TG = 1.9             # the shared rhythm of the synchronous ones (s)
NF = 90              # fireflies

POOLS = [".,';:", "-~_=+", "coaexz", "k%&8#"]   # dark -> bright
CHARS = " .,:~+*^01|/\\-_" + "".join(POOLS)
AT = {c: i for i, c in enumerate(CHARS)}
FILL = np.array([[AT[p[k % len(p)]] for k in range(12)] for p in POOLS])


def smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


# the field

#          fly core        fly fade         grass            grass tips      leaves          mist           star
TAG_COLOR = [[219, 255, 141], [130, 200, 80], [30, 58, 38], [96, 150, 74], [34, 44, 28], [40, 56, 44], [140, 152, 140]]
CORE, FADE, GRASS, TIPS, LEAF, MIST, STAR = range(7)

GY = 0.18                     # where the grass begins (frame height = 1)
GRASS_D = 0.32                # how deep the grass goes


class Fireflies:
    def __init__(self, aspect, rng):
        n = NF
        self.aspect = aspect
        sync = rng.random(n) < 0.4
        self.sync = sync
        self.T = np.where(sync, TG, 1.3 + 1.3 * rng.random(n))
        self.ax = (rng.random(n) * 2 - 1) * 0.5 * aspect
        # the synchronous ones hold the shared rhythm, offset across the field:
        # together their flashes make a wave that crosses from left to right
        self.phase = np.where(sync, (0.35 + 0.85 * (self.ax / aspect + 0.5)) % 1.0, rng.random(n))
        self.ay = GY - 0.30 * rng.random(n) + 0.02
        self.w = 0.3 + 0.6 * rng.random((n, 4))
        self.p = rng.random((n, 4)) * TAU
        self.jit = rng.random(n) * TAU

    def pose(self, t):
        x = self.ax + 0.045 * np.sin(self.w[:, 0] * t + self.p[:, 0]) + 0.02 * np.sin(self.w[:, 1] * t + self.p[:, 1])
        y = self.ay + 0.03 * np.sin(self.w[:, 2] * t + self.p[:, 2]) + 0.015 * np.sin(self.w[:, 3] * t + self.p[:, 3])
        u = (t / self.T + self.phase) % 1.0
        env = np.exp(-((u - 0.15) / 0.10) ** 2) + 0.30 * np.exp(-((u - 0.62) / 0.42) ** 2)
        return x, y, env


_grid = {}


def grid(cols, rows, aspect):
    key = (cols, rows)
    if key not in _grid:
        rng = np.random.default_rng(37)
        x = ((np.arange(cols) + 0.5) / cols - 0.5) * aspect
        y = (np.arange(rows) + 0.5) / rows - 0.5
        X, Y = np.meshgrid(x, y)
        _grid[key] = X, Y, rng.random((rows, cols)), rng.integers(0, 12, (rows, cols))
    return _grid[key]


def frame(t, cols, rows, aspect, flies):
    X, Y, rnd, hsh = grid(cols, rows, aspect)
    fx, fy, env = flies.pose(t)

    bright = np.zeros_like(X)
    tag = np.full(X.shape, GRASS, int)

    # 1. the grass: blades swaying, dense and dark at the bottom, pale tips
    v = smooth((Y - GY) / GRASS_D)
    shear = 0.22 * np.sin(0.7 * t + X * 2.2) * (Y - GY) / GRASS_D
    blade = (np.sin((X + shear) * 200.0) > 0.62 - 0.45 * v) & (Y > GY)
    grass_b = np.where(blade, 0.18 + 0.12 * v + 0.22 * (1 - v) * (0.5 + 0.5 * np.sin(hsh * TAU + 1.1 * t)), 0.0)
    grass_b = grass_b * (0.8 + 0.2 * np.sin(0.7 * t + X * 2.2))
    bright = np.where(blade, grass_b, bright)
    tag = np.where(blade & (grass_b > 0.20), TIPS, GRASS)
    tag = np.where(~blade & (Y > GY), GRASS, tag)

    # 2. mist drifting just above the tips
    mist = np.exp(-((Y - (GY - 0.05)) / 0.06) ** 2) * (0.5 + 0.5 * np.sin(2.1 * X + 0.6 * t)) * 0.16
    mist = np.clip(mist, 0, None) * (0.6 + 0.4 * np.sin(0.43 * t))
    over = (Y < GY) & (mist > 0.03)
    bright = np.where(over, np.maximum(bright, mist), bright)
    tag = np.where(over, MIST, tag)

    # 3. leaves hanging in from the top corners
    leaf_l = (Y < -0.42 + 0.10 * np.exp(-((X + 0.25) / 0.26) ** 2)) & (rnd > 0.25)
    leaf_r = (((X - 0.34) / 0.15) ** 2 + ((Y + 0.465) / 0.11) ** 2 < 1) & (rnd > 0.3)
    bright = np.where(leaf_l | leaf_r, 0.11 + 0.05 * (hsh % 3), bright)
    tag = np.where(leaf_l | leaf_r, LEAF, tag)

    # 4. a few stars over the field
    star = (Y < -0.30) & (bright < 0.04) & (rnd < 0.0016)
    twk = 0.55 + 0.45 * np.sin(1.3 * t + rnd * 77)
    bright = np.where(star, 0.22 * twk, bright)
    tag = np.where(star, STAR, tag)

    # 5. the fireflies
    ix = np.clip(((fx / aspect + 0.5) * cols).astype(int), 0, cols - 1)
    iy = np.clip(((fy + 0.5) * rows).astype(int), 0, rows - 1)
    in_grass = fy > GY
    b = env * (0.75 + 0.25 * np.sin(flies.jit + t)) * np.where(in_grass, 0.7, 1.0)
    for dxk, dyk, dim in ((0, 0, 1.0), (1, 0, 0.30), (-1, 0, 0.30), (0, 1, 0.30), (0, -1, 0.30)):
        jx = np.clip(ix + dxk, 0, cols - 1)
        jy = np.clip(iy + dyk, 0, rows - 1)
        glow = b * dim
        bright[jy, jx] = np.maximum(bright[jy, jx], glow)
        tag[jy, jx] = np.where(b > 0.4, CORE, FADE)

    on = bright > 0.045
    level = np.clip((bright * 3.3).astype(int), 0, 3)
    char = FILL[level, (hsh + (X * 9).astype(int)) % 12]
    char = np.where(on, char, AT[" "])
    # the fireflies themselves read as marks, not texture
    hot = b > 0.5
    char[iy, ix] = np.where(hot, AT["*"], np.where(b > 0.25, AT["+"], AT["."]))

    lum = np.where(on, np.clip(0.40 + 0.85 * bright, 0, 1.3)
                   * (0.35 + 0.65 * smooth((bright - 0.045) / 0.10)), 0.0)
    tag = np.where(on, tag, GRASS)

    # the wave of the synchronous ones
    u_wave = (t / TG) % 1.0
    x_norm = ((0.15 - u_wave - 0.35) % 1.0) / 0.85
    passing = x_norm < 1.0 / 0.85
    count = int((char != AT[" "]).sum())
    return char.astype(int), lum.astype(np.float32), tag.astype(int), \
        {"flashing": int((env > 0.5).sum()), "wave": bool(passing), "crest": float(np.clip(x_norm, 0, 1))}, count


# window

TITLE = "Firefly Field - phaethos"
SIGN = "@phaethos · 2026"
CW, CH, FONT_PX = 7, 11, 12
W, H = 1080, 960
COLS, ROWS = W // CW, H // CH
ASPECT = (COLS * CW) / (ROWS * CH)
TRAIL = 0.4
COLORS = np.array(TAG_COLOR, np.float32) / 255
DIM, AMBER = (110, 104, 120), (255, 190, 110)
MONO = "consolas,menlo,dejavusansmono,couriernew,monospace"


def hud(info):
    mood = f"wave crest {info['crest'] * 100:3.0f}%" if info["wave"] else "resting"
    return f"fireflies {NF}   flashing {info['flashing']:02d}   {mood}"


def glyphs():
    font = pygame.font.SysFont(MONO, FONT_PX)
    atlas = []
    for ch in CHARS:
        s = pygame.Surface((CW, CH))
        g = font.render(ch, True, (255, 255, 255))
        s.blit(g, ((CW - g.get_width()) // 2, (CH - g.get_height()) // 2))
        atlas.append(pygame.surfarray.array3d(s)[:, :, 0].T.astype(np.float32) / 255)
    return np.stack(atlas)


class Canvas:
    def __init__(self, atlas):
        self.atlas = (atlas * 255).astype(np.uint8)
        self.shape = pygame.Surface((COLS * CW, ROWS * CH))
        self.trail = pygame.Surface((W, H))
        self.fade = (int(TRAIL * 255),) * 3
        rng = np.random.default_rng(41)
        self.flies = Fireflies(ASPECT, rng)

    def reset(self):
        self.trail.fill((0, 0, 0))

    def draw(self, t):
        char, lum, tag, info, count = frame(t, COLS, ROWS, ASPECT, self.flies)
        mask = self.atlas[char.T].transpose(0, 3, 1, 2).reshape(COLS * CW, ROWS * CH)
        pygame.surfarray.blit_array(self.shape, np.repeat(mask[..., None], 3, 2))
        col = np.clip(COLORS[np.clip(tag, 0, len(COLORS) - 1)] * lum[..., None] * 255, 0, 255).astype(np.uint8)
        tint = pygame.transform.scale(pygame.surfarray.make_surface(col.transpose(1, 0, 2)), self.shape.get_size())
        self.shape.blit(tint, (0, 0), special_flags=pygame.BLEND_MULT)
        self.trail.fill(self.fade, special_flags=pygame.BLEND_MULT)     # previous frame fades
        self.trail.blit(self.shape, (0, 0), special_flags=pygame.BLEND_MAX)
        return self.trail, info, count


def blur(surf, k, radius):
    small = pygame.transform.smoothscale(surf, (W // k, H // k))
    if hasattr(pygame.transform, "gaussian_blur"):
        small = pygame.transform.gaussian_blur(small, max(1, radius // k))
    return pygame.transform.smoothscale(small, (W, H))


def glow_layer(surf, amount):
    layer = surf.copy()
    layer.fill((int(255 * amount),) * 3, special_flags=pygame.BLEND_MULT)
    return layer


def window_size():
    # shrink on small / scaled displays
    info = pygame.display.Info()
    k = 1.0
    if info.current_w > 0 and info.current_h > 0:
        k = min(1.0, 0.85 * info.current_h / H, 0.95 * info.current_w / W)
    return int(W * k), int(H * k)


def main():
    pygame.init()
    size = window_size()
    window = pygame.display.set_mode(size)
    pygame.display.set_caption(TITLE)
    screen = pygame.Surface((W, H))
    small = pygame.font.SysFont(MONO, 17)
    canvas, clock = Canvas(glyphs()), pygame.time.Clock()
    t, paused = 0.0, False
    art, info, count = canvas.draw(t)
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                pygame.quit()
                return
            if e.type == pygame.KEYDOWN and e.key == pygame.K_SPACE:
                paused = not paused
            if e.type == pygame.KEYDOWN and e.key == pygame.K_r:
                t = 0.0
                canvas.reset()
            if e.type == pygame.KEYDOWN and e.key == pygame.K_s:
                pygame.image.save(screen, str(Path(__file__).with_name(f"firefly_field_{int(time.time())}.png")))
        dt = clock.tick(30) / 1000
        if not paused:
            t += min(dt, 1 / 15)
            if t > LOOP:
                t = 0.0
                canvas.reset()
            art, info, count = canvas.draw(t)
        screen.fill((0, 0, 0))
        screen.blit(art, (0, 0))
        screen.blit(glow_layer(blur(art, 4, 5), 0.75), (0, 0), special_flags=pygame.BLEND_ADD)
        screen.blit(glow_layer(blur(art, 8, 22), 0.45), (0, 0), special_flags=pygame.BLEND_ADD)
        y = H - 70
        screen.blit(small.render(SIGN, True, (120, 112, 128)), (64, y - 26))
        screen.blit(small.render(hud(info), True, DIM), (64, y))
        screen.blit(small.render(f"letters {count:05,d}", True, DIM), (64, y + 26))
        tt = small.render(f"{'●' if int(t * 2) % 2 == 0 else ' '} t {t:05.2f}s", True, AMBER)
        screen.blit(tt, (W - 64 - tt.get_width(), 30))
        window.blit(screen if size == (W, H) else pygame.transform.smoothscale(screen, size), (0, 0))
        pygame.display.flip()


if __name__ == "__main__":
    sys.exit(main())

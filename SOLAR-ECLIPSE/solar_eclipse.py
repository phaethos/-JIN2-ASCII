# Solar Eclipse
# phaethos, 2026. Free to use for personal projects, see LICENSE.txt.
#
#   pip install -r requirements.txt
#   python solar_eclipse.py
#
# Space pause, R restart, S screenshot, Esc quit

import sys
import time
from pathlib import Path

import numpy as np
import pygame

TAU = np.pi * 2
LOOP = 22.0          # length of one run (s)

POOLS = [".,';:", "-~_=+", "coaexz", "k%&8#"]   # dark -> bright
CHARS = " .,:~+*^01|/\\-_" + "".join(POOLS)
AT = {c: i for i, c in enumerate(CHARS)}
FILL = np.array([[AT[p[k % len(p)]] for k in range(12)] for p in POOLS])


def smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def wrap(a):
    return (a + np.pi) % TAU - np.pi


# the eclipse

#          photosphere      diamond bead      corona           chromosphere    prominence     star          earthshine
TAG_COLOR = [[255, 244, 208], [255, 250, 230], [222, 218, 198], [204, 52, 26], [218, 60, 28], [165, 178, 168], [60, 60, 56]]
PHOT, BEAD, CORONA, CHROM, PROM, STAR, MOON = range(7)

CX, CY = 0.0, -0.06          # the sun sits a little above centre
RS = 0.16                    # sun radius
RM = 0.168                   # moon radius (frame height = 1)
C1, C2 = 8.55, 15.15         # second and third contact (s)


def moon_x(t):
    # the moon slides in, lingers over the sun, and slides out the other side
    wp = [(0.0, -0.34), (4.5, -0.13), (7.8, -0.014), (8.6, 0.0),
          (15.0, 0.004), (15.8, 0.014), (18.5, 0.13), (22.0, 0.34)]
    for (t0, x0), (t1, x1) in zip(wp, wp[1:]):
        if t <= t1:
            u = np.clip((t - t0) / (t1 - t0), 0.0, 1.0)
            return x0 + (x1 - x0) * (u * u * (3 - 2 * u))
    return wp[-1][1]


def jag(theta):
    # the lunar limb, worn into mountains and valleys
    return 0.5 * np.sin(3 * theta + 1.3) + 0.3 * np.sin(7 * theta - 0.4) + 0.2 * np.sin(11 * theta + 2.2)


def radial_char(phi):
    # letters along the direction of a ray
    s = (-np.degrees(phi)) % 180
    out = np.full(np.shape(s), AT["-"])
    out[(s >= 22.5) & (s < 67.5)] = AT["/"]
    out[(s >= 67.5) & (s < 112.5)] = AT["|"]
    out[(s >= 112.5) & (s < 157.5)] = AT["\\"]
    return out


_grid = {}


def grid(cols, rows, aspect):
    key = (cols, rows)
    if key not in _grid:
        rng = np.random.default_rng(29)
        x = ((np.arange(cols) + 0.5) / cols - 0.5) * aspect
        y = (np.arange(rows) + 0.5) / rows - 0.5
        X, Y = np.meshgrid(x, y)
        _grid[key] = X, Y, rng.random((rows, cols)), rng.integers(0, 12, (rows, cols))
    return _grid[key]


def frame(t, cols, rows, aspect):
    X, Y, rnd, hsh = grid(cols, rows, aspect)
    dx = moon_x(t)

    rs = np.hypot(X - CX, Y - CY)
    phi = np.arctan2(Y - CY, X - CX)
    rm = np.hypot(X - dx, Y - CY)
    thm = np.arctan2(Y - CY, X - dx)
    limb = RM * (1 + 0.016 * jag(thm))
    inmoon = smooth((limb - rm) / 0.010)
    on_disc = rs < RS

    totality_env = smooth((t - C1 + 0.15) / 1.2) * (1 - smooth((t - C2 - 0.15) / 1.2))
    contact_env = np.exp(-((t - (C1 + 0.35)) / 0.55) ** 2) + np.exp(-((t - (C2 - 0.35)) / 0.55) ** 2)

    bright = np.zeros_like(X)
    tag = np.full(X.shape, CORONA, int)

    # 1. the sun itself: a disc with a soft edge, bitten by the moon
    disc = on_disc & (rs > RS - 0.09)
    edge = smooth((RS - rs) / 0.010) * (1 - inmoon)
    phot = np.where(on_disc, edge * 1.05, 0.0)
    bright = np.where(phot > 0.03, phot, bright)
    tag = np.where(phot > 0.03, PHOT, tag)

    # 2. the corona: fine streamers that lean and breathe, polar plumes, occluded by the moon
    dr = np.maximum(rs - RS, 0)
    base = np.exp(-dr / 0.045) * np.exp(-dr / 0.30)
    ridge = np.abs(np.cos(9 * phi + 0.4 * np.sin(0.31 * t))) ** 3 * (0.72 + 0.28 * np.sin(3 * phi + 0.5 * t))
    fine = 0.75 + 0.25 * np.sin(23 * phi - 0.7 * t)
    plume = np.exp(-((np.cos(phi) / 0.30) ** 2)) * 0.45
    corona = (0.30 + 0.70 * ridge) * fine * (base * (1 + plume)) * (1 - inmoon)
    corona = corona * (0.12 + 0.88 * totality_env) * 1.5
    bright = np.where(~on_disc, np.maximum(bright, corona * (0.30 + 0.95 * totality_env)), bright)
    tag = np.where(~on_disc & (corona * (0.30 + 0.95 * totality_env) > 0.04), CORONA, tag)

    # 3. the diamond ring: one last bead of sunlight on the limb, with its cross of light
    phi_b = np.where(t < (C1 + C2) / 2, 0.0, np.pi)
    bx, by = RS * np.cos(phi_b), RS * np.sin(phi_b)
    d_b = np.hypot(X - bx, Y - CY - by)
    bead = np.exp(-(d_b / 0.016) ** 2) * contact_env * 1.6 * (1 - inmoon)
    ray = np.exp(-(wrap(phi - phi_b) / 0.05) ** 2) * np.exp(-np.maximum(rs - RS, 0) / 0.16)
    cross = (np.exp(-(wrap(phi - phi_b - np.pi / 2) / 0.05) ** 2)
             + np.exp(-(wrap(phi - phi_b + np.pi / 2) / 0.05) ** 2)) \
        * np.exp(-np.maximum(rs - RS, 0) / 0.06)
    ring = (bead + 1.1 * ray * contact_env + 0.6 * cross * contact_env) * (1 - inmoon)
    bright = np.where(ring > 0.04, np.maximum(bright, ring), bright)
    tag = np.where(ring > 0.30, BEAD, tag)
    tag = np.where((ring > 0.04) & (tag != BEAD), CORONA, tag)

    # 4. the chromosphere: a thin red rim, only at the edges of totality
    rim = np.exp(-((rs - RS) / 0.012) ** 2) * (1 - inmoon) * contact_env * 0.9
    bright = np.where(rim > 0.05, np.maximum(bright, rim), bright)
    tag = np.where(rim > 0.12, CHROM, tag)

    # 5. prominences: red loops hanging off the limb while the sun is dark
    prom = np.zeros_like(X)
    for k, (pa, pw) in enumerate(((0.55, 0.07), (2.35, 0.05), (-1.95, 0.08))):
        flick = 0.7 + 0.3 * np.sin(1.3 * t + 2.1 * k)
        near = np.exp(-((rs - RS * 1.005) / 0.014) ** 2) * np.exp(-((wrap(phi - pa) / pw) ** 2))
        prom = prom + near * flick
    prom = prom * totality_env * (1 - inmoon) * 0.85
    bright = np.where(prom > 0.05, np.maximum(bright, prom), bright)
    tag = np.where(prom > 0.12, PROM, tag)

    # 6. the moon itself, faint by earthshine, and the stars coming out
    shine = on_disc & (inmoon > 0.5) & (totality_env > 0.3) & (rnd < 0.45)
    bright = np.where(shine, np.maximum(bright, 0.038 + 0.018 * (hsh % 3)), bright)
    tag = np.where(shine, MOON, tag)
    dark = smooth((t - 7.6) / 1.3) * (1 - smooth((t - 15.9) / 1.3))
    star = (rnd < 0.0028) & (bright < 0.04)
    twk = 0.55 + 0.45 * np.sin(1.3 * t + rnd * 77)
    bright = np.where(star, 0.30 * twk * dark, bright)
    tag = np.where(star, STAR, tag)

    on = bright > 0.045
    level = np.clip((bright * 3.3).astype(int), 0, 3)
    char = FILL[level, (hsh + (phi * 3).astype(int)) % 12]
    # strong corona streaks are drawn along their own ray, and only close to the sun
    streak = (tag == CORONA) & (bright > 0.08) & (ridge > 0.85) & (rs > RS * 1.02) & (rs < RS * 2.2)
    char = np.where(streak, radial_char(phi), char)
    char = np.where(on, char, AT[" "])

    lum = np.where(on, np.clip(0.40 + 0.85 * bright, 0, 1.3)
                   * (0.35 + 0.65 * smooth((bright - 0.045) / 0.10)), 0.0)
    tag = np.where(on, tag, CORONA)

    disc_cells = int(on_disc.sum())
    visible = int((on_disc & (inmoon < 0.5)).sum())
    coverage = 1 - visible / max(disc_cells, 1)
    if coverage > 0.995:
        phase = "totality"
    elif contact_env > 0.35:
        phase = "diamond ring"
    elif coverage > 0.02:
        phase = "partial"
    else:
        phase = "clear"
    count = int((char != AT[" "]).sum())
    return char.astype(int), lum.astype(np.float32), tag.astype(int), \
        {"phase": phase, "coverage": float(np.clip(coverage, 0, 1))}, count


# window

TITLE = "Solar Eclipse - phaethos"
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
    return f"{info['phase']}   sun covered {info['coverage'] * 100:5.1f}%"


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

    def reset(self):
        self.trail.fill((0, 0, 0))

    def draw(self, t):
        char, lum, tag, info, count = frame(t, COLS, ROWS, ASPECT)
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
                pygame.image.save(screen, str(Path(__file__).with_name(f"solar_eclipse_{int(time.time())}.png")))
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

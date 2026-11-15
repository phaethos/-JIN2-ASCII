# The Angler
# phaethos, 2026. Free to use for personal projects, see LICENSE.txt.
#
#   pip install -r requirements.txt
#   python angler.py
#
# Down where the sun has never been, an anglerfish drifts in out of
# the dark with nothing visible but its lure. The fish is only there
# where the lure's light falls on it.
#
# Space pause, R restart, S screenshot, Esc quit

import sys
import time
from pathlib import Path

import numpy as np
import pygame

TAU = np.pi * 2
LOOP = 20.0          # length of one run (s)

IN_AT = 1.0          # when the fish starts drifting in
LURK_AT = 11.0       # when it settles
STRIKE_AT = 14.55    # when the jaw snaps shut
NSNOW = 130          # flakes of marine snow

POOLS = [".,';:", "-~_=+", "coaexz", "k%&8#"]   # dark -> bright
CHARS = " .,:~+*^01|/\\-_v" + "".join(POOLS)
AT = {c: i for i, c in enumerate(CHARS)}
FILL = np.array([[AT[p[k % len(p)]] for k in range(12)] for p in POOLS])


def smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def wrap(a):
    return (a + np.pi) % TAU - np.pi


# the deep

#          lure core        lure glow        lit water        snow            body           fins           teeth           eye             prey            strike flash
TAG_COLOR = [[240, 255, 230], [215, 255, 205], [46, 110, 104], [70, 120, 115], [118, 116, 94], [96, 96, 78], [210, 220, 212], [180, 195, 185], [150, 190, 170], [230, 240, 225]]
LCORE, LGLOW, WATER, SNOW, BODY, FIN, TEETH, EYE, PREY, FLASH = range(10)

HINGE = (0.10, -0.010)        # the jaw hinge, in fish coordinates (frame height = 1)
LURE_TIP = (0.148, 0.004)     # where the esca hangs
STALK_P0, STALK_P1 = (0.030, 0.042), (0.115, 0.108)


def fish_pose(t):
    # drifts in out of the dark, lurks, lunges, and drifts away again
    if t < LURK_AT:
        u = t / LURK_AT
        fx = -0.62 + 0.56 * (u * u * (3 - 2 * u))
    elif t < STRIKE_AT:
        fx = -0.06 + 0.008 * np.sin(1.1 * t)
    else:
        u = (t - STRIKE_AT) / (LOOP - STRIKE_AT)
        fx = -0.06 - 0.44 * smooth(u)
    fy = 0.02 + 0.03 * np.sin(0.7 * t) + 0.04 * smooth(max(t - STRIKE_AT, 0.0) / (LOOP - STRIKE_AT))
    lunge = 0.035 * np.exp(-((t - STRIKE_AT - 0.07) / 0.15) ** 2)
    return fx + lunge, fy, 0.05 * np.sin(0.33 * t)


def jaw_open(t):
    if t < STRIKE_AT:
        return 0.0
    if t < STRIKE_AT + 0.10:
        return (t - STRIKE_AT) / 0.10
    if t < STRIKE_AT + 0.30:
        return 1.0
    if t < STRIKE_AT + 0.50:
        return 1.0 - (t - STRIKE_AT - 0.30) / 0.20
    return 0.0


def prey_pose(t, ex, ey):
    # a small curious fish, drawn in by the light it cannot resist
    u = np.clip((t - 9.0) / (STRIKE_AT - 9.0), 0.0, 1.0)
    px = 0.52 - (0.52 - ex - 0.004) * smooth(u)
    py = ey + 0.05 * (1 - u) + 0.025 * np.sin(2.3 * t) * (1 - u)
    return px, py


class Angler:
    def __init__(self, cols, rows, aspect, rng):
        self.cols, self.rows, self.aspect = cols, rows, aspect
        self.sx = (rng.random(NSNOW) * 2 - 1) * 0.5 * aspect
        self.sy = rng.random(NSNOW) - 0.5
        self.sv = 0.010 + 0.022 * rng.random(NSNOW)
        self.sdrift = 0.008 * (rng.random(NSNOW) - 0.5)

    def step(self, dt):
        self.sy = (self.sy + self.sv * dt + 0.5) % 1.0 - 0.5
        self.sx = self.sx + self.sdrift * dt


_grid = {}


def grid(cols, rows, aspect):
    key = (cols, rows)
    if key not in _grid:
        rng = np.random.default_rng(43)
        x = ((np.arange(cols) + 0.5) / cols - 0.5) * aspect
        y = (np.arange(rows) + 0.5) / rows - 0.5
        X, Y = np.meshgrid(x, y)
        _grid[key] = X, Y, rng.random((rows, cols)), rng.integers(0, 12, (rows, cols))
    return _grid[key]


def frame(t, cols, rows, aspect, sea):
    X, Y, rnd, hsh = grid(cols, rows, aspect)
    sea.step(1 / 30)
    fx, fy, theta = fish_pose(t)
    open_j = jaw_open(t)
    I = 0.55 + 0.45 * np.sin(TAU * t / 1.7) + 0.15 * np.sin(9.1 * t) \
        + 2.0 * np.exp(-((t - STRIKE_AT - 0.08) / 0.14) ** 2)
    I = float(np.clip(I, 0.15, 2.6))

    cth, sth = np.cos(theta), np.sin(theta)
    dx, dy = X - fx, Y - fy
    xf = dx * cth + dy * sth
    yf = -dx * sth + dy * cth

    # the lure, its stalk, and the light they throw
    sway_x, sway_y = 0.010 * np.sin(1.7 * t), 0.008 * np.sin(1.3 * t + 1.0)
    lx, ly = LURE_TIP
    ex_w = fx + lx * cth - (ly + sway_y) * sth
    ey_w = fy + lx * sth + (ly + sway_y) * cth
    d_l = np.hypot(X - ex_w, Y - ey_w)
    r0 = 0.075 * (0.75 + 0.25 * I)
    light = I / (1 + (d_l / r0) ** 2)

    # the stalk, as a chain of points along its curve
    ss = np.linspace(0.0, 1.0, 18)[:, None, None]
    bx = ((1 - ss) ** 2 * STALK_P0[0] + 2 * (1 - ss) * ss * STALK_P1[0] + ss ** 2 * lx)
    by = ((1 - ss) ** 2 * STALK_P0[1] + 2 * (1 - ss) * ss * STALK_P1[1] + ss ** 2 * (ly + sway_y))
    px_w = fx + bx * cth - by * sth
    py_w = fy + bx * sth + by * cth
    d_s = np.min(np.hypot(X[None] - px_w, Y[None] - py_w), axis=0)

    bright = np.zeros_like(X)
    tag = np.full(X.shape, WATER, int)

    # 1. lit water: the glow reaches a little way into the dark
    amb = light * 0.14
    speck = (rnd < 0.12 + 0.60 * light ** 2)
    bright = np.where(speck, np.maximum(bright, amb), bright)
    tag = np.where(speck & (amb > 0.02), WATER, tag)

    # 2. marine snow, brightening as it drifts through the glow
    isx = np.clip(((sea.sx / aspect + 0.5) * cols).astype(int), 0, cols - 1)
    isy = np.clip(((sea.sy + 0.5) * rows).astype(int), 0, rows - 1)
    snow_b = 0.10 + 0.42 * light[isy, isx]
    bright[isy, isx] = np.maximum(bright[isy, isx], snow_b)
    tag[isy, isx] = SNOW

    # 3. the stalk of the illicium
    stalk = d_s < 0.008
    bright = np.where(stalk, np.maximum(bright, 0.16 + 0.18 * I), bright)
    tag = np.where(stalk, LGLOW, tag)

    # 4. the fish: only the parts the light reaches exist at all
    beta = 0.30 * np.sin(2.4 * t)
    body = ((xf / 0.115) ** 2 + (yf / 0.052) ** 2 < 1) | (((xf - 0.075) / 0.055) ** 2 + ((yf + 0.004) / 0.048) ** 2 < 1)
    rel_x, rel_y = xf + 0.105, yf
    rx2 = rel_x * np.cos(beta) - rel_y * np.sin(beta)
    ry2 = rel_x * np.sin(beta) + rel_y * np.cos(beta)
    hw = 0.020 + 0.34 * (-rx2)
    tail = (rx2 < -0.005) & (rx2 > -0.085) & (np.abs(ry2) < hw)
    dorsal = (xf > -0.06) & (xf < 0.06) & (yf > 0.052) & (yf < 0.052 + 0.026 * (1 - np.abs(xf) / 0.06))
    pect = ((xf + 0.01) / 0.028) ** 2 + ((yf + 0.052 + 0.008 * np.sin(2.0 * t)) / 0.014) ** 2 < 1
    hx, hy = HINGE
    phi_j = np.arctan2(yf - hy, xf - hx)
    L_j = np.hypot(xf - hx, yf - hy)
    th_u, th_l = 0.05 + open_j * 0.50, -0.05 - open_j * 0.60
    jaw_u = (L_j > 0.015) & (L_j < 0.078) & (np.abs(wrap(phi_j - th_u)) < 0.14)
    jaw_l = (L_j > 0.015) & (L_j < 0.078) & (np.abs(wrap(phi_j - th_l)) < 0.14)
    fish_any = body | tail | dorsal | pect | jaw_u | jaw_l

    fin = (dorsal | pect | tail) & fish_any
    flesh = body & fish_any
    lit = fish_any & (light > 0.10)
    fish_b = light * 0.72 * (0.85 + 0.15 * (hsh % 3))
    bright = np.where(lit, np.maximum(bright, fish_b), bright)
    tag = np.where(lit & ~fin, BODY, tag)
    tag = np.where(lit & fin, FIN, tag)

    # teeth, out only when the jaw opens
    teeth_u = jaw_u & (open_j > 0.15) & (L_j > 0.022) & (L_j < 0.070) \
        & (wrap(phi_j - th_u) > -0.13) & (wrap(phi_j - th_u) < -0.06) & ((hsh % 4) < 2)
    teeth_l = jaw_l & (open_j > 0.15) & (L_j > 0.022) & (L_j < 0.070) \
        & (wrap(phi_j - th_l) > 0.06) & (wrap(phi_j - th_l) < 0.13) & ((hsh % 4) >= 2)
    bright = np.where(teeth_u | teeth_l, light * 0.85, bright)
    tag = np.where(teeth_u | teeth_l, TEETH, tag)

    # the eye, catching the light
    eye = np.hypot(xf - 0.075, yf - 0.020) < 0.009
    bright = np.where(eye & (light > 0.12), light * 0.95, bright)
    tag = np.where(eye & (light > 0.12), EYE, tag)

    # 5. the prey, until the moment it is gone
    if 9.0 <= t < STRIKE_AT + 0.03:
        ppx, ppy = prey_pose(t, ex_w, ey_w)
        ipx = np.clip(int(round((ppx / aspect + 0.5) * cols)), 1, cols - 2)
        ipy = np.clip(int(round((ppy + 0.5) * rows)), 1, rows - 2)
        pl = light[ipy, ipx]
        if pl > 0.05:
            bright[ipy, ipx] = max(bright[ipy, ipx], 0.25 + 0.5 * pl)
            tag[ipy, ipx] = PREY
            bright[ipy, ipx - 1] = max(bright[ipy, ipx - 1], 0.12 + 0.3 * pl)
            tag[ipy, ipx - 1] = PREY
            bright[ipy, ipx + 1] = max(bright[ipy, ipx + 1], 0.10 + 0.25 * pl)
            tag[ipy, ipx + 1] = PREY

    # 6. the esca itself, and the strike flashing white for a breath
    core = d_l < 0.011
    halo = d_l < 0.034
    bright = np.where(halo, np.maximum(bright, I * 0.55 * np.exp(-(d_l / 0.020) ** 2)), bright)
    tag = np.where(halo & (bright > 0.10), LGLOW, tag)
    bright = np.where(core, np.maximum(bright, 0.85 + 0.45 * I), bright)
    tag = np.where(core, LCORE, tag)
    flash = np.exp(-((t - STRIKE_AT - 0.12) / 0.16) ** 2)
    if flash > 0.05:
        bright = np.where(d_l < 0.08, np.maximum(bright, flash * 0.9 * np.exp(-(d_l / 0.045) ** 2)), bright)
        tag = np.where((d_l < 0.08) & (flash * np.exp(-(d_l / 0.045) ** 2) > 0.25), FLASH, tag)

    on = bright > 0.045
    level = np.clip((bright * 3.2).astype(int), 0, 3)
    char = FILL[level, (hsh + (X * 5).astype(int)) % 12]
    char = np.where(on, char, AT[" "])
    # a few deliberate marks: the stalk, the snow, the teeth
    char = np.where(stalk & on, AT["~"], char)
    char[isy, isx] = np.where(~fish_any[isy, isx], np.where(rnd[isy, isx] < 0.5, AT["."], AT[","]), char[isy, isx])
    char = np.where(teeth_u & on, AT["v"], char)
    char = np.where(teeth_l & on, AT["^"], char)
    char = np.where(eye & on, AT["o"], char)
    char = np.where(core, AT["*"], char)

    lum = np.where(on, np.clip(0.40 + 0.85 * bright, 0, 1.3)
                   * (0.35 + 0.65 * smooth((bright - 0.045) / 0.10)), 0.0)
    tag = np.where(on, tag, WATER)

    if t < LURK_AT - 0.5:
        state = "drifting closer"
    elif t < STRIKE_AT:
        state = "lurking"
    elif t < STRIKE_AT + 0.6:
        state = "STRIKE"
    else:
        state = "drifting away"
    count = int((char != AT[" "]).sum())
    return char.astype(int), lum.astype(np.float32), tag.astype(int), \
        {"state": state, "lure": float(I)}, count


# window

TITLE = "The Angler - phaethos"
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
    return f"{info['state']}   lure {info['lure']:.2f}"


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
        rng = np.random.default_rng(47)
        self.sea = Angler(COLS, ROWS, ASPECT, rng)

    def reset(self):
        self.trail.fill((0, 0, 0))

    def draw(self, t):
        char, lum, tag, info, count = frame(t, COLS, ROWS, ASPECT, self.sea)
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
                pygame.image.save(screen, str(Path(__file__).with_name(f"angler_{int(time.time())}.png")))
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

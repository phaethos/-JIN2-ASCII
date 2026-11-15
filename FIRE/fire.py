# Fire
# phaethos, 2026. Free to use for personal projects, see LICENSE.txt.
# After the classic fire effect from the demoscene (early 1990s):
# heat is injected at the bottom, cools as it rises, and every cell
# asks its three neighbours below what is left of their warmth.
#
#   pip install -r requirements.txt
#   python fire.py
#
# Space pause, R restart, S screenshot, Esc quit

import sys
import time
from pathlib import Path

import numpy as np
import pygame

TAU = np.pi * 2
LOOP = 24.0          # length of one run (s)

POOLS = [".,';:", "~-_=", "coaes", "%&#8$"]     # dark -> bright
CHARS = " .,:~+*^01|/\\-_" + "".join(POOLS)
AT = {c: i for i, c in enumerate(CHARS)}
FILL = np.array([[AT[p[k % len(p)]] for k in range(12)] for p in POOLS])


def smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


# the fire

#          ember white      yellow           orange           red           deep red        smoke
TAG_COLOR = [[255, 240, 200], [255, 192, 86], [255, 116, 26], [206, 48, 16], [128, 28, 12], [86, 80, 70]]
WHITE, YELLOW, ORANGE, RED, DEEP, SMOKE = range(6)

FLARE_T = 7.0                  # seconds between flare-ups
MAX_EMBERS = 90


class Fire:
    """The heat field and the embers riding it."""

    def __init__(self, cols, rows, aspect):
        self.cols, self.rows, self.aspect = cols, rows, aspect
        self.heat = np.zeros((rows, cols), np.float32)
        x = ((np.arange(cols) + 0.5) / cols - 0.5) * aspect
        self.x = x
        r = np.arange(rows, dtype=np.float32) / (rows - 1)          # 0 top, 1 bottom
        self.decay = 0.985 + 0.014 * r[:-1] ** 1.5                  # heat barely cools climbing
        self.bite = 0.004 + 0.05 * r[:-1] ** 3                      # ...but the air takes its bite
        self.fade = 1 - smooth((np.abs(x) - 0.40 * aspect) / (0.09 * aspect))
        rng = np.random.default_rng(23)
        self.rng = rng
        k = MAX_EMBERS
        self.ex, self.ey = rng.random(k) * 0.2 - 0.1, rng.random(k)          # spawn over the run
        self.evx, self.evy = rng.random(k) * 0.02 - 0.01, 0.05 + 0.12 * rng.random(k)
        self.el = rng.random(k) * 0.4                                # life, starts staggered
        self.ef = rng.random(k) * TAU

    def wind(self, t):
        # where the coals slide, in cells
        return 2.5 * np.sin(0.5 * t) + 1.2 * np.sin(0.19 * t + 1.7)

    def breath(self, t):
        # the fire breathes, and every so often it flares up
        return (0.85 + 0.15 * np.sin(TAU * t / 9.0)
                + 0.5 * np.exp(-(((t % FLARE_T) - 2.4) / 0.55) ** 2))

    def step(self, t, dt):
        rows, cols = self.rows, self.cols
        b = self.breath(t)
        w = self.wind(t)

        # the bed of coals along the bottom edge, sliding slowly with the wind
        sx = self.x - w
        src = 0.62 + 0.38 * np.sin(0.9 * sx + 2.6 * t) * np.sin(2.1 * sx - 1.3 * t)
        src = src + 0.22 * self.rng.random(cols) - 0.11
        src = np.clip(src * b * self.fade, 0.0, 1.0)
        self.heat[rows - 1] = src
        self.heat[rows - 2] = src * 0.78
        self.heat[rows - 3] = src * 0.50

        # every cell asks the three below it; the answer cools on the way up.
        # a sub-cell sideways pull per step, so the plume leans with the wind
        avg = (self.heat[1:] + np.roll(self.heat[1:], 1, 1) + np.roll(self.heat[1:], -1, 1)) / 3
        c = 0.30 * np.sin(0.9 * t) + 0.22 * np.sin(0.31 * t + 2.1)
        fl, f = np.floor(c).astype(int), c - np.floor(c)
        a1 = np.take(avg, (np.arange(cols) - fl) % cols, axis=1)
        a2 = np.take(avg, (np.arange(cols) - fl - 1) % cols, axis=1)
        self.heat[:-1] = ((1 - f) * a1 + f * a2) * self.decay[:, None]
        self.heat[:-1] -= self.rng.random((rows - 1, cols)) * self.bite[:, None]
        np.clip(self.heat, 0, 1.5, out=self.heat)

        self.embers(t, dt)

    def embers(self, t, dt):
        rng = self.rng
        dead = self.el <= 0
        n = int(dead.sum())
        if n:
            i = np.where(dead)[0]
            self.ex[i] = (rng.random(n) * 2 - 1) * 0.16 * self.aspect
            self.ey[i] = 0.44 + 0.04 * rng.random(n)
            self.evx[i] = rng.random(n) * 0.03 - 0.015
            self.evy[i] = 0.05 + 0.14 * rng.random(n)
            self.el[i] = 0.55 + 0.75 * rng.random(n)
            self.ef[i] = rng.random(n) * TAU
        self.el -= dt
        drift = self.wind(t) * 0.012
        self.ex += (self.evx + drift) * dt * 6
        self.ey -= self.evy * dt
        self.el = np.clip(self.el, 0, None)


def frame(t, cols, rows, aspect, fire):
    fire.step(t, 1 / 30)
    heat = fire.heat

    on = heat > 0.06
    level = np.clip((heat * 3.8).astype(int), 0, 3)
    char = FILL[level, ((heat * 40).astype(int)) % 12]
    char = np.where(on, char, AT[" "])

    tag = np.select([heat < 0.16, heat < 0.34, heat < 0.52, heat < 0.72, heat < 0.92],
                    [SMOKE, DEEP, RED, ORANGE, YELLOW], WHITE)
    # smoke keeps only where there is no fire left to speak of
    tag = np.where((heat < 0.16) & (heat > 0.06), SMOKE, tag)
    lum = np.where(on, np.clip(0.40 + 0.95 * heat, 0, 1.3)
                   * (0.35 + 0.65 * smooth((heat - 0.06) / 0.12)), 0.0)

    # embers ride up out of the fire and die out on the way
    ex, ey, el, ef = fire.ex, fire.ey, fire.el, fire.ef
    ix = np.clip(((ex / aspect + 0.5) * cols).astype(int), 0, cols - 1)
    iy = np.clip(((ey + 0.5) * rows).astype(int), 0, rows - 1)
    alive = el > 0.05
    eb = np.where(alive, el * (0.75 + 0.25 * np.sin(ef + 9 * t)), 0.0)
    lum[iy[alive], ix[alive]] = np.maximum(lum[iy[alive], ix[alive]], eb[alive])
    char[iy[alive], ix[alive]] = AT["*"]
    char[iy[alive & (eb < 0.45)], ix[alive & (eb < 0.45)]] = AT["+"]
    tag[iy[alive], ix[alive]] = WHITE

    count = int((char != AT[" "]).sum())
    return char.astype(int), lum.astype(np.float32), tag.astype(int), \
        {"wind": float(fire.wind(t)), "flame": float(fire.breath(t)), "embers": int((el > 0).sum())}, count


# window

TITLE = "Fire - phaethos"
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
    return f"wind {info['wind']:+.2f}   flame {info['flame']:.2f}   embers {info['embers']:02d}"


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
        self.fire = Fire(COLS, ROWS, ASPECT)

    def reset(self):
        self.trail.fill((0, 0, 0))

    def draw(self, t):
        char, lum, tag, info, count = frame(t, COLS, ROWS, ASPECT, self.fire)
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
    canvas.fire = Fire(COLS, ROWS, ASPECT)
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
                canvas.fire = Fire(COLS, ROWS, ASPECT)
                canvas.reset()
            if e.type == pygame.KEYDOWN and e.key == pygame.K_s:
                pygame.image.save(screen, str(Path(__file__).with_name(f"fire_{int(time.time())}.png")))
        dt = clock.tick(30) / 1000
        if not paused:
            t += min(dt, 1 / 15)
            if t > LOOP:
                t = 0.0
                canvas.fire = Fire(COLS, ROWS, ASPECT)
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

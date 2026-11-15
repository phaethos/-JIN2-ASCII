# Lighthouse
# phaethos, 2026. Free to use for personal projects, see LICENSE.txt.
#
#   pip install -r requirements.txt
#   python lighthouse.py
#
# Space pause, R restart, S screenshot, Esc quit

import sys
import time
from pathlib import Path

import numpy as np
import pygame

TAU = np.pi * 2
LOOP = 18.0          # length of one run (s)
BEAM_T = 6.0         # one turn of the lamp (s)

POOLS = [".,';:", "-~_=+", "coaexz", "k%&8#"]   # dark -> bright
CHARS = " .,:~+*^01|/\\-_" + "".join(POOLS)
AT = {c: i for i, c in enumerate(CHARS)}
FILL = np.array([[AT[p[k % len(p)]] for k in range(12)] for p in POOLS])


def smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def wrap(a):
    return (a + np.pi) % TAU - np.pi


# the lighthouse

#          lamp white       lamp glow         beam haze        sea          foam           stone         star           cloud
TAG_COLOR = [[255, 236, 196], [255, 214, 142], [255, 186, 104], [42, 118, 110], [190, 226, 208], [78, 70, 58], [172, 190, 180], [86, 102, 98]]
LAMPW, LAMP, HAZE, SEA, FOAM, STONE, STAR, CLOUD = range(8)

HZ = 0.16                      # horizon (frame height = 1)
LX, LY = -0.34, -0.342         # the lamp
Y_BASE, Y_DECK = 0.10, -0.310  # tower, rock top to gallery deck
R_BASE, R_TOP = 0.050, 0.024   # tower radius at base and deck
FLASH_AT = 2.1                 # beam angle that reads as "pointing at you"

_grid = {}


def grid(cols, rows, aspect):
    key = (cols, rows)
    if key not in _grid:
        rng = np.random.default_rng(11)
        x = ((np.arange(cols) + 0.5) / cols - 0.5) * aspect
        y = (np.arange(rows) + 0.5) / rows - 0.5
        X, Y = np.meshgrid(x, y)
        _grid[key] = (X, Y, rng.random((rows, cols)),
                      rng.integers(0, 12, (rows, cols)), rng.random((rows, cols)) * TAU)
    return _grid[key]


def beam_field(X, Y, t):
    # one cone of light on a slow turn; a soft skirt around the hard edge
    d = np.hypot(X - LX, Y - LY)
    ang = np.arctan2(Y - LY, X - LX)
    b = TAU * t / BEAM_T
    a = wrap(ang - b)
    cone = np.exp(-(a / 0.115) ** 2) + 0.22 * np.exp(-(a / 0.30) ** 2)
    fall = 1 / (1 + (d / 0.16) ** 1.7)
    flash = np.exp(-(wrap(b - FLASH_AT) / 0.26) ** 2) * 2.2
    return d, cone * fall, flash


def sea_field(X, Y, t):
    # foam lines riding toward the viewer, spaced wider as they come close
    v = smooth((Y - HZ) / 0.34)
    wavey = 0.32 * np.sin(6.3 * X + 1.1 * t) + 0.18 * np.sin(11.3 * X - 0.7 * t + 2.0)
    freq = 3.5 + 24 * v
    s = Y * freq + 0.22 * t * (0.35 + 0.75 * v) + wavey * (0.35 + 0.75 * v)
    g = s - np.round(s)
    line = np.exp(-(g / 0.14) ** 2) * (0.10 + 0.16 * v)
    return v, line


def tower_mask(X, Y):
    # tapered tower, gallery deck, lamp room, cap - the solid parts of the light
    r = R_BASE + (R_TOP - R_BASE) * (Y - Y_BASE) / (Y_DECK - Y_BASE)
    tower = (Y > Y_DECK) & (Y < Y_BASE) & (np.abs(X - LX) < r)
    deck = (np.abs(Y + 0.303) < 0.012) & (np.abs(X - LX) < 0.047)
    room = (Y > -0.375) & (Y < -0.312) & (np.abs(X - LX) < 0.032)
    rc = 0.032 * np.clip((Y + 0.415) / 0.040, 0, 1)
    cap = (Y > -0.415) & (Y <= -0.375) & (np.abs(X - LX) < rc)
    return tower, deck, room, cap


def rock_mask(X, Y):
    r1 = ((X - LX + 0.045) / 0.115) ** 2 + ((Y - HZ - 0.028) / 0.055) ** 2 < 1
    r2 = ((X - LX - 0.10) / 0.075) ** 2 + ((Y - HZ - 0.020) / 0.040) ** 2 < 1
    return r1 | r2


def frame(t, cols, rows, aspect):
    X, Y, rnd, hsh, phs = grid(cols, rows, aspect)
    d, beam, flash = beam_field(X, Y, t)
    v, line = sea_field(X, Y, t)
    lift = 1 + 0.30 * flash                       # the whole scene lifts as the beam sweeps past you
    tower, deck, room, cap = tower_mask(X, Y)
    rock = rock_mask(X, Y)
    solid = tower | deck | cap | rock

    bright = np.zeros_like(X)
    tag = np.full(X.shape, SEA, int)

    # 1. the lamp room glows, and flares when the beam faces you
    dl = np.hypot(X - LX, Y - LY)
    glass = room & ~solid
    core = dl < 0.012
    halo = np.exp(-(dl / 0.045) ** 2)
    bright = np.where(glass, 0.42 + 0.30 * flash + 0.55 * halo, bright)
    tag = np.where(glass, LAMP, tag)
    mul = room & (np.abs(np.abs(X - LX) - 0.014) < 0.0035)      # the lamp room mullions
    bright = np.where(mul, 0.12, bright)
    tag = np.where(mul, STONE, tag)
    bright = np.where(core, 1.30 + 0.55 * flash, bright)
    tag = np.where(core, LAMPW, tag)

    # 2. the beam paints the air; over the water it breaks into glitter
    air = (~solid) & (Y < HZ) & (dl > 0.05)
    wisp = np.exp(-((Y + 0.24) / 0.05) ** 2) * (0.45 + 0.45 * np.sin(2.3 * X + 0.8 * t)) \
        * (0.5 + 0.5 * np.sin(0.7 * X - 0.23 * t))
    wisp = np.clip(wisp, 0, None) * 0.14
    haze = beam * 0.55 * lift + wisp * beam * 3.0
    bright = np.where(air, np.maximum(bright, haze), bright)
    tag = np.where(air & (haze > 0.04), HAZE, tag)

    # 3. the sea: faint swell lines, beam glitter, and the lamp's broken reflection
    sea = (Y > HZ) & ~rock
    spk = (0.5 + 0.5 * np.sin(hsh * TAU + 3.1 * t)) ** 4 * (0.5 + 0.5 * np.sin(9 * X + 1.7 * t))
    glint = beam * (0.25 + 1.15 * spk)
    refl = np.exp(-((X - LX) / 0.024) ** 2) * np.exp(-((Y - HZ) / 0.26) ** 2) * (0.10 + 0.45 * spk)
    sea_b = (0.035 + 0.045 * v + line) * lift
    wet = np.maximum(np.maximum(sea_b, glint), refl)
    bright = np.where(sea, np.maximum(bright, wet), bright)
    tag = np.where(sea & (refl > wet * 0.6) & (refl > 0.05), HAZE, tag)
    tag = np.where(sea & (glint > sea_b) & (glint > 0.05), HAZE, tag)
    tag = np.where(sea & (bright <= 0.05), SEA, tag)

    # 4. foam crowding the rocks
    drock = np.minimum(np.hypot((X - LX + 0.045) / 0.115, (Y - HZ - 0.028) / 0.055),
                       np.hypot((X - LX - 0.10) / 0.075, (Y - HZ - 0.020) / 0.040))
    foam = (Y > HZ - 0.02) & (drock > 1.0) & (drock < 1.22) & ((0.5 + 0.5 * np.sin(hsh * TAU + 2.2 * t)) > 0.45)
    bright = np.where(foam, np.maximum(bright, 0.18 + 0.10 * np.sin(5 * t + hsh)), bright)
    tag = np.where(foam, FOAM, tag)

    # 5. the tower itself, barely more than a silhouette
    stone_lum = 0.10 + 0.05 * (hsh % 3) / 2
    bright = np.where(solid, stone_lum, bright)
    tag = np.where(solid, STONE, tag)
    rim = deck & (np.abs(X - LX) > 0.036)
    bright = np.where(rim, 0.30, bright)

    # 6. stars, washed out where the beam passes
    star = (Y < HZ - 0.03) & (~solid) & (rnd < 0.0028) & (bright < 0.06)
    twk = 0.55 + 0.45 * np.sin(1.3 * t + rnd * 77)
    star_b = 0.30 * twk * (1 - np.minimum(beam * 1.6, 0.85))
    bright = np.where(star, star_b, bright)
    tag = np.where(star, STAR, tag)
    tag = np.where(air & (wisp > 0.02) & (beam < 0.05) & (bright < 0.06), CLOUD, tag)
    bright = np.where(tag == CLOUD, wisp, bright)

    on = bright > 0.045
    level = np.clip((bright * 3.3).astype(int), 0, 3)
    char = FILL[level, (hsh + (phs + t * 0.9).astype(int)) % 12]
    char = np.where(on, char, AT[" "])

    lum = np.where(on, np.clip(0.40 + 0.85 * bright, 0, 1.3)
                   * (0.35 + 0.65 * smooth((bright - 0.045) / 0.10)), 0.0)
    tag = np.where(on, tag, SEA)

    count = int((char != AT[" "]).sum())
    return char.astype(int), lum.astype(np.float32), tag.astype(int), \
        {"bearing": float(np.degrees(TAU * t / BEAM_T) % 360), "flash": float(flash)}, count


# window

TITLE = "Lighthouse - phaethos"
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
    mood = "toward you" if info["flash"] > 0.5 else "sweeping"
    return f"bearing {info['bearing']:5.1f}°   beam {mood}"


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
                pygame.image.save(screen, str(Path(__file__).with_name(f"lighthouse_{int(time.time())}.png")))
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

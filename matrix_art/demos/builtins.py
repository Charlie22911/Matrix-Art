from __future__ import annotations

BUILTIN_DEMOS = [
    {
        "slug": 'rgb-plasma',
        "title": 'Direct Buffer Plasma Test',
        "description": 'High-speed NumPy plasma using the direct writable frame buffer path.',
        "default_fps": 60,
        "code": r'''
import math
import random
import numpy as np

NAME = "Direct Buffer Plasma Test"
DEFAULT_FPS = 60

PARAMS = {
    "speed": {"type": "float", "default": 1.0, "min": 0.1, "max": 4.0, "step": 0.1},
    "scale": {"type": "float", "default": 0.135, "min": 0.04, "max": 0.40, "step": 0.005},
    "warp": {"type": "float", "default": 2, "min": 0.0, "max": 2.0, "step": 0.05},
    "contrast": {"type": "float", "default": 1.25, "min": 0.0, "max": 1.0, "step": 0.05},
    "brightness": {"type": "float", "default": 1, "min": 0.2, "max": 1.5, "step": 0.05},

    # 0 = RGB plasma
    # 1 = hot neon
    # 2 = ocean electric
    # 3 = acid candy
    # 4 = firestorm
    "palette": {"type": "int", "default": 0, "min": 0, "max": 4, "step": 1},
}


def smoothstep(a, b, x):
    if x <= a:
        return 0.0
    if x >= b:
        return 1.0
    t = (x - a) / (b - a)
    return t * t * (3.0 - 2.0 * t)


def clamp_byte(v):
    if v <= 0:
        return 0
    if v >= 255:
        return 255
    return int(v)


def make_base_palette(style):
    palette = np.empty((256, 3), dtype=np.uint8)

    for i in range(256):
        t = i / 255.0

        if style == 1:
            r = 255 * smoothstep(0.05, 0.55, t)
            g = 255 * smoothstep(0.35, 0.90, t)
            b = 80 * (1.0 - smoothstep(0.10, 0.70, t)) + 255 * smoothstep(0.86, 1.0, t)

        elif style == 2:
            r = 40 * smoothstep(0.55, 1.0, t)
            g = 255 * smoothstep(0.10, 0.86, t)
            b = 110 + 145 * (1.0 - smoothstep(0.72, 1.0, t))

        elif style == 3:
            a = t * math.tau
            r = (math.sin(a * 1.0 + 0.0) + 1.0) * 127.5
            g = (math.sin(a * 1.7 + 1.4) + 1.0) * 127.5
            b = (math.sin(a * 2.3 + 3.0) + 1.0) * 127.5

        elif style == 4:
            r = 255 * smoothstep(0.00, 0.45, t)
            g = 220 * smoothstep(0.30, 0.78, t)
            b = 55 * smoothstep(0.75, 1.00, t)

        else:
            a = t * math.tau
            r = (math.sin(a + 0.0) + 1.0) * 127.5
            g = (math.sin(a + 2.1) + 1.0) * 127.5
            b = (math.sin(a + 4.2) + 1.0) * 127.5

        palette[i, 0] = clamp_byte(r)
        palette[i, 1] = clamp_byte(g)
        palette[i, 2] = clamp_byte(b)

    return palette


def make_lit_palette(style):
    base = make_base_palette(style).astype(np.uint16)
    lut = np.empty((256 * 256, 3), dtype=np.uint8)

    for level in range(256):
        start = level * 256
        lut[start:start + 256, :] = ((base * level) // 255).astype(np.uint8)

    return lut


def ensure_palette(state, style):
    style = max(0, min(4, int(style)))

    if state.get("palette_style") != style:
        state["palette_style"] = style
        state["palette_lut"] = make_lit_palette(style)

    return state["palette_lut"]


def setup(ctx):
    y, x = np.mgrid[0:ctx.height, 0:ctx.width]
    x = x.astype(np.float32)
    y = y.astype(np.float32)

    cx = x - (ctx.width - 1) * 0.5
    cy = y - (ctx.height - 1) * 0.5

    radius = np.sqrt(cx * cx + cy * cy).astype(np.float32)
    angle = np.arctan2(cy, cx).astype(np.float32)

    return {
        "x": x,
        "y": y,
        "radius": radius,
        "angle": angle,

        "time": random.uniform(0.0, 1000.0),
        "palette_style": None,
        "palette_lut": None,
    }


def render(ctx, t, dt, frame, params, state):
    # Hard requirement for this test. No fallback.
    rgb = frame.rgb_array()

    speed = float(params.get("speed", 1.0))
    scale = float(params.get("scale", 0.135))
    warp = float(params.get("warp", 1.0))
    contrast = float(params.get("contrast", 0.80))
    brightness_gain = float(params.get("brightness", 0.95))
    palette_style = int(params.get("palette", 0))

    state["time"] += dt * speed
    tt = state["time"]

    x = state["x"]
    y = state["y"]
    radius = state["radius"]
    angle = state["angle"]

    lut = ensure_palette(state, palette_style)

    # Evolving coordinate warp.
    wx = np.sin(y * 0.085 + tt * 1.41) * (2.0 + 3.0 * warp)
    wy = np.cos(x * 0.075 - tt * 1.23) * (2.0 + 3.0 * warp)

    xx = x * scale + wx * 0.16
    yy = y * scale + wy * 0.16
    rr = radius * scale

    # Plasma field.
    v = (
        np.sin(xx * 1.25 + tt * 1.70) +
        np.sin(yy * 1.15 - tt * 1.30) +
        np.sin((xx + yy) * 0.85 + tt * 0.90) +
        np.sin(rr * 1.45 - tt * 1.10) +
        np.sin(angle * 3.0 + rr * 0.75 + tt * 0.75) * 0.75
    )

    ripple = np.sin((x * 0.17 - y * 0.11) + tt * 2.40)
    cloud = np.sin(v * 0.65 + ripple * 0.70 + tt * 0.35)

    color_index = ((np.sin(v * 0.88 + tt * 0.42) + 1.0) * 127.5 + ripple * 24.0)
    color_index = color_index.astype(np.uint16) & 255

    shadow = (cloud + 1.0) * 0.5
    shadow = shadow * shadow * (3.0 - 2.0 * shadow)

    bright = 1.0 - contrast * shadow * 0.75
    bright *= brightness_gain
    bright += 0.08 * np.sin(v * 1.70 + tt * 3.0)
    bright = np.clip(bright, 0.0, 1.0)

    bright_index = (bright * 255.0).astype(np.uint16)

    # Direct write into Matrix-Art's current frame buffer.
    rgb[:, :, :] = lut[(bright_index << 8) + color_index]
'''.strip(),
    },
    {
        "slug": 'starfield',
        "title": 'Starfield',
        "description": 'A simple flying-through-space effect using persistent star positions.',
        "default_fps": 30,
        "code": r'''
import random

NAME = "Starfield"
DEFAULT_FPS = 30
PARAMS = {
    "stars": {"type": "int", "default": 120, "min": 20, "max": 300, "step": 10},
    "speed": {"type": "float", "default": 0.55, "min": 0.1, "max": 2.0, "step": 0.05},
}

def setup(ctx):
    count = 300
    stars = []
    for _ in range(count):
        stars.append([random.uniform(-1, 1), random.uniform(-1, 1), random.uniform(0.12, 1.0)])
    return {"stars": stars}

def render(ctx, t, dt, frame, params, state):
    frame.fill(0, 0, 8)
    desired = int(params.get("stars", 120))
    speed = float(params.get("speed", 0.55))
    stars = state["stars"]
    cx = ctx.width / 2
    cy = ctx.height / 2
    for star in stars[:desired]:
        star[2] -= dt * speed
        if star[2] <= 0.04:
            star[0] = random.uniform(-1, 1)
            star[1] = random.uniform(-1, 1)
            star[2] = 1.0
        z = star[2]
        x = int(cx + star[0] * cx / z)
        y = int(cy + star[1] * cy / z)
        brightness = int(max(40, min(255, 255 * (1.0 - z))))
        frame.set_pixel(x, y, brightness, brightness, brightness)
'''.strip(),
    },
    {
        "slug": 'fire',
        "title": 'Fire',
        "description": 'A tiny old-school fire simulation with a simple heat palette.',
        "default_fps": 25,
        "code": r'''
import random

NAME = "Fire"
DEFAULT_FPS = 25
PARAMS = {
    "cooling": {"type": "int", "default": 3, "min": 0, "max": 10, "step": 1},
    "sparks": {"type": "int", "default": 85, "min": 0, "max": 100, "step": 5},
}

def setup(ctx):
    return {"heat": [[0 for _ in range(ctx.width)] for _ in range(ctx.height)]}

def palette(v):
    v = max(0, min(255, int(v)))
    if v < 85:
        return (v * 3, 0, 0)
    if v < 170:
        return (255, (v - 85) * 3, 0)
    return (255, 255, (v - 170) * 3)

def render(ctx, t, dt, frame, params, state):
    heat = state["heat"]
    cooling = int(params.get("cooling", 3))
    sparks = int(params.get("sparks", 85))
    for x in range(ctx.width):
        heat[ctx.height - 1][x] = 255 if random.randrange(100) < sparks else random.randrange(60, 160)
    for y in range(ctx.height - 2, -1, -1):
        below = heat[y + 1]
        for x in range(ctx.width):
            left = below[(x - 1) % ctx.width]
            center = below[x]
            right = below[(x + 1) % ctx.width]
            heat[y][x] = max(0, ((left + center + right) // 3) - random.randrange(cooling + 1))
    for y in range(ctx.height):
        for x in range(ctx.width):
            frame.set_pixel(x, y, *palette(heat[y][x]))
'''.strip(),
    },
    {
        "slug": 'rainbow-swirl',
        "title": 'Rainbow Swirl',
        "description": 'A rotating HSV swirl converted into RGB without external libraries.',
        "default_fps": 30,
        "code": r'''
import math

NAME = "Rainbow Swirl"
DEFAULT_FPS = 30
PARAMS = {
    "speed": {"type": "float", "default": 0.75, "min": 0.1, "max": 3.0, "step": 0.05},
    "twist": {"type": "float", "default": 2.0, "min": 0.1, "max": 8.0, "step": 0.1},
}

def hsv_to_rgb(h, s, v):
    h = h % 1.0
    i = int(h * 6)
    f = h * 6 - i
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)
    i %= 6
    if i == 0: r, g, b = v, t, p
    elif i == 1: r, g, b = q, v, p
    elif i == 2: r, g, b = p, v, t
    elif i == 3: r, g, b = p, q, v
    elif i == 4: r, g, b = t, p, v
    else: r, g, b = v, p, q
    return int(r * 255), int(g * 255), int(b * 255)

def render(ctx, t, dt, frame, params):
    speed = float(params.get("speed", 0.75))
    twist = float(params.get("twist", 2.0))
    cx = (ctx.width - 1) / 2
    cy = (ctx.height - 1) / 2
    for y in range(ctx.height):
        for x in range(ctx.width):
            dx = x - cx
            dy = y - cy
            angle = math.atan2(dy, dx) / (math.pi * 2)
            dist = math.sqrt(dx * dx + dy * dy) / max(1, cx)
            hue = angle + dist * twist * 0.12 + t * speed * 0.12
            r, g, b = hsv_to_rgb(hue, 1.0, 1.0)
            frame.set_pixel(x, y, r, g, b)
'''.strip(),
    },
    {
        "slug": 'bouncing-balls',
        "title": 'Bouncing Balls',
        "description": 'Colorful bouncing balls with a slight frame fade.',
        "default_fps": 30,
        "code": r'''
import random

NAME = "Bouncing Balls"
DEFAULT_FPS = 30
PARAMS = {
    "count": {"type": "int", "default": 9, "min": 1, "max": 30, "step": 1},
    "radius": {"type": "int", "default": 3, "min": 1, "max": 8, "step": 1},
}

def setup(ctx):
    balls = []
    colors = [(255, 64, 64), (64, 255, 96), (64, 160, 255), (255, 240, 64), (255, 64, 255), (64, 255, 255)]
    for i in range(30):
        balls.append({
            "x": random.uniform(4, ctx.width - 5),
            "y": random.uniform(4, ctx.height - 5),
            "vx": random.choice([-1, 1]) * random.uniform(10, 28),
            "vy": random.choice([-1, 1]) * random.uniform(10, 28),
            "color": colors[i % len(colors)],
        })
    return {"balls": balls}

def render(ctx, t, dt, frame, params, state):
    frame.fill(0, 0, 0)
    count = int(params.get("count", 9))
    radius = int(params.get("radius", 3))
    for ball in state["balls"][:count]:
        ball["x"] += ball["vx"] * dt
        ball["y"] += ball["vy"] * dt
        if ball["x"] < radius or ball["x"] > ctx.width - 1 - radius:
            ball["vx"] *= -1
            ball["x"] = max(radius, min(ctx.width - 1 - radius, ball["x"]))
        if ball["y"] < radius or ball["y"] > ctx.height - 1 - radius:
            ball["vy"] *= -1
            ball["y"] = max(radius, min(ctx.height - 1 - radius, ball["y"]))
        frame.circle(int(ball["x"]), int(ball["y"]), radius, *ball["color"], fill=True)
'''.strip(),
    },
    {
        "slug": 'conway-life',
        "title": "Conway's Game of Life",
        "description": 'A randomized Conway simulation, recolored by cell age.',
        "default_fps": 12,
        "code": r'''
import random

NAME = "Conway's Game of Life"
DEFAULT_FPS = 12
PARAMS = {
    "density": {"type": "int", "default": 30, "min": 5, "max": 70, "step": 5},
}

def setup(ctx):
    grid = [[1 if random.randrange(100) < 30 else 0 for _ in range(ctx.width)] for _ in range(ctx.height)]
    age = [[0 for _ in range(ctx.width)] for _ in range(ctx.height)]
    return {"grid": grid, "age": age, "last_density": 30}

def render(ctx, t, dt, frame, params, state):
    density = int(params.get("density", 30))
    if density != state.get("last_density"):
        state["grid"] = [[1 if random.randrange(100) < density else 0 for _ in range(ctx.width)] for _ in range(ctx.height)]
        state["age"] = [[0 for _ in range(ctx.width)] for _ in range(ctx.height)]
        state["last_density"] = density
    grid = state["grid"]
    age = state["age"]
    new = [[0 for _ in range(ctx.width)] for _ in range(ctx.height)]
    for y in range(ctx.height):
        for x in range(ctx.width):
            n = 0
            for yy in (-1, 0, 1):
                for xx in (-1, 0, 1):
                    if xx == 0 and yy == 0:
                        continue
                    n += grid[(y + yy) % ctx.height][(x + xx) % ctx.width]
            new[y][x] = 1 if n == 3 or (grid[y][x] and n == 2) else 0
    frame.fill(0, 0, 0)
    for y in range(ctx.height):
        for x in range(ctx.width):
            grid[y][x] = new[y][x]
            if new[y][x]:
                age[y][x] = min(255, age[y][x] + 20)
                frame.set_pixel(x, y, 40, age[y][x], 255 - age[y][x] // 2)
            else:
                age[y][x] = max(0, age[y][x] - 30)
'''.strip(),
    },
    {
        "slug": 'current-weather',
        "title": 'Clock Weather',
        "description": 'Clock, date, animated weather icon, location label, precipitation chance, and 24-hour temperature trend using Open-Meteo.',
        "default_fps": 12,
        "code": r'''
import datetime
import json
import math
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

NAME = "Clock Weather"
DEFAULT_FPS = 12

# ----- EDIT THESE -----
# Leave ZIP_CODE blank to use approximate public-IP location.
# Enter a ZIP like "23434" to pin weather/time to that location.
ZIP_CODE = ""
COUNTRY_CODE = "US"
USE_24_HOUR_TIME = False
REFRESH_MINUTES = 20
TEMP_UNIT = "fahrenheit"     # "fahrenheit" or "celsius"
WIND_UNIT = "mph"            # "mph", "kmh", "ms", or "kn"
SHOW_CITY = True
# ----------------------

PARAMS = {
    "refresh_minutes": {"type": "int", "default": REFRESH_MINUTES, "min": 5, "max": 180, "step": 5},
}

FONT3 = {
    " ": ["000", "000", "000", "000", "000"],
    "0": ["111", "101", "101", "101", "111"],
    "1": ["010", "110", "010", "010", "111"],
    "2": ["111", "001", "111", "100", "111"],
    "3": ["111", "001", "111", "001", "111"],
    "4": ["101", "101", "111", "001", "001"],
    "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"],
    "7": ["111", "001", "010", "010", "010"],
    "8": ["111", "101", "111", "101", "111"],
    "9": ["111", "101", "111", "001", "111"],
    ":": ["000", "010", "000", "010", "000"],
    "/": ["001", "001", "010", "100", "100"],
    "-": ["000", "000", "111", "000", "000"],
    "%": ["101", "001", "010", "100", "101"],
    ".": ["000", "000", "000", "000", "010"],
    "?": ["111", "001", "011", "000", "010"],
    "A": ["010", "101", "111", "101", "101"],
    "B": ["110", "101", "110", "101", "110"],
    "C": ["111", "100", "100", "100", "111"],
    "D": ["110", "101", "101", "101", "110"],
    "E": ["111", "100", "110", "100", "111"],
    "F": ["111", "100", "110", "100", "100"],
    "G": ["111", "100", "101", "101", "111"],
    "H": ["101", "101", "111", "101", "101"],
    "I": ["111", "010", "010", "010", "111"],
    "J": ["001", "001", "001", "101", "111"],
    "K": ["101", "101", "110", "101", "101"],
    "L": ["100", "100", "100", "100", "111"],
    "M": ["101", "111", "111", "101", "101"],
    "N": ["101", "111", "111", "111", "101"],
    "O": ["111", "101", "101", "101", "111"],
    "P": ["111", "101", "111", "100", "100"],
    "Q": ["111", "101", "101", "111", "001"],
    "R": ["110", "101", "110", "101", "101"],
    "S": ["111", "100", "111", "001", "111"],
    "T": ["111", "010", "010", "010", "010"],
    "U": ["101", "101", "101", "101", "111"],
    "V": ["101", "101", "101", "101", "010"],
    "W": ["101", "101", "111", "111", "101"],
    "X": ["101", "101", "010", "101", "101"],
    "Y": ["101", "101", "010", "010", "010"],
    "Z": ["111", "001", "010", "100", "111"],
}

FONT5 = {
    " ": ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
    "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
    ":": ["00000", "00100", "00100", "00000", "00100", "00100", "00000"],
}

WMO_KIND = {
    0: "SUN", 1: "SUN", 2: "PART", 3: "CLOUD",
    45: "FOG", 48: "FOG",
    51: "RAIN", 53: "RAIN", 55: "RAIN", 56: "MIX", 57: "MIX",
    61: "RAIN", 63: "RAIN", 65: "RAIN", 66: "MIX", 67: "MIX",
    71: "SNOW", 73: "SNOW", 75: "SNOW", 77: "SNOW",
    80: "RAIN", 81: "RAIN", 82: "RAIN",
    85: "SNOW", 86: "SNOW",
    95: "STORM", 96: "STORM", 99: "STORM",
}

WMO_TEXT = {
    0: "CLEAR", 1: "MOSTLY CLEAR", 2: "PARTLY CLOUDY", 3: "CLOUDY",
    45: "FOG", 48: "FOG", 51: "DRIZZLE", 53: "DRIZZLE", 55: "DRIZZLE",
    61: "RAIN", 63: "RAIN", 65: "HEAVY RAIN", 71: "SNOW", 73: "SNOW",
    75: "HEAVY SNOW", 80: "SHOWERS", 81: "SHOWERS", 82: "HEAVY SHOWERS",
    95: "STORM", 96: "STORM", 99: "STORM",
}


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def http_json(url, timeout=5):
    req = urllib.request.Request(url, headers={"User-Agent": "MatrixArt-ClockWeather/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def locate_by_ip():
    fields = "status,message,city,regionName,zip,lat,lon,timezone"
    url = "http://ip-api.com/json/?" + urllib.parse.urlencode({"fields": fields})
    data = http_json(url, timeout=4)
    if data.get("status") != "success":
        raise RuntimeError(data.get("message", "IP location failed"))
    return {
        "lat": float(data["lat"]),
        "lon": float(data["lon"]),
        "timezone": data.get("timezone") or "UTC",
        "label": (data.get("city") or data.get("zip") or "LOCAL").upper()[:16],
    }


def locate_by_zip(zip_code, country_code):
    query = urllib.parse.urlencode({
        "name": str(zip_code).strip(),
        "count": 1,
        "language": "en",
        "format": "json",
        "countryCode": str(country_code or "US").upper(),
    })
    data = http_json("https://geocoding-api.open-meteo.com/v1/search?" + query, timeout=5)
    results = data.get("results") or []
    if not results:
        raise RuntimeError("ZIP not found")
    hit = results[0]
    label = hit.get("name") or str(zip_code)
    admin = hit.get("admin1") or ""
    if admin:
        label = label + " " + admin
    return {
        "lat": float(hit["latitude"]),
        "lon": float(hit["longitude"]),
        "timezone": hit.get("timezone") or "UTC",
        "label": label.upper()[:16],
    }


def fetch_weather(location):
    current = "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,is_day,wind_speed_10m"
    daily = "temperature_2m_max,temperature_2m_min,precipitation_probability_max"
    hourly = "temperature_2m,precipitation_probability"
    query = urllib.parse.urlencode({
        "latitude": location["lat"],
        "longitude": location["lon"],
        "current": current,
        "daily": daily,
        "hourly": hourly,
        "forecast_days": 2,
        "timezone": "auto",
        "temperature_unit": TEMP_UNIT,
        "wind_speed_unit": WIND_UNIT,
        "precipitation_unit": "inch",
    })
    data = http_json("https://api.open-meteo.com/v1/forecast?" + query, timeout=6)
    cur = data.get("current", {})
    day = data.get("daily", {})
    hourly_data = data.get("hourly", {})
    temps = [float(x) for x in (hourly_data.get("temperature_2m") or [])[:24] if x is not None]
    pops = [int(x) for x in (hourly_data.get("precipitation_probability") or [])[:24] if x is not None]
    code = int(cur.get("weather_code", -1))
    return {
        "ok": True,
        "error": "",
        "temp": round(float(cur.get("temperature_2m", 0))),
        "feels": round(float(cur.get("apparent_temperature", 0))),
        "humidity": int(cur.get("relative_humidity_2m", 0)),
        "wind": round(float(cur.get("wind_speed_10m", 0))),
        "code": code,
        "kind": WMO_KIND.get(code, "CLOUD"),
        "text": WMO_TEXT.get(code, "WEATHER"),
        "is_day": int(cur.get("is_day", 1)),
        "high": round(float((day.get("temperature_2m_max") or [cur.get("temperature_2m", 0)])[0])),
        "low": round(float((day.get("temperature_2m_min") or [cur.get("temperature_2m", 0)])[0])),
        "rain": int((day.get("precipitation_probability_max") or [max(pops) if pops else 0])[0]),
        "hourly_temps": temps,
        "hourly_rain": pops,
        "timezone": data.get("timezone") or location.get("timezone") or "UTC",
        "label": location.get("label", "LOCAL"),
        "fetched_at": time.time(),
    }


def draw_text(frame, text, x, y, r, g, b, scale=1, font=FONT3, spacing=1):
    cursor = int(x)
    for ch in str(text).upper():
        glyph = font.get(ch, font.get("?", FONT3["?"]))
        for gy, row in enumerate(glyph):
            for gx, bit in enumerate(row):
                if bit == "1":
                    frame.rect(cursor + gx * scale, y + gy * scale, scale, scale, r, g, b, fill=True)
        cursor += (len(glyph[0]) + spacing) * scale
    return cursor


def text_width(text, scale=1, font=FONT3, spacing=1):
    if not text:
        return 0
    first = next(iter(font.values()))
    return len(str(text)) * (len(first[0]) + spacing) * scale - spacing * scale


def centered_text(frame, text, y, r, g, b, scale=1, font=FONT3):
    x = (64 - text_width(text, scale=scale, font=font)) // 2
    draw_text(frame, text, x, y, r, g, b, scale=scale, font=font)


def draw_degree(frame, x, y):
    frame.set_pixel(x + 1, y, 255, 255, 255)
    frame.set_pixel(x, y + 1, 255, 255, 255)
    frame.set_pixel(x + 2, y + 1, 255, 255, 255)
    frame.set_pixel(x + 1, y + 2, 255, 255, 255)


def draw_sun(frame, cx, cy, t):
    frame.circle(cx, cy, 6, 255, 185, 25, fill=True)
    for i in range(8):
        a = t * 0.45 + i * math.pi / 4
        frame.line(
            int(cx + math.cos(a) * 9),
            int(cy + math.sin(a) * 9),
            int(cx + math.cos(a) * 12),
            int(cy + math.sin(a) * 12),
            255,
            145,
            20,
        )


def draw_cloud(frame, x, y, r=120, g=135, b=160):
    frame.circle(x + 7, y + 7, 6, r, g, b, fill=True)
    frame.circle(x + 16, y + 5, 8, r + 12, g + 12, b + 12, fill=True)
    frame.circle(x + 25, y + 8, 6, r, g, b, fill=True)
    frame.rect(x + 5, y + 10, 25, 7, r, g, b, fill=True)


def draw_weather_icon(frame, kind, is_day, t):
    if kind == "SUN":
        draw_sun(frame, 13, 38, t)
    elif kind == "PART":
        draw_sun(frame, 9, 35, t)
        draw_cloud(frame, 5, 35, 105, 125, 150)
    elif kind == "RAIN":
        draw_cloud(frame, 1, 29, 100, 120, 155)
        for i in range(5):
            x = 5 + i * 5
            y = 45 + int((t * 18 + i * 4) % 9)
            frame.line(x, y, x - 2, y + 5, 50, 160, 255)
    elif kind == "SNOW":
        draw_cloud(frame, 1, 29, 115, 130, 155)
        for i in range(9):
            frame.set_pixel((5 + i * 5 + int(t * 3)) % 31, 45 + int((i * 7 + t * 8) % 12), 200, 230, 255)
    elif kind == "STORM":
        draw_cloud(frame, 1, 29, 80, 85, 120)
        frame.line(15, 45, 10, 55, 255, 235, 30)
        frame.line(10, 55, 20, 51, 255, 235, 30)
        frame.line(20, 51, 14, 63, 255, 235, 30)
    elif kind == "FOG":
        draw_cloud(frame, 1, 28, 120, 125, 135)
        for y in (47, 51, 55):
            frame.line(3, y, 29, y, 160, 170, 180)
    elif kind == "MIX":
        draw_cloud(frame, 1, 29, 115, 125, 150)
        for i in range(4):
            frame.line(6 + i * 6, 46, 4 + i * 6, 52, 80, 160, 255)
        for i in range(4):
            frame.set_pixel(8 + i * 6, 56, 220, 240, 255)
    else:
        draw_cloud(frame, 1, 31, 110, 120, 145)


def draw_temp_graph(frame, weather):
    temps = weather.get("hourly_temps") or []
    if not temps:
        temps = [weather.get("low", 0), weather.get("temp", 0), weather.get("high", 0)]

    lo = min(temps + [weather.get("low", min(temps))])
    hi = max(temps + [weather.get("high", max(temps))])
    if hi == lo:
        hi = lo + 1

    frame.line(7, 61, 56, 61, 35, 45, 60)

    max_points = min(24, len(temps))
    last_x = None
    last_y = None
    for i in range(max_points):
        x = 8 + i * 2
        scaled = (temps[i] - lo) / (hi - lo)
        y = int(60 - scaled * 9)
        if last_x is not None:
            frame.line(last_x, last_y, x, y, 0, 230, 150)
        frame.set_pixel(x, y, 0, 255, 160)
        last_x, last_y = x, y

    draw_text(frame, str(int(lo)), 0, 58, 0, 120, 255, scale=1)
    hi_text = str(int(hi))
    draw_text(frame, hi_text, 64 - text_width(hi_text), 58, 255, 130, 0, scale=1)


def setup(ctx):
    return {
        "location": None,
        "weather": {
            "ok": False,
            "error": "LOADING",
            "temp": 0,
            "kind": "CLOUD",
            "text": "LOADING",
            "timezone": "UTC",
            "label": "LOCAL",
        },
        "next_fetch": 0,
        "last_fetch_error": "",
    }


def render(ctx, t, dt, frame, params, state):
    now = time.time()
    refresh = max(300, int(params.get("refresh_minutes", REFRESH_MINUTES)) * 60)

    if now >= state.get("next_fetch", 0):
        try:
            if ZIP_CODE.strip():
                location = locate_by_zip(ZIP_CODE.strip(), COUNTRY_CODE)
            else:
                location = locate_by_ip()

            state["location"] = location
            state["weather"] = fetch_weather(location)
            state["last_fetch_error"] = ""
            state["next_fetch"] = now + refresh
        except Exception as exc:
            state["last_fetch_error"] = str(exc)[:24].upper()
            state["next_fetch"] = now + 60
            if not state.get("weather", {}).get("ok"):
                state["weather"] = {
                    "ok": False,
                    "error": state["last_fetch_error"],
                    "kind": "CLOUD",
                    "text": "NO DATA",
                    "timezone": "UTC",
                    "label": "NO WX",
                }

    weather = state.get("weather", {})
    tz_name = weather.get("timezone") or (state.get("location") or {}).get("timezone") or "UTC"

    try:
        local_now = datetime.datetime.now(ZoneInfo(tz_name))
    except Exception:
        local_now = datetime.datetime.now(datetime.timezone.utc)

    is_day = int(weather.get("is_day", 1))

    if is_day:
        frame.fill(4, 10, 28)
    else:
        frame.fill(0, 2, 10)
        for i in range(18):
            x = (i * 17 + 3) % 64
            y = (i * 29 + 5) % 25
            frame.set_pixel(x, y, 80, 85, 130)

    # Time, AM/PM, date
    if USE_24_HOUR_TIME:
        hour_text = local_now.strftime("%H")
        minute_text = local_now.strftime("%M")
        ampm = ""
    else:
        hour_text = local_now.strftime("%I").lstrip("0")
        minute_text = local_now.strftime("%M")
        ampm = local_now.strftime("%p")

    show_colon = int(t * 2) % 2 != 0

    hour_w = text_width(hour_text, scale=2, font=FONT5, spacing=1)
    colon_w = text_width(":", scale=2, font=FONT5, spacing=1)
    minute_w = text_width(minute_text, scale=2, font=FONT5, spacing=1)

    total_w = hour_w + colon_w + minute_w
    base_x = (64 - total_w) // 2

    hour_x = base_x
    colon_x = base_x + hour_w - 2
    minute_x = base_x + hour_w + colon_w - 4

    draw_text(frame, hour_text, hour_x, 0, 255, 255, 255, scale=2, font=FONT5, spacing=1)

    if show_colon:
        draw_text(frame, ":", colon_x, 0, 255, 255, 255, scale=2, font=FONT5, spacing=1)

    draw_text(frame, minute_text, minute_x, 0, 255, 255, 255, scale=2, font=FONT5, spacing=1)

    if ampm:
        ampm_w = text_width(ampm, scale=1, font=FONT3, spacing=1)
        draw_text(frame, ampm, 64 - ampm_w, 3, 180, 190, 210, scale=1, font=FONT3, spacing=1)

    try:
        date_text = local_now.strftime("%a %b %-d")
    except Exception:
        date_text = local_now.strftime("%a %b %d").replace(" 0", " ")

    centered_text(frame, date_text.upper()[:16], 16, 180, 210, 255, scale=1)

    # Weather icon and middle text area.
    kind = weather.get("kind", "CLOUD")
    draw_weather_icon(frame, kind, is_day, t)

    if weather.get("ok"):
        temp = str(int(weather.get("temp", 0)))
        temp_x = 33
        draw_text(frame, temp, temp_x, 29, 255, 255, 255, scale=2, font=FONT3, spacing=1)

        deg_x = temp_x + text_width(temp, scale=2, font=FONT3, spacing=1) + 1
        draw_degree(frame, deg_x, 29)

        unit = "F" if TEMP_UNIT == "fahrenheit" else "C"

        # Degree symbol occupies deg_x through deg_x + 2.
        # Unit starts one pixel to the right of the symbol.
        unit_x = deg_x + 4
        draw_text(frame, unit, unit_x, 34, 255, 255, 255, scale=1)

        rain = str(int(weather.get("rain", 0)))
        draw_text(frame, rain + "%", 45, 44, 80, 170, 255, scale=1)

        words = (weather.get("text", "WEATHER") + " " + (weather.get("label", "") if SHOW_CITY else "")).split()
        if words:
            word = words[int(local_now.second) % len(words)]
            centered_text(frame, word[:10], 23, 220, 225, 235, scale=1)

        draw_temp_graph(frame, weather)
    else:
        centered_text(frame, "WEATHER", 28, 255, 90, 90, scale=1)
        centered_text(frame, "WAIT", 37, 255, 190, 60, scale=2)
        err = weather.get("error") or state.get("last_fetch_error") or "NO DATA"
        centered_text(frame, str(err)[:10], 54, 255, 90, 90, scale=1)
'''.strip(),
    },
]


def ensure_builtin_demos(db) -> dict[str, int]:
    inserted = 0
    updated = 0
    for demo in BUILTIN_DEMOS:
        if hasattr(db, "is_builtin_demo_deleted") and db.is_builtin_demo_deleted(demo["slug"]):
            continue
        if hasattr(db, "is_builtin_demo_customized") and db.is_builtin_demo_customized(demo["slug"]):
            continue
        result = db.upsert_demo(
            slug=demo["slug"],
            title=demo["title"],
            description=demo["description"],
            code=demo["code"],
            default_fps=int(demo["default_fps"]),
            builtin=True,
        )
        if result == "inserted":
            inserted += 1
        else:
            updated += 1
    return {"inserted": inserted, "updated": updated}

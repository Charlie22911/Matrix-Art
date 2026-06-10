# Code Help Page

The Code Help page documents how to write Python effects for the 64×64 RGB matrix.

Code effects can be simple learning exercises, small animations, or advanced procedural artwork. Beginners can start by changing numbers in the examples below. Experienced users can use the API reference to build custom effects more quickly.

## How Matrix-Art runs code

A Code item is a Python script. Matrix-Art runs that script in a separate effect process, calls its `render()` function repeatedly, and sends each generated frame to the panel.

The display is 64 pixels wide and 64 pixels tall. Pixel coordinates start at the top-left corner:

```text
(0, 0)                  (63, 0)
  +------------------------+
  |                        |
  |                        |
  |                        |
  +------------------------+
(0, 63)                (63, 63)
```

RGB color values are usually 0 to 255:

```python
red = (255, 0, 0)
green = (0, 255, 0)
blue = (0, 0, 255)
white = (255, 255, 255)
black = (0, 0, 0)
```

Values outside 0 to 255 are clamped automatically.

## Minimum effect

A Code effect needs a `render()` function.

```python
def render(ctx, t, dt, frame, params):
    frame.fill(0, 0, 0)
    frame.set_pixel(32, 32, 255, 0, 0)
```

This clears the panel to black, then lights one red pixel near the center.

## Function arguments

`render()` receives these values:

```python
def render(ctx, t, dt, frame, params):
    ...
```

It may also accept persistent state returned by `setup()`:

```python
def render(ctx, t, dt, frame, params, state):
    ...
```

### ctx

`ctx` is a context object with display and timing values.

Common values:

- `ctx.width`: display width, normally `64`
- `ctx.height`: display height, normally `64`
- `ctx.fps`: target FPS for this Code item
- `ctx.frame_index`: frame counter starting at `0`
- `ctx.time`: seconds since the effect started
- `ctx.dt`: seconds since the previous rendered frame

### t

`t` is seconds since the effect started. This is useful for animation based on time.

```python
x = int((t * 10) % ctx.width)
```

### dt

`dt` is seconds since the previous rendered frame. Use it when motion should keep the same speed even if FPS changes.

```python
state["x"] += 20 * dt
```

That moves about 20 pixels per second.

### frame

`frame` is the 64×64 drawing buffer. Draw into it with helpers such as `set_pixel()`, `line()`, `rect()`, and `circle()`.

### params

`params` is a dictionary of default parameter values declared in `PARAMS`.

### state

`state` is optional persistent storage returned by `setup()`. Use it for values that need to survive between frames.

## Optional setup function

Use `setup()` to create persistent effect state.

```python
def setup(ctx):
    return {"x": 0, "direction": 1}


def render(ctx, t, dt, frame, params, state):
    state["x"] += state["direction"]

    if state["x"] <= 0 or state["x"] >= ctx.width - 1:
        state["direction"] *= -1

    frame.fill(0, 0, 0)
    frame.set_pixel(state["x"], 32, 0, 255, 80)
```

This makes a green pixel bounce left and right.

## Drawing helpers

Available frame helpers:

```python
frame.fill(r, g, b)
frame.clear()
frame.set_pixel(x, y, r, g, b)
frame.get_pixel(x, y)
frame.fade(amount)
frame.line(x0, y0, x1, y1, r, g, b)
frame.rect(x, y, w, h, r, g, b, fill=False)
frame.circle(cx, cy, radius, r, g, b, fill=False)
```

### Fill the background

```python
def render(ctx, t, dt, frame, params):
    frame.fill(4, 8, 20)
```

### Draw pixels

```python
def render(ctx, t, dt, frame, params):
    frame.clear()
    frame.set_pixel(10, 10, 255, 0, 0)
    frame.set_pixel(11, 10, 0, 255, 0)
    frame.set_pixel(12, 10, 0, 0, 255)
```

### Draw lines and shapes

```python
def render(ctx, t, dt, frame, params):
    frame.clear()
    frame.line(0, 0, 63, 63, 255, 255, 255)
    frame.rect(6, 6, 20, 14, 255, 80, 0, fill=False)
    frame.circle(46, 32, 10, 80, 180, 255, fill=True)
```

### Fade the previous frame data inside one frame

`frame.fade()` fades whatever is already in the current frame buffer. Each render starts with a new blank frame, so `fade()` is most useful after drawing or when combined with state-driven redraw patterns.

```python
def render(ctx, t, dt, frame, params):
    frame.fill(60, 20, 0)
    frame.fade(0.5)
```

## Beginner examples

### Moving dot using time

This example uses `t`, so the dot moves smoothly even if the frame rate changes.

```python
def render(ctx, t, dt, frame, params):
    frame.clear()

    x = int((t * 18) % ctx.width)
    y = 32

    frame.set_pixel(x, y, 255, 120, 0)
```

Change `18` to make the dot faster or slower.

### Sine wave

This example uses the `math` module.

```python
import math


def render(ctx, t, dt, frame, params):
    frame.clear()

    for x in range(ctx.width):
        y = int(32 + math.sin(x * 0.25 + t * 4) * 12)
        frame.set_pixel(x, y, 0, 200, 255)
```

Change `12` to adjust the wave height. Change `t * 4` to adjust the animation speed.

### Bouncing ball with state

This example uses `setup()` because the ball has position and velocity.

```python
def setup(ctx):
    return {
        "x": 12.0,
        "y": 16.0,
        "vx": 22.0,
        "vy": 15.0,
    }


def render(ctx, t, dt, frame, params, state):
    state["x"] += state["vx"] * dt
    state["y"] += state["vy"] * dt

    if state["x"] < 2 or state["x"] > ctx.width - 3:
        state["vx"] *= -1
    if state["y"] < 2 or state["y"] > ctx.height - 3:
        state["vy"] *= -1

    frame.clear()
    frame.circle(int(state["x"]), int(state["y"]), 2, 255, 80, 160, fill=True)
```

### Random stars

This example creates random star positions once, then twinkles them over time.

```python
import random


def setup(ctx):
    stars = []
    for i in range(40):
        stars.append({
            "x": random.randrange(ctx.width),
            "y": random.randrange(ctx.height),
            "phase": random.random() * 6.28,
        })
    return {"stars": stars}


def render(ctx, t, dt, frame, params, state):
    frame.fill(0, 0, 8)

    for star in state["stars"]:
        brightness = int(120 + 100 * random.random())
        frame.set_pixel(star["x"], star["y"], brightness, brightness, 255)
```

## Parameters

Effects can define `PARAMS`.

```python
PARAMS = {
    "speed": {"type": "float", "default": 1.0, "min": 0.1, "max": 4.0, "step": 0.1},
    "count": {"type": "int", "default": 12, "min": 1, "max": 50, "step": 1},
}
```

Matrix-Art currently uses default values. The format is designed so UI controls can be added later without changing the effect format.

Example using parameter defaults:

```python
PARAMS = {
    "speed": {"type": "float", "default": 20.0, "min": 1.0, "max": 80.0, "step": 1.0},
    "red": {"type": "int", "default": 255, "min": 0, "max": 255, "step": 1},
}


def render(ctx, t, dt, frame, params):
    speed = params.get("speed", 20.0)
    red = params.get("red", 255)

    x = int((t * speed) % ctx.width)

    frame.clear()
    frame.set_pixel(x, 32, red, 80, 20)
```

## Common Python patterns

### Loops

Loops are useful for drawing repeated shapes.

```python
def render(ctx, t, dt, frame, params):
    frame.clear()

    for x in range(0, ctx.width, 4):
        frame.line(x, 0, x, ctx.height - 1, 30, 30, 80)
```

### If statements

Use `if` statements to change behavior.

```python
def render(ctx, t, dt, frame, params):
    frame.clear()

    if int(t) % 2 == 0:
        frame.fill(40, 0, 0)
    else:
        frame.fill(0, 0, 40)
```

### Lists and dictionaries

Lists store multiple things. Dictionaries store named values.

```python
def setup(ctx):
    return {
        "points": [
            {"x": 8, "y": 8},
            {"x": 20, "y": 18},
            {"x": 44, "y": 40},
        ]
    }


def render(ctx, t, dt, frame, params, state):
    frame.clear()

    for point in state["points"]:
        frame.circle(point["x"], point["y"], 2, 0, 255, 120, fill=True)
```

## Advanced notes

- Code runs in a separate process from the web UI.
- Each frame starts with a fresh blank buffer.
- The runner drops old frames if the effect generates frames faster than the display worker can use them.
- Long blocking work inside `render()` will cause stutter.
- Network calls should be done rarely and cached in `state`. The built-in weather example shows this pattern.
- Keep file and system access limited. Code effects are regular Python and run locally on the Pi.

## Testing and debugging

Use **Check** to validate syntax without starting the effect.

Use **Run Editor** to test unsaved changes.

Use **Save** to store changes and regenerate the Library thumbnail.

Use **Use Current Display as Thumbnail** when startup frames are blank or unrepresentative.

When something fails, the Code page shows the current error. Common issues:

- Missing colon after `def`, `if`, `for`, or `while`
- Mismatched parentheses, brackets, or quotes
- Typo in a function name, such as `setpixel` instead of `set_pixel`
- Using a variable before assigning it
- Indentation that mixes tabs and spaces

## Practical tips

- Start from a small working example, then change one thing at a time.
- Keep full-screen loops simple. The panel has 4,096 pixels.
- Use `dt` for movement math.
- Use `setup()` for particles, balls, grids, random seeds, or cached network data.
- Keep imports simple. Built-in modules like `math`, `random`, and `time` are good choices.
- Lower the FPS if an effect is too heavy.

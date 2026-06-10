# Code Help Page

The Code Help page documents how to write Python effects for the 64×64 RGB matrix.

## Minimum effect

A Code effect needs a `render()` function.

```python
def render(ctx, t, dt, frame, params):
    frame.fill(0, 0, 0)
    frame.set_pixel(32, 32, 255, 0, 0)
```

Matrix-Art calls `render()` repeatedly and sends each generated frame to the panel.

## Function arguments

### ctx

Context object with display and timing values.

Common values:

- `ctx.width`
- `ctx.height`
- `ctx.fps`
- `ctx.frame_index`
- `ctx.time`
- `ctx.dt`

### t

Seconds since the effect started.

### dt

Seconds since the previous rendered frame.

Use `dt` to make motion speed independent of FPS.

### frame

The 64×64 drawing buffer.

### params

Dictionary of default parameter values declared in `PARAMS`.

### state

Optional persistent state returned by `setup()`.

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

## Frame helpers

Available drawing helpers:

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

RGB values are normally 0 to 255.

## Parameters

Effects can define `PARAMS`.

```python
PARAMS = {
    "speed": {"type": "float", "default": 1.0, "min": 0.1, "max": 4.0, "step": 0.1},
    "count": {"type": "int", "default": 12, "min": 1, "max": 50, "step": 1},
}
```

Matrix-Art currently uses default values. The format is designed so slider controls can be added later.

## Practical tips

- Keep full-screen loops simple. The panel has 4,096 pixels.
- Prefer `dt` for movement math.
- Use `setup()` for stars, particles, balls, grids, random seeds, or network caches.
- Keep imports simple.
- Use Run Editor to test unsaved changes.
- Use Save to store changes and regenerate the Library thumbnail.
- Use Use Current Display as Thumbnail when startup frames are blank or unrepresentative.

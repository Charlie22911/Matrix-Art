# Draw Page

The Draw page is a browser-based 64×64 pixel-art editor. It supports mouse, touch, and stylus input, updates the RGB matrix live while drawing, and saves the exact 64×64 drawing to the Library.

Opening the Draw page pauses slideshow and stops active Code effects so the live drawing preview can own the display.

## Main fields

### Title

Name used when the drawing is saved to the Library.

### Folder

Folder path for the saved drawing. Defaults to `Drawings`.

Existing folders are offered through a datalist. New folder paths can be typed directly.

## Drawing tools

### Color

Chooses the active drawing color.

### Recent colors

Matrix-Art remembers the last eight unique colors used in the browser. Reusing an existing color moves it back to the front of the hotbar. Duplicate colors are not added.

### Brush size

Brush sizes:

- 1 px
- 2 px
- 3 px
- 4 px

### Pencil

Draws with the active color.

### Eraser

Draws transparent/black pixels over existing pixels.

### Fill

Flood-fills a connected area with the active color.

### Undo

Reverts the previous drawing action.

### Clear

Clears the drawing canvas.

## Canvas behavior

The drawing canvas represents a 64×64 grid. It is displayed large in the browser for easier editing.

Input support:

- mouse click and drag
- touch tap and drag
- stylus tap and drag

The panel updates live while drawing.

## Save options

### Enabled in slideshow/library

When checked, the drawing starts enabled and can appear in slideshow rotation.

### Show on panel after save

When checked, the saved drawing remains on the panel after saving.

### Save drawing to library

Saves the exact 64×64 drawing to SQLite as `kind = drawing`.

When saving, the matrix briefly flashes like a camera flash and then restores the drawing. The flash respects the current matrix brightness.

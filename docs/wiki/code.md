# Code Page

The Code page is a browser-based Python effect editor and runner. It provides an editor for visual effects that generate live 64×64 RGB frames, similar to demoscene-style effects.

Due to the potential for misuse, the Code page can be disabled from Settings. When disabled, the Code navigation link is hidden and `/code` is blocked.
Code previously saved in the Library will remain available for display unless deleted.

## Runtime model

A Code item is Python source stored in SQLite. When run, Matrix-Art starts a separate effect runner process, renders frames, and sends those frames to the display worker.

Code effects can also appear in the normal Library as `kind = code`. From the Library, Code items can be:

- shown manually
- included in slideshow rotation
- enabled or disabled
- renamed
- moved to folders
- moved to Trash
- recovered
- destroyed

## Top status panel

The Code page shows:

- whether a Code effect is running
- current FPS target
- frames rendered
- total Code items
- current panel preview
- active Code status or error

## Run Code / Stop Code

This is a toggle button.

- Run Code starts the selected saved Code item.
- Stop Code stops the active Code runner.

Running Code pauses slideshow.

## Help

Opens the Code Help page. It includes the effect API reference, beginner examples, common Python patterns, testing notes, and advanced render paths such as direct RGB buffer rendering with NumPy.

## Back to Library

Returns to the Library page.

## Code list

The left panel lists saved Code items.

Each row shows:

- title
- default FPS
- built-in marker, when applicable

Click a Code item to load it into the editor.

## New

Creates a new custom Code item template in the editor.

## Editor fields

### Title

Name of the Code item. Saving updates both the Code entry and its linked Library item.

### FPS

Target frame rate for this Code item.

Actual achievable FPS depends on effect complexity, Python speed, matrix driver timing, and system load.

### Enabled

Controls whether the Code item participates in normal Library/slideshow behavior.

### Description

Short text description stored with the Code item.

### Python code

Main editor area for the effect source.

Keyboard helpers:

- Tab inserts spaces.
- Ctrl+S saves.
- Ctrl+Enter runs the editor version.

## Editor actions

### Check

Runs Python syntax validation without starting the effect.

### Run Editor

Runs the current editor contents without requiring a save first. This is useful for testing drafts.

### Save

Saves the current editor contents into the selected Code item. Saving updates the linked Library item and regenerates its default thumbnail from frame 10.

### Use Current Display as Thumbnail

Saves the current matrix frame as the Code item’s Library thumbnail.

Use this when frame 10 is not representative, or when the effect needs runtime setup/weather/network data before a useful image appears.

### Save as copy

Creates a separate editable copy of the current Code item.

### Delete

Moves the linked Library Code item to Trash. From Trash it can be recovered or permanently destroyed.

## Built-in Code items

Built-in examples are stored in SQLite on startup. They can be edited in place. Once edited, they are marked customized so startup refresh does not overwrite customized code.

Save as copy preserves the built-in version and creates a separate custom version.


## Advanced render paths

Simple effects should use the drawing helpers such as `frame.set_pixel()`, `frame.line()`, `frame.rect()`, and `frame.circle()`.

Effects that calculate most or all pixels every frame can use the full-frame APIs documented in Code Help:

- `frame.set_rgb_bytes(data)` for packed RGB byte output
- `frame.set_rgb_array(array)` for finished NumPy-style RGB arrays
- `frame.rgb_buffer()` for direct byte-level writes into the current frame
- `frame.rgb_array()` for direct NumPy writes into the current frame

The direct-buffer path is intended for advanced procedural effects such as plasma, fire, particle fields, noise, and simulation-style output. It avoids thousands of Python `set_pixel()` calls per frame.

## Code thumbnails

Code thumbnails are normally generated from frame 10 at save time.

If a Code effect needs runtime setup before a useful frame appears, run it, wait for a good frame, then click Use Current Display as Thumbnail.

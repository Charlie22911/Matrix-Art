# Upload Page

The Upload page imports still images and animated GIFs from a browser, lets users scale or stretch them, previews the 64×64 result, and saves the panel-ready result into SQLite.

## Supported browser input

The file picker accepts:

- PNG
- JPEG
- WebP
- BMP
- animated GIF

Still images are previewed in the browser and also processed by the Pi before panel preview or save. This keeps resampling behavior consistent across desktop and mobile browsers. The original still image file is not stored.

GIFs are processed by the Pi using the same scale, position, resampling, background, and animation settings shown in the browser preview. The original GIF file is not stored.

## Main fields

### Image or animated GIF

Select a source file from a phone, tablet, or PC.

### Title

Name saved into the Library.

### Folder

Folder path for the saved item. Defaults to `Uploads`. Existing folders are offered through a datalist. New paths can be typed directly.

Examples:

```text
Uploads
Uploads/Favorites
Animations/Weather
```

## Transform controls

These controls affect still images and GIFs.

### Mode

The Upload page has two modes:

- Scale: preserves the source image aspect ratio. Users can fit the whole image, fill the full panel, zoom further, and drag the highlighted source selection area when it is smaller than the image.
- Stretch: forces the source into 64×64 without preserving aspect ratio.

The default mode is controlled by `config.toml` under `[image] scale_mode`. Older values such as `fit`, `fill`, and `crop` open as Scale mode. The shipped default is `fit`, which starts Scale mode at the Fit position so non-square images are fully visible with padding.

### Resampling

- Nearest/pixel: crisp pixel-art scaling.
- Smooth: smoother photo-like scaling.
- Bicubic: smoother scaling with more interpolation.
- Bilinear: lighter interpolation.

For pixel art, use Nearest/pixel. Panel preview and save are processed by the Pi, so resampling does not depend on the phone, tablet, or desktop browser canvas implementation.

### Background

Used for padded areas when Scale mode is zoomed out far enough to leave empty space around the image.

### Zoom

Appears in Scale mode. It adjusts how large the source image is on the 64×64 panel.

The minimum zoom is Fit, which keeps the entire source image visible. The maximum zoom is intentionally limited to a practical range so users can crop into an image without accidentally creating extreme transforms. The zoom label shows the zoom relative to Fit and the current source-to-LED pixel ratio.

### Fit

Appears in Scale mode. It shows the entire source image and pads the remaining area with the selected background color.

### Fill

Appears in Scale mode. It scales the image until the whole 64×64 panel is covered. Non-square images are cropped at the edges, and the highlighted source selection area can be dragged to choose the visible area.

### Pixel snap

Appears in Scale mode. It snaps both zoom and position to the source-pixel grid. This is useful for pixel art and other images where users want source pixels to land cleanly on the 64×64 matrix.

Pixel snap chooses an aligned zoom near the current slider position:

- zoom-in values use whole LED-per-source-pixel scales such as 1 LED per source pixel, 2 LEDs per source pixel, or 3 LEDs per source pixel
- zoom-out values use whole source-pixels-per-LED scales such as 2 source pixels per LED, 3 source pixels per LED, or 4 source pixels per LED

If the full source image is currently visible, Pixel snap prefers the nearest aligned zoom-out value. This helps slightly oversized pixel-art images stay fully visible with background padding instead of snapping inward and cropping. Zoom-out snap is limited so the image does not become impractically small.

The source position is snapped at the same time. When zoomed in, the selected source origin snaps to whole source pixels. When zoomed out, it snaps to whole source-pixel groups. Dragging the highlighted source selection after Pixel snap keeps the selection on the same pixel-aligned grid.

## Source area

The source area shows the original image. In Scale mode, the highlighted rectangle shows which part of the source image contributes to the 64×64 result. Dragging the highlighted rectangle down selects a lower part of the source image, and dragging it right selects a farther-right part of the source image.

On touch devices, drag with a finger. On PC, drag with the mouse.

## 64×64 preview

The preview area shows:

- the 64×64 processed preview
- a large integer-scaled grid preview

The grid overlay represents the physical LED cells. It is drawn at integer scale to avoid interpolation artifacts. Pixel snap uses this same idea for uploads by keeping the source-image pixel grid aligned to the matrix pixel grid.

## GIF animation settings

These appear when an animated GIF is selected.

### Max frames

Maximum number of GIF frames to import.

This prevents large GIFs from creating huge database entries or taking a long time to process.

### Default frame ms

Duration used when a GIF frame does not provide a valid duration.

### Min frame ms

Shortest allowed frame duration. Very small GIF frame times are clamped up to this value.

### Max frame ms

Longest allowed frame duration. Very long GIF frame times are clamped down to this value.

The browser GIF preview, panel preview, and saved GIF all use these values.

## Enabled in slideshow/library

When checked, the item is enabled after saving and can appear in slideshow rotation.

When unchecked, the item is saved but starts disabled.

## Show on panel after save

When checked, the item is displayed immediately after saving.

## Preview on panel

Sends the current still preview or processed GIF preview to the physical matrix without saving it.

For GIFs, this pauses slideshow and starts temporary GIF playback.

## Save to library

Saves the preview into SQLite.

- still image: saves exact 64×64 preview PNG
- GIF: saves processed 64×64 frames and per-frame durations

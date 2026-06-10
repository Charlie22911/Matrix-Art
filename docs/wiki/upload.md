# Upload Page

The Upload page imports still images and animated GIFs from a browser, lets you crop/scale them, previews the 64×64 result, and saves the panel-ready result into SQLite.

Route:

```text
/upload
```

## Supported browser input

The file picker accepts:

- PNG
- JPEG
- WebP
- BMP
- animated GIF

Still images are rendered in the browser to an exact 64×64 PNG preview. That exact preview is saved to the library.

GIFs are processed by the Pi using the same crop, scale, and animation settings shown in the browser preview. The original GIF file is not stored.

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

- Crop square: user-positioned square crop becomes the 64×64 result.
- Fit full image: preserves the full source image and pads the remaining area.
- Fill/crop center: fills the whole 64×64 area while preserving aspect ratio, cropping edges as needed.
- Stretch: forces the source into 64×64 without preserving aspect ratio.

### Resampling

- Nearest/pixel: crisp pixel-art scaling.
- Smooth: smoother photo-like scaling.
- Bicubic: smoother scaling with more interpolation.
- Bilinear: lighter interpolation.

For pixel art, use Nearest/pixel.

### Background

Used for padded areas when using Fit full image.

### Crop zoom

Adjusts how much of the source image fits inside the crop square.

### Fit square

Sets the crop square so the whole image fits.

### Center crop

Centers the crop square.

## Source crop area

The source crop canvas shows the original image and the crop square. Drag the crop square to reposition the selected area.

On touch devices, drag with a finger. On PC, drag with the mouse.

## 64×64 preview

The preview area shows:

- the exact 64×64 browser preview
- a large integer-scaled grid preview

The grid overlay represents the physical LED cells. It is drawn at integer scale to avoid interpolation artifacts.

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

After saving, the item appears in the Library.

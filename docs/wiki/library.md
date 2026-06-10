# Library Page

The Library page is the main control page for Matrix-Art. It shows the current panel output, library contents, display controls, slideshow controls, transition settings, folder filters, and bulk actions.


## Top navigation

The top navigation links to:

- Library
- Upload
- Draw
- Code, when the Code editor is enabled
- Settings

The top-right Current card shows:

- current 64×64 preview frame
- current item title
- active display driver
- priority/timing status text

The Current preview updates when the displayed frame changes, or about once every 4 seconds when animation frames are displayed.

## Status counters

The status panel shows:

- total library items
- enabled library items
- current brightness
- display on/off state
- slideshow on/off state

Library items can be still images, drawings, GIF animations, or Code effects.

## Display controls

### Clear panel

Clears the physical panel and stops active Code output.

### Toggle display

Turns the matrix display output on or off. Turning the display off blanks the panel without deleting the current library item.

### Brightness

Adjusts matrix brightness from 1 to 100. Brightness changes are applied live.

## Slideshow controls

### Previous and Next

Manually steps through the enabled library rotation. These buttons stop active Code output before switching.

### Start/Pause slideshow

Starts or pauses automatic slideshow rotation.

### Shuffle

When enabled, slideshow order is randomized.

### Interval

Number of seconds between slideshow advances. Valid range is 1 to 3600 seconds.

## Transition controls

Transitions apply when switching between library items manually or through slideshow rotation.

Options:

- Transitions on/off
- Effect
- Duration in milliseconds
- FPS
- Smoothing on/off
- Smoothing strength

Available effects:

- none
- fade
- wipe-left
- wipe-right
- wipe-up
- wipe-down
- slide-left
- slide-right
- slide-up
- slide-down
- dissolve
- checkerboard
- random

GIF and Code items continue animating during transitions. The outgoing animation or Code process is stopped only after the transition completes.

## Search and filters

The filter bar includes:

- search box for title or folder text
- enabled filter: All, Enabled, Disabled
- folder dropdown
- New Folder
- Filter
- Reset

The folder dropdown includes:

- All folders
- Unfiled
- user-created folders
- Trash, when selected explicitly

Trash is hidden from normal All folders view. Trash contents appear only when Trash is selected.

## Creating folders

Click New Folder, enter a folder path, and save. Nested folders are supported using slash-separated paths, for example:

```text
Favorites/Weather
Animations/Loops
```

Folder deletion and folder protection are handled from Settings.

## Bulk move

Use Move Image to move multiple items at once.

Workflow:

1. Click Move Image.
2. Choose a destination folder from the dropdown.
3. Tap/click the items to select.
4. Click Move Items to complete the move.
5. Use Cancel to leave selection mode.

## Bulk delete to Trash

Use Delete to move items into Trash.

Workflow:

1. Click Delete.
2. Tap/click items to select.
3. Click Delete again to move selected items to Trash.

Items in Trash do not appear in normal slideshow rotation or All folders view.

## Trash mode

Select Trash from the folder dropdown to enter Trash mode.

Trash mode replaces normal bulk actions with:

- Recover
- Destroy

### Recover

Moves selected Trash items back out of Trash.

### Destroy

Permanently deletes selected Trash items, including their frames and metadata.

Destroy is irreversible.

## Enable All / Disable All

The Enable All / Disable All button affects the currently selected folder view.

- If all visible items are enabled, the button disables them.
- If any visible item is disabled, the button enables them.

Disabled items remain in the library but are skipped by slideshow rotation.

## Item cards

Each item card includes:

- thumbnail
- title
- rename pencil
- kind badge
- frame count, when applicable
- folder path
- folder selector
- Show button
- Enabled/Disabled toggle

### Show

Displays the item immediately on the matrix. For Code items, this starts the associated Code effect. For GIFs, this starts GIF playback.

### Rename

Click the pencil icon next to the title, enter a new name, and save. Empty names are rejected. Renaming a Code item also updates the linked Code title.

### Folder selector

Moves a single item to a different folder. Choose New folder… to create a new folder path during the move.

### Enabled/Disabled toggle

Green means enabled. Red means disabled. Disabled items can still be shown manually but are skipped during slideshow rotation.

# Settings Page

The Settings page contains administrative and system-level controls.

Settings can be protected by a PIN. When locked, Matrix-Art shows the Settings unlock page and blocks Settings-only API actions.

## Settings PIN

The PIN card controls Settings access.

Actions:

- Set PIN
- Change PIN
- Lock Now
- Disable PIN

PINs must be 4 to 12 digits. They are stored as salted PBKDF2-SHA256 hashes in SQLite.

If the PIN is forgotten, set `reset_settings_pin = true` under `[security]` in `config.toml`, then restart the service.

See [Settings PIN](settings-pin.md).

## Database backup

The Database backup card downloads and restores Matrix-Art runtime data.

Backups include:

- artwork records
- stored PNG frames
- uploaded GIF frames
- browser drawings
- folders and folder protection settings
- page text settings
- animation and Code settings
- saved Code effects and demos
- saved Wi-Fi entries stored in the database

Backups exclude the Settings PIN and Flask session secret. A restore keeps the current device PIN instead of importing the PIN from the backup file.

### Download a backup

Open Settings, then click Download backup. The browser downloads a JSON file named like:

```text
matrix-art-backup-20260610-153000Z.json
```

The file is portable between Matrix-Art installs using the same backup format version.

### Restore a backup

Open Settings, choose a Matrix-Art backup JSON file, then click Restore database. Restore replaces the current database contents with the uploaded backup while preserving the current Settings PIN.

During restore, Matrix-Art stops active display playback and reloads the Settings page after the import finishes.

Keep backup files somewhere private if they contain personal artwork, local network names, or saved Wi-Fi entries.

## Page text

The Page text card controls the title and subtitles shown at the top of each web UI page.

Editable fields:

- Site title
- Library subtitle
- Upload subtitle
- Draw subtitle
- Code subtitle
- Settings subtitle

Click Save page text to store changes.

## Folders

The Folders card handles folder administration.

Functions:

- refresh folder list
- protect or unprotect normal folders
- delete unprotected folders

Protected folders cannot be deleted. Trash and Unfiled are always protected system folders.

Deleting a folder moves its contents, including subfolder contents, to Unfiled.

## Code timing

Controls Code effect runtime defaults.

Options:

- Enable Code editor page
- Default code FPS
- Max code FPS

Max FPS of `0` means uncapped, with a safety ceiling of 1000 FPS.

Disabling the Code editor hides the Code navigation link and blocks `/code` and `/code/help`. Existing Code items may still exist in the Library depending on database state, but editing is disabled, and they can still be deleted.

## Animation defaults

Defaults used by the Upload page for GIF processing.

Options:

- Max GIF frames
- Default frame ms
- Min frame ms
- Max frame ms

The Upload page can override these values per upload.

## Diagnostics

Shows system status such as:

- CPU usage
- CPU temperature
- CPU clock
- RAM usage
- network rates and totals
- IP addresses
- detailed status text

Use Refresh to update the diagnostic snapshot.

## Matrix timing

Verifies matrix timing-related setup.

It reports:

- hardware PWM status
- core affinity status
- boot isolation status
- audio module status
- timing details

Use this page after installation or timing changes to confirm the matrix refresh thread is pinned correctly.

See [Matrix Timing](matrix-timing.md).

## Wi-Fi

The Wi-Fi card manages client Wi-Fi and hotspot mode using NetworkManager through `nmcli`.

Functions:

- refresh status
- select interface
- view saved networks
- scan networks
- disconnect selected interface
- connect to Wi-Fi
- save Wi-Fi profile
- connect and save
- start hotspot

See [Wi-Fi and Hotspot](wifi-hotspot.md).

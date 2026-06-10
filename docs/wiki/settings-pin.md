# Settings PIN

Matrix-Art can protect the Settings page behind a numeric PIN.

## What the PIN protects

When locked, Settings-only controls are blocked, including:

- page text changes
- enabling and disabling the Code page
- Code timing settings
- animation defaults
- diagnostics and matrix timing APIs
- folder protection and folder deletion
- Wi-Fi and hotspot controls
- PIN/security changes

The normal Library, Upload, Draw, slideshow, and display controls remain available.

## Set a PIN

1. Open Settings.
2. Find the Settings PIN card.
3. Enter a new PIN.
4. Confirm the new PIN.
5. Click Set PIN.

PIN rules:

- digits only
- 4 to 12 digits

## Lock Settings

Click Lock Now from the Settings PIN card.

The next Settings visit will show the unlock form.

## Unlock Settings

1. Open Settings.
2. Enter the PIN.
3. Click Unlock.

## Change the PIN

1. Unlock Settings.
2. Enter the current PIN.
3. Enter the new PIN.
4. Confirm the new PIN.
5. Click Change PIN.

## Disable the PIN

1. Unlock Settings.
2. Enter the current PIN.
3. Click Disable PIN.

## Forgotten PIN recovery

From SSH or local terminal, edit `config.toml`:

```toml
[security]
reset_settings_pin = true
```

Restart the service:

```bash
sudo systemctl restart matrix-art.service
```

On startup, Matrix-Art clears the Settings PIN from SQLite, records the reset, and attempts to flip `reset_settings_pin` back to `false`.

After that, Settings will open unlocked and a new PIN can be set.

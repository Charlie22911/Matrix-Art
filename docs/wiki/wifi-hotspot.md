# Wi-Fi and Hotspot

Matrix-Art can operate as a Wi-Fi client or as a hotspot. Wi-Fi controls are on the Settings page.

Matrix-Art uses NetworkManager through `nmcli`.

## Wi-Fi client mode

Client mode connects the Pi to an existing Wi-Fi network.

Fields:

- Interface
- SSID
- Password
- Hidden network
- Autoconnect when saved

Actions:

- Scan networks
- Connect
- Save
- Connect + Save
- Disconnect selected interface

## Scan networks

Click Scan networks to list nearby SSIDs. Scanning can briefly disrupt Wi-Fi if the selected adapter is also the current access path.

Selecting a scanned network loads its SSID into the form.

## Connect

Connects to the SSID using the entered password but does not store it in Matrix-Art’s saved network list.

## Save

Stores the network in Matrix-Art’s SQLite settings and creates or updates a Matrix-Art NetworkManager profile.

## Connect + Save

Saves the profile and connects immediately.

Choosing Wi-Fi client mode switches the saved Wi-Fi mode back to `wifi`, so hotspot mode will not be restored on the next boot.

## Saved networks

Saved networks are shown in the Settings Wi-Fi card.

Functions:

- load saved network into the form
- connect a saved network
- remove a saved network

Removing a saved network also removes the Matrix-Art-created NetworkManager profile when possible.

## Hotspot mode

Hotspot mode starts an access point from the Pi.

Fields:

- Hotspot SSID
- Hotspot password

The password must be suitable for WPA/WPA2, typically 8 to 63 characters.

## Start Hotspot

Starting hotspot mode warns that existing wireless client connections on the selected adapter will be disconnected.

When started:

- existing wireless client connections on the selected adapter are disconnected
- Matrix-Art starts a NetworkManager hotspot profile
- hotspot mode is saved
- hotspot mode persists across reboot until Wi-Fi mode is chosen again
- the matrix shows the IP address, web port, SSID, password, and startup countdown

## Startup network behavior

On startup, Matrix-Art waits for an IP address. If saved Wi-Fi is unavailable, it can fall back to hotspot mode.

The panel shows an IP screen for the configured countdown period.

Normal Wi-Fi mode display:

```text
xxx.xxx.xxx.xxx
PORT:80
STARTING
XX SEC
```

Hotspot mode display:

```text
xxx.xxx.xxx.xxx
PORT:80
AP:SSID
PW:PASSWORD
STARTING
XX SEC
```

When the IP screen needs to show, Matrix-Art stops active Code effects, stops active GIF/image animation playback, pauses slideshow, clears the panel, and then draws the IP screen.

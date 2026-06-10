#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOOT_CONFIG="${MATRIX_ART_BOOT_CONFIG:-}"
BOOT_CMDLINE="${MATRIX_ART_BOOT_CMDLINE:-}"
DRIVER_URL="${MATRIX_ART_MATRIX_DRIVER_URL:-https://github.com/hzeller/rpi-rgb-led-matrix.git}"
DRIVER_DIR="${MATRIX_ART_MATRIX_DRIVER_DIR:-$APP_DIR/vendor/rpi-rgb-led-matrix}"
VENV_DIR="${MATRIX_ART_VENV:-$APP_DIR/.venv}"
MATRIX_COMMIT="${MATRIX_ART_MATRIX_COMMIT:-latest}"

DRY_RUN=0
ASSUME_YES=0
APPLY_BOOT=1
INSTALL_DRIVER=1
ONLY_DRIVER=0
ONLY_SERVICE=0
START_NOW=0

# Empty means ask interactively unless --yes is used.
WEB_PORT="${MATRIX_ART_WEB_PORT:-}"
ENABLE_ISOLATION=""
SERVICE_MODE=""       # enable, disabled, none
HARDWARE_PWM=""       # yes = adafruit-hat-pwm, no = adafruit-hat/convenience

usage() {
  cat <<USAGE
Matrix-Art installer

Usage:
  ./scripts/install.sh [options]

Common options:
  -y, --yes                  Use recommended defaults and do not prompt.
  --dry-run                  Print actions without changing files or installing packages.
  --port PORT                Set the Matrix-Art web UI port. Default: 80.
  --hardware-pwm yes|no      yes = Adafruit quality wiring, GPIO4 jumpered to GPIO18. Default: yes.
  --isolation yes|no         Add or remove CPU-isolation boot settings. Recommended: yes.
  --service enable|disabled|none
                              enable   = install and enable matrix-art.service at boot. Default/recommended.
                              disabled = install service but leave it disabled.
                              none     = do not install a service.
  --start                    Start/restart matrix-art.service after installing it.
  --no-boot-config           Do not edit config.txt or cmdline.txt.
  --no-driver                Skip RGB matrix driver build/install.
  --driver-commit HASH       Install a specific hzeller/rpi-rgb-led-matrix commit instead of latest.
  --latest                   Install latest hzeller/rpi-rgb-led-matrix. Default.

Maintenance shortcuts:
  --only-driver              Only install/update the RGB matrix driver and Matrix-Art venv.
  --only-service             Only install/update the systemd service.

Environment overrides:
  MATRIX_ART_BOOT_CONFIG=/path/to/config.txt
  MATRIX_ART_BOOT_CMDLINE=/path/to/cmdline.txt
  MATRIX_ART_WEB_PORT=80
  MATRIX_ART_MATRIX_DRIVER_URL=https://github.com/hzeller/rpi-rgb-led-matrix.git
  MATRIX_ART_MATRIX_COMMIT=latest
  MATRIX_ART_MATRIX_DRIVER_DIR=/path/to/rpi-rgb-led-matrix
  MATRIX_ART_VENV=/path/to/.venv
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -y|--yes) ASSUME_YES=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --port)
      shift
      [[ $# -gt 0 ]] || { echo "--port requires a value" >&2; exit 2; }
      WEB_PORT="$1"
      ;;
    --hardware-pwm|--pwm|--quality)
      if [[ "$1" == "--quality" ]]; then
        HARDWARE_PWM="yes"
      else
        shift
        [[ $# -gt 0 ]] || { echo "--hardware-pwm requires yes or no" >&2; exit 2; }
        HARDWARE_PWM="$1"
      fi
      ;;
    --convenience)
      HARDWARE_PWM="no"
      ;;
    --isolation)
      shift
      [[ $# -gt 0 ]] || { echo "--isolation requires yes or no" >&2; exit 2; }
      ENABLE_ISOLATION="$1"
      ;;
    --service)
      shift
      [[ $# -gt 0 ]] || { echo "--service requires enable, disabled, or none" >&2; exit 2; }
      SERVICE_MODE="$1"
      ;;
    --start) START_NOW=1 ;;
    --no-boot-config) APPLY_BOOT=0 ;;
    --no-driver) INSTALL_DRIVER=0 ;;
    --driver-commit|--commit)
      shift
      [[ $# -gt 0 ]] || { echo "--driver-commit requires a value" >&2; exit 2; }
      MATRIX_COMMIT="$1"
      ;;
    --latest) MATRIX_COMMIT="latest" ;;
    --only-driver) ONLY_DRIVER=1 ;;
    --only-service) ONLY_SERVICE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

case "${ENABLE_ISOLATION:-}" in
  ""|yes|Yes|YES|y|Y|true|TRUE|1|no|No|NO|n|N|false|FALSE|0) ;;
  *) echo "--isolation must be yes or no" >&2; exit 2 ;;
esac
case "${HARDWARE_PWM:-}" in
  ""|yes|Yes|YES|y|Y|true|TRUE|1|no|No|NO|n|N|false|FALSE|0) ;;
  *) echo "--hardware-pwm must be yes or no" >&2; exit 2 ;;
esac
case "${SERVICE_MODE:-}" in
  ""|enable|enabled|on|yes|disabled|disable|off|no|none) ;;
  *) echo "--service must be enable, disabled, or none" >&2; exit 2 ;;
esac

if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
  SUDO=""
else
  SUDO="sudo"
fi

say() { printf '\n== %s ==\n' "$*"; }
info() { printf '  %s\n' "$*"; }
run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[dry-run] '
    printf '%q ' "$@"
    printf '\n'
  else
    "$@"
  fi
}
run_sudo() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[dry-run] '
    [[ -n "$SUDO" ]] && printf 'sudo '
    printf '%q ' "$@"
    printf '\n'
  else
    if [[ -n "$SUDO" ]]; then
      $SUDO "$@"
    else
      "$@"
    fi
  fi
}
confirm_default_yes() {
  local prompt="$1"
  if [[ "$ASSUME_YES" -eq 1 ]]; then
    return 0
  fi
  printf '%s [Y/n] ' "$prompt"
  read -r ans
  [[ -z "$ans" || "$ans" =~ ^[Yy]$|^[Yy][Ee][Ss]$ ]]
}
confirm_default_no() {
  local prompt="$1"
  if [[ "$ASSUME_YES" -eq 1 ]]; then
    return 0
  fi
  printf '%s [y/N] ' "$prompt"
  read -r ans
  [[ "$ans" =~ ^[Yy]$|^[Yy][Ee][Ss]$ ]]
}
ask_value() {
  local prompt="$1"
  local default="$2"
  local value
  if [[ "$ASSUME_YES" -eq 1 ]]; then
    printf '%s\n' "$default"
    return 0
  fi
  printf '%s [%s]: ' "$prompt" "$default" >&2
  read -r value
  if [[ -z "$value" ]]; then
    value="$default"
  fi
  printf '%s\n' "$value"
}
find_boot_file() {
  local requested="$1"
  local firmware_path="$2"
  local legacy_path="$3"
  if [[ -n "$requested" ]]; then
    printf '%s\n' "$requested"
  elif [[ -f "$firmware_path" ]]; then
    printf '%s\n' "$firmware_path"
  else
    printf '%s\n' "$legacy_path"
  fi
}
backup_file() {
  local path="$1"
  [[ -f "$path" ]] || return 0
  local backup="${path}.matrix-art.$(date +%Y%m%d-%H%M%S).bak"
  run_sudo cp "$path" "$backup"
  info "Backed up $path to $backup"
}
normalize_bool_yes_no() {
  case "$1" in
    yes|Yes|YES|y|Y|true|TRUE|1|enable|enabled|on) printf 'yes\n' ;;
    *) printf 'no\n' ;;
  esac
}
normalize_service_mode() {
  case "$1" in
    enable|enabled|on|yes) printf 'enable\n' ;;
    disabled|disable|off|no) printf 'disabled\n' ;;
    none) printf 'none\n' ;;
    *) printf 'enable\n' ;;
  esac
}
validate_port() {
  local port="$1"
  if ! [[ "$port" =~ ^[0-9]+$ ]] || [[ "$port" -lt 1 || "$port" -gt 65535 ]]; then
    echo "Invalid port: $port. Use 1-65535." >&2
    exit 2
  fi
}

if [[ -z "$WEB_PORT" ]]; then
  WEB_PORT="80"
fi
validate_port "$WEB_PORT"

if [[ -z "$ENABLE_ISOLATION" ]]; then
  ENABLE_ISOLATION="yes"
fi
ENABLE_ISOLATION="$(normalize_bool_yes_no "$ENABLE_ISOLATION")"

if [[ -z "$HARDWARE_PWM" ]]; then
  HARDWARE_PWM="yes"
fi
HARDWARE_PWM="$(normalize_bool_yes_no "$HARDWARE_PWM")"

if [[ -z "$SERVICE_MODE" ]]; then
  SERVICE_MODE="enable"
fi
SERVICE_MODE="$(normalize_service_mode "$SERVICE_MODE")"

prompt_for_install_choices() {
  if [[ "$ASSUME_YES" -eq 1 || "$ONLY_DRIVER" -eq 1 || "$ONLY_SERVICE" -eq 1 ]]; then
    return 0
  fi

  cat <<'INTRO'
Matrix-Art setup

This installs Matrix-Art, the RGB matrix driver, and the web UI for a
Raspberry Pi RGB matrix panel.
INTRO

  local chosen_port
  chosen_port="$(ask_value "Web UI port. You can change this later in config.toml [server] port or from Settings" "$WEB_PORT")"
  validate_port "$chosen_port"
  WEB_PORT="$chosen_port"

  cat <<'PWM_NOTE'

Adafruit Bonnet quality mode uses the GPIO4-to-GPIO18 jumper for hardware PWM timing.
It gives the panel steadier output. If you use it, onboard Pi audio must stay off.
Matrix-Art will set dtparam=audio=off and keep the Pi onboard audio module from loading.
PWM_NOTE
  if confirm_default_yes "Are you using the GPIO4-to-GPIO18 hardware PWM jumper?"; then
    HARDWARE_PWM="yes"
  else
    HARDWARE_PWM="no"
  fi

  cat <<'CPU_NOTE'

CPU isolation keeps normal Linux work away from CPU 3 so the matrix refresh thread
has steadier timing. It is recommended for a dedicated RGB matrix appliance.
CPU_NOTE
  if confirm_default_yes "Enable CPU isolation and Matrix-Art CPU pinning?"; then
    ENABLE_ISOLATION="yes"
  else
    ENABLE_ISOLATION="no"
  fi

  cat <<'SERVICE_NOTE'

Startup mode:
  1. Start Matrix-Art automatically at boot  [recommended for a dedicated panel]
  2. Install the service but leave it off    [useful for testing]
  3. Manual start only                       [run ./run.sh yourself]
SERVICE_NOTE
  local ans
  printf 'Choose startup mode [1]: '
  read -r ans
  case "${ans:-1}" in
    1) SERVICE_MODE="enable" ;;
    2) SERVICE_MODE="disabled" ;;
    3) SERVICE_MODE="none" ;;
    *) echo "Invalid startup choice." >&2; exit 2 ;;
  esac
}

install_packages() {
  say "Installing dependencies"
  if command -v apt >/dev/null 2>&1; then
    run_sudo apt update
    run_sudo env DEBIAN_FRONTEND=noninteractive apt install -y \
      python3 \
      python3-venv \
      python3-pip \
      python3-dev \
      python3-setuptools \
      python3-wheel \
      git \
      curl \
      unzip \
      build-essential \
      cmake \
      ninja-build \
      pkg-config \
      cython3 \
      python3-pil \
      network-manager \
      iw \
      wireless-tools \
      rfkill \
      sysstat \
      iproute2 \
      procps
  else
    info "apt not found. Install Python venv/pip, git, build tools, Cython, Pillow, and NetworkManager manually."
  fi
}

prepare_venv() {
  say "Preparing Matrix-Art Python environment"
  if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    run python3 -m venv "$VENV_DIR"
  fi
  run "$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
  run "$VENV_DIR/bin/python" -m pip install -r "$APP_DIR/requirements.txt"
  # Needed when installing the latest rgbmatrix pyproject without build isolation.
  run "$VENV_DIR/bin/python" -m pip install --upgrade scikit-build-core cython cmake ninja
}

install_matrix_driver() {
  if [[ "$INSTALL_DRIVER" -ne 1 ]]; then
    info "Skipped RGB matrix driver install."
    return 0
  fi

  say "Installing RGB matrix driver"
  info "Driver source: $DRIVER_URL"
  info "Driver version: $MATRIX_COMMIT"
  info "Checkout path: $DRIVER_DIR"
  info "Python venv: $VENV_DIR"
  if [[ "$HARDWARE_PWM" == "yes" ]]; then
    info "Panel mapping: adafruit-hat-pwm, for the GPIO4-to-GPIO18 hardware PWM jumper."
  else
    info "Panel mapping: adafruit-hat, convenience wiring without the GPIO4-to-GPIO18 jumper."
  fi

  run mkdir -p "$(dirname "$DRIVER_DIR")"
  if [[ ! -d "$DRIVER_DIR/.git" ]]; then
    if [[ "$MATRIX_COMMIT" == "latest" ]]; then
      run git clone --depth=1 "$DRIVER_URL" "$DRIVER_DIR"
    else
      run git clone "$DRIVER_URL" "$DRIVER_DIR"
    fi
  else
    run git -C "$DRIVER_DIR" remote set-url origin "$DRIVER_URL"
    run git -C "$DRIVER_DIR" fetch origin
  fi

  if [[ "$MATRIX_COMMIT" == "latest" ]]; then
    if [[ "$DRY_RUN" -eq 1 ]]; then
      echo "[dry-run] git -C '$DRIVER_DIR' fetch --depth=1 origin"
      echo "[dry-run] git -C '$DRIVER_DIR' checkout -f origin/<default-branch>"
    else
      git -C "$DRIVER_DIR" fetch --depth=1 origin
      default_branch="$(git -C "$DRIVER_DIR" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##' || true)"
      if [[ -z "$default_branch" ]]; then
        default_branch="$(git -C "$DRIVER_DIR" remote show origin 2>/dev/null | awk '/HEAD branch/ {print $NF}' || true)"
      fi
      if [[ -z "$default_branch" ]]; then
        default_branch="master"
      fi
      git -C "$DRIVER_DIR" checkout -f "origin/$default_branch"
    fi
  else
    run git -C "$DRIVER_DIR" fetch origin "$MATRIX_COMMIT" || true
    run git -C "$DRIVER_DIR" checkout -f "$MATRIX_COMMIT"
  fi

  if [[ "$DRY_RUN" -eq 1 ]]; then
    info "Would remove old app-local rgbmatrix/ directory, if present."
  else
    rm -rf "$APP_DIR/rgbmatrix"
  fi

  say "Installing rgbmatrix Python bindings into Matrix-Art venv"
  set +e
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1 $VENV_DIR/bin/python -m pip install --no-build-isolation --no-cache-dir --upgrade $DRIVER_DIR"
    pip_status=0
  else
    CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1 "$VENV_DIR/bin/python" -m pip install --no-build-isolation --no-cache-dir --upgrade "$DRIVER_DIR"
    pip_status=$?
  fi
  set -e

  if [[ "$pip_status" -ne 0 ]]; then
    say "Root install failed, trying bindings/python install path"
    if [[ -d "$DRIVER_DIR/bindings/python" ]]; then
      run bash -c "cd '$DRIVER_DIR/bindings/python' && CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1 '$VENV_DIR/bin/python' -m pip install --no-build-isolation --no-cache-dir --upgrade ."
    else
      echo "Could not find $DRIVER_DIR/bindings/python for fallback install." >&2
      exit "$pip_status"
    fi
  fi

  say "Verifying rgbmatrix import"
  run "$VENV_DIR/bin/python" - <<'PY'
from rgbmatrix import RGBMatrix, RGBMatrixOptions
print("rgbmatrix Python bindings import OK")
PY
}

update_config_toml() {
  say "Updating Matrix-Art config.toml"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    info "Would update $APP_DIR/config.toml with port $WEB_PORT, panel mapping, timing, startup, and CPU-affinity defaults."
    return 0
  fi
  MATRIX_ART_INSTALL_PORT="$WEB_PORT" MATRIX_ART_INSTALL_ISOLATION="$ENABLE_ISOLATION" MATRIX_ART_INSTALL_HARDWARE_PWM="$HARDWARE_PWM" python3 - "$APP_DIR/config.toml" <<'PY'
from __future__ import annotations
from pathlib import Path
import os
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8") if path.exists() else ""
port = os.environ.get("MATRIX_ART_INSTALL_PORT", "80")
isolation = os.environ.get("MATRIX_ART_INSTALL_ISOLATION", "yes").lower() in {"1", "true", "yes", "y", "on"}
hardware_pwm = os.environ.get("MATRIX_ART_INSTALL_HARDWARE_PWM", "yes").lower() in {"1", "true", "yes", "y", "on"}
edits = {
    "panel": {
        "rows": "64",
        "cols": "64",
        "chain_length": "1",
        "parallel": "1",
        "gpio_mapping": '"adafruit-hat-pwm"' if hardware_pwm else '"adafruit-hat"',
        "hardware_pulse": "true" if hardware_pwm else "false",
        "slowdown_gpio": "2",
        "limit_refresh_rate_hz": "90",
        "drop_privileges": "false",
    },
    "server": {
        "host": '"0.0.0.0"',
        "port": str(int(port)),
    },
    "runtime": {
        "auto_sudo": "true",
        "mock_display": "false",
        "process_nice": "-10",
        "matrix_realtime_priority": "55",
        "display_thread_realtime_priority": "45",
        "restore_main_scheduler_after_matrix_init": "true",
        "enable_matrix_core_affinity": "true" if isolation else "false",
        "matrix_cpu_core": "3",
        "app_cpu_cores": '"0-2"',
    },
    "startup": {
        "show_ip_on_start": "true",
        "ip_display_seconds": "60",
        "ip_wait_seconds": "35",
        "hotspot_fallback": "true",
        "default_hotspot_ssid": '"Matrix-Art"',
        "default_hotspot_password": '"matrixart1234"',
    },
    "security": {
        "reset_settings_pin": "false",
    },
}

lines = text.splitlines()
section_re = re.compile(r"^\s*\[([^\]]+)\]\s*$")
key_re = re.compile(r"^(\s*)([A-Za-z0-9_]+)(\s*=\s*)(.*)$")
seen = {section: set() for section in edits}
out: list[str] = []
current: str | None = None

for line in lines:
    m = section_re.match(line)
    if m:
        if current in edits:
            for key, value in edits[current].items():
                if key not in seen[current]:
                    out.append(f"{key} = {value}")
                    seen[current].add(key)
        current = m.group(1).strip()
        out.append(line)
        continue
    km = key_re.match(line)
    if current in edits and km:
        key = km.group(2)
        if key in edits[current]:
            out.append(f"{key} = {edits[current][key]}")
            seen[current].add(key)
            continue
    out.append(line)

if current in edits:
    for key, value in edits[current].items():
        if key not in seen[current]:
            out.append(f"{key} = {value}")
            seen[current].add(key)

for section, values in edits.items():
    missing = [key for key in values if key not in seen.get(section, set())]
    if missing:
        if out and out[-1].strip():
            out.append("")
        out.append(f"[{section}]")
        for key in missing:
            out.append(f"{key} = {values[key]}")
            seen.setdefault(section, set()).add(key)

path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
PY
}

set_config_audio_off() {
  local path="$1"
  local tmp
  [[ -f "$path" || "$DRY_RUN" -eq 1 ]] || run_sudo touch "$path"
  backup_file "$path"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    info "Would set dtparam=audio=off in $path"
    return 0
  fi
  tmp="$(mktemp)"
  if [[ -f "$path" ]]; then
    awk '
      BEGIN {done=0}
      /^[[:space:]]*#?[[:space:]]*dtparam=audio=/ {
        if (done == 0) {
          print "dtparam=audio=off"
          done=1
        }
        next
      }
      {print}
      END {
        if (done == 0) {
          print ""
          print "# Matrix-Art: Adafruit Bonnet hardware PWM mode uses PWM timing, so onboard audio is off."
          print "dtparam=audio=off"
        }
      }
    ' "$path" > "$tmp"
  else
    {
      printf '# Matrix-Art: Adafruit Bonnet hardware PWM mode uses PWM timing, so onboard audio is off.\n'
      printf 'dtparam=audio=off\n'
    } > "$tmp"
  fi
  run_sudo cp "$tmp" "$path"
  rm -f "$tmp"
}

blacklist_audio_module_for_pwm() {
  local path="/etc/modprobe.d/matrix-art-no-audio.conf"
  local tmp

  if [[ "$DRY_RUN" -eq 1 ]]; then
    info "Would keep the Pi onboard audio module from loading by writing $path."
    info "Would try to unload snd_bcm2835 now if it is currently loaded."
    return 0
  fi

  run_sudo mkdir -p /etc/modprobe.d
  backup_file "$path"
  tmp="$(mktemp)"
  cat > "$tmp" <<'EOF_AUDIO_BLACKLIST'
# Matrix-Art: Adafruit Bonnet hardware PWM mode needs the Pi onboard audio driver kept off.
blacklist snd_bcm2835
EOF_AUDIO_BLACKLIST
  run_sudo cp "$tmp" "$path"
  rm -f "$tmp"
  info "Pi onboard audio module will stay off for hardware PWM mode."

  if lsmod | grep -q '^snd_bcm2835'; then
    if run_sudo modprobe -r snd_bcm2835 2>/dev/null; then
      info "Unloaded the currently loaded Pi onboard audio module."
    else
      info "Pi onboard audio is still loaded right now; reboot before starting Matrix-Art hardware PWM mode."
    fi
  fi
}

is_isolation_arg() {
  case "$1" in
    isolcpus=*|nohz_full=*|rcu_nocbs=*|irqaffinity=*) return 0 ;;
    *) return 1 ;;
  esac
}

is_matrix_art_isolation_arg() {
  case "$1" in
    isolcpus=domain,managed_irq,3|nohz_full=3|rcu_nocbs=3|irqaffinity=0,1,2) return 0 ;;
    *) return 1 ;;
  esac
}

rewrite_cmdline_isolation() {
  local path="$1"
  local line token
  local custom=()
  local kept=()
  local desired="isolcpus=domain,managed_irq,3 nohz_full=3 rcu_nocbs=3 irqaffinity=0,1,2"

  line="$(tr '\n' ' ' < "$path" | xargs)"

  for token in $line; do
    if is_isolation_arg "$token"; then
      if ! is_matrix_art_isolation_arg "$token"; then
        custom+=("$token")
      fi
    fi
  done

  if [[ "$ENABLE_ISOLATION" == "yes" && "${#custom[@]}" -gt 0 ]]; then
    info "Existing CPU isolation settings were found: ${custom[*]}"
    if [[ "$ASSUME_YES" -eq 1 ]] || confirm_default_no "Use Matrix-Art's CPU 3 isolation settings instead?"; then
      info "Using Matrix-Art CPU 3 isolation settings."
    else
      info "Leaving existing CPU isolation settings unchanged."
      return 0
    fi
  fi

  for token in $line; do
    if [[ "$ENABLE_ISOLATION" == "yes" ]]; then
      if is_isolation_arg "$token"; then
        continue
      fi
    else
      if is_matrix_art_isolation_arg "$token"; then
        continue
      fi
    fi
    kept+=("$token")
  done

  if [[ "$ENABLE_ISOLATION" == "yes" ]]; then
    printf '%s %s\n' "${kept[*]}" "$desired" | xargs | run_sudo tee "$path" >/dev/null
  else
    printf '%s\n' "${kept[*]}" | xargs | run_sudo tee "$path" >/dev/null
  fi
}

apply_boot_config() {
  if [[ "$APPLY_BOOT" -ne 1 ]]; then
    info "Skipped boot settings."
    return 0
  fi

  say "Applying selected boot settings"
  BOOT_CONFIG="$(find_boot_file "$BOOT_CONFIG" /boot/firmware/config.txt /boot/config.txt)"
  BOOT_CMDLINE="$(find_boot_file "$BOOT_CMDLINE" /boot/firmware/cmdline.txt /boot/cmdline.txt)"

  if [[ "$HARDWARE_PWM" == "yes" ]]; then
    info "Hardware PWM selected: onboard audio will be turned off in $BOOT_CONFIG."
    set_config_audio_off "$BOOT_CONFIG"
    blacklist_audio_module_for_pwm
  else
    info "Hardware PWM not selected: leaving config.txt audio settings unchanged."
  fi

  if [[ ! -f "$BOOT_CMDLINE" && "$DRY_RUN" -ne 1 ]]; then
    echo "Could not find cmdline.txt at $BOOT_CMDLINE" >&2
    exit 1
  fi
  backup_file "$BOOT_CMDLINE"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    if [[ "$ENABLE_ISOLATION" == "yes" ]]; then
      info "Would enable Matrix-Art CPU 3 isolation in $BOOT_CMDLINE."
      info "If other CPU isolation settings already exist, the installer will ask before replacing them."
    else
      info "Would remove Matrix-Art CPU-isolation tokens from $BOOT_CMDLINE and leave other isolation settings unchanged."
    fi
  else
    rewrite_cmdline_isolation "$BOOT_CMDLINE"
  fi
}

service_file_content() {
  local python_bin="$1"
  cat <<EOF_SERVICE
[Unit]
Description=Matrix-Art RGB Matrix Art Server
After=NetworkManager.service
Wants=NetworkManager.service

[Service]
Type=simple
WorkingDirectory=$APP_DIR
Environment=PATH=$APP_DIR/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
Environment=PYTHONUNBUFFERED=1
ExecStart=$python_bin -m matrix_art --config $APP_DIR/config.toml --no-sudo-reexec
Restart=on-failure
RestartSec=3
TimeoutStopSec=12
KillSignal=SIGTERM
KillMode=mixed
User=root

# Permit the service to use all cores at the systemd boundary.
# Matrix-Art can then pin the native matrix refresh thread to CPU 3
# and move web/app work back to CPUs 0-2 when CPU pinning is enabled.
CPUAffinity=0 1 2 3

# Give the RGB matrix scan/PWM threads room to run with stable timing.
# Matrix-Art briefly enters SCHED_FIFO while constructing the matrix so
# native matrix threads inherit realtime priority, then restores the web
# server and app logic to normal scheduling.
Nice=-10
LimitNICE=-20
LimitRTPRIO=95

[Install]
WantedBy=multi-user.target
EOF_SERVICE
}

install_service() {
  if [[ "$SERVICE_MODE" == "none" ]]; then
    info "Skipped systemd service install. Use ./run.sh for manual startup."
    return 0
  fi
  say "Installing systemd service"
  local service_file="/etc/systemd/system/matrix-art.service"
  local python_bin="$VENV_DIR/bin/python"
  if [[ ! -x "$python_bin" ]]; then
    python_bin="/usr/bin/python3"
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    info "Would write $service_file using Python: $python_bin"
  else
    service_file_content "$python_bin" | run_sudo tee "$service_file" >/dev/null
  fi
  run_sudo systemctl daemon-reload
  if [[ "$SERVICE_MODE" == "enable" ]]; then
    run_sudo systemctl enable matrix-art.service
    info "matrix-art.service installed and enabled for boot."
  else
    run_sudo systemctl disable matrix-art.service 2>/dev/null || true
    info "matrix-art.service installed but left disabled."
  fi
  if [[ "$START_NOW" -eq 1 ]]; then
    run_sudo systemctl restart matrix-art.service
  fi
}


enable_networkmanager() {
  say "Enabling NetworkManager"
  run_sudo systemctl enable --now NetworkManager.service || true
}

verify_project() {
  say "Verifying installed project"
  local py="$VENV_DIR/bin/python"
  if [[ ! -x "$py" ]]; then
    py="$(command -v python3)"
  fi
  run "$py" -m compileall -q "$APP_DIR/matrix_art"
  if [[ "$INSTALL_DRIVER" -eq 1 ]]; then
    run "$py" - <<'PY'
from rgbmatrix import RGBMatrix, RGBMatrixOptions
print("rgbmatrix Python bindings import OK")
PY
  else
    info "Skipped rgbmatrix import verification because --no-driver was used."
  fi
  for shell_file in "$APP_DIR/run.sh" "$APP_DIR/scripts/"*.sh; do
    run bash -n "$shell_file"
  done
}

prompt_for_install_choices

say "Matrix-Art installer"
info "App directory: $APP_DIR"
info "Hardware target: Raspberry Pi Zero 2W, Adafruit RGB Matrix Bonnet, 64x64 HUB75 panel"
info "Power target: 5V 4A minimum through 5.5mm OD / 2.1mm ID DC barrel jack"
info "Web UI port: $WEB_PORT"
info "Hardware PWM jumper: $HARDWARE_PWM"
info "CPU isolation/pinning: $ENABLE_ISOLATION"
info "Startup mode: $SERVICE_MODE"

if [[ "$ASSUME_YES" -ne 1 && "$ONLY_DRIVER" -ne 1 && "$ONLY_SERVICE" -ne 1 ]]; then
  cat <<'SUMMARY'

Setup will install packages, create Matrix-Art's Python environment, build the RGB
matrix driver, save your Matrix-Art configuration, and set up the startup mode you chose.
SUMMARY
  confirm_default_yes "Continue?" || exit 1
fi

say "Making scripts executable"
run chmod +x "$APP_DIR/run.sh" "$APP_DIR/scripts/"*.sh

if [[ "$ONLY_SERVICE" -eq 1 ]]; then
  install_service
  exit 0
fi

install_packages
prepare_venv
run mkdir -p "$APP_DIR/data" "$APP_DIR/data/originals" "$APP_DIR/data/exports"
install_matrix_driver

if [[ "$ONLY_DRIVER" -eq 1 ]]; then
  verify_project
  exit 0
fi

apply_boot_config
update_config_toml
enable_networkmanager
install_service
verify_project

cat <<DONE

Matrix-Art setup completed.

Recommended next step:
  sudo reboot

After reboot:
  http://<panel-ip>:$WEB_PORT/

The web port can be changed later in:
  config.toml  [server] port
or from the Matrix-Art Settings page.

Useful checks:
  cd $APP_DIR
  ./scripts/check_matrix_timing.sh
  journalctl -u matrix-art.service -f

DONE

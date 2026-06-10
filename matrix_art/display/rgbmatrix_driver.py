from __future__ import annotations

from threading import RLock

from PIL import Image

from ..config import PanelConfig
from .base import DisplayDriver


class RGBMatrixDisplayDriver(DisplayDriver):
    name = "rgbmatrix"

    def __init__(self, config: PanelConfig):
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        self.config = config
        self.hardware_pwm_expected = config.gpio_mapping == "adafruit-hat-pwm" and bool(config.hardware_pulse)

        options = RGBMatrixOptions()
        options.rows = config.rows
        options.cols = config.cols
        options.chain_length = config.chain_length
        options.parallel = config.parallel
        options.row_address_type = config.row_address_type
        options.multiplexing = config.multiplexing
        options.pwm_bits = config.pwm_bits
        options.brightness = max(1, min(100, int(config.brightness)))
        options.pwm_lsb_nanoseconds = config.pwm_lsb_nanoseconds
        options.led_rgb_sequence = config.rgb_sequence
        options.pixel_mapper_config = config.pixel_mapper
        options.panel_type = config.panel_type
        options.scan_mode = config.scan_mode
        options.gpio_slowdown = config.slowdown_gpio
        options.drop_privileges = bool(config.drop_privileges)
        if config.gpio_mapping:
            options.hardware_mapping = config.gpio_mapping
        if config.show_refresh_rate:
            options.show_refresh_rate = 1
        if not config.hardware_pulse:
            options.disable_hardware_pulsing = True
        if config.limit_refresh_rate_hz:
            options.limit_refresh_rate_hz = config.limit_refresh_rate_hz

        self.matrix = RGBMatrix(options=options)
        self.canvas = self.matrix.CreateFrameCanvas()
        self.lock = RLock()
        self.clear()


    def timing_info(self) -> dict[str, object]:
        mapping = str(self.config.gpio_mapping or "")
        hardware_pulse_enabled = bool(self.config.hardware_pulse)
        return {
            "driver": self.name,
            "rows": int(self.config.rows),
            "cols": int(self.config.cols),
            "chain_length": int(self.config.chain_length),
            "parallel": int(self.config.parallel),
            "gpio_mapping": mapping,
            "hardware_pulse_enabled": hardware_pulse_enabled,
            "hardware_pwm_expected": bool(mapping == "adafruit-hat-pwm" and hardware_pulse_enabled),
            "slowdown_gpio": int(self.config.slowdown_gpio),
            "limit_refresh_rate_hz": int(self.config.limit_refresh_rate_hz),
            "pwm_bits": int(self.config.pwm_bits),
            "pwm_lsb_nanoseconds": int(self.config.pwm_lsb_nanoseconds),
            "drop_privileges": bool(self.config.drop_privileges),
        }

    @property
    def width(self) -> int:
        return int(self.matrix.width)

    @property
    def height(self) -> int:
        return int(self.matrix.height)

    def show_image(self, image: Image.Image) -> None:
        img = image.convert("RGB")
        if img.size != (self.width, self.height):
            img = img.resize((self.width, self.height), Image.Resampling.NEAREST)
        with self.lock:
            self.canvas.Clear()
            self.canvas.SetImage(img, 0, 0)
            self.canvas = self.matrix.SwapOnVSync(self.canvas)

    def clear(self) -> None:
        with self.lock:
            self.canvas.Clear()
            self.canvas = self.matrix.SwapOnVSync(self.canvas)

    def set_brightness(self, value: int) -> None:
        value = max(1, min(100, int(value)))
        with self.lock:
            self.matrix.brightness = value
            try:
                self.canvas.brightness = value
            except Exception:
                pass

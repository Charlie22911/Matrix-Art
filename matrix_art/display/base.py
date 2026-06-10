from __future__ import annotations

from abc import ABC, abstractmethod

from PIL import Image


class DisplayDriver(ABC):
    name = "base"

    @property
    @abstractmethod
    def width(self) -> int:
        raise NotImplementedError

    @property
    @abstractmethod
    def height(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def show_image(self, image: Image.Image) -> None:
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_brightness(self, value: int) -> None:
        raise NotImplementedError

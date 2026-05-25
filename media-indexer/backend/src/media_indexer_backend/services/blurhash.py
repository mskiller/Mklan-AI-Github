from __future__ import annotations

import math

from PIL import Image


BASE83_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz#$%*+,-.:;=?@[]^_{|}~"


def _encode83(value: int, length: int) -> str:
    result = ""
    for index in range(length):
        digit = (value // (83 ** (length - index - 1))) % 83
        result += BASE83_ALPHABET[digit]
    return result


def _srgb_to_linear(value: int) -> float:
    value = value / 255.0
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(value: float) -> int:
    value = max(0.0, min(1.0, value))
    if value <= 0.0031308:
        value = value * 12.92
    else:
        value = 1.055 * (value ** (1.0 / 2.4)) - 0.055
    return int(value * 255 + 0.5)


def _sign_pow(value: float, exp: float) -> float:
    return math.copysign(abs(value) ** exp, value)


def _encode_dc(color: tuple[float, float, float]) -> int:
    r = _linear_to_srgb(color[0])
    g = _linear_to_srgb(color[1])
    b = _linear_to_srgb(color[2])
    return (r << 16) + (g << 8) + b


def _encode_ac(color: tuple[float, float, float], maximum_value: float) -> int:
    quant_r = max(0, min(18, int(math.floor(_sign_pow(color[0] / maximum_value, 0.5) * 9 + 9.5))))
    quant_g = max(0, min(18, int(math.floor(_sign_pow(color[1] / maximum_value, 0.5) * 9 + 9.5))))
    quant_b = max(0, min(18, int(math.floor(_sign_pow(color[2] / maximum_value, 0.5) * 9 + 9.5))))
    return quant_r * 19 * 19 + quant_g * 19 + quant_b


def encode_blurhash(image: Image.Image, x_components: int = 4, y_components: int = 3) -> str:
    x_components = max(1, min(9, x_components))
    y_components = max(1, min(9, y_components))
    prepared = image.convert("RGB")
    width, height = prepared.size
    pixels = prepared.load()
    factors: list[tuple[float, float, float]] = []

    for y_component in range(y_components):
        for x_component in range(x_components):
            normalisation = 1.0 if x_component == 0 and y_component == 0 else 2.0
            r = 0.0
            g = 0.0
            b = 0.0

            for y in range(height):
                for x in range(width):
                    basis = (
                        normalisation
                        * math.cos(math.pi * x_component * x / width)
                        * math.cos(math.pi * y_component * y / height)
                    )
                    pixel = pixels[x, y]
                    r += basis * _srgb_to_linear(pixel[0])
                    g += basis * _srgb_to_linear(pixel[1])
                    b += basis * _srgb_to_linear(pixel[2])

            scale = 1.0 / (width * height)
            factors.append((r * scale, g * scale, b * scale))

    dc = factors[0]
    ac = factors[1:]
    size_flag = (x_components - 1) + (y_components - 1) * 9

    if ac:
        maximum_value = max(max(abs(component) for component in factor) for factor in ac)
        quantised_maximum_value = max(0, min(82, int(math.floor(maximum_value * 166 - 0.5))))
        actual_maximum_value = (quantised_maximum_value + 1) / 166
    else:
        quantised_maximum_value = 0
        actual_maximum_value = 1

    blurhash = _encode83(size_flag, 1) + _encode83(quantised_maximum_value, 1) + _encode83(_encode_dc(dc), 4)
    for factor in ac:
        blurhash += _encode83(_encode_ac(factor, actual_maximum_value), 2)
    return blurhash

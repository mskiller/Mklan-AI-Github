"use client";

import { useEffect, useRef } from "react";


const BASE83_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz#$%*+,-.:;=?@[]^_{|}~";


function decode83(value: string) {
  let result = 0;
  for (const character of value) {
    result = result * 83 + BASE83_ALPHABET.indexOf(character);
  }
  return result;
}


function srgbToLinear(value: number) {
  const component = value / 255;
  if (component <= 0.04045) {
    return component / 12.92;
  }
  return ((component + 0.055) / 1.055) ** 2.4;
}


function linearToSrgb(value: number) {
  const component = Math.max(0, Math.min(1, value));
  if (component <= 0.0031308) {
    return Math.round(component * 12.92 * 255 + 0.5);
  }
  return Math.round((1.055 * component ** (1 / 2.4) - 0.055) * 255 + 0.5);
}


function signPow(value: number, exp: number) {
  return Math.sign(value) * Math.abs(value) ** exp;
}


function decodeDc(value: number) {
  return [
    srgbToLinear(value >> 16),
    srgbToLinear((value >> 8) & 255),
    srgbToLinear(value & 255),
  ] as const;
}


function decodeAc(value: number, maximumValue: number) {
  const quantR = Math.floor(value / (19 * 19));
  const quantG = Math.floor(value / 19) % 19;
  const quantB = value % 19;
  return [
    signPow((quantR - 9) / 9, 2) * maximumValue,
    signPow((quantG - 9) / 9, 2) * maximumValue,
    signPow((quantB - 9) / 9, 2) * maximumValue,
  ] as const;
}


function decodeBlurhash(blurhash: string, width: number, height: number) {
  const sizeFlag = decode83(blurhash[0]);
  const numY = Math.floor(sizeFlag / 9) + 1;
  const numX = (sizeFlag % 9) + 1;
  const quantizedMaximumValue = decode83(blurhash[1]);
  const maximumValue = (quantizedMaximumValue + 1) / 166;
  const colors: Array<readonly [number, number, number]> = [];

  colors.push(decodeDc(decode83(blurhash.substring(2, 6))));
  for (let index = 1; index < numX * numY; index += 1) {
    const value = decode83(blurhash.substring(4 + index * 2, 6 + index * 2));
    colors.push(decodeAc(value, maximumValue));
  }

  const pixels = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      let r = 0;
      let g = 0;
      let b = 0;

      for (let j = 0; j < numY; j += 1) {
        for (let i = 0; i < numX; i += 1) {
          const basis =
            Math.cos((Math.PI * x * i) / width) *
            Math.cos((Math.PI * y * j) / height);
          const color = colors[i + j * numX];
          r += color[0] * basis;
          g += color[1] * basis;
          b += color[2] * basis;
        }
      }

      const offset = 4 * (x + y * width);
      pixels[offset] = linearToSrgb(r);
      pixels[offset + 1] = linearToSrgb(g);
      pixels[offset + 2] = linearToSrgb(b);
      pixels[offset + 3] = 255;
    }
  }
  return pixels;
}


export function BlurhashPlaceholder({
  hash,
  width = 32,
  height = 32,
  className = "",
}: {
  hash: string;
  width?: number;
  height?: number;
  className?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }
    const context = canvas.getContext("2d");
    if (!context) {
      return;
    }
    const imageData = context.createImageData(width, height);
    imageData.data.set(decodeBlurhash(hash, width, height));
    context.putImageData(imageData, 0, 0);
  }, [hash, width, height]);

  return <canvas ref={canvasRef} width={width} height={height} className={`blurhash-placeholder ${className}`.trim()} />;
}

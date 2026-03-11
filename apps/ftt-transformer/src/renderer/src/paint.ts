import type { Point, Stroke } from "@renderer/types";

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));

const toIntPoint = (point: Point) => ({ x: Math.round(point.x), y: Math.round(point.y) });

export function strokeToMask(stroke: Stroke, width: number, height: number) {
  const mask = new Uint8ClampedArray(width * height);
  const radius = Math.max(1, Math.round(stroke.radiusPx));
  const points = stroke.points.map(toIntPoint);

  const drawCircle = (cx: number, cy: number) => {
    const r2 = radius * radius;
    const minX = clamp(cx - radius, 0, width - 1);
    const maxX = clamp(cx + radius, 0, width - 1);
    const minY = clamp(cy - radius, 0, height - 1);
    const maxY = clamp(cy + radius, 0, height - 1);
    for (let y = minY; y <= maxY; y += 1) {
      for (let x = minX; x <= maxX; x += 1) {
        const dx = x - cx;
        const dy = y - cy;
        if (dx * dx + dy * dy <= r2) {
          mask[y * width + x] = 1;
        }
      }
    }
  };

  const drawSegment = (start: Point, end: Point) => {
    const dx = end.x - start.x;
    const dy = end.y - start.y;
    const distance = Math.max(1, Math.hypot(dx, dy));
    const steps = Math.ceil(distance / Math.max(1, radius * 0.5));
    for (let i = 0; i <= steps; i += 1) {
      const t = i / steps;
      const x = Math.round(start.x + dx * t);
      const y = Math.round(start.y + dy * t);
      drawCircle(x, y);
    }
  };

  if (points.length === 1) {
    drawCircle(points[0].x, points[0].y);
  } else {
    for (let i = 0; i < points.length - 1; i += 1) {
      drawSegment(points[i], points[i + 1]);
    }
  }

  return mask;
}

export function applyStrokeMask(source: ImageData, mask: Uint8ClampedArray) {
  const cropCanvas = document.createElement("canvas");
  cropCanvas.width = source.width;
  cropCanvas.height = source.height;
  const cropCtx = cropCanvas.getContext("2d");
  if (!cropCtx) return null;

  const output = cropCtx.createImageData(source.width, source.height);
  for (let i = 0; i < mask.length; i += 1) {
    if (mask[i] !== 1) continue;
    const offset = i * 4;
    output.data[offset] = source.data[offset];
    output.data[offset + 1] = source.data[offset + 1];
    output.data[offset + 2] = source.data[offset + 2];
    output.data[offset + 3] = 255;
  }
  cropCtx.putImageData(output, 0, 0);
  return cropCanvas;
}

export function floodFillFromStroke(
  mask: Uint8ClampedArray,
  width: number,
  height: number,
) {
  const outside = new Uint8ClampedArray(width * height);
  const queueX = new Int32Array(width * height);
  const queueY = new Int32Array(width * height);
  let head = 0;
  let tail = 0;

  const push = (x: number, y: number) => {
    queueX[tail] = x;
    queueY[tail] = y;
    tail += 1;
  };

  for (let x = 0; x < width; x += 1) {
    if (mask[x] === 0) {
      outside[x] = 1;
      push(x, 0);
    }
    const bottom = (height - 1) * width + x;
    if (mask[bottom] === 0 && outside[bottom] === 0) {
      outside[bottom] = 1;
      push(x, height - 1);
    }
  }
  for (let y = 0; y < height; y += 1) {
    const left = y * width;
    if (mask[left] === 0 && outside[left] === 0) {
      outside[left] = 1;
      push(0, y);
    }
    const right = y * width + (width - 1);
    if (mask[right] === 0 && outside[right] === 0) {
      outside[right] = 1;
      push(width - 1, y);
    }
  }

  const directions = [
    [1, 0],
    [-1, 0],
    [0, 1],
    [0, -1],
  ];

  while (head < tail) {
    const x = queueX[head];
    const y = queueY[head];
    head += 1;
    for (const [dx, dy] of directions) {
      const nx = x + dx;
      const ny = y + dy;
      if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
      const idx = ny * width + nx;
      if (mask[idx] !== 0 || outside[idx] !== 0) continue;
      outside[idx] = 1;
      push(nx, ny);
    }
  }

  const filled = new Uint8ClampedArray(mask.length);
  for (let i = 0; i < mask.length; i += 1) {
    if (mask[i] === 1 || outside[i] === 0) {
      filled[i] = 1;
    }
  }
  return filled;
}

export function buildFilledMask(stroke: Stroke, width: number, height: number) {
  const outline = strokeToMask(stroke, width, height);
  if (!stroke.filled) return outline;

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return outline;

  const points = stroke.points;
  if (points.length < 2) return outline;

  ctx.lineWidth = stroke.radiusPx * 2;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.strokeStyle = "#fff";
  ctx.fillStyle = "#fff";

  ctx.beginPath();
  points.forEach((p, i) => {
    if (i === 0) ctx.moveTo(p.x, p.y);
    else ctx.lineTo(p.x, p.y);
  });
  ctx.closePath();
  ctx.fill();
  ctx.stroke();

  const imageData = ctx.getImageData(0, 0, width, height);
  const filled = new Uint8ClampedArray(width * height);
  for (let i = 0; i < filled.length; i += 1) {
    if (imageData.data[i * 4 + 3] > 0) filled[i] = 1;
  }
  return filled;
}

export function buildFilledMaskForBbox(
  stroke: Stroke,
  bbox: { x: number; y: number; width: number; height: number },
) {
  const shifted: Stroke = {
    ...stroke,
    points: stroke.points.map((point) => ({
      x: point.x - bbox.x,
      y: point.y - bbox.y,
    })),
    bbox: { x: 0, y: 0, width: bbox.width, height: bbox.height },
  };
  return buildFilledMask(shifted, bbox.width, bbox.height);
}

const hexToRgb = (hex: string) => {
  const normalized = hex.replace("#", "");
  const value = normalized.length === 3
    ? normalized.split("").map((char) => char + char).join("")
    : normalized;
  const parsed = parseInt(value, 16);
  return {
    r: (parsed >> 16) & 0xff,
    g: (parsed >> 8) & 0xff,
    b: parsed & 0xff,
  };
};

export function paintMask(
  ctx: CanvasRenderingContext2D,
  mask: Uint8ClampedArray,
  bbox: { x: number; y: number; width: number; height: number },
  color: string,
  alpha: number,
) {
  const image = ctx.createImageData(bbox.width, bbox.height);
  const { r, g, b } = hexToRgb(color);
  const a = clamp(Math.round(alpha * 255), 0, 255);
  for (let i = 0; i < mask.length; i += 1) {
    if (mask[i] !== 1) continue;
    const offset = i * 4;
    image.data[offset] = r;
    image.data[offset + 1] = g;
    image.data[offset + 2] = b;
    image.data[offset + 3] = a;
  }
  ctx.putImageData(image, bbox.x, bbox.y);
}

export function clampBbox(
  bbox: { x: number; y: number; width: number; height: number },
  width: number,
  height: number,
) {
  const x = clamp(Math.floor(bbox.x), 0, width - 1);
  const y = clamp(Math.floor(bbox.y), 0, height - 1);
  const maxX = clamp(Math.ceil(bbox.x + bbox.width), 0, width);
  const maxY = clamp(Math.ceil(bbox.y + bbox.height), 0, height);
  return {
    x,
    y,
    width: Math.max(1, maxX - x),
    height: Math.max(1, maxY - y),
  };
}

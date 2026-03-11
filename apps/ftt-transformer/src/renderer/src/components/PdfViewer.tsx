import { useEffect, useMemo, useRef, useState } from "react";
import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist";
import { getDocument, GlobalWorkerOptions } from "pdfjs-dist";
import type { PenType, Stroke } from "@renderer/types";
import { buildFilledMaskForBbox, clampBbox, paintMask } from "@renderer/paint";

GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

const filePathToUrl = (filePath: string) => {
  if (filePath.startsWith("file://")) return filePath;
  const normalized = filePath.replace(/\\/g, "/");
  return encodeURI(`file://${normalized}`);
};

const loadPdf = async (filePath: string) => {
  if (filePath.startsWith("http://") || filePath.startsWith("https://")) {
    return getDocument({ url: filePath }).promise;
  }
  if (!window.ftt?.readFile) {
    const url = filePathToUrl(filePath);
    return getDocument({ url }).promise;
  }
  const buffer = await window.ftt.readFile(filePath);
  return getDocument({ data: new Uint8Array(buffer) }).promise;
};

const drawStroke = (
  ctx: CanvasRenderingContext2D,
  stroke: Stroke,
  color: string,
  filled: boolean,
) => {
  if (stroke.points.length < 2) return;
  ctx.strokeStyle = color;
  ctx.lineWidth = stroke.radiusPx * 2;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.beginPath();
  stroke.points.forEach((point, idx) => {
    if (idx === 0) ctx.moveTo(point.x, point.y);
    else ctx.lineTo(point.x, point.y);
  });
  ctx.stroke();
    if (filled) {
      ctx.fillStyle = `${color}22`;
      ctx.fillRect(stroke.bbox.x, stroke.bbox.y, stroke.bbox.width, stroke.bbox.height);
    }
};

const getColor = (pen: PenType) => {
  if (pen === "tesseract") return "#3b82f6";
  if (pen === "describe") return "#22c55e";
  return "#a855f7";
};

const findStrokeAt = (strokes: Stroke[], x: number, y: number) =>
  strokes.find(
    (stroke) =>
      x >= stroke.bbox.x &&
      x <= stroke.bbox.x + stroke.bbox.width &&
      y >= stroke.bbox.y &&
      y <= stroke.bbox.y + stroke.bbox.height,
  );

export function PdfViewer({
  fileId,
  filePath,
  strokes,
  activePen,
  radiusPx,
  unit,
  onAddStroke,
  onContextMenu,
  onPageCanvas,
}: {
  fileId: string;
  filePath: string;
  strokes: Stroke[];
  activePen: PenType;
  radiusPx: number;
  unit: "px" | "cm" | "mm";
  onAddStroke: (stroke: Stroke) => void;
  onContextMenu: (strokeId: string, x: number, y: number) => void;
  onPageCanvas?: (fileId: string, pageIndex: number, canvas: HTMLCanvasElement | null) => void;
}) {
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [pages, setPages] = useState<PDFPageProxy[]>([]);
  const [containerWidth, setContainerWidth] = useState(0);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    const updateSize = () => setContainerWidth(node.clientWidth);
    updateSize();
    const observer = new ResizeObserver(() => updateSize());
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    let canceled = false;
    setDoc(null);
    setPages([]);
    loadPdf(filePath)
      .then((pdf) => {
        if (canceled) return;
        setDoc(pdf);
        return Promise.all(
          Array.from({ length: pdf.numPages }, (_, idx) => pdf.getPage(idx + 1)),
        );
      })
      .then((pdfPages) => {
        if (!canceled && pdfPages) setPages(pdfPages);
      })
      .catch(() => {
        if (!canceled) setPages([]);
      });
    return () => {
      canceled = true;
    };
  }, [filePath]);

  const strokesByPage = useMemo(() => {
    const grouped = new Map<number, Stroke[]>();
    for (const stroke of strokes) {
      if (stroke.fileId !== fileId) continue;
      const pageList = grouped.get(stroke.pageIndex) || [];
      pageList.push(stroke);
      grouped.set(stroke.pageIndex, pageList);
    }
    return grouped;
  }, [strokes, fileId]);

  if (!doc) {
    return <div className="viewer-empty">Loading document...</div>;
  }

  return (
    <div className="pdf-scroll" ref={containerRef}>
      {pages.map((page, idx) => (
        <PdfPage
          key={page.pageNumber}
          fileId={fileId}
          pageIndex={idx}
          page={page}
          strokes={strokesByPage.get(idx) || []}
          containerWidth={containerWidth}
          pen={activePen}
          radiusPx={radiusPx}
          unit={unit}
          onAddStroke={(stroke) => onAddStroke(stroke)}
          onContextMenu={onContextMenu}
          onPageCanvas={onPageCanvas}
        />
      ))}
    </div>
  );
}

function PdfPage({
  fileId,
  page,
  pageIndex,
  strokes,
  containerWidth,
  pen,
  radiusPx,
  unit,
  onAddStroke,
  onContextMenu,
  onPageCanvas,
}: {
  fileId: string;
  page: PDFPageProxy;
  pageIndex: number;
  strokes: Stroke[];
  containerWidth: number;
  pen: PenType;
  radiusPx: number;
  unit: "px" | "cm" | "mm";
  onAddStroke: (stroke: Stroke) => void;
  onContextMenu: (strokeId: string, x: number, y: number) => void;
  onPageCanvas?: (fileId: string, pageIndex: number, canvas: HTMLCanvasElement | null) => void;
}) {
  const baseRef = useRef<HTMLCanvasElement | null>(null);
  const overlayRef = useRef<HTMLCanvasElement | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [currentPoints, setCurrentPoints] = useState<{ x: number; y: number }[]>([]);

  useEffect(() => {
    const canvas = baseRef.current;
    if (!canvas) return;
    const baseViewport = page.getViewport({ scale: 1 });
    const availableWidth = Math.max(200, containerWidth - 48);
    const scale = containerWidth > 0 ? Math.min(1.2, availableWidth / baseViewport.width) : 1;
    const viewport = page.getViewport({ scale });
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    page.render({ canvasContext: ctx, viewport });
    onPageCanvas?.(fileId, pageIndex, canvas);
  }, [page, fileId, pageIndex, onPageCanvas, containerWidth]);

  useEffect(() => {
    const overlay = overlayRef.current;
    if (!overlay) return;
    overlay.width = baseRef.current?.width || 0;
    overlay.height = baseRef.current?.height || 0;
    const ctx = overlay.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, overlay.width, overlay.height);
    for (const stroke of strokes) {
      drawStroke(ctx, stroke, getColor(stroke.pen), false);
      if (stroke.filled) {
        const safeBbox = clampBbox(stroke.bbox, overlay.width, overlay.height);
        const mask = buildFilledMaskForBbox(stroke, safeBbox);
        paintMask(ctx, mask, safeBbox, getColor(stroke.pen), 0.2);
      }
    }
    if (currentPoints.length > 1) {
      drawStroke(
        ctx,
        {
          id: "current",
          fileId: "",
          pageIndex,
          pen,
          points: currentPoints,
          radiusPx,
          unit,
          filled: false,
          bbox: { x: 0, y: 0, width: 0, height: 0 },
        },
        getColor(pen),
        false,
      );
    }
  }, [strokes, currentPoints, pen, radiusPx, unit, pageIndex]);

  const pointFromEvent = (
    clientX: number,
    clientY: number,
    target: HTMLCanvasElement,
  ) => {
    const rect = target.getBoundingClientRect();
    return { x: clientX - rect.left, y: clientY - rect.top };
  };

  const handlePointerDown = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (event.button !== 0) return;
    const point = pointFromEvent(event.clientX, event.clientY, event.currentTarget);
    setDrawing(true);
    setCurrentPoints([point]);
  };

  const handlePointerMove = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawing) return;
    const point = pointFromEvent(event.clientX, event.clientY, event.currentTarget);
    setCurrentPoints((prev) => [...prev, point]);
  };

  const handlePointerUp = () => {
    if (!drawing || currentPoints.length < 2) {
      setDrawing(false);
      setCurrentPoints([]);
      return;
    }
    const xs = currentPoints.map((p) => p.x);
    const ys = currentPoints.map((p) => p.y);
    const minX = Math.min(...xs);
    const minY = Math.min(...ys);
    const maxX = Math.max(...xs);
    const maxY = Math.max(...ys);
    const bbox = {
      x: minX - radiusPx,
      y: minY - radiusPx,
      width: maxX - minX + radiusPx * 2,
      height: maxY - minY + radiusPx * 2,
    };
    onAddStroke({
      id: crypto.randomUUID(),
      fileId,
      pageIndex,
      pen,
      points: currentPoints,
      radiusPx,
      unit,
      filled: false,
      bbox,
    });
    setDrawing(false);
    setCurrentPoints([]);
  };

  const handleContextMenu = (event: React.MouseEvent<HTMLCanvasElement>) => {
    event.preventDefault();
    const point = pointFromEvent(event.clientX, event.clientY, event.currentTarget);
    const hit = findStrokeAt(strokes, point.x, point.y);
    if (hit) {
      onContextMenu(hit.id, event.clientX, event.clientY);
    }
  };

  return (
    <div className="pdf-page">
      <canvas ref={baseRef} className="pdf-canvas" />
      <canvas
        ref={overlayRef}
        className="pdf-overlay"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
        onContextMenu={handleContextMenu}
      />
    </div>
  );
}

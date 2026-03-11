import { useEffect, useMemo, useRef, useState } from "react";
import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist";
import { getDocument, GlobalWorkerOptions } from "pdfjs-dist";
import type { PenType, Stroke } from "@renderer/types";

GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

const filePathToUrl = (filePath: string) => {
  if (filePath.startsWith("file://")) return filePath;
  return `file://${filePath.replace(/\\/g, "/")}`;
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

  useEffect(() => {
    let canceled = false;
    setDoc(null);
    setPages([]);
    const url = filePathToUrl(filePath);
    getDocument({ url })
      .promise.then((pdf) => {
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
    <div className="pdf-scroll">
      {pages.map((page, idx) => (
        <PdfPage
          key={page.pageNumber}
          fileId={fileId}
          pageIndex={idx}
          page={page}
          strokes={strokesByPage.get(idx) || []}
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
    const viewport = page.getViewport({ scale: 1.4 });
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    page.render({ canvasContext: ctx, viewport });
    onPageCanvas?.(fileId, pageIndex, canvas);
  }, [page, fileId, pageIndex, onPageCanvas]);

  useEffect(() => {
    const overlay = overlayRef.current;
    if (!overlay) return;
    overlay.width = baseRef.current?.width || 0;
    overlay.height = baseRef.current?.height || 0;
    const ctx = overlay.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, overlay.width, overlay.height);
    for (const stroke of strokes) {
      drawStroke(ctx, stroke, getColor(stroke.pen), stroke.filled);
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
    const bbox = {
      x: Math.min(...xs),
      y: Math.min(...ys),
      width: Math.max(...xs) - Math.min(...xs),
      height: Math.max(...ys) - Math.min(...ys),
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

import { useCallback, useEffect, useRef, useState } from "react";
import { PdfViewer } from "@renderer/components/PdfViewer";
import { HomePage } from "@renderer/components/HomePage";
import { SelectionPage } from "@renderer/components/SelectionPage";
import { ConvertingPage } from "@renderer/components/ConvertingPage";
import { FileSidebar } from "@renderer/components/FileSidebar";
import { PenBar, type PenConfig } from "@renderer/components/PenBar";
import { StrokeContextMenu } from "@renderer/components/StrokeContextMenu";
import { SaveModal } from "@renderer/components/SaveModal";
import { applyStrokeMask, buildFilledMaskForBbox, clampBbox } from "@renderer/paint";
import { useUndoRedo } from "@renderer/hooks/useUndoRedo";
import type { ConversionResult, ExtractionFlags, PenType, SourceFile, Stroke } from "@renderer/types";
import { CHART_MODELS } from "@renderer/types";

/* ── helpers ─────────────────────────────────────────────── */

const DEFAULT_PENS: Record<PenType, PenConfig> = {
  tesseract: { radiusPx: 18, unit: "px" },
  describe: { radiusPx: 14, unit: "px" },
  graph: { radiusPx: 16, unit: "px" },
};

const inferKind = (filePath: string) => {
  const ext = filePath.split(".").pop()?.toLowerCase() || "";
  if (ext === "pdf") return "pdf";
  if (["png", "jpg", "jpeg", "bmp", "gif", "tiff", "tif"].includes(ext)) return "image";
  if (ext === "docx") return "docx";
  if (ext === "pptx") return "pptx";
  if (ext === "xlsx") return "xlsx";
  return "other";
};

const baseName = (filePath: string) => {
  const parts = filePath.replace(/\\/g, "/").split("/");
  return parts[parts.length - 1] || filePath;
};

const normalizeFiles = (paths: string[]): SourceFile[] =>
  paths.map((filePath) => {
    const kind = inferKind(filePath);
    const selected = ["pdf", "image", "docx"].includes(kind);
    return {
      id: crypto.randomUUID(),
      path: filePath,
      name: baseName(filePath),
      kind,
      selected,
      fullExtraction: { tesseract: selected, python: !selected },
    };
  });

const buildProjectPayload = (name: string, files: SourceFile[], strokes: Stroke[]) => ({
  name,
  createdAt: new Date().toISOString(),
  uploads: files.map((f) => f.path),
  files: files.map((f) => ({
    id: f.id,
    name: f.name,
    path: f.path,
    kind: f.kind,
    convertedPath: f.convertedPath || "",
    fullExtraction: f.fullExtraction,
  })),
  strokes,
});

const strokeFileName = (file: SourceFile | undefined, stroke: Stroke) => {
  const name = file?.name ? file.name.replace(/\.[^.]+$/, "") : "file";
  return `${name}_${stroke.id}.png`;
};

/* ── App ─────────────────────────────────────────────────── */

export default function App() {
  const [step, setStep] = useState<"home" | "select" | "converting" | "workspace">("home");
  const [files, setFiles] = useState<SourceFile[]>([]);
  const [activeFileId, setActiveFileId] = useState<string | null>(null);
  const [activePen, setActivePen] = useState<PenType>("tesseract");
  const [penSettings, setPenSettings] = useState(DEFAULT_PENS);
  const [progress, setProgress] = useState({ current: 0, total: 0, file: "" });
  const [strokeCtx, setStrokeCtx] = useState<{ strokeId: string; x: number; y: number } | null>(null);
  const [showSave, setShowSave] = useState(false);
  const [saveName] = useState("assignment");

  const pageCanvases = useRef<Map<string, HTMLCanvasElement>>(new Map());
  const viewerBodyRef = useRef<HTMLDivElement | null>(null);
  const [viewerWidth, setViewerWidth] = useState(0);

  const { present: strokes, set: setStrokes, undo, redo, canUndo, canRedo } =
    useUndoRedo<Stroke[]>([]);

  /* keyboard shortcuts */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        e.shiftKey ? redo() : undo();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [undo, redo]);

  /* conversion progress */
  useEffect(() => {
    const handler = (_: unknown, p: unknown) => {
      const d = p as { current: number; total: number; file: string };
      setProgress({ current: d.current, total: d.total, file: baseName(d.file) });
    };
    window.ftt?.onConvertProgress(handler);
    return () => window.ftt?.offConvertProgress?.(handler);
  }, []);

  /* viewer width tracking */
  useEffect(() => {
    const node = viewerBodyRef.current;
    if (!node) return;
    const update = () => setViewerWidth(node.clientWidth);
    update();
    const obs = new ResizeObserver(update);
    obs.observe(node);
    return () => obs.disconnect();
  }, [step]);

  const activeFile = files.find((f) => f.id === activeFileId) || null;

  /* ── file management ──────────────────────────────────── */

  const handleAddFiles = useCallback((paths: string[]) => {
    if (!paths.length) return;
    setFiles((prev) => [...prev, ...normalizeFiles(paths)]);
  }, []);

  const handleSelectFiles = useCallback(async () => {
    const result = await window.ftt?.selectFiles();
    if (result) handleAddFiles(result);
  }, [handleAddFiles]);

  const updateSelection = useCallback((id: string, selected: boolean) => {
    setFiles((prev) =>
      prev.map((f) =>
        f.id === id
          ? { ...f, selected, fullExtraction: { tesseract: selected, python: !selected } }
          : f,
      ),
    );
  }, []);

  const updateExtractionFlags = useCallback((id: string, flags: Partial<ExtractionFlags>) => {
    setFiles((prev) =>
      prev.map((f) =>
        f.id === id
          ? { ...f, fullExtraction: { ...f.fullExtraction, ...flags } }
          : f,
      ),
    );
  }, []);

  /* ── conversion ───────────────────────────────────────── */

  const handleConfirmSelection = useCallback(async () => {
    const selected = files.filter((f) => f.selected);
    if (!selected.length) return;
    setStep("converting");
    const requestId = crypto.randomUUID();
    const results = (await window.ftt?.convertFiles({
      requestId,
      files: selected.map((f) => f.path),
    })) as ConversionResult[];

    setFiles((prev) =>
      prev.map((f) => {
        const match = results.find((r) => r.source === f.path);
        if (!match) return f;
        const ck = match.kind === "pdf" ? "pdf" as const : match.kind === "image" ? "image" as const : "other" as const;
        return { ...f, convertedPath: match.converted, convertedKind: ck, error: match.error };
      }),
    );

    const firstConverted = results.find((r) => r.converted)?.source;
    const first = selected.find((f) => f.path === firstConverted) || selected[0];
    setActiveFileId(first?.id || null);
    setStep("workspace");
  }, [files]);

  /* ── stroke management ────────────────────────────────── */

  const handleAddStroke = useCallback(
    (stroke: Stroke) => {
      if (!activeFile) return;
      const newStroke = { ...stroke, fileId: activeFile.id };
      if (stroke.pen === "graph" && !stroke.graphModels) {
        newStroke.graphModels = CHART_MODELS.map((m) => m.id);
      }
      setStrokes([...strokes, newStroke]);
    },
    [activeFile, strokes, setStrokes],
  );

  const updateStroke = useCallback(
    (strokeId: string, update: Partial<Stroke>) => {
      setStrokes(strokes.map((s) => (s.id === strokeId ? { ...s, ...update } : s)));
      setStrokeCtx(null);
    },
    [strokes, setStrokes],
  );

  const deleteStroke = useCallback(
    (strokeId: string) => {
      setStrokes(strokes.filter((s) => s.id !== strokeId));
      setStrokeCtx(null);
    },
    [strokes, setStrokes],
  );

  const registerPageCanvas = useCallback(
    (fileId: string, pageIndex: number, canvas: HTMLCanvasElement | null) => {
      if (canvas) pageCanvases.current.set(`${fileId}:${pageIndex}`, canvas);
    },
    [],
  );

  /* ── pen settings ─────────────────────────────────────── */

  const updatePenConfig = useCallback((pen: PenType, config: Partial<PenConfig>) => {
    setPenSettings((prev) => ({ ...prev, [pen]: { ...prev[pen], ...config } }));
  }, []);

  /* ── save & export ────────────────────────────────────── */

  const handleSave = useCallback(
    async (opts: { name: string; format: "selections" | "full"; location: string }) => {
      const project = buildProjectPayload(opts.name, files, strokes);
      await window.ftt?.saveProject({
        project,
        targetDir: opts.location,
        includeUploads: opts.format === "full",
      });
      setShowSave(false);
    },
    [files, strokes],
  );

  const handleExport = useCallback(async () => {
    const folder = await window.ftt?.selectFolder();
    if (!folder) return;
    const project = buildProjectPayload(saveName, files, strokes);
    const regions = strokes.map((stroke) => {
      const key = `${stroke.fileId}:${stroke.pageIndex}`;
      const canvas = pageCanvases.current.get(key);
      const name = strokeFileName(files.find((f) => f.id === stroke.fileId), stroke);
      if (!canvas) return { pen: stroke.pen, name, dataUrl: "", graphModels: stroke.graphModels };
      const ctx = canvas.getContext("2d");
      if (!ctx) return { pen: stroke.pen, name, dataUrl: "", graphModels: stroke.graphModels };
      const safeBbox = clampBbox(stroke.bbox, canvas.width, canvas.height);
      const cropImage = ctx.getImageData(safeBbox.x, safeBbox.y, safeBbox.width, safeBbox.height);
      const mask = buildFilledMaskForBbox(stroke, safeBbox);
      const cropCanvas = applyStrokeMask(cropImage, mask);
      if (!cropCanvas) return { pen: stroke.pen, name, dataUrl: "", graphModels: stroke.graphModels };
      return { pen: stroke.pen, name, dataUrl: cropCanvas.toDataURL("image/png"), graphModels: stroke.graphModels };
    });
    const targetZip = `${folder}/${saveName || "ftt"}.zip`;
    await window.ftt?.exportProject({ project, regions, targetZip });
  }, [files, strokes, saveName]);

  /* ── render ───────────────────────────────────────────── */

  if (step === "home") {
    return (
      <HomePage
        files={files}
        onAddFiles={handleAddFiles}
        onSelectFiles={handleSelectFiles}
        onUpdateSelection={updateSelection}
        onConfirm={() => setStep("select")}
      />
    );
  }

  if (step === "select") {
    return (
      <SelectionPage
        files={files}
        onUpdateSelection={updateSelection}
        onConfirm={handleConfirmSelection}
        onBack={() => setStep("home")}
      />
    );
  }

  if (step === "converting") {
    return (
      <ConvertingPage
        current={progress.current}
        total={progress.total}
        fileName={progress.file}
      />
    );
  }

  const ctxStroke = strokeCtx ? strokes.find((s) => s.id === strokeCtx.strokeId) : null;

  return (
    <div className="app workspace" onClick={() => setStrokeCtx(null)}>
      <FileSidebar
        files={files}
        activeFileId={activeFileId}
        onSelectFile={setActiveFileId}
        onUpdateFlags={updateExtractionFlags}
      />

      <main className="viewer">
        <div className="viewer-header">
          <div className="viewer-header-left">
            <h2>{activeFile?.name || "Select a file"}</h2>
            <span className="muted">
              {canUndo ? "⌘Z undo" : ""} {canRedo ? "⇧⌘Z redo" : ""}
            </span>
          </div>
          <div className="viewer-actions">
            <button className="ghost" onClick={() => setShowSave(true)}>
              Save
            </button>
            <button className="primary" onClick={handleExport}>
              Export
            </button>
          </div>
        </div>

        <div className="viewer-body" ref={viewerBodyRef}>
          {!activeFile && <div className="viewer-empty">Select a file to annotate.</div>}
          {activeFile?.convertedPath && (
            <PdfViewer
              fileId={activeFile.id}
              filePath={activeFile.convertedPath}
              fileKind={activeFile.convertedKind || "pdf"}
              strokes={strokes}
              activePen={activePen}
              radiusPx={penSettings[activePen].radiusPx}
              unit={penSettings[activePen].unit}
              containerWidth={viewerWidth}
              onAddStroke={handleAddStroke}
              onContextMenu={(id, x, y) => setStrokeCtx({ strokeId: id, x, y })}
              onPageCanvas={registerPageCanvas}
            />
          )}
        </div>
      </main>

      <PenBar
        activePen={activePen}
        penSettings={penSettings}
        onSelectPen={setActivePen}
        onUpdatePenConfig={updatePenConfig}
      />

      {strokeCtx && ctxStroke && (
        <StrokeContextMenu
          stroke={ctxStroke}
          x={strokeCtx.x}
          y={strokeCtx.y}
          onChangePen={(pen) => updateStroke(strokeCtx.strokeId, { pen })}
          onToggleFill={() => updateStroke(strokeCtx.strokeId, { filled: !ctxStroke.filled })}
          onDelete={() => deleteStroke(strokeCtx.strokeId)}
          onClose={() => setStrokeCtx(null)}
          onUpdateGraphModels={(models) => updateStroke(strokeCtx.strokeId, { graphModels: models })}
        />
      )}

      {showSave && (
        <SaveModal
          defaultName={saveName}
          onSave={handleSave}
          onClose={() => setShowSave(false)}
          onSelectFolder={async () => (await window.ftt?.selectFolder()) || ""}
        />
      )}
    </div>
  );
}

import { useEffect, useMemo, useRef, useState } from "react";
import { PdfViewer } from "@renderer/components/PdfViewer";
import { applyStrokeMask, buildFilledMaskForBbox, clampBbox } from "@renderer/paint";
import { useUndoRedo } from "@renderer/hooks/useUndoRedo";
import type { ConversionResult, PenType, SourceFile, Stroke } from "@renderer/types";

const DEFAULT_PENS: Record<PenType, { radiusPx: number; unit: "px" | "cm" | "mm" }> = {
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

const formatPenLabel = (pen: PenType) => {
  if (pen === "tesseract") return "Tesseract Image > Text";
  if (pen === "describe") return "Image Describe";
  return "Graph Data Extract";
};

const normalizeFiles = (paths: string[]) =>
  paths.map((filePath) => {
    const kind = inferKind(filePath);
    const selected = ["pdf", "image", "docx"].includes(kind);
    return {
      id: crypto.randomUUID(),
      path: filePath,
      name: baseName(filePath),
      kind,
      selected,
      fullExtraction: {
        tesseract: selected,
        python: !selected,
      },
    } satisfies SourceFile;
  });

const buildProjectPayload = (name: string, files: SourceFile[], strokes: Stroke[]) => {
  return {
    name,
    createdAt: new Date().toISOString(),
    uploads: files.map((file) => file.path),
    files: files.map((file) => ({
      id: file.id,
      name: file.name,
      path: file.path,
      kind: file.kind,
      convertedPath: file.convertedPath || "",
      fullExtraction: file.fullExtraction,
    })),
    strokes,
  };
};

const getStrokeFileName = (file: SourceFile | undefined, stroke: Stroke) => {
  const name = file?.name ? file.name.replace(/\.[^.]+$/, "") : "file";
  return `${name}_${stroke.id}.png`;
};

export default function App() {
  const [step, setStep] = useState<"home" | "select" | "converting" | "workspace">("home");
  const [files, setFiles] = useState<SourceFile[]>([]);
  const [activeFileId, setActiveFileId] = useState<string | null>(null);
  const [activePen, setActivePen] = useState<PenType>("tesseract");
  const [penSettings, setPenSettings] = useState(DEFAULT_PENS);
  const [progress, setProgress] = useState({ current: 0, total: 0, file: "", status: "" });
  const [contextMenu, setContextMenu] = useState<{ strokeId: string; x: number; y: number } | null>(
    null,
  );
  const [showSave, setShowSave] = useState(false);
  const [saveName, setSaveName] = useState("assignment");
  const [saveFormat, setSaveFormat] = useState<"selections" | "full">("selections");
  const [saveLocation, setSaveLocation] = useState<string>("");
  const pageCanvases = useRef<Map<string, HTMLCanvasElement>>(new Map());
  const viewerBodyRef = useRef<HTMLDivElement | null>(null);
  const [viewerWidth, setViewerWidth] = useState(0);

  const {
    present: strokes,
    set: setStrokes,
    undo,
    redo,
    canUndo,
    canRedo,
  } = useUndoRedo<Stroke[]>([]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") {
        event.preventDefault();
        if (event.shiftKey) redo();
        else undo();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [undo, redo]);

  useEffect(() => {
    const handler = (_event: unknown, payload: unknown) => {
      const data = payload as { current: number; total: number; file: string; status: string };
      setProgress({
        current: data.current,
        total: data.total,
        file: baseName(data.file),
        status: data.status,
      });
    };
    window.ftt?.onConvertProgress(handler);
    return () => {
      window.ftt?.offConvertProgress?.(handler);
    };
  }, []);

  useEffect(() => {
    const node = viewerBodyRef.current;
    if (!node) return;
    const updateSize = () => setViewerWidth(node.clientWidth);
    updateSize();
    const observer = new ResizeObserver(() => updateSize());
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const activeFile = files.find((file) => file.id === activeFileId) || null;

  const handleAddFiles = (paths: string[]) => {
    if (!paths.length) return;
    setFiles((prev) => [...prev, ...normalizeFiles(paths)]);
  };

  const handleSelectFiles = async () => {
    const result = await window.ftt?.selectFiles();
    if (result) handleAddFiles(result);
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const dropped = Array.from(event.dataTransfer.files).map((file) => file.path);
    handleAddFiles(dropped);
  };

  const updateSelection = (id: string, selected: boolean) => {
    setFiles((prev) =>
      prev.map((file) =>
        file.id === id
          ? {
              ...file,
              selected,
              fullExtraction: {
                tesseract: selected,
                python: !selected,
              },
            }
          : file,
      ),
    );
  };

  const handleConfirmSelection = async () => {
    const selected = files.filter((file) => file.selected);
    if (selected.length === 0) return;
    setStep("converting");
    const requestId = crypto.randomUUID();
    const results = (await window.ftt?.convertFiles({
      requestId,
      files: selected.map((file) => file.path),
    })) as ConversionResult[];

    setFiles((prev) =>
      prev.map((file) => {
        const match = results.find((result) => result.source === file.path);
        if (!match) return file;
        return {
          ...file,
          convertedPath: match.converted,
          convertedKind: match.kind === "pdf" ? "pdf" : "other",
          error: match.error,
        };
      }),
    );

    const firstConverted = results.find((result) => result.converted)?.source;
    const firstFile =
      selected.find((file) => file.path === firstConverted) || selected[0];
    setActiveFileId(firstFile?.id || null);
    setStep("workspace");
  };

  const handleAddStroke = (stroke: Stroke) => {
    if (!activeFile) return;
    const fullStroke = { ...stroke, fileId: activeFile.id };
    setStrokes([...strokes, fullStroke]);
  };

  const handleContextMenu = (strokeId: string, x: number, y: number) => {
    setContextMenu({ strokeId, x, y });
  };

  const applyStrokeUpdate = (strokeId: string, update: Partial<Stroke>) => {
    setStrokes(
      strokes.map((stroke) =>
        stroke.id === strokeId ? { ...stroke, ...update } : stroke,
      ),
    );
    setContextMenu(null);
  };

  const registerPageCanvas = (fileId: string, pageIndex: number, canvas: HTMLCanvasElement | null) => {
    if (!canvas) return;
    pageCanvases.current.set(`${fileId}:${pageIndex}`, canvas);
  };

  const handleSave = async () => {
    if (!saveLocation) {
      const folder = await window.ftt?.selectFolder();
      if (folder) setSaveLocation(folder);
      return;
    }
    const project = buildProjectPayload(saveName, files, strokes);
    await window.ftt?.saveProject({
      project,
      targetDir: saveLocation,
      includeUploads: saveFormat === "full",
    });
    setShowSave(false);
  };

  const handleExport = async () => {
    const folder = await window.ftt?.selectFolder();
    if (!folder) return;
    const project = buildProjectPayload(saveName, files, strokes);
    const regions = strokes.map((stroke) => {
      const key = `${stroke.fileId}:${stroke.pageIndex}`;
      const canvas = pageCanvases.current.get(key);
      if (!canvas) {
        return {
          pen: stroke.pen,
          name: getStrokeFileName(files.find((file) => file.id === stroke.fileId), stroke),
          dataUrl: "",
        };
      }
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        return {
          pen: stroke.pen,
          name: getStrokeFileName(files.find((file) => file.id === stroke.fileId), stroke),
          dataUrl: "",
        };
      }
      const safeBbox = clampBbox(stroke.bbox, canvas.width, canvas.height);
      const cropImage = ctx.getImageData(safeBbox.x, safeBbox.y, safeBbox.width, safeBbox.height);
      const mask = buildFilledMaskForBbox(stroke, safeBbox);
      const cropCanvas = applyStrokeMask(cropImage, mask);
      if (!cropCanvas) {
        return {
          pen: stroke.pen,
          name: getStrokeFileName(files.find((file) => file.id === stroke.fileId), stroke),
          dataUrl: "",
        };
      }
      return {
        pen: stroke.pen,
        name: getStrokeFileName(files.find((file) => file.id === stroke.fileId), stroke),
        dataUrl: cropCanvas.toDataURL("image/png"),
      };
    });
    const targetZip = `${folder}/${saveName || "ftt"}.zip`;
    await window.ftt?.exportProject({ project, regions, targetZip });
  };

  const workspaceEmpty = !activeFile;

  if (step === "home") {
    return (
      <div className="app">
        <div className="home">
          <div
            className="drop-zone"
            onDrop={handleDrop}
            onDragOver={(event) => event.preventDefault()}
            onClick={handleSelectFiles}
          >
            <h2>Paste files in here from clipboard or drop files in</h2>
            <p>Click to open file selector</p>
          </div>
          {files.length > 0 && (
            <div className="selection-inline">
              <header>
                <h3>Selected files</h3>
                <span className="muted">{files.length} total</span>
              </header>
              <div className="selection-list">
                {files.map((file) => (
                  <label key={file.id} className="selection-item">
                    <input
                      type="checkbox"
                      checked={file.selected}
                      onChange={(event) => updateSelection(file.id, event.target.checked)}
                    />
                    <span>{file.name}</span>
                    <span className="chip">{file.kind}</span>
                  </label>
                ))}
              </div>
              <button className="primary" onClick={() => setStep("select")}>
                Confirm
              </button>
            </div>
          )}
        </div>
      </div>
    );
  }

  if (step === "select") {
    return (
      <div className="app">
        <div className="selection">
          <header>
            <h2>Select files to convert for annotation</h2>
            <p>Default: PDF, images, DOCX</p>
          </header>
          <div className="selection-list">
            {files.map((file) => (
              <label key={file.id} className="selection-item">
                <input
                  type="checkbox"
                  checked={file.selected}
                  onChange={(event) => updateSelection(file.id, event.target.checked)}
                />
                <span>{file.name}</span>
                <span className="chip">{file.kind}</span>
              </label>
            ))}
          </div>
          <button className="primary" onClick={handleConfirmSelection}>
            Confirm selection
          </button>
        </div>
      </div>
    );
  }

  if (step === "converting") {
    return (
      <div className="app">
        <div className="loading">
          <h2>Converting files</h2>
          <p>
            {progress.current} of {progress.total} — {progress.file}
          </p>
          <div className="progress">
            <div
              className="progress-bar"
              style={{ width: `${(progress.current / Math.max(progress.total, 1)) * 100}%` }}
            />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app workspace" onClick={() => setContextMenu(null)}>
      <aside className="sidebar">
        <h3>Files</h3>
        <div className="file-list">
          {files
            .filter((file) => file.selected)
            .map((file) => (
              <div
                key={file.id}
                className={`file-card ${file.id === activeFileId ? "active" : ""}`}
                onClick={() => setActiveFileId(file.id)}
              >
                <div className="file-title">{file.name}</div>
                <div className="file-tags">
                  <label>
                    <input
                      type="checkbox"
                      checked={file.fullExtraction.tesseract}
                      onChange={(event) =>
                        setFiles((prev) =>
                          prev.map((item) =>
                            item.id === file.id
                              ? {
                                  ...item,
                                  fullExtraction: {
                                    ...item.fullExtraction,
                                    tesseract: event.target.checked,
                                  },
                                }
                              : item,
                          ),
                        )
                      }
                    />
                    Tesseract
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={file.fullExtraction.python}
                      onChange={(event) =>
                        setFiles((prev) =>
                          prev.map((item) =>
                            item.id === file.id
                              ? {
                                  ...item,
                                  fullExtraction: {
                                    ...item.fullExtraction,
                                    python: event.target.checked,
                                  },
                                }
                              : item,
                          ),
                        )
                      }
                    />
                    Python
                  </label>
                </div>
              </div>
            ))}
        </div>
      </aside>

      <main className="viewer">
        <div className="viewer-header">
          <div>
            <h2>{activeFile?.name || "Select a file"}</h2>
            <span className="muted">Undo: {canUndo ? "Ready" : "—"} · Redo: {canRedo ? "Ready" : "—"}</span>
          </div>
          <div className="viewer-actions">
            <button onClick={() => setShowSave(true)}>Save</button>
            <button className="primary" onClick={handleExport}>
              Export
            </button>
          </div>
        </div>

        <div className="viewer-body" ref={viewerBodyRef}>
          {workspaceEmpty && <div className="viewer-empty">Select a file to annotate.</div>}
          {!workspaceEmpty && activeFile?.convertedPath && (
            <PdfViewer
              fileId={activeFile.id}
              filePath={activeFile.convertedPath}
              strokes={strokes}
              activePen={activePen}
              radiusPx={penSettings[activePen].radiusPx}
              unit={penSettings[activePen].unit}
              containerWidth={viewerWidth}
              onAddStroke={handleAddStroke}
              onContextMenu={handleContextMenu}
              onPageCanvas={registerPageCanvas}
            />
          )}
        </div>
      </main>

      <aside className="penbar">
        <h3>Tools</h3>
        {(["tesseract", "describe", "graph"] as PenType[]).map((pen) => (
          <button
            key={pen}
            className={`pen-button ${activePen === pen ? "active" : ""}`}
            onClick={() => setActivePen(pen)}
          >
            <span className={`pen-dot ${pen}`} />
            {formatPenLabel(pen)}
          </button>
        ))}
      </aside>

      {contextMenu && (
        <div
          className="context-menu"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <div className="menu-title">Change Pen Type</div>
          {(["tesseract", "describe", "graph"] as PenType[]).map((pen) => (
            <button
              key={pen}
              onClick={() => applyStrokeUpdate(contextMenu.strokeId, { pen })}
            >
              {formatPenLabel(pen)}
            </button>
          ))}
          <div className="menu-divider" />
          <button
            onClick={() =>
              applyStrokeUpdate(contextMenu.strokeId, {
                filled: !strokes.find((stroke) => stroke.id === contextMenu.strokeId)?.filled,
              })
            }
          >
            Fill Region Inside
          </button>
        </div>
      )}

      {showSave && (
        <div className="modal-backdrop" onClick={() => setShowSave(false)}>
          <div className="modal" onClick={(event) => event.stopPropagation()}>
            <h3>Save Draft Project</h3>
            <label>
              Name
              <input value={saveName} onChange={(event) => setSaveName(event.target.value)} />
            </label>
            <label>
              Save Format
              <select value={saveFormat} onChange={(event) => setSaveFormat(event.target.value as "selections" | "full")}>
                <option value="selections">Selections only + file paths</option>
                <option value="full">Full files + selections</option>
              </select>
            </label>
            <label>
              Location
              <div className="row">
                <input value={saveLocation} onChange={(event) => setSaveLocation(event.target.value)} />
                <button onClick={async () => setSaveLocation((await window.ftt?.selectFolder()) || "")}>Choose</button>
              </div>
            </label>
            <div className="modal-actions">
              <button onClick={() => setShowSave(false)}>Cancel</button>
              <button className="primary" onClick={handleSave}>Confirm</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

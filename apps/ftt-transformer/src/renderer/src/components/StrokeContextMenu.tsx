import type { PenType, Stroke } from "@renderer/types";
import { CHART_MODELS } from "@renderer/types";
import { useEffect, useRef, useState } from "react";

const PEN_LABELS: Record<PenType, string> = {
  tesseract: "OCR Text Extraction",
  describe: "Image Describe",
  graph: "Graph Data Extract",
};

export function StrokeContextMenu({
  stroke,
  x,
  y,
  onChangePen,
  onToggleFill,
  onDelete,
  onClose,
  onUpdateGraphModels,
}: {
  stroke: Stroke;
  x: number;
  y: number;
  onChangePen: (pen: PenType) => void;
  onToggleFill: () => void;
  onDelete: () => void;
  onClose: () => void;
  onUpdateGraphModels?: (models: string[]) => void;
}) {
  const pens: PenType[] = ["tesseract", "describe", "graph"];
  const [expandedModel, setExpandedModel] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ left: x, top: y });

  useEffect(() => {
    const el = menuRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let left = x;
    let top = y;
    if (left + rect.width > vw) left = Math.max(0, vw - rect.width - 8);
    if (top + rect.height > vh) top = Math.max(0, vh - rect.height - 8);
    setPos({ left, top });
  }, [x, y]);

  const currentModels = stroke.graphModels ?? CHART_MODELS.map((m) => m.id);

  const toggleModel = (modelId: string) => {
    const updated = currentModels.includes(modelId)
      ? currentModels.filter((m) => m !== modelId)
      : [...currentModels, modelId];
    // Ensure at least one model stays enabled
    if (updated.length === 0) return;
    onUpdateGraphModels?.(updated);
  };

  return (
    <div ref={menuRef} className="context-menu" style={{ left: pos.left, top: pos.top }} onClick={(e) => e.stopPropagation()}>
      <div className="menu-title">
        Change Pen Type <span className="muted">(current: {PEN_LABELS[stroke.pen]})</span>
      </div>
      {pens.map((pen) => (
        <button
          key={pen}
          className={pen === stroke.pen ? "menu-active" : ""}
          onClick={() => {
            onChangePen(pen);
            onClose();
          }}
        >
          <span className="pen-dot-inline" style={{ background: pen === "tesseract" ? "#3b82f6" : pen === "describe" ? "#22c55e" : "#a855f7" }} />
          {PEN_LABELS[pen]}
        </button>
      ))}

      {stroke.pen === "graph" && (
        <>
          <div className="menu-divider" />
          <div className="menu-title">Graph Extraction Models</div>
          {CHART_MODELS.map((model) => {
            const enabled = currentModels.includes(model.id);
            const isExpanded = expandedModel === model.id;
            return (
              <div key={model.id} className="model-picker-item">
                <label className="menu-check model-row">
                  <input
                    type="checkbox"
                    checked={enabled}
                    onChange={() => toggleModel(model.id)}
                  />
                  <span className="model-label">
                    <strong>{model.label}</strong>
                    <span className="muted model-desc">{model.description}</span>
                  </span>
                  <button
                    className="model-info-toggle"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setExpandedModel(isExpanded ? null : model.id);
                    }}
                    title="Show strengths and weaknesses"
                  >
                    {isExpanded ? "Hide" : "Info"}
                  </button>
                </label>
                {isExpanded && (
                  <div className="model-details">
                    <div className="model-section">
                      <span className="model-section-label good">Good at:</span>
                      <ul>
                        {model.strengths.map((s, i) => (
                          <li key={i}>{s}</li>
                        ))}
                      </ul>
                    </div>
                    <div className="model-section">
                      <span className="model-section-label bad">Bad at:</span>
                      <ul>
                        {model.weaknesses.map((w, i) => (
                          <li key={i}>{w}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </>
      )}

      <div className="menu-divider" />
      <button
        onClick={() => {
          onToggleFill();
          onClose();
        }}
      >
        {stroke.filled ? "Unfill Region Inside" : "Fill Region Inside"}
      </button>
      <div className="menu-divider" />
      <button
        className="menu-danger"
        onClick={() => {
          onDelete();
          onClose();
        }}
      >
        Delete Drawing
      </button>
    </div>
  );
}

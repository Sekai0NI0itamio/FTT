import { useState } from "react";
import type { PenType } from "@renderer/types";

export type PenConfig = {
  radiusPx: number;
  unit: "px" | "cm" | "mm";
};

const PEN_COLORS: Record<PenType, string> = {
  tesseract: "#3b82f6",
  describe: "#22c55e",
  graph: "#a855f7",
};

const PEN_LABELS: Record<PenType, string> = {
  tesseract: "Tesseract Image → Text",
  describe: "Image Describe",
  graph: "Graph Data Extract",
};

const PEN_NUMBERS: Record<PenType, number> = {
  tesseract: 1,
  describe: 2,
  graph: 3,
};

export function PenBar({
  activePen,
  penSettings,
  onSelectPen,
  onUpdatePenConfig,
}: {
  activePen: PenType;
  penSettings: Record<PenType, PenConfig>;
  onSelectPen: (pen: PenType) => void;
  onUpdatePenConfig: (pen: PenType, config: Partial<PenConfig>) => void;
}) {
  const [expandedPen, setExpandedPen] = useState<PenType | null>(null);
  const pens: PenType[] = ["tesseract", "describe", "graph"];

  const toggleExpand = (pen: PenType) => {
    setExpandedPen(expandedPen === pen ? null : pen);
  };

  return (
    <aside className="penbar">
      <h3>Drawing Tools</h3>
      {pens.map((pen) => {
        const config = penSettings[pen];
        const isActive = activePen === pen;
        const isExpanded = expandedPen === pen;
        return (
          <div key={pen} className="pen-group">
            <button
              className={`pen-button ${isActive ? "active" : ""}`}
              onClick={() => onSelectPen(pen)}
            >
              <span
                className="pen-dot"
                style={{ background: PEN_COLORS[pen] }}
              />
              <span className="pen-label">
                <strong>Pen {PEN_NUMBERS[pen]}</strong>
                <span className="pen-desc">{PEN_LABELS[pen]}</span>
              </span>
            </button>
            <button
              className="pen-config-toggle"
              onClick={() => toggleExpand(pen)}
              title="Configure pen radius"
            >
              ⚙
            </button>
            {isExpanded && (
              <div className="pen-config">
                <label className="pen-config-row">
                  <span>Radius</span>
                  <input
                    type="number"
                    min={1}
                    max={200}
                    value={config.radiusPx}
                    onChange={(e) =>
                      onUpdatePenConfig(pen, {
                        radiusPx: Math.max(1, parseInt(e.target.value) || 1),
                      })
                    }
                  />
                </label>
                <label className="pen-config-row">
                  <span>Unit</span>
                  <select
                    value={config.unit}
                    onChange={(e) =>
                      onUpdatePenConfig(pen, {
                        unit: e.target.value as "px" | "cm" | "mm",
                      })
                    }
                  >
                    <option value="px">Pixels</option>
                    <option value="cm">Centimeters</option>
                    <option value="mm">Millimeters</option>
                  </select>
                </label>
              </div>
            )}
          </div>
        );
      })}
    </aside>
  );
}

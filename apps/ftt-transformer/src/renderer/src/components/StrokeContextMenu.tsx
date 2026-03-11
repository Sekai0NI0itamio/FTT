import type { PenType, Stroke } from "@renderer/types";

const PEN_LABELS: Record<PenType, string> = {
  tesseract: "Tesseract Image → Text",
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
}: {
  stroke: Stroke;
  x: number;
  y: number;
  onChangePen: (pen: PenType) => void;
  onToggleFill: () => void;
  onDelete: () => void;
  onClose: () => void;
}) {
  const pens: PenType[] = ["tesseract", "describe", "graph"];

  return (
    <div className="context-menu" style={{ left: x, top: y }} onClick={(e) => e.stopPropagation()}>
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

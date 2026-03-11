import type { SourceFile } from "@renderer/types";

export function SelectionPage({
  files,
  onUpdateSelection,
  onConfirm,
  onBack,
}: {
  files: SourceFile[];
  onUpdateSelection: (id: string, selected: boolean) => void;
  onConfirm: () => void;
  onBack: () => void;
}) {
  const selectedCount = files.filter((f) => f.selected).length;

  return (
    <div className="app">
      <div className="selection">
        <header className="selection-page-header">
          <div>
            <h2>Select files to convert for annotation</h2>
            <p className="muted">
              PDF, image, and Word documents are selected by default.
              Uncheck files you don't want to annotate.
            </p>
          </div>
          <button className="ghost" onClick={onBack}>
            ← Back
          </button>
        </header>

        <div className="selection-list">
          {files.map((file) => (
            <label key={file.id} className="selection-item">
              <input
                type="checkbox"
                checked={file.selected}
                onChange={(e) => onUpdateSelection(file.id, e.target.checked)}
              />
              <span className="selection-name">{file.name}</span>
              <span className={`chip chip-${file.kind}`}>{file.kind}</span>
            </label>
          ))}
        </div>

        <div className="selection-footer">
          <span className="muted">{selectedCount} of {files.length} selected</span>
          <button
            className="primary"
            onClick={onConfirm}
            disabled={selectedCount === 0}
          >
            Confirm Selection
          </button>
        </div>
      </div>
    </div>
  );
}

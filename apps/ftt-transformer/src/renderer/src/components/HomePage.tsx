import type { SourceFile } from "@renderer/types";

export function HomePage({
  files,
  onAddFiles,
  onSelectFiles,
  onUpdateSelection,
  onConfirm,
}: {
  files: SourceFile[];
  onAddFiles: (paths: string[]) => void;
  onSelectFiles: () => void;
  onUpdateSelection: (id: string, selected: boolean) => void;
  onConfirm: () => void;
}) {
  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const dropped = Array.from(event.dataTransfer.files).map((f) => (f as File & { path: string }).path);
    onAddFiles(dropped);
  };

  const handlePaste = (event: React.ClipboardEvent<HTMLDivElement>) => {
    const pasted = Array.from(event.clipboardData.files).map((f) => (f as File & { path: string }).path);
    if (pasted.length) onAddFiles(pasted);
  };

  return (
    <div className="app">
      <div className="home">
        <div
          className="drop-zone"
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          onPaste={handlePaste}
          onClick={onSelectFiles}
          tabIndex={0}
        >
          <div className="drop-icon">📂</div>
          <h2>Paste files from clipboard or drop files here</h2>
          <p className="muted">Click to open file selector</p>
        </div>

        {files.length > 0 && (
          <div className="selection-inline">
            <header className="selection-header">
              <h3>Uploaded Files</h3>
              <span className="badge">{files.length}</span>
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
            <button className="primary full-width" onClick={onConfirm}>
              Confirm
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

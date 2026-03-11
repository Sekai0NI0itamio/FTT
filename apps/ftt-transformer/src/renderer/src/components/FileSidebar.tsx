import { useState } from "react";
import type { ExtractionFlags, SourceFile } from "@renderer/types";

export function FileSidebar({
  files,
  activeFileId,
  onSelectFile,
  onUpdateFlags,
}: {
  files: SourceFile[];
  activeFileId: string | null;
  onSelectFile: (id: string) => void;
  onUpdateFlags: (id: string, flags: Partial<ExtractionFlags>) => void;
}) {
  const [contextMenu, setContextMenu] = useState<{ id: string; x: number; y: number } | null>(
    null,
  );

  const handleContextMenu = (event: React.MouseEvent, fileId: string) => {
    event.preventDefault();
    setContextMenu({ id: fileId, x: event.clientX, y: event.clientY });
  };

  const file = contextMenu ? files.find((f) => f.id === contextMenu.id) : null;

  return (
    <aside className="sidebar" onClick={() => setContextMenu(null)}>
      <h3>Files</h3>
      <div className="file-list">
        {files
          .filter((f) => f.selected)
          .map((f) => (
            <div
              key={f.id}
              className={`file-card ${f.id === activeFileId ? "active" : ""}`}
              onClick={() => onSelectFile(f.id)}
              onContextMenu={(e) => handleContextMenu(e, f.id)}
            >
              <div className="file-title">{f.name}</div>
              <div className="file-status-chips">
                {f.fullExtraction.tesseract && (
                  <span className="status-chip tesseract">Tesseract</span>
                )}
                {f.fullExtraction.python && (
                  <span className="status-chip python">Python</span>
                )}
              </div>
            </div>
          ))}
      </div>

      {contextMenu && file && (
        <div
          className="context-menu"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="menu-title">Extraction Methods</div>
          <label className="menu-check">
            <input
              type="checkbox"
              checked={file.fullExtraction.tesseract}
              onChange={(e) =>
                onUpdateFlags(file.id, { tesseract: e.target.checked })
              }
            />
            Extract full file using Tesseract
          </label>
          <label className="menu-check">
            <input
              type="checkbox"
              checked={file.fullExtraction.python}
              onChange={(e) =>
                onUpdateFlags(file.id, { python: e.target.checked })
              }
            />
            Extract full file using Python
          </label>
        </div>
      )}
    </aside>
  );
}

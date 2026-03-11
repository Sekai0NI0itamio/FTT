import { useState } from "react";

export function SaveModal({
  defaultName,
  onSave,
  onClose,
  onSelectFolder,
}: {
  defaultName: string;
  onSave: (opts: {
    name: string;
    format: "selections" | "full";
    location: string;
  }) => void;
  onClose: () => void;
  onSelectFolder: () => Promise<string>;
}) {
  const [name, setName] = useState(defaultName);
  const [format, setFormat] = useState<"selections" | "full">("selections");
  const [location, setLocation] = useState("");

  const handleChooseFolder = async () => {
    const folder = await onSelectFolder();
    if (folder) setLocation(folder);
  };

  const handleConfirm = () => {
    if (!location) {
      handleChooseFolder();
      return;
    }
    onSave({ name, format, location });
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>Save Draft Project</h3>

        <label className="modal-field">
          <span>Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="assignment" />
        </label>

        <label className="modal-field">
          <span>Save Format</span>
          <select value={format} onChange={(e) => setFormat(e.target.value as "selections" | "full")}>
            <option value="selections">
              Selections (pen draws) only + file paths + converted PDFs
            </option>
            <option value="full">
              Full files + selection data + converted PDFs
            </option>
          </select>
        </label>

        <label className="modal-field">
          <span>Location</span>
          <div className="row">
            <input
              value={location}
              readOnly
              placeholder="Desktop (click Choose)"
            />
            <button onClick={handleChooseFolder}>Choose</button>
          </div>
        </label>

        <div className="modal-actions">
          <button onClick={onClose}>Cancel</button>
          <button className="primary" onClick={handleConfirm}>
            Confirm
          </button>
        </div>
      </div>
    </div>
  );
}

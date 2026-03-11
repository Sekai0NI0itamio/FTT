export function ConvertingPage({
  current,
  total,
  fileName,
}: {
  current: number;
  total: number;
  fileName: string;
}) {
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;

  return (
    <div className="app">
      <div className="loading">
        <div className="loading-icon">⚙️</div>
        <h2>Converting files…</h2>
        <p className="muted">
          {current} of {total} pages — <strong>{fileName}</strong>
        </p>
        <div className="progress">
          <div className="progress-bar" style={{ width: `${pct}%` }} />
        </div>
        <span className="progress-label">{pct}%</span>
      </div>
    </div>
  );
}

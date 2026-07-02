export interface KeyValueEditorProps {
  label: string;
  value: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
  keyPlaceholder?: string;
  valuePlaceholder?: string;
}

export function KeyValueEditor({
  label,
  value,
  onChange,
  keyPlaceholder = 'key',
  valuePlaceholder = 'value',
}: KeyValueEditorProps) {
  const entries = Object.entries(value);
  return (
    <div>
      <span style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>{label}</span>
      <div className="asset-kv-list">
        {entries.length === 0 && <p className="asset-form-help">No entries. Click "Add" to create one.</p>}
        {entries.map(([k, v], idx) => (
          <div key={`${k}-${idx}`} className="asset-kv-row">
            <input
              value={k}
              onChange={(e) => {
                const next: Record<string, string> = {};
                entries.forEach(([ek, ev], i) => {
                  next[i === idx ? e.target.value : ek] = ev;
                });
                onChange(next);
              }}
              placeholder={keyPlaceholder}
            />
            <input
              value={v}
              onChange={(e) => onChange({ ...value, [k]: e.target.value })}
              placeholder={valuePlaceholder}
            />
            <button
              type="button"
              className="asset-kv-remove"
              onClick={() => {
                const next = { ...value };
                delete next[k];
                onChange(next);
              }}
            >×</button>
          </div>
        ))}
        <button
          type="button"
          className="asset-kv-add"
          onClick={() => onChange({ ...value, '': '' })}
        >+ Add entry</button>
      </div>
    </div>
  );
}

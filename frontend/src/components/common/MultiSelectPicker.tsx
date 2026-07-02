import './MultiSelectPicker.css';

export interface MultiSelectOption {
  value: string;
  label: string;
}

interface MultiSelectPickerProps {
  label?: string;
  options: MultiSelectOption[];
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  emptyMessage?: string;
  disabled?: boolean;
  testId?: string;
}

export function MultiSelectPicker({
  label,
  options,
  value,
  onChange,
  placeholder = 'No items selected',
  emptyMessage = 'No available options',
  disabled = false,
  testId,
}: MultiSelectPickerProps) {
  const selectedSet = new Set(value);
  const selectedOptions = options.filter((opt) => selectedSet.has(opt.value));
  const valueLabelByKey: Record<string, string> = {};
  options.forEach((opt) => {
    valueLabelByKey[opt.value] = opt.label;
  });
  const orphanValues = value.filter((v) => !(v in valueLabelByKey));

  function toggle(optionValue: string) {
    if (disabled) return;
    const next = new Set(value);
    if (next.has(optionValue)) {
      next.delete(optionValue);
    } else {
      next.add(optionValue);
    }
    onChange(Array.from(next));
  }

  function removeOne(optionValue: string) {
    if (disabled) return;
    onChange(value.filter((v) => v !== optionValue));
  }

  return (
    <div className="multi-select-picker" data-testid={testId}>
      {label && (
        <div className="multi-select-picker-header">
          <span className="multi-select-picker-label">{label}</span>
          <span className="multi-select-picker-count">
            {value.length}/{options.length}
          </span>
        </div>
      )}
      <div className="multi-select-picker-list" role="listbox" aria-multiselectable="true">
        {options.length === 0 ? (
          <div className="multi-select-picker-empty">{emptyMessage}</div>
        ) : (
          options.map((opt) => {
            const checked = selectedSet.has(opt.value);
            return (
              <label
                key={opt.value}
                className={`multi-select-picker-option${checked ? ' is-checked' : ''}`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={disabled}
                  onChange={() => toggle(opt.value)}
                />
                <span className="multi-select-picker-option-label">{opt.label}</span>
              </label>
            );
          })
        )}
      </div>
      {selectedOptions.length > 0 && (
        <div className="multi-select-picker-chips">
          {selectedOptions.map((opt) => (
            <span key={opt.value} className="multi-select-chip" title={opt.label}>
              <span className="multi-select-chip-label">{opt.label}</span>
              <button
                type="button"
                className="multi-select-chip-remove"
                onClick={() => removeOne(opt.value)}
                disabled={disabled}
                aria-label={`Remove ${opt.label}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      {orphanValues.length > 0 && (
        <div className="multi-select-picker-chips multi-select-picker-orphans">
          {orphanValues.map((v) => (
            <span
              key={v}
              className="multi-select-chip multi-select-chip-orphan"
              title={`${v} (not in registry — will be dropped on save)`}
            >
              <span className="multi-select-chip-label">
                {v} <em>(missing)</em>
              </span>
              <button
                type="button"
                className="multi-select-chip-remove"
                onClick={() => removeOne(v)}
                disabled={disabled}
                aria-label={`Remove orphan ${v}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      {selectedOptions.length === 0 && orphanValues.length === 0 && options.length > 0 && (
        <p className="multi-select-picker-hint">{placeholder}</p>
      )}
      <span className="multi-select-picker-sr-only" aria-hidden>
        {value.map((v) => valueLabelByKey[v] ?? v).join(', ')}
      </span>
    </div>
  );
}

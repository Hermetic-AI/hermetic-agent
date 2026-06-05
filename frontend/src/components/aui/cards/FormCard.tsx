import { useState } from 'react';
import type { CardDescriptor, CardField } from '../../../types';
import { CardShell } from '../CardShell';

export interface FormCardProps {
  card: CardDescriptor;
  suspended?: boolean;
  submitted?: boolean;
  onSubmit: (userInput: Record<string, unknown>, actionId?: string) => void;
}

// Generic form renderer used for OD_INPUT, PASSENGER_FORM, OAT_BINDING.
// Collects field values, then submits as a flat dict.
export function FormCard({ card, suspended, submitted, onSubmit }: FormCardProps) {
  const fields = card.fields ?? [];
  const [values, setValues] = useState<Record<string, unknown>>(() => initialValues(fields));

  const update = (id: string, value: unknown) => {
    setValues((prev) => ({ ...prev, [id]: value }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (suspended || submitted) return;
    onSubmit(values, 'submit');
  };

  return (
    <CardShell
      card={card}
      suspended={suspended}
      submitted={submitted}
      footer={
        <button
          type="submit"
          form={`aui-form-${card.card_id}`}
          className="aui-action aui-action-primary"
          disabled={suspended || submitted}
        >
          {submitted ? '已提交' : '确认'}
        </button>
      }
    >
      {card.message && <p className="aui-card-message">{String(card.message)}</p>}
      <form id={`aui-form-${card.card_id}`} onSubmit={handleSubmit} className="aui-card-body">
        {fields.map((f) => (
          <FieldRow key={f.id} field={f} value={values[f.id]} onChange={(v) => update(f.id, v)} />
        ))}
      </form>
    </CardShell>
  );
}

function FieldRow({
  field,
  value,
  onChange,
}: {
  field: CardField;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const id = `field-${field.id}`;
  return (
    <div className="aui-field">
      <label className="aui-field-label" htmlFor={id}>
        {field.label}
        {field.required && <span className="aui-field-required">*</span>}
      </label>
      {field.type === 'select' || field.options ? (
        <select
          id={id}
          className="aui-field-select"
          value={value == null ? '' : String(value)}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">请选择…</option>
          {(field.options ?? []).map((opt) => (
            <option key={String(opt.value)} value={String(opt.value)}>
              {opt.label}
            </option>
          ))}
        </select>
      ) : field.type === 'textarea' ? (
        <textarea
          id={id}
          className="aui-field-textarea"
          value={value == null ? '' : String(value)}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
        />
      ) : field.type === 'date' ? (
        <input
          id={id}
          type="date"
          className="aui-field-input"
          value={value == null ? '' : String(value)}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <input
          id={id}
          type={field.type === 'number' ? 'number' : 'text'}
          className="aui-field-input"
          value={value == null ? '' : String(value)}
          onChange={(e) => onChange(field.type === 'number' ? Number(e.target.value) : e.target.value)}
          placeholder={field.placeholder}
        />
      )}
    </div>
  );
}

function initialValues(fields: CardField[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of fields) {
    if (f.default !== undefined) out[f.id] = f.default;
  }
  return out;
}

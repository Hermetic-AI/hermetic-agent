// FilesTab — left-side list of file products from the active turn, with
// DiffViewer showing the payload content on selection.  v1: renders the
// product payload as plain text; future phases can add git-diff or
// structured diff rendering when backend emits true diffs.

import { useState } from 'react';
import type { TraceEvent } from '../../hooks/useWorkPanel';
import { DiffViewer } from './DiffViewer';
import './FilesTab.css';

export interface FilesTabProps {
  events: TraceEvent[];
}

export function FilesTab({ events }: FilesTabProps) {
  const products = events.filter((e) => e.kind === 'product');
  const [selected, setSelected] = useState<TraceEvent | null>(null);

  if (products.length === 0) {
    return (
      <div className="files-tab files-empty">
        No files changed yet.
      </div>
    );
  }

  return (
    <div className="files-tab">
      <ul className="files-list">
        {products.map((p) => {
          const path = (p.payload.path as string | undefined)
            ?? (p.payload.url as string | undefined)
            ?? `event-${p.seq}`;
          const isActive = selected?.seq === p.seq;
          return (
            <li key={p.seq}>
              <button
                type="button"
                className={`files-item ${isActive ? 'is-active' : ''}`}
                onClick={() => setSelected(p)}
              >
                <span className={`files-kind files-kind-${p.payload.kind as string}`}>
                  {p.payload.kind as string}
                </span>
                <span className="files-path">{path}</span>
              </button>
            </li>
          );
        })}
      </ul>
      {selected && (
        <div className="files-preview">
          <DiffViewer
            before=""
            after={JSON.stringify(selected.payload, null, 2)}
            fileName={
              (selected.payload.path as string | undefined) ??
              (selected.payload.url as string | undefined) ??
              'product'
            }
          />
        </div>
      )}
    </div>
  );
}
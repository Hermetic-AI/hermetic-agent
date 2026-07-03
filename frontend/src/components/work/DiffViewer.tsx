// DiffViewer — line-level diff using the `diff` npm package.
//
// Used by FilesTab to render before/after text comparisons.  Reads `diff`
// synchronously so the component is pure-functional with no async effects.

import { useMemo } from 'react';
import { diffLines } from 'diff';
import './DiffViewer.css';

export interface DiffViewerProps {
  before: string;
  after: string;
  fileName?: string;
}

export function DiffViewer({ before, after, fileName }: DiffViewerProps) {
  const parts = useMemo(() => diffLines(before, after), [before, after]);
  return (
    <div className="diff-viewer">
      {fileName && <div className="diff-header">{fileName}</div>}
      <pre className="diff-body">
        {parts.map((part, i) => (
          <div
            key={i}
            className={`diff-line diff-${part.added ? 'add' : part.removed ? 'del' : 'eq'}`}
          >
            <span className="diff-marker">
              {part.added ? '+' : part.removed ? '-' : ' '}
            </span>
            <span className="diff-text">{part.value}</span>
          </div>
        ))}
      </pre>
    </div>
  );
}
// PlanTab — Q&A prompts + todo progress.  Two sections stacked vertically;
// compact, scannable at a glance.

import type { TraceEvent } from '../../hooks/useWorkPanel';
import './PlanTab.css';

export interface PlanTabProps {
  events: TraceEvent[];
}

interface TodoItem {
  content: string;
  status: string;
  priority?: string;
}

export function PlanTab({ events }: PlanTabProps) {
  const todosByUpdate = events.filter((e) => e.kind === 'todo');
  const latestTodos: TodoItem[] =
    todosByUpdate.length > 0
      ? ((todosByUpdate[todosByUpdate.length - 1].payload.items as TodoItem[]) ?? [])
      : [];

  const questions = events.filter((e) => e.kind === 'question');
  const states = events.filter((e) => e.kind === 'state');

  return (
    <div className="plan-tab">
      <section className="plan-section">
        <h4 className="plan-section-title">Plan / Todos</h4>
        {latestTodos.length === 0 ? (
          <div className="plan-empty">No todos</div>
        ) : (
          <ul className="plan-todos">
            {latestTodos.map((t, i) => (
              <li
                key={i}
                className={`plan-todo plan-todo-${t.status}`}
              >
                <span className="plan-todo-marker">{statusMarker(t.status)}</span>
                <span className="plan-todo-content">{t.content}</span>
                {t.priority && (
                  <span className={`plan-todo-priority plan-todo-priority-${t.priority}`}>
                    {t.priority}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="plan-section">
        <h4 className="plan-section-title">Questions</h4>
        {questions.length === 0 ? (
          <div className="plan-empty">No questions yet</div>
        ) : (
          <ul className="plan-questions">
            {questions.map((q) => (
              <li key={q.seq} className={`plan-question plan-question-${q.payload.status}`}>
                <span className="plan-question-status">
                  {q.payload.status as string}
                </span>
                <span className="plan-question-prompt">
                  {stringifyPrompt(q.payload.prompt)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="plan-section">
        <h4 className="plan-section-title">State transitions</h4>
        {states.length === 0 ? (
          <div className="plan-empty">No state changes yet</div>
        ) : (
          <ul className="plan-states">
            {states.map((s) => (
              <li key={s.seq} className="plan-state">
                {s.payload.from as string} → {s.payload.to as string}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function statusMarker(status: string): string {
  switch (status) {
    case 'completed':
    case 'done':
      return '✓';
    case 'in_progress':
      return '…';
    case 'pending':
      return '○';
    case 'cancelled':
    case 'failed':
      return '✗';
    default:
      return '?';
  }
}

function stringifyPrompt(p: unknown): string {
  if (typeof p === 'string') return p;
  if (Array.isArray(p)) {
    return p
      .map((q: unknown) =>
        typeof q === 'object' && q && 'question' in q
          ? String((q as { question: unknown }).question)
          : String(q),
      )
      .join('; ');
  }
  return JSON.stringify(p);
}
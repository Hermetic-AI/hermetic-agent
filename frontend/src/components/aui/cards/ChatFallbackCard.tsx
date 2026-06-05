import { useState } from 'react';
import type { CardDescriptor } from '../../../types';
import { CardShell } from '../CardShell';

export interface ChatFallbackCardProps {
  card: CardDescriptor;
  suspended?: boolean;
  submitted?: boolean;
  onSubmit: (userInput: Record<string, unknown>, actionId?: string) => void;
}

// CHAT_FALLBACK — legacy "ask user in plain text" path.  Renders a single
// textarea; the resume body becomes `{ _text: "..." }` so the agent can
// NLU the answer.  See docs/design/book-flight-hitl-design.md §4.2.2.
export function ChatFallbackCard({ card, suspended, submitted, onSubmit }: ChatFallbackCardProps) {
  const [text, setText] = useState('');
  return (
    <CardShell
      card={card}
      suspended={suspended}
      submitted={submitted}
      footer={
        <button
          type="button"
          className="aui-action aui-action-primary"
          disabled={!text.trim() || suspended || submitted}
          onClick={() => onSubmit({ _text: text.trim() }, 'submit')}
        >
          {submitted ? '已发送' : '发送'}
        </button>
      }
    >
      {card.message && <p className="aui-card-message">{String(card.message)}</p>}
      <textarea
        className="aui-field-textarea"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="请输入您的回答…"
        disabled={suspended || submitted}
      />
    </CardShell>
  );
}

import { useState, useRef, useCallback, type FormEvent, type KeyboardEvent } from 'react';
import { SendIcon, EmojiIcon, MicIcon } from './Icons';
import './ChatInput.css';

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInput({ onSend, disabled = false, placeholder = '输入消息...' }: ChatInputProps) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustHeight = useCallback(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 120)}px`;
    }
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
    adjustHeight();
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (value.trim() && !disabled) {
      onSend(value.trim());
      setValue('');
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleEmoji = () => {
    const emojis = ['😊', '👍', '🙏', '😅', '🤔', '😎'];
    const randomEmoji = emojis[Math.floor(Math.random() * emojis.length)];
    setValue((prev) => prev + randomEmoji);
    textareaRef.current?.focus();
  };

  const canSend = value.trim().length > 0 && !disabled;

  return (
    <form className="chat-input-form" onSubmit={handleSubmit}>
      <div className="chat-input-container">
        <button type="button" className="input-action-btn" onClick={handleEmoji}>
          <EmojiIcon />
        </button>
        <textarea
          ref={textareaRef}
          className="chat-input"
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
        />
        <button type="button" className="input-action-btn">
          <MicIcon />
        </button>
        <button
          type="submit"
          className={`chat-send-btn ${canSend ? 'active' : ''}`}
          disabled={!canSend}
        >
          <SendIcon />
        </button>
      </div>
      <div className="input-hint">
        按 Enter 发送，Shift + Enter 换行
      </div>
    </form>
  );
}

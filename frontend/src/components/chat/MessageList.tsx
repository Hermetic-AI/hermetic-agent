import { useRef, useEffect, type ReactNode } from 'react';
import { LoadingIcon } from './Icons';
import './MessageList.css';

interface MessageListProps {
  children: ReactNode;
  loading?: boolean;
}

export function MessageList({ children, loading = false }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [children]);

  return (
    <div className="message-list">
      {children}
      {loading && (
        <div className="message-loading">
          <LoadingIcon />
          <span>AI 思考中...</span>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}

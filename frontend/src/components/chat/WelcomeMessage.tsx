import type { ReactNode } from 'react';
import './WelcomeMessage.css';

interface QuickAction {
  label: string;
  value: string;
  icon: ReactNode;
}

interface WelcomeMessageProps {
  onQuickReply: (value: string) => void;
  backendReady?: boolean;
}

export function WelcomeMessage({
  onQuickReply,
  backendReady = true,
}: WelcomeMessageProps) {
  const actions = pickActions();

  return (
    <div className="welcome-hero">
      <div className="welcome-hero-inner">
        <div className="welcome-hero-mark" aria-hidden="true">
          <SparkleIcon />
        </div>
        <h1 className="welcome-hero-title">How can I help today?</h1>
        <p className="welcome-hero-subtitle">
          {backendReady
            ? 'Ask anything, or pick a starter prompt below.'
            : 'Cannot reach the backend service. Check VITE_MCP_TOKEN and confirm the server is running.'}
        </p>

        {backendReady && (
          <div className="welcome-hero-grid">
            {actions.map((a) => (
              <button
                key={a.value}
                type="button"
                className="welcome-hero-card"
                onClick={() => onQuickReply(a.value)}
                disabled={!backendReady}
              >
                <span className="welcome-hero-card-icon" aria-hidden="true">
                  {a.icon}
                </span>
                <span className="welcome-hero-card-label">{a.label}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function pickActions(): QuickAction[] {
  return [
    { label: 'Write a hello world', value: 'Write a hello world program in Python', icon: <CodeIcon /> },
    { label: 'Explain quantum computing', value: 'Explain quantum computing in simple terms', icon: <BookIcon /> },
    { label: 'Review my code', value: 'Help me review a piece of code', icon: <SearchIcon /> },
    { label: 'Tell me a joke', value: 'Tell me a programming joke', icon: <SparkIcon /> },
  ];
}

function SparkleIcon() {
  return (
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" />
    </svg>
  );
}

function CodeIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="16 18 22 12 16 6" />
      <polyline points="8 6 2 12 8 18" />
    </svg>
  );
}

function BookIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

function SparkIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="12 2 15 9 22 12 15 15 12 22 9 15 2 12 9 9 12 2" />
    </svg>
  );
}
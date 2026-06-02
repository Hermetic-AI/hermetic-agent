import type { ReactNode } from 'react';
import { Button } from './Button';
import './Empty.css';

interface EmptyProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
}

export function Empty({ icon, title, description, action }: EmptyProps) {
  return (
    <div className="empty-container">
      {icon ? (
        <div className="empty-icon">{icon}</div>
      ) : (
        <div className="empty-icon">
          <DefaultEmptyIcon />
        </div>
      )}
      <h3 className="empty-title">{title}</h3>
      {description && <p className="empty-description">{description}</p>}
      {action && (
        <Button onClick={action.onClick} style={{ marginTop: '16px' }}>
          {action.label}
        </Button>
      )}
    </div>
  );
}

function DefaultEmptyIcon() {
  return (
    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#E5E5EA" strokeWidth="1.5">
      <path d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

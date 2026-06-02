import type { InputHTMLAttributes } from 'react';
import './Input.css';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  prefixIcon?: React.ReactNode;
  suffixIcon?: React.ReactNode;
}

export function Input({
  label,
  error,
  prefixIcon,
  suffixIcon,
  className = '',
  id,
  ...props
}: InputProps) {
  const inputId = id || `input-${Math.random().toString(36).slice(2)}`;

  return (
    <div className={`input-wrapper ${error ? 'input-error' : ''} ${className}`}>
      {label && <label htmlFor={inputId} className="input-label">{label}</label>}
      <div className="input-container">
        {prefixIcon && <span className="input-prefix">{prefixIcon}</span>}
        <input
          id={inputId}
          className="input-field"
          {...props}
        />
        {suffixIcon && <span className="input-suffix">{suffixIcon}</span>}
      </div>
      {error && <span className="input-error-msg">{error}</span>}
    </div>
  );
}

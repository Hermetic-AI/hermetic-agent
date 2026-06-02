type LogLevel = 'info' | 'warn' | 'error' | 'debug';

interface LogEntry {
  level: LogLevel;
  message: string;
  timestamp: string;
  data?: Record<string, unknown>;
}

class Logger {
  private static instance: Logger;
  private logs: LogEntry[] = [];

  private constructor() {}

  public static getInstance(): Logger {
    if (!Logger.instance) {
      Logger.instance = new Logger();
    }
    return Logger.instance;
  }

  private formatMessage(level: LogLevel, message: string, data?: Record<string, unknown>): LogEntry {
    return {
      level,
      message,
      timestamp: new Date().toISOString(),
      data
    };
  }

  private log(level: LogLevel, message: string, data?: Record<string, unknown>): void {
    const entry = this.formatMessage(level, message, data);
    this.logs.push(entry);
    const prefix = `[${entry.timestamp}] [${level.toUpperCase()}]`;
    const output = data ? `${prefix} ${message}` : `${prefix} ${message}`;
    if (level === 'error') {
      console.error(output, data ?? '');
    } else if (level === 'warn') {
      console.warn(output, data ?? '');
    } else {
      console.log(output, data ?? '');
    }
  }

  public info(message: string, data?: Record<string, unknown>): void {
    this.log('info', message, data);
  }

  public warn(message: string, data?: Record<string, unknown>): void {
    this.log('warn', message, data);
  }

  public error(message: string, data?: Record<string, unknown>): void {
    this.log('error', message, data);
  }

  public debug(message: string, data?: Record<string, unknown>): void {
    this.log('debug', message, data);
  }

  public getLogs(): LogEntry[] {
    return [...this.logs];
  }

  public clearLogs(): void {
    this.logs = [];
  }
}

export const logger = Logger.getInstance();

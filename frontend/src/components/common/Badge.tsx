import type { ReactNode } from 'react';
import './Badge.css';

type BadgeVariant = 'default' | 'success' | 'warning' | 'danger' | 'info';

interface BadgeProps {
  children: ReactNode;
  variant?: BadgeVariant;
  className?: string;
}

export function Badge({ children, variant = 'default', className = '' }: BadgeProps) {
  return (
    <span className={`badge badge-${variant} ${className}`}>
      {children}
    </span>
  );
}

interface StatusBadgeProps {
  status: 'pending' | 'paid' | 'confirmed' | 'completed' | 'cancelled' | 'refunded' | 'violation';
}

const statusConfig: Record<StatusBadgeProps['status'], { label: string; variant: BadgeVariant }> = {
  pending: { label: '待支付', variant: 'warning' },
  paid: { label: '已支付', variant: 'info' },
  confirmed: { label: '已确认', variant: 'success' },
  completed: { label: '已完成', variant: 'success' },
  cancelled: { label: '已取消', variant: 'danger' },
  refunded: { label: '已退款', variant: 'danger' },
  violation: { label: '违规', variant: 'danger' }
};

export function StatusBadge({ status }: StatusBadgeProps) {
  const config = statusConfig[status];
  return <Badge variant={config.variant}>{config.label}</Badge>;
}

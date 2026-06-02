import './Skeleton.css';

interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  variant?: 'text' | 'circular' | 'rectangular';
  className?: string;
}

export function Skeleton({
  width,
  height,
  variant = 'rectangular',
  className = ''
}: SkeletonProps) {
  const style: React.CSSProperties = {
    width: typeof width === 'number' ? `${width}px` : width,
    height: typeof height === 'number' ? `${height}px` : height
  };

  return (
    <div
      className={`skeleton skeleton-${variant} ${className}`}
      style={style}
    />
  );
}

export function FlightCardSkeleton() {
  return (
    <div className="flight-card-skeleton">
      <div className="skeleton-header">
        <div className="skeleton-airline">
          <Skeleton variant="circular" width={32} height={32} />
          <Skeleton width={80} height={16} />
          <Skeleton width={60} height={20} />
        </div>
        <Skeleton width={80} height={28} />
      </div>
      <div className="skeleton-body">
        <div className="skeleton-time">
          <Skeleton width={60} height={24} />
          <Skeleton width={40} height={14} />
        </div>
        <div className="skeleton-duration">
          <Skeleton width={100} height={2} />
          <Skeleton width={50} height={12} />
        </div>
        <div className="skeleton-time">
          <Skeleton width={60} height={24} />
          <Skeleton width={40} height={14} />
        </div>
      </div>
      <div className="skeleton-footer">
        <Skeleton width={120} height={14} />
        <Skeleton width={60} height={32} />
      </div>
    </div>
  );
}

export function OrderCardSkeleton() {
  return (
    <div className="order-card-skeleton">
      <div className="skeleton-header">
        <Skeleton width={140} height={16} />
        <Skeleton width={60} height={22} />
      </div>
      <div className="skeleton-body">
        <Skeleton width={200} height={20} />
        <Skeleton width={150} height={14} />
        <Skeleton width={180} height={40} />
      </div>
      <div className="skeleton-footer">
        <Skeleton width={80} height={24} />
        <Skeleton width={100} height={32} />
      </div>
    </div>
  );
}

export function ChatBubbleSkeleton() {
  return (
    <div className="chat-bubble-skeleton">
      <Skeleton variant="circular" width={36} height={36} />
      <div className="skeleton-content">
        <Skeleton width="70%" height={60} />
      </div>
    </div>
  );
}

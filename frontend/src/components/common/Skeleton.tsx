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
  className = '',
}: SkeletonProps) {
  const style: React.CSSProperties = {
    width: typeof width === 'number' ? `${width}px` : width,
    height: typeof height === 'number' ? `${height}px` : height,
  };

  return (
    <div
      className={`skeleton skeleton-${variant} ${className}`}
      style={style}
    />
  );
}

export function ChatBubbleSkeleton() {
  return (
    <div className="chat-bubble-skeleton">
      <Skeleton variant="circular" width={28} height={28} />
      <div className="skeleton-content">
        <Skeleton width="60%" height={14} />
        <Skeleton width="80%" height={14} />
      </div>
    </div>
  );
}
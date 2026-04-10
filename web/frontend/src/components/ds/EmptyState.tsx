import type { ReactNode } from "react";

export type EmptyStateProps = {
  title: string;
  description?: string;
  children?: ReactNode;
};

export function EmptyState({ title, description, children }: EmptyStateProps) {
  return (
    <div className="empty-state" role="status">
      <p className="empty-state-title">{title}</p>
      {description ? <p className="empty-state-desc muted">{description}</p> : null}
      {children ? <div className="empty-state-cta">{children}</div> : null}
    </div>
  );
}

import type { CSSProperties, ReactNode } from 'react';
import styles from './Card.module.css';

interface CardProps {
  padding?: number;
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
}

export function Card({ padding = 18, children, className, style }: CardProps) {
  return (
    <div
      className={[styles.card, className ?? ''].filter(Boolean).join(' ')}
      style={{ padding, ...style }}
    >
      {children}
    </div>
  );
}

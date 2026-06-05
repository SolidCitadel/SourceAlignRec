import type { HTMLAttributes, ReactNode } from 'react';
import styles from './Chip.module.css';

interface ChipProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'active' | 'soft';
  children: ReactNode;
}

export function Chip({ variant = 'default', className, children, ...rest }: ChipProps) {
  const classes = [styles.chip, styles[`v-${variant}`], className ?? '']
    .filter(Boolean)
    .join(' ');
  return (
    <span className={classes} {...rest}>
      {children}
    </span>
  );
}

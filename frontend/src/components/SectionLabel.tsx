import type { ReactNode } from 'react';
import styles from './SectionLabel.module.css';

interface SectionLabelProps {
  children: ReactNode;
}

export function SectionLabel({ children }: SectionLabelProps) {
  return <div className={styles.label}>{children}</div>;
}

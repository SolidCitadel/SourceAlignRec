import type { CSSProperties } from 'react';
import styles from './Field.module.css';

interface FieldProps {
  label?: string;
  placeholder?: string;
  value?: string;
  suffix?: string;
  dropdown?: boolean;
  full?: boolean;
  width?: string | number;
  style?: CSSProperties;
}

export function Field({
  label,
  placeholder,
  value,
  suffix,
  dropdown,
  full,
  width,
  style,
}: FieldProps) {
  const wrap: CSSProperties = { width: full ? '100%' : width, ...style };
  return (
    <div style={wrap}>
      {label && <div className={styles.label}>{label}</div>}
      <div className={styles.field}>
        <div className={value ? styles.value : styles.placeholder}>{value || placeholder}</div>
        {suffix && <div className={styles.suffix}>{suffix}</div>}
        {dropdown && <div className={styles.dropdown}>▾</div>}
      </div>
    </div>
  );
}

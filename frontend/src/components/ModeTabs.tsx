import type { WorkspaceMode } from '../types/domain';
import styles from './ModeTabs.module.css';

const MODES: WorkspaceMode[] = ['시간표 짜기', '과목 찾기'];

interface ModeTabsProps {
  active: WorkspaceMode;
  onChange: (mode: WorkspaceMode) => void;
}

export function ModeTabs({ active, onChange }: ModeTabsProps) {
  return (
    <div className={styles.bar}>
      {MODES.map((m) => (
        <button
          key={m}
          type="button"
          onClick={() => onChange(m)}
          className={[styles.tab, active === m ? styles.active : ''].filter(Boolean).join(' ')}
        >
          {m}
        </button>
      ))}
    </div>
  );
}
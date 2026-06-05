import { useEffect, useRef, useState } from 'react';
import {
  useActiveTimetable,
  useWorkspaceStore,
} from '../stores/workspaceStore';
import { Chip } from './Chip';
import styles from './ScheduleSelector.module.css';

export function ScheduleSelector() {
  const active = useActiveTimetable();
  const timetables = useWorkspaceStore((s) => s.timetables);
  const setActiveTimetable = useWorkspaceStore((s) => s.setActiveTimetable);
  const newTimetable = useWorkspaceStore((s) => s.newTimetable);
  const duplicateActiveTimetable = useWorkspaceStore((s) => s.duplicateActiveTimetable);
  const deleteTimetable = useWorkspaceStore((s) => s.deleteTimetable);
  const isLast = timetables.length <= 1;

  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  return (
    <div className={styles.wrap} ref={wrapRef}>
      <Chip
        onClick={() => setOpen((v) => !v)}
        style={{ cursor: 'pointer' }}
      >
        {active.name} ▾
      </Chip>
      {open && (
        <div className={styles.menu} role="menu">
          {timetables.map((t) => {
            const isActive = t.id === active.id;
            return (
              <div
                key={t.id}
                className={[styles.itemRow, isActive ? styles.itemRowActive : '']
                  .filter(Boolean)
                  .join(' ')}
              >
                <button
                  type="button"
                  role="menuitem"
                  className={[styles.item, isActive ? styles.itemActive : '']
                    .filter(Boolean)
                    .join(' ')}
                  onClick={() => {
                    setActiveTimetable(t.id);
                    setOpen(false);
                  }}
                >
                  <span>{t.name}</span>
                  <span className={styles.itemMeta}>
                    {t.courses.length}과목 · {t.courses.reduce((s, c) => s + c.credit, 0)}학점
                  </span>
                </button>
                <button
                  type="button"
                  className={styles.itemRemove}
                  onClick={() => deleteTimetable(t.id)}
                  disabled={isLast}
                  aria-label={`${t.name} 삭제`}
                  title={isLast ? '마지막 시간표는 삭제할 수 없습니다' : '시간표 삭제'}
                >
                  ×
                </button>
              </div>
            );
          })}
          <div className={styles.divider} />
          <button
            type="button"
            role="menuitem"
            className={styles.item}
            onClick={() => {
              newTimetable();
              setOpen(false);
            }}
          >
            + 새 시안
          </button>
          <button
            type="button"
            role="menuitem"
            className={styles.item}
            onClick={() => {
              duplicateActiveTimetable();
              setOpen(false);
            }}
          >
            활성 시안 복제
          </button>
        </div>
      )}
    </div>
  );
}

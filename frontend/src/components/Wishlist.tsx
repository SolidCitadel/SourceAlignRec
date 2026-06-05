import type { WishlistItemView } from '../types/domain';
import styles from './Wishlist.module.css';

interface WishlistProps {
  open: boolean;
  items: WishlistItemView[];
  hiddenByConflict: number;
  onClose: () => void;
  onItemClick?: (item: WishlistItemView) => void;
  onItemRemove?: (item: WishlistItemView) => void;
}

export function Wishlist({
  open,
  items,
  hiddenByConflict,
  onClose,
  onItemClick,
  onItemRemove,
}: WishlistProps) {
  if (!open) return null;
  return (
    <aside className={styles.panel}>
      <header className={styles.header}>
        <div>
          <div className={styles.title}>
            Wishlist <span className={styles.count}>({items.length})</span>
          </div>
          {hiddenByConflict > 0 ? (
            <div className={styles.sort}>충돌 {hiddenByConflict}개 숨김</div>
          ) : (
            <div className={styles.sort}>정렬 · 추가순 ▾</div>
          )}
        </div>
        <button type="button" onClick={onClose} className={styles.collapse} aria-label="Wishlist 접기">
          ‹
        </button>
      </header>
      <ul className={styles.list}>
        {items.map((it) => {
          const locked = it.inSchedule;
          const cls = [
            styles.item,
            it.conflict ? styles.conflict : '',
            it.inSchedule ? styles.inSchedule : '',
            locked ? styles.locked : '',
          ]
            .filter(Boolean)
            .join(' ');
          return (
            <li key={it.id} className={styles.itemWrap}>
              <button
                type="button"
                className={cls}
                disabled={locked}
                onClick={() => onItemClick?.(it)}
                title={
                  it.inSchedule
                    ? '이미 등록된 과목'
                    : it.conflict
                      ? '시간 충돌 — 클릭 시 추가 시도 (alert)'
                      : '시간표에 추가'
                }
              >
                {it.conflict && <span className={styles.badgeDanger}>충돌</span>}
                <div className={styles.name}>{it.courseName}</div>
                <div className={styles.meta}>
                  {it.professorName} · {it.credit}학점 · {it.type}
                </div>
              </button>
              {onItemRemove && (
                <button
                  type="button"
                  className={styles.remove}
                  onClick={(e) => {
                    e.stopPropagation();
                    onItemRemove(it);
                  }}
                  aria-label={`${it.courseName} Wishlist에서 제거`}
                  title="Wishlist에서 제거"
                >
                  ×
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </aside>
  );
}

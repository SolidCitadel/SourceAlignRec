import { useState } from 'react';
import type { OfferingSearchResultView } from '../types/domain';
import { formatMeetings, lastDeptSegment } from '../utils/format';
import styles from './OfferingCard.module.css';

interface OfferingCardProps {
  result: OfferingSearchResultView;
  onClick?: () => void;
  onToggleWishlist?: () => void;
}

export function OfferingCard({ result, onClick, onToggleWishlist }: OfferingCardProps) {
  const [hover, setHover] = useState(false);
  const cls = [styles.card, result.conflict ? styles.conflict : ''].filter(Boolean).join(' ');
  const room = result.meetings.find((m) => m.room)?.room;
  // meetings 빈 list: 온라인이면 "온라인", 아니면 "시간 미정". 둘 다 room 표시 X.
  const scheduleText =
    result.meetings.length > 0
      ? formatMeetings(result.meetings)
      : result.isOnline
        ? '온라인'
        : '시간 미정';
  const showRoom = result.meetings.length > 0 && !!room;

  return (
    <div
      className={cls}
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick?.();
        }
      }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <div className={styles.row}>
        <div className={styles.body}>
          <div className={styles.name}>{result.courseName}</div>
          <div className={styles.professor}>
            {result.professorName} · {lastDeptSegment(result.department)}
          </div>
          <div className={styles.meta}>
            {result.credit}학점 · {result.type} · {scheduleText}
            {showRoom ? ` · ${room}` : ''}
          </div>
          {(result.taken || result.conflict) && (
            <div className={styles.badges}>
              {result.taken && (
                <span className={styles.badge}>
                  이미 수강{result.takenGrade ? ` · ${result.takenGrade}` : ''}
                </span>
              )}
              {result.conflict && (
                <span className={`${styles.badge} ${styles.badgeDanger}`}>충돌</span>
              )}
            </div>
          )}
        </div>
        <button
          type="button"
          className={[styles.action, result.inWishlist ? styles.actionActive : '']
            .filter(Boolean)
            .join(' ')}
          onClick={(e) => {
            e.stopPropagation();
            onToggleWishlist?.();
          }}
          title={result.inWishlist ? 'Wishlist에서 제거' : 'Wishlist 담기'}
        >
          {result.inWishlist ? (hover ? '✕ 제거' : '✓ 담김') : '+ Wishlist'}
        </button>
      </div>
    </div>
  );
}

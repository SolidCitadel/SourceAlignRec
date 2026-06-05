import { useEffect, useRef, useState } from 'react';
import {
  useSearchResults,
  useWorkspaceStore,
} from '../stores/workspaceStore';
import type { OfferingSearchResultView, SortKey } from '../types/domain';
import { Button } from './Button';
import { OfferingCard } from './OfferingCard';
import styles from './ResultBoard.module.css';

const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: 'course_name', label: '과목명 가나다' },
  { key: 'course_id', label: '강의코드 순' },
  { key: 'credit', label: '학점 순' },
];

interface ResultBoardProps {
  onCardClick: (result: OfferingSearchResultView) => void;
  onAIClick: () => void;
}

export function ResultBoard({ onCardClick, onAIClick }: ResultBoardProps) {
  const { items, total, hiddenByConflict, hiddenByTaken, page, pageCount } = useSearchResults();
  const sort = useWorkspaceStore((s) => s.searchSort);
  const setSort = useWorkspaceStore((s) => s.setSearchSort);
  const setPage = useWorkspaceStore((s) => s.setSearchPage);
  const addToWishlist = useWorkspaceStore((s) => s.addToWishlist);
  const removeFromWishlist = useWorkspaceStore((s) => s.removeFromWishlist);

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <div className={styles.count}>
          결과 {total}개
          {hiddenByTaken > 0 && (
            <span className={styles.countDim}> · 수료 {hiddenByTaken}개 숨김</span>
          )}
          {hiddenByConflict > 0 && (
            <span className={styles.countDim}> · 충돌 {hiddenByConflict}개 숨김</span>
          )}
          <span className={styles.countDim}> · {page}/{pageCount} 페이지</span>
        </div>
        <div className={styles.actions}>
          <SortDropdown value={sort} onChange={setSort} />
          <Button
            variant="primary"
            size="sm"
            onClick={onAIClick}
            disabled={total === 0}
            title={total === 0 ? '검색 결과가 없어 추천할 수 없습니다' : 'AI에게 추천받기'}
          >
            AI에게 추천받기
          </Button>
        </div>
      </div>

      {items.length === 0 ? (
        <div className={styles.empty}>조건에 맞는 강의가 없습니다. 필터를 완화해보세요.</div>
      ) : (
        <ul className={styles.list}>
          {items.map((r) => (
            <li key={r.id}>
              <OfferingCard
                result={r}
                onClick={() => onCardClick(r)}
                onToggleWishlist={() => {
                  if (r.inWishlist) {
                    removeFromWishlist(r.id);
                  } else {
                    addToWishlist({
                      id: r.id,
                      courseName: r.courseName,
                      professorName: r.professorName,
                      credit: r.credit,
                      type: r.type,
                      meetings: r.meetings,
                    });
                  }
                }}
              />
            </li>
          ))}
        </ul>
      )}

      {pageCount > 1 && <Pagination page={page} pageCount={pageCount} onChange={setPage} />}
    </div>
  );
}

function SortDropdown({ value, onChange }: { value: SortKey; onChange: (k: SortKey) => void }) {
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

  const current = SORT_OPTIONS.find((o) => o.key === value)?.label ?? '';
  return (
    <div className={styles.sortWrap} ref={wrapRef}>
      <button type="button" className={styles.sortBtn} onClick={() => setOpen((v) => !v)}>
        정렬 · {current} ▾
      </button>
      {open && (
        <div className={styles.sortMenu} role="menu">
          {SORT_OPTIONS.map((o) => (
            <button
              key={o.key}
              type="button"
              role="menuitem"
              className={[styles.sortItem, o.key === value ? styles.sortItemActive : '']
                .filter(Boolean)
                .join(' ')}
              onClick={() => {
                onChange(o.key);
                setOpen(false);
              }}
            >
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Pagination({
  page,
  pageCount,
  onChange,
}: {
  page: number;
  pageCount: number;
  onChange: (p: number) => void;
}) {
  // 페이지 수가 적으면 다 보여주고, 많으면 [1, ..., p-1, p, p+1, ..., last] 식.
  const pages = buildPages(page, pageCount);

  return (
    <div className={styles.pagination}>
      <button
        type="button"
        className={styles.pageBtn}
        onClick={() => onChange(page - 1)}
        disabled={page <= 1}
        aria-label="이전 페이지"
      >
        ‹
      </button>
      {pages.map((p, i) =>
        p === 'ellipsis' ? (
          <span key={`e${i}`} className={styles.ellipsis}>
            …
          </span>
        ) : (
          <button
            key={p}
            type="button"
            className={[styles.pageBtn, p === page ? styles.pageBtnActive : '']
              .filter(Boolean)
              .join(' ')}
            onClick={() => onChange(p)}
          >
            {p}
          </button>
        ),
      )}
      <button
        type="button"
        className={styles.pageBtn}
        onClick={() => onChange(page + 1)}
        disabled={page >= pageCount}
        aria-label="다음 페이지"
      >
        ›
      </button>
    </div>
  );
}

function buildPages(page: number, pageCount: number): (number | 'ellipsis')[] {
  if (pageCount <= 7) return Array.from({ length: pageCount }, (_, i) => i + 1);
  const result: (number | 'ellipsis')[] = [1];
  const left = Math.max(2, page - 1);
  const right = Math.min(pageCount - 1, page + 1);
  if (left > 2) result.push('ellipsis');
  for (let i = left; i <= right; i++) result.push(i);
  if (right < pageCount - 1) result.push('ellipsis');
  result.push(pageCount);
  return result;
}

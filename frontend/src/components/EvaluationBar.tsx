import type { EvaluationItem } from '../types/domain';
import styles from './EvaluationBar.module.css';

// chat-summary L38 — 중간/기말=ink, 과제=sun, 출석=line gray. 그 외 카테고리 fallback.
const COLOR_BY_ITEM: Record<string, string> = {
  중간고사: 'var(--color-ink)',
  기말고사: 'var(--color-ink-dim)',
  과제: 'var(--color-primary)',
  '팀 프로젝트': 'var(--color-primary-soft)',
  발표: 'var(--color-line)',
  출석: 'var(--color-line-soft)',
};

const ALL_COLORS = [
  'var(--color-ink)',
  'var(--color-primary)',
  'var(--color-ink-dim)',
  'var(--color-primary-soft)',
  'var(--color-line)',
  'var(--color-line-soft)',
];

interface EvaluationBarProps {
  items: EvaluationItem[];
}

/** 매 item에 색 할당. 알려진 항목명은 fixed, 그 외는 unused 색 픽 (색 충돌 회피). */
function assignColors(items: EvaluationItem[]): string[] {
  const result: (string | null)[] = items.map((it) => COLOR_BY_ITEM[it.item] ?? null);
  const used = new Set(result.filter((c): c is string => c !== null));
  let fallbackIdx = 0;
  for (let i = 0; i < result.length; i++) {
    if (result[i] !== null) continue;
    let next = ALL_COLORS.find((c) => !used.has(c));
    if (!next) next = ALL_COLORS[fallbackIdx++ % ALL_COLORS.length];
    result[i] = next;
    used.add(next);
  }
  return result as string[];
}

export function EvaluationBar({ items }: EvaluationBarProps) {
  // 0% 항목은 학생 결정에 가치 없음 — 표시 X (bar width 0 + legend noise 제거).
  const visible = items.filter((it) => it.weight > 0);
  const colors = assignColors(visible);
  const colorFor = (_item: string, idx: number): string => colors[idx];

  return (
    <div className={styles.wrap}>
      <div className={styles.bar}>
        {visible.map((it, idx) => (
          <div
            key={it.item}
            className={styles.segment}
            style={{ width: `${it.weight}%`, background: colorFor(it.item, idx) }}
            title={`${it.item} ${it.weight}%`}
          />
        ))}
      </div>
      <div className={styles.legend}>
        {visible.map((it, idx) => (
          <div key={it.item} className={styles.legendItem}>
            <span
              className={styles.legendSwatch}
              style={{ background: colorFor(it.item, idx) }}
            />
            <span>{it.item}</span>
            <span className={styles.legendWeight}>{it.weight}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

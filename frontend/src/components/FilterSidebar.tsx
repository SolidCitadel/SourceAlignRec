import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { fetchDepartments } from '../api/search';
import {
  CREDIT_OPTIONS,
  useWorkspaceStore,
} from '../stores/workspaceStore';
import { ATTR_META, ATTR_VALUES, EXAM_WEIGHT_CHIP_HINT } from '../types/domain';
import { Chip } from './Chip';
import styles from './FilterSidebar.module.css';

function toggle<T>(arr: T[], v: T): T[] {
  return arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v];
}

export function FilterSidebar() {
  const filter = useWorkspaceStore((s) => s.searchFilter);
  const patchRaw = useWorkspaceStore((s) => s.patchSearchFilter);
  const resetRaw = useWorkspaceStore((s) => s.resetSearchFilter);
  const clearAI = useWorkspaceStore((s) => s.newAIThread);
  const userDept = useWorkspaceStore((s) => s.currentUser?.department ?? '');

  // 새 검색 = 추천 컨텍스트 stale. 사용자 명시 filter 변경에서만 chat reset.
  // (시스템 default 적용은 store action 직접 호출이라 영향 없음.)
  const patch: typeof patchRaw = (p) => {
    patchRaw(p);
    clearAI();
  };
  const reset = () => {
    resetRaw();
    clearAI();
  };

  // 이수구분 선택지 = 선택 학과(미선택 시 본인 학과) 카탈로그의 실재 라벨(위계순). 하드코딩 아님.
  const { data: departments = [] } = useQuery({
    queryKey: ['departments'],
    queryFn: fetchDepartments,
    staleTime: Infinity,
  });
  const ownCode = departments.find((d) => userDept && d.name.includes(userDept))?.code ?? '';
  const activeCode = filter.department || ownCode;
  const courseTypeOptions = departments.find((d) => d.code === activeCode)?.courseTypes ?? [];

  // 빈 배열 = 전체 (search.py: `if course_types and …`). 표시는 전체 체크, collapse로 일관.
  const ctChecked = (t: string) =>
    filter.courseTypes.length === 0 || filter.courseTypes.includes(t);
  const toggleCourseType = (t: string) => {
    const cur = filter.courseTypes.length === 0 ? courseTypeOptions : filter.courseTypes;
    let next = cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t];
    if (courseTypeOptions.length > 0 && courseTypeOptions.every((x) => next.includes(x))) next = [];
    patch({ courseTypes: next });
  };

  return (
    <aside className={styles.sidebar}>
      <div className={styles.header}>
        <div className={styles.title}>필터</div>
        <button type="button" className={styles.reset} onClick={reset}>
          초기화
        </button>
      </div>

      <div className={styles.group}>
        <div className={styles.groupLabel}>학과</div>
        <DepartmentSelect
          selected={filter.department}
          onChange={(v) => patch({ department: v, courseTypes: [] })}
        />
      </div>

      <div className={styles.group}>
        <div className={styles.groupLabel}>이수구분</div>
        {courseTypeOptions.length === 0 ? (
          <div className={styles.checkRow}>학과를 선택하면 이수구분이 표시됩니다</div>
        ) : (
          courseTypeOptions.map((t) => (
            <label key={t} className={styles.checkRow}>
              <input
                type="checkbox"
                checked={ctChecked(t)}
                onChange={() => toggleCourseType(t)}
              />
              {t}
            </label>
          ))
        )}
      </div>

      <div className={styles.group}>
        <div className={styles.groupLabel}>학점</div>
        <div className={styles.chipRow}>
          {CREDIT_OPTIONS.map((c) => (
            <Chip
              key={c}
              variant={filter.credits.includes(c) ? 'active' : 'default'}
              onClick={() => patch({ credits: toggle(filter.credits, c) })}
              style={{ cursor: 'pointer' }}
            >
              {c}
            </Chip>
          ))}
        </div>
      </div>

      <div className={styles.group}>
        <div className={styles.groupLabel}>키워드</div>
        <input
          className={styles.input}
          type="text"
          placeholder="과목명·교수명"
          value={filter.keyword}
          onChange={(e) => patch({ keyword: e.target.value })}
        />
      </div>

      <div className={styles.group}>
        <label className={styles.checkRow}>
          <input
            type="checkbox"
            checked={filter.englishOnly}
            onChange={(e) => patch({ englishOnly: e.target.checked })}
          />
          영어강좌만
        </label>
      </div>

      <div className={styles.group}>
        <div className={styles.groupLabel}>Attribute</div>
        <AttrRow
          meta={ATTR_META.grading}
          options={ATTR_VALUES.grading}
          selected={filter.attributes.grading}
          onToggle={(v) =>
            patch({ attributes: { ...filter.attributes, grading: toggle(filter.attributes.grading, v) } })
          }
        />
        <AttrRow
          meta={ATTR_META.assignment}
          options={ATTR_VALUES.assignment}
          selected={filter.attributes.assignment}
          onToggle={(v) =>
            patch({
              attributes: { ...filter.attributes, assignment: toggle(filter.attributes.assignment, v) },
            })
          }
        />
        <AttrRow
          meta={ATTR_META.teamProject}
          options={ATTR_VALUES.teamProject}
          selected={filter.attributes.teamProject}
          onToggle={(v) =>
            patch({
              attributes: { ...filter.attributes, teamProject: toggle(filter.attributes.teamProject, v) },
            })
          }
        />
        <AttrRow
          meta={ATTR_META.examWeight}
          options={ATTR_VALUES.examWeight}
          selected={filter.attributes.examWeight}
          chipHint={EXAM_WEIGHT_CHIP_HINT}
          onToggle={(v) =>
            patch({
              attributes: { ...filter.attributes, examWeight: toggle(filter.attributes.examWeight, v) },
            })
          }
        />
        <AttrRow
          meta={ATTR_META.attendance}
          options={ATTR_VALUES.attendance}
          selected={filter.attributes.attendance}
          onToggle={(v) =>
            patch({
              attributes: { ...filter.attributes, attendance: toggle(filter.attributes.attendance, v) },
            })
          }
        />
      </div>
    </aside>
  );
}

function AttrRow<T extends string>({
  meta,
  options,
  selected,
  onToggle,
  chipHint,
}: {
  meta: { label: string; hint: string };
  options: readonly T[];
  selected: T[];
  onToggle: (v: T) => void;
  chipHint?: Record<string, string>;
}) {
  return (
    <div className={styles.attrRow}>
      <div className={styles.attrLabel} title={meta.hint}>{meta.label}</div>
      <div className={styles.chipRow}>
        {options.map((o) => (
          <Chip
            key={o}
            variant={selected.includes(o) ? 'active' : 'default'}
            onClick={() => onToggle(o)}
            style={{ cursor: 'pointer' }}
            title={chipHint?.[o]}
          >
            {o}
          </Chip>
        ))}
      </div>
    </div>
  );
}

function shortDeptName(fullPath: string): string {
  // "소프트웨어융합대학 컴퓨터공학부 컴퓨터공학과" → "컴퓨터공학과"
  const parts = fullPath.trim().split(/\s+/);
  return parts[parts.length - 1] || fullPath;
}

/** 단일 학과 선택 = 카탈로그 필터 + 이수구분 렌즈. '' = 본인 학과 자동(백엔드 resolve). */
function DepartmentSelect({
  selected,
  onChange,
}: {
  selected: string;
  onChange: (code: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const userDept = useWorkspaceStore((s) => s.currentUser?.department ?? '');
  const { data: departments = [] } = useQuery({
    queryKey: ['departments'],
    queryFn: fetchDepartments,
    staleTime: Infinity,
  });

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

  // '' = 본인 학과 자동 → 표시는 user.department에 매칭되는 학과를 현재 렌즈로.
  const ownCode = departments.find((d) => userDept && d.name.includes(userDept))?.code ?? '';
  const activeCode = selected || ownCode;
  const activeName = departments.find((d) => d.code === activeCode)?.name ?? '';
  const summary = activeName
    ? shortDeptName(activeName)
    : userDept
      ? `${userDept} (미수집)`
      : '학과 선택';

  return (
    <div className={styles.deptWrap} ref={wrapRef}>
      <button
        type="button"
        className={styles.deptTrigger}
        onClick={() => setOpen((v) => !v)}
      >
        <span className={activeName ? '' : styles.deptPlaceholder}>{summary}</span>
        <span>▾</span>
      </button>
      {open && (
        <div className={styles.deptMenu}>
          {departments.length === 0 && <div className={styles.deptItem}>수집된 학과 없음</div>}
          {departments.map((d) => (
            <label key={d.code} className={styles.deptItem}>
              <input
                type="radio"
                name="dept-select"
                checked={activeCode === d.code}
                onChange={() => {
                  onChange(d.code);
                  setOpen(false);
                }}
              />
              {shortDeptName(d.name)}
              {ownCode === d.code ? ' · 본인 학과' : ''}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

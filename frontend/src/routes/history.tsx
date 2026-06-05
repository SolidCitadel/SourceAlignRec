import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import * as coursesApi from '../api/courses';
import { Button } from '../components/Button';
import { PageHeader } from '../components/PageHeader';
import { SectionLabel } from '../components/SectionLabel';
import { TopBar } from '../components/TopBar';
import {
  useGraduationProgress,
  useHistoryByTerm,
  useWorkspaceStore,
} from '../stores/workspaceStore';
import type { Grade, HistoryEntry, RequirementCategory } from '../types/domain';
import styles from './history.module.css';

const TERM_OPTIONS = ['2026-1', '2025-2', '2025-1', '2024-2', '2024-1', '2023-2'];
const GRADE_OPTIONS: Grade[] = [
  'A+', 'A0', 'A-',
  'B+', 'B0', 'B-',
  'C+', 'C0', 'C-',
  'D+', 'D0', 'D-',
  'F', 'P',
];
export function History() {
  const navigate = useNavigate();
  const progress = useGraduationProgress();
  const total = progress.gradTotalRequired;
  const sub =
    total == null
      ? `이수 학점 ${progress.totalCredits}학점 · 졸업 총 이수학점 미설정`
      : `이수 학점 ${progress.totalCredits} / ${total} · 졸업까지 ${Math.max(0, total - progress.totalCredits)}학점`;

  return (
    <div className={styles.shell}>
      <TopBar />
      <PageHeader
        title="수강 이력 · 졸업 진행률"
        sub={sub}
        onBack={() => navigate('/')}
      />
      <div className={styles.grid}>
        <SearchAddPane />
        <HistoryListPane />
        <ProgressPane />
      </div>
    </div>
  );
}

// ===== 좌: 검색·추가 =====

interface SearchHit {
  id: string;
  name: string;
  meta: string;
  type: string;   // 카탈로그 KHU 이수구분(본인 학과 렌즈). 졸업요건 영역 default hint로만 쓴다.
  credit: number;
}

/**
 * 졸업요건 영역 선택 — 요건 설정이 정본. 카테고리 목록에서 고르거나 '+ 새 영역'으로 즉시 추가.
 * 새 영역은 addRequirement(name, 0)으로 요건에 등록되어 이후 자동 합산된다(하드코딩·seed 없음).
 * hint = 카탈로그 KHU 이수구분 — '+ 새 영역' 입력칸 prefill로만 제안(다른 축이라 강제 안 함).
 */
function RequirementCategorySelect({
  value,
  onChange,
  className,
  hint,
}: {
  value: string;
  onChange: (v: string) => void;
  className: string;
  hint?: string;
}) {
  const requirements = useWorkspaceStore((s) => s.requirements);
  const addRequirement = useWorkspaceStore((s) => s.addRequirement);
  const categories = requirements.map((r) => r.category);
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState('');

  const submitNew = async () => {
    const name = newName.trim();
    if (!name || name === 'total') return;
    if (!categories.includes(name)) await addRequirement(name, 0);
    onChange(name);
    setAdding(false);
    setNewName('');
  };

  if (adding) {
    return (
      <div className={styles.inlineAddWrap}>
        <input
          className={className}
          type="text"
          value={newName}
          autoFocus
          placeholder="졸업요건 영역 이름"
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') submitNew();
            if (e.key === 'Escape') {
              setAdding(false);
              setNewName('');
            }
          }}
        />
        <Button size="sm" variant="primary" onClick={submitNew} disabled={!newName.trim()}>
          추가
        </Button>
      </div>
    );
  }

  return (
    <select
      className={className}
      value={value}
      onChange={(e) => {
        if (e.target.value === '__new__') {
          setNewName(hint ?? '');
          setAdding(true);
        } else {
          onChange(e.target.value);
        }
      }}
    >
      <option value="" disabled>
        영역 선택
      </option>
      {categories.map((c) => (
        <option key={c} value={c}>
          {c}
        </option>
      ))}
      <option value="__new__">+ 새 영역…</option>
    </select>
  );
}

function SearchAddPane() {
  const addEntry = useWorkspaceStore((s) => s.addHistoryEntry);
  const [term, setTerm] = useState<string>(TERM_OPTIONS[0]);
  const [keyword, setKeyword] = useState('');
  const [openId, setOpenId] = useState<string | null>(null);
  const [showCustom, setShowCustom] = useState(false);
  const [results, setResults] = useState<SearchHit[]>([]);

  // 카탈로그(GET /courses) 검색 — 입력 디바운스 250ms.
  useEffect(() => {
    const k = keyword.trim();
    if (!k) {
      setResults([]);
      return;
    }
    let cancelled = false;
    const t = setTimeout(async () => {
      try {
        const { items } = await coursesApi.search(k);
        if (cancelled) return;
        setResults(
          items.map((hit) => ({
            id: hit.id,
            name: hit.name,
            meta: `${hit.id} · ${hit.department ?? '학과 정보 없음'} · ${hit.credits}학점`,
            type: hit.courseType,
            credit: hit.credits,
          })),
        );
      } catch {
        if (!cancelled) setResults([]);
      }
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [keyword]);

  return (
    <aside className={styles.searchPane}>
      <SectionLabel>검색 · 추가</SectionLabel>
      <div className={styles.termSelectWrap}>
        <div className={styles.fieldLabel}>학기</div>
        <select
          className={styles.select}
          value={term}
          onChange={(e) => setTerm(e.target.value)}
        >
          {TERM_OPTIONS.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>
      <input
        className={styles.input}
        type="text"
        value={keyword}
        onChange={(e) => setKeyword(e.target.value)}
        placeholder="과목명·교수명 검색"
      />
      {results.length > 0 ? (
        <div className={styles.resultList}>
          {results.map((r) => (
            <SearchResultCard
              key={r.id}
              hit={r}
              defaultTerm={term}
              isOpen={openId === r.id}
              onToggle={() => setOpenId((cur) => (cur === r.id ? null : r.id))}
              onAdd={(form) => {
                addEntry({
                  courseId: r.id,
                  courseName: r.name,
                  credits: r.credit,
                  courseType: form.courseType,
                  term: form.term,
                  grade: form.grade,
                });
                setOpenId(null);
              }}
            />
          ))}
        </div>
      ) : keyword.trim() ? (
        <div className={styles.resultEmpty}>일치하는 과목이 없습니다.</div>
      ) : (
        <div className={styles.resultEmpty}>과목명·교수명·학수번호로 검색</div>
      )}
      <div className={styles.divider} />
      <Button onClick={() => setShowCustom(true)} full>
        직접 입력
      </Button>
      <div className={styles.hint}>시스템에 없는 과목은 직접 추가할 수 있어요.</div>

      {showCustom && (
        <CustomEntryModal
          defaultTerm={term}
          onClose={() => setShowCustom(false)}
          onSubmit={(form) => {
            addEntry({
              courseId: null,
              courseName: form.name,
              credits: form.credits,
              courseType: form.courseType,
              term: form.term,
              grade: form.grade,
              custom: true,
            });
            setShowCustom(false);
          }}
        />
      )}
    </aside>
  );
}

function SearchResultCard({
  hit,
  defaultTerm,
  isOpen,
  onToggle,
  onAdd,
}: {
  hit: SearchHit;
  defaultTerm: string;
  isOpen: boolean;
  onToggle: () => void;
  onAdd: (form: { term: string; grade: Grade; courseType: string }) => void;
}) {
  const requirements = useWorkspaceStore((s) => s.requirements);
  // 졸업요건 영역 default = 카탈로그 KHU 이수구분이 요건 카테고리에 있을 때만 preselect(같은 이름이면 일치).
  const matchedDefault = () => (requirements.some((r) => r.category === hit.type) ? hit.type : '');
  const [term, setTerm] = useState<string>(defaultTerm);
  const [grade, setGrade] = useState<Grade>('A0');
  const [courseType, setCourseType] = useState<string>(matchedDefault());

  return (
    <div className={styles.resultCardWrap}>
      <button
        type="button"
        className={[styles.resultCard, isOpen ? styles.resultCardOpen : ''].filter(Boolean).join(' ')}
        onClick={() => {
          if (!isOpen) {
            setTerm(defaultTerm);
            setGrade('A0');
            setCourseType(matchedDefault());
          }
          onToggle();
        }}
      >
        <div className={styles.resultName}>{hit.name}</div>
        <div className={styles.resultMeta}>{hit.meta}</div>
      </button>
      {isOpen && (
        <div className={styles.inlineForm}>
          <div className={styles.inlineRow}>
            <label className={styles.inlineFieldLabel}>학기</label>
            <select
              className={styles.inlineSelect}
              value={term}
              onChange={(e) => setTerm(e.target.value)}
            >
              {TERM_OPTIONS.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
          <div className={styles.inlineRow}>
            <label className={styles.inlineFieldLabel}>성적</label>
            <select
              className={styles.inlineSelect}
              value={grade}
              onChange={(e) => setGrade(e.target.value as Grade)}
            >
              {GRADE_OPTIONS.map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </select>
          </div>
          <div className={styles.inlineRow}>
            <label className={styles.inlineFieldLabel}>이수구분</label>
            <RequirementCategorySelect
              value={courseType}
              onChange={setCourseType}
              className={styles.inlineSelect}
              hint={hit.type}
            />
          </div>
          <Button
            size="sm"
            variant="primary"
            full
            disabled={!courseType}
            onClick={() => onAdd({ term, grade, courseType })}
          >
            추가
          </Button>
        </div>
      )}
    </div>
  );
}

interface CustomForm {
  name: string;
  credits: number;
  term: string;
  grade: Grade;
  courseType: string;
}

function CustomEntryModal({
  defaultTerm,
  onClose,
  onSubmit,
}: {
  defaultTerm: string;
  onClose: () => void;
  onSubmit: (form: CustomForm) => void;
}) {
  const [name, setName] = useState('');
  const [credits, setCredits] = useState<string>('3');
  const [term, setTerm] = useState<string>(defaultTerm);
  const [grade, setGrade] = useState<Grade>('A0');
  const [courseType, setCourseType] = useState<string>('');

  const creditNum = Number(credits);
  const canSubmit =
    name.trim().length > 0 &&
    courseType.length > 0 &&
    Number.isFinite(creditNum) &&
    creditNum > 0 &&
    creditNum <= 6;

  return (
    <div className={styles.modalOverlay} onClick={onClose} role="presentation">
      <div className={styles.modal} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <header className={styles.modalHeader}>
          <div className={styles.modalTitle}>직접 입력</div>
          <button type="button" className={styles.modalClose} onClick={onClose} aria-label="닫기">
            ×
          </button>
        </header>
        <div className={styles.modalBody}>
          <div className={styles.modalField}>
            <label className={styles.modalLabel}>과목명</label>
            <input
              className={styles.modalInput}
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="예: 자유 교양 세미나"
              autoFocus
            />
          </div>
          <div className={styles.modalRow}>
            <div className={styles.modalField}>
              <label className={styles.modalLabel}>학점</label>
              <input
                className={styles.modalInput}
                type="number"
                min={1}
                max={6}
                value={credits}
                onChange={(e) => setCredits(e.target.value)}
              />
            </div>
            <div className={styles.modalField}>
              <label className={styles.modalLabel}>이수구분</label>
              <RequirementCategorySelect
                value={courseType}
                onChange={setCourseType}
                className={styles.modalSelect}
              />
            </div>
          </div>
          <div className={styles.modalRow}>
            <div className={styles.modalField}>
              <label className={styles.modalLabel}>학기</label>
              <select
                className={styles.modalSelect}
                value={term}
                onChange={(e) => setTerm(e.target.value)}
              >
                {TERM_OPTIONS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
            <div className={styles.modalField}>
              <label className={styles.modalLabel}>성적</label>
              <select
                className={styles.modalSelect}
                value={grade}
                onChange={(e) => setGrade(e.target.value as Grade)}
              >
                {GRADE_OPTIONS.map((g) => (
                  <option key={g} value={g}>
                    {g}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className={styles.modalActions}>
            <Button size="sm" onClick={onClose}>
              취소
            </Button>
            <Button
              size="sm"
              variant="primary"
              disabled={!canSubmit}
              onClick={() =>
                onSubmit({ name: name.trim(), credits: creditNum, term, grade, courseType })
              }
            >
              추가
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ===== 중: 학기별 이력 =====

function HistoryListPane() {
  const groups = useHistoryByTerm();
  const removeEntry = useWorkspaceStore((s) => s.removeHistoryEntry);

  if (groups.length === 0) {
    return (
      <div className={styles.listPane}>
        <div className={styles.listEmpty}>
          아직 등록된 수강 이력이 없습니다. 왼쪽에서 과목을 검색해 추가하세요.
        </div>
      </div>
    );
  }

  return (
    <div className={styles.listPane}>
      {groups.map((g) => (
        <section key={g.term} className={styles.termGroup}>
          <header className={styles.termHeader}>
            <div className={styles.termName}>{g.term}</div>
            <div className={styles.termCredits}>{g.credits}학점</div>
          </header>
          <ul className={styles.entryList}>
            {g.entries.map((e) => (
              <EntryRow key={e.id} entry={e} onRemove={() => removeEntry(e.id)} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function EntryRow({ entry, onRemove }: { entry: HistoryEntry; onRemove: () => void }) {
  return (
    <li className={styles.entryRow}>
      <div className={styles.entryName}>
        {entry.courseName}
        {entry.custom && <span className={styles.customBadge}>직접</span>}
      </div>
      <div className={styles.entryType}>{entry.courseType}</div>
      <div className={styles.entryCredits}>{entry.credits}학점</div>
      <div className={[styles.entryGrade, gradeClass(entry.grade)].join(' ')}>{entry.grade}</div>
      <button
        type="button"
        className={styles.removeBtn}
        onClick={onRemove}
        aria-label="삭제"
        title="삭제"
      >
        ×
      </button>
    </li>
  );
}

function gradeClass(grade: Grade): string {
  if (grade === 'F') return styles.gradeFail;
  if (grade === 'P') return styles.gradePass;
  return '';
}

// ===== 우: 진행률 =====

/** 영역 충족 판정: 요건이 있고(required>0) 이수가 그 이상. 매칭 이력 없으면 current=0이라 미충족. */
function isMet(c: { current: number; required: number }): boolean {
  return c.required > 0 && c.current >= c.required;
}

function ProgressPane() {
  const progress = useGraduationProgress();
  const requirements = useWorkspaceStore((s) => s.requirements);
  const gradTotalRequired = useWorkspaceStore((s) => s.gradTotalRequired);
  const patchRequirement = useWorkspaceStore((s) => s.patchRequirement);
  const addRequirement = useWorkspaceStore((s) => s.addRequirement);
  const removeRequirement = useWorkspaceStore((s) => s.removeRequirement);
  const setGradTotal = useWorkspaceStore((s) => s.setGradTotalRequired);
  const [editing, setEditing] = useState<Record<string, string>>({});
  const [totalEdit, setTotalEdit] = useState('');
  const [newName, setNewName] = useState('');
  const [newCredits, setNewCredits] = useState('');
  const [showEditor, setShowEditor] = useState(false);

  const hasTotal = gradTotalRequired != null;
  const percent =
    hasTotal && gradTotalRequired
      ? Math.min(100, Math.round((progress.totalCredits / gradTotalRequired) * 100))
      : 0;
  const remaining = hasTotal ? Math.max(0, gradTotalRequired - progress.totalCredits) : 0;
  const metCount = progress.byCategory.filter(isMet).length;

  const openEditor = () => {
    setShowEditor(true);
    setTotalEdit(gradTotalRequired != null ? String(gradTotalRequired) : '');
  };

  const totalChanged = totalEdit.trim() !== '' && Number(totalEdit) !== gradTotalRequired;
  const dirty = Object.keys(editing).length > 0 || totalChanged;

  const onSave = () => {
    if (totalChanged) {
      const tn = Number(totalEdit);
      if (Number.isFinite(tn) && tn >= 0) setGradTotal(tn);
    }
    for (const r of requirements) {
      const v = editing[r.category];
      if (v === undefined) continue;
      const n = Number(v);
      if (!Number.isFinite(n) || n < 0) continue;
      if (n !== r.required) patchRequirement(r.category as RequirementCategory, n);
    }
    setEditing({});
  };

  const onAddCategory = () => {
    const name = newName.trim();
    const credits = Number(newCredits);
    // 'total'은 PUT /requirements/total 예약어 — 카테고리명으로 금지.
    if (!name || name === 'total' || !Number.isFinite(credits) || credits <= 0) return;
    if (requirements.some((r) => r.category === name)) return;
    addRequirement(name, credits);
    setNewName('');
    setNewCredits('');
  };

  return (
    <aside className={styles.progressPane}>
      <section>
        <SectionLabel>전체 진행률</SectionLabel>
        {hasTotal ? (
          <>
            <div className={styles.bigNumber}>
              {progress.totalCredits}
              <span className={styles.bigNumberDim}>/{gradTotalRequired}</span>
            </div>
            <div className={styles.bigBar}>
              <div className={styles.bigBarFill} style={{ width: `${percent}%` }} />
            </div>
            <div className={styles.bigBarSub}>
              {percent}% 완료 · 졸업까지 {remaining}학점
            </div>
          </>
        ) : (
          <div className={styles.totalUnset}>
            <div className={styles.bigNumber}>
              {progress.totalCredits}
              <span className={styles.bigNumberDim}> 학점 이수</span>
            </div>
            <p className={styles.totalUnsetMsg}>
              졸업 총 이수학점이 설정되지 않았습니다. 영역별 최소의 합과 별개로, 학과 졸업학점을 입력하면 전체 진행률을 계산합니다.
            </p>
            <Button size="sm" variant="primary" onClick={openEditor}>
              졸업 총 이수학점 설정
            </Button>
          </div>
        )}
      </section>

      <section className={styles.catSection}>
        <div className={styles.catSectionHead}>
          <SectionLabel>영역별 최소</SectionLabel>
          {progress.byCategory.length > 0 && (
            <span className={styles.metCount}>
              {metCount}/{progress.byCategory.length} 충족
            </span>
          )}
        </div>
        {progress.byCategory.length === 0 ? (
          <div className={styles.catEmpty}>
            영역별 최소 요건이 없습니다. 아래 요건 설정에서 추가하세요.
          </div>
        ) : (
          progress.byCategory.map((c) => {
            const met = isMet(c);
            const pct = c.required ? Math.min(100, Math.round((c.current / c.required) * 100)) : 0;
            return (
              <div key={c.category} className={styles.checkRow}>
                <div className={styles.catHead}>
                  <span className={styles.catName}>{c.category}</span>
                  <span className={[styles.catNum, met ? styles.catNumMet : ''].filter(Boolean).join(' ')}>
                    {c.current}/{c.required}
                    {met && <span className={styles.checkMark}> ✓</span>}
                  </span>
                </div>
                {!met && (
                  <>
                    <div className={styles.catBar}>
                      <div className={styles.catBarFill} style={{ width: `${pct}%` }} />
                    </div>
                    <div className={styles.checkRemain}>
                      {Math.max(0, c.required - c.current)}학점 남음
                    </div>
                  </>
                )}
              </div>
            );
          })
        )}
      </section>

      <section className={styles.requireSection}>
        <div className={styles.requireHead}>
          <SectionLabel>요건 설정</SectionLabel>
          <button
            type="button"
            className={styles.requireToggle}
            onClick={() => {
              if (showEditor) {
                setShowEditor(false);
                setEditing({});
                setTotalEdit('');
                setNewName('');
                setNewCredits('');
              } else {
                openEditor();
              }
            }}
          >
            {showEditor ? '닫기 ▴' : '편집 ▾'}
          </button>
        </div>
        {showEditor && (
          <>
            <div className={[styles.requireRow, styles.requireTotalRow].join(' ')}>
              <div className={styles.requireLabel}>졸업 총 이수학점</div>
              <input
                className={styles.requireInput}
                type="number"
                min={0}
                max={300}
                placeholder="예: 130"
                value={totalEdit}
                onChange={(e) => setTotalEdit(e.target.value)}
              />
            </div>
            <div className={styles.divider} />
            {requirements.map((r) => (
              <div key={r.category} className={styles.requireRow}>
                <div className={styles.requireLabel}>{r.category}</div>
                <input
                  className={styles.requireInput}
                  type="number"
                  min={0}
                  max={200}
                  value={editing[r.category] ?? r.required}
                  onChange={(e) => setEditing((m) => ({ ...m, [r.category]: e.target.value }))}
                />
                <button
                  type="button"
                  className={styles.requireRemove}
                  onClick={() => removeRequirement(r.category)}
                  aria-label="카테고리 삭제"
                  title="삭제"
                >
                  ×
                </button>
              </div>
            ))}
            <Button size="sm" onClick={onSave} disabled={!dirty}>
              저장
            </Button>
            <div className={styles.divider} />
            <div className={styles.requireAddRow}>
              <input
                className={styles.requireAddName}
                type="text"
                placeholder="카테고리 이름"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
              />
              <input
                className={styles.requireInput}
                type="number"
                min={0}
                max={200}
                placeholder="학점"
                value={newCredits}
                onChange={(e) => setNewCredits(e.target.value)}
              />
            </div>
            <Button
              size="sm"
              variant="primary"
              onClick={onAddCategory}
              disabled={!newName.trim() || newName.trim() === 'total' || !Number(newCredits)}
            >
              + 카테고리 추가
            </Button>
          </>
        )}
      </section>

      <section className={styles.gradeLegend}>
        <SectionLabel>학점 매핑</SectionLabel>
        <div className={styles.gradeLegendBody}>
          <div>• 졸업 총 이수학점과 영역별 최소는 별개 — 둘 다 충족해야 졸업</div>
          <div>• F는 졸업 학점에서 제외, P(Pass)는 포함</div>
          <div>• 수강 이력의 이수구분은 졸업요건 영역에서 골라 등록 — 같은 영역끼리 자동 합산</div>
        </div>
      </section>
    </aside>
  );
}

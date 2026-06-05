import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { Button } from '../components/Button';
import { SectionLabel } from '../components/SectionLabel';
import { TopBar } from '../components/TopBar';
import { fixtureDepartments } from '../fixtures/searchResults';
import { useWorkspaceStore } from '../stores/workspaceStore';
import styles from './profile.module.css';

const SCHOOLS = ['경희대학교'];
// mock 정적 값. User 도메인 확장 전까지 임시.
const MOCK_JOIN_DATE = '2024-03-05';

interface FormState {
  school: string;
  department: string;
  grade: string;
  admissionYear: string;
  name: string;
}

export function Profile() {
  const navigate = useNavigate();
  const user = useWorkspaceStore((s) => s.currentUser);
  const updateProfile = useWorkspaceStore((s) => s.updateProfile);
  const logout = useWorkspaceStore((s) => s.logout);

  const initial: FormState = useMemo(
    () => ({
      school: user?.school ?? '',
      department: user?.department ?? '',
      grade: String(user?.grade ?? ''),
      admissionYear: String(user?.admissionYear ?? ''),
      name: user?.name ?? '',
    }),
    [user],
  );

  const [form, setForm] = useState<FormState>(initial);
  const [saveError, setSaveError] = useState<string | null>(null);
  const dirty =
    form.school !== initial.school ||
    form.department !== initial.department ||
    form.grade !== initial.grade ||
    form.admissionYear !== initial.admissionYear ||
    form.name !== initial.name;

  const onSave = async () => {
    const grade = Number(form.grade);
    const year = Number(form.admissionYear);
    setSaveError(null);
    try {
      await updateProfile({
        name: form.name.trim(),
        school: form.school,
        department: form.department,
        grade: Number.isFinite(grade) && grade > 0 ? grade : (user?.grade ?? 1),
        admissionYear: Number.isFinite(year) ? year : (user?.admissionYear ?? 2024),
      });
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : '저장 중 오류가 발생했습니다.');
    }
  };

  const update = (patch: Partial<FormState>) => setForm((f) => ({ ...f, ...patch }));

  if (!user) {
    // ProtectedRoute가 차단하지만 type-narrow용.
    return null;
  }

  return (
    <div className={styles.shell}>
      <TopBar />
      <div className={styles.container}>
        <header className={styles.header}>
          <button type="button" className={styles.back} onClick={() => navigate('/')}>
            ← 작업공간
          </button>
          <h1 className={styles.title}>프로필</h1>
        </header>

        <Card>
          <SectionLabel>기본 정보</SectionLabel>
          <div className={styles.formStack}>
            <div className={styles.row}>
              <Field label="학교">
                <select
                  className={styles.select}
                  value={form.school}
                  onChange={(e) => update({ school: e.target.value })}
                >
                  {SCHOOLS.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="학과">
                <select
                  className={styles.select}
                  value={form.department}
                  onChange={(e) => update({ department: e.target.value })}
                >
                  {fixtureDepartments.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <div className={styles.row}>
              <Field label="학년" width={120}>
                <select
                  className={styles.select}
                  value={form.grade}
                  onChange={(e) => update({ grade: e.target.value })}
                >
                  {[1, 2, 3, 4, 5, 6].map((g) => (
                    <option key={g} value={g}>
                      {g}학년
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="입학년도" width={140}>
                <input
                  className={styles.input}
                  type="number"
                  min={1990}
                  max={2030}
                  value={form.admissionYear}
                  onChange={(e) => update({ admissionYear: e.target.value })}
                />
              </Field>
              <Field label="이름">
                <input
                  className={styles.input}
                  type="text"
                  value={form.name}
                  onChange={(e) => update({ name: e.target.value })}
                />
              </Field>
            </div>
          </div>
          <div className={styles.cardActions}>
            {saveError && (
              <span style={{ color: 'var(--color-danger)', fontSize: 12 }}>{saveError}</span>
            )}
            <Button variant="primary" size="sm" onClick={onSave} disabled={!dirty}>
              저장
            </Button>
          </div>
        </Card>

        <Card>
          <SectionLabel>계정</SectionLabel>
          <div className={styles.kvList}>
            <KvRow label="이메일" value={user.email} />
            <KvRow label="비밀번호" action="변경 →" onAction={() => alert('비밀번호 변경 — Tier 2')} />
            <KvRow label="가입일" value={MOCK_JOIN_DATE} />
          </div>
          <div className={styles.cardActions}>
            <Button
              size="sm"
              onClick={() => {
                logout();
                navigate('/landing', { replace: true });
              }}
            >
              로그아웃
            </Button>
          </div>
        </Card>

        <Card>
          <SectionLabel>빠른 링크</SectionLabel>
          <div className={styles.quickLinks}>
            <Link to="/history" className={styles.quickLink}>
              수강 이력 →
            </Link>
            <Link to="/" className={styles.quickLink}>
              Wishlist →
            </Link>
            <button
              type="button"
              className={styles.quickLink}
              onClick={() => alert('내 리뷰 페이지 — Tier 2')}
            >
              내 리뷰 →
            </button>
          </div>
        </Card>
      </div>
    </div>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return <div className={styles.card}>{children}</div>;
}

function Field({
  label,
  width,
  children,
}: {
  label: string;
  width?: number;
  children: React.ReactNode;
}) {
  return (
    <div className={styles.field} style={width ? { flex: `0 0 ${width}px` } : undefined}>
      <div className={styles.fieldLabel}>{label}</div>
      {children}
    </div>
  );
}

function KvRow({
  label,
  value,
  action,
  onAction,
}: {
  label: string;
  value?: string;
  action?: string;
  onAction?: () => void;
}) {
  return (
    <div className={styles.kvRow}>
      <div className={styles.kvLabel}>{label}</div>
      {value && <div className={styles.kvValue}>{value}</div>}
      {action && (
        <button type="button" className={styles.kvAction} onClick={onAction}>
          {action}
        </button>
      )}
    </div>
  );
}

import { Fragment, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { Logo } from '../components/Logo';
import { fixtureDepartments } from '../fixtures/searchResults';
import { useWorkspaceStore } from '../stores/workspaceStore';
import styles from './signup.module.css';

const SCHOOLS: { name: string; sub: string; active: boolean }[] = [
  { name: '경희대학교', sub: '현재 지원 중 · 강의 482 · 리뷰 3,891', active: true },
  { name: '서울대학교', sub: '준비 중', active: false },
  { name: '연세대학교', sub: '준비 중', active: false },
  { name: '고려대학교', sub: '준비 중', active: false },
];

const CURRENT_YEAR = new Date().getFullYear();
const MIN_YEAR = 1990;

const STEP_DEFS: { num: number; label: string; title: string; help: string }[] = [
  {
    num: 1,
    label: '가입정보',
    title: '계정을 만들어주세요',
    help: '이메일은 로그인 ID로 사용됩니다. 학교 이메일 아니어도 됩니다.',
  },
  {
    num: 2,
    label: '학교',
    title: '어느 학교 다녀요?',
    help: '학교에 따라 강의 풀이 달라져요. 나중에 바꿀 수 있어요.',
  },
  {
    num: 3,
    label: '학과·학년',
    title: '학과와 학년을 알려주세요',
    help: '추천 결과를 사용자에게 맞추는 데 사용됩니다.',
  },
  {
    num: 4,
    label: '완료',
    title: '거의 다 됐어요',
    help: '가입을 마치면 바로 작업공간으로 이동합니다.',
  },
];

interface SignupState {
  name: string;
  email: string;
  password: string;
  passwordConfirm: string;
  school: string;
  department: string;
  grade: string;
  admissionYear: string;
}

const INITIAL: SignupState = {
  name: '',
  email: '',
  password: '',
  passwordConfirm: '',
  school: '',
  department: '',
  grade: '',
  admissionYear: '',
};

export function Signup() {
  const signup = useWorkspaceStore((s) => s.signup);
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [data, setData] = useState<SignupState>(INITIAL);
  const [error, setError] = useState<string | null>(null);

  const update = (patch: Partial<SignupState>) => setData((d) => ({ ...d, ...patch }));

  const valid = useMemo(() => validateStep(step, data), [step, data]);
  const def = STEP_DEFS[step - 1];

  const goNext = async () => {
    if (!valid.ok) {
      setError(valid.message);
      return;
    }
    setError(null);
    if (step < STEP_DEFS.length) {
      setStep(step + 1);
    } else {
      try {
        await signup({
          name: data.name.trim(),
          email: data.email,
          password: data.password,
          school: data.school,
          department: data.department,
          grade: Number(data.grade),
          admissionYear: Number(data.admissionYear),
        });
        navigate('/', { replace: true });
      } catch (e) {
        setError(e instanceof Error ? e.message : '가입 중 오류가 발생했습니다.');
      }
    }
  };

  const goBack = () => {
    setError(null);
    if (step > 1) setStep(step - 1);
  };

  return (
    <div className={styles.shell}>
      <nav className={styles.nav}>
        <div className={styles.brand}>
          <Logo size={26} />
          <span className={styles.brandName}>CourseHub</span>
        </div>
        <Link
          to="/login"
          style={{ fontSize: 14, color: 'var(--color-ink-dim)', textDecoration: 'none' }}
        >
          이미 계정이 있어요 →
        </Link>
      </nav>

      <div className={styles.body}>
        <Stepper currentStep={step} />

        <div className={styles.card}>
          <div className={styles.stepBadge}>
            STEP {step} / {STEP_DEFS.length}
          </div>
          <h1 className={styles.stepTitle}>{def.title}</h1>
          <p className={styles.stepHelp}>{def.help}</p>

          {step === 1 && <StepAccount data={data} update={update} />}
          {step === 2 && <StepSchool data={data} update={update} />}
          {step === 3 && <StepDeptGrade data={data} update={update} />}
          {step === 4 && <StepDone />}

          {error && <div className={styles.error}>{error}</div>}

          <div className={styles.actions}>
            {step > 1 ? (
              <button type="button" className={styles.pillBtn} onClick={goBack}>
                ← 이전
              </button>
            ) : (
              <span />
            )}
            <button
              type="button"
              className={`${styles.pillBtn} ${styles.pillBtnPrimary}`}
              onClick={goNext}
            >
              {step < STEP_DEFS.length ? '다음 →' : '가입 완료 →'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Stepper({ currentStep }: { currentStep: number }) {
  return (
    <div className={styles.stepper}>
      {STEP_DEFS.map((s, i) => {
        const isDone = s.num < currentStep;
        const isActive = s.num === currentStep;
        const isNext = s.num > currentStep;
        return (
          <Fragment key={s.num}>
            <div className={styles.step}>
              <div
                className={[styles.stepNode, isNext ? styles.stepNodeNext : '']
                  .filter(Boolean)
                  .join(' ')}
              >
                {isDone ? '✓' : s.num}
              </div>
              <span
                className={[styles.stepLabel, isActive ? styles.stepLabelActive : '']
                  .filter(Boolean)
                  .join(' ')}
              >
                {s.label}
              </span>
            </div>
            {i < STEP_DEFS.length - 1 && (
              <div
                className={[styles.stepConnector, isDone ? styles.stepConnectorDone : '']
                  .filter(Boolean)
                  .join(' ')}
              />
            )}
          </Fragment>
        );
      })}
    </div>
  );
}

function StepAccount({
  data,
  update,
}: {
  data: SignupState;
  update: (p: Partial<SignupState>) => void;
}) {
  return (
    <div className={styles.form}>
      <div className={styles.field}>
        <label className={styles.label}>이름</label>
        <input
          className={styles.input}
          type="text"
          value={data.name}
          onChange={(e) => update({ name: e.target.value })}
          placeholder="홍길동"
          autoComplete="name"
        />
      </div>
      <div className={styles.field}>
        <label className={styles.label}>이메일</label>
        <input
          className={styles.input}
          type="email"
          value={data.email}
          onChange={(e) => update({ email: e.target.value })}
          placeholder="hong@khu.ac.kr"
          autoComplete="email"
        />
      </div>
      <div className={styles.field}>
        <label className={styles.label}>비밀번호</label>
        <input
          className={styles.input}
          type="password"
          value={data.password}
          onChange={(e) => update({ password: e.target.value })}
          autoComplete="new-password"
        />
      </div>
      <div className={styles.field}>
        <label className={styles.label}>비밀번호 확인</label>
        <input
          className={styles.input}
          type="password"
          value={data.passwordConfirm}
          onChange={(e) => update({ passwordConfirm: e.target.value })}
          autoComplete="new-password"
        />
      </div>
    </div>
  );
}

function StepSchool({
  data,
  update,
}: {
  data: SignupState;
  update: (p: Partial<SignupState>) => void;
}) {
  return (
    <div className={styles.schoolList}>
      {SCHOOLS.map((s) => {
        const selected = s.name === data.school;
        return (
          <div
            key={s.name}
            className={[
              styles.schoolCard,
              selected ? styles.schoolCardSelected : '',
              !s.active ? styles.schoolCardDisabled : '',
            ]
              .filter(Boolean)
              .join(' ')}
            onClick={() => {
              if (s.active) update({ school: s.name });
            }}
          >
            <div
              className={[styles.schoolAvatar, selected ? styles.schoolAvatarSelected : '']
                .filter(Boolean)
                .join(' ')}
            >
              {s.name[0]}
            </div>
            <div className={styles.schoolBody}>
              <div className={styles.schoolName}>{s.name}</div>
              <div className={styles.schoolSub}>{s.sub}</div>
            </div>
            {selected && <span className={styles.schoolCheck}>✓</span>}
          </div>
        );
      })}
    </div>
  );
}

function StepDeptGrade({
  data,
  update,
}: {
  data: SignupState;
  update: (p: Partial<SignupState>) => void;
}) {
  return (
    <div className={styles.form}>
      <div className={styles.field}>
        <label className={styles.label}>학과</label>
        <select
          className={styles.select}
          value={data.department}
          onChange={(e) => update({ department: e.target.value })}
        >
          <option value="">— 선택 —</option>
          {fixtureDepartments.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </div>
      <div className={styles.fieldRow}>
        <div className={styles.field}>
          <label className={styles.label}>학년</label>
          <select
            className={styles.select}
            value={data.grade}
            onChange={(e) => update({ grade: e.target.value })}
          >
            <option value="">—</option>
            {[1, 2, 3, 4, 5, 6].map((g) => (
              <option key={g} value={g}>
                {g}학년
              </option>
            ))}
          </select>
        </div>
        <div className={styles.field}>
          <label className={styles.label}>입학년도</label>
          <input
            className={styles.input}
            type="number"
            value={data.admissionYear}
            onChange={(e) => update({ admissionYear: e.target.value })}
            placeholder="2023"
            min={MIN_YEAR}
            max={CURRENT_YEAR}
          />
        </div>
      </div>
    </div>
  );
}

function StepDone() {
  return (
    <div className={styles.doneBody}>
      <div className={styles.doneIcon}>✓</div>
      <p className={styles.doneText}>
        가입 정보를 모두 입력했습니다.
        <br />
        가입 완료 버튼을 누르면 작업공간으로 이동합니다.
      </p>
    </div>
  );
}

type StepValidation = { ok: true } | { ok: false; message: string };

function validateStep(step: number, d: SignupState): StepValidation {
  switch (step) {
    case 1:
      if (!d.name.trim() || !d.email.trim() || !d.password || !d.passwordConfirm)
        return { ok: false, message: '모든 항목을 입력하세요.' };
      if (!/^.+@.+\..+$/.test(d.email))
        return { ok: false, message: '올바른 이메일 형식이 아닙니다.' };
      if (d.password !== d.passwordConfirm)
        return { ok: false, message: '비밀번호가 일치하지 않습니다.' };
      if (d.password.length < 8) return { ok: false, message: '비밀번호는 8자 이상이어야 합니다.' };
      return { ok: true };
    case 2:
      if (!d.school) return { ok: false, message: '학교를 선택하세요.' };
      return { ok: true };
    case 3: {
      const grade = Number(d.grade);
      const year = Number(d.admissionYear);
      if (!d.department.trim()) return { ok: false, message: '학과를 선택하세요.' };
      if (!grade || grade < 1 || grade > 6) return { ok: false, message: '학년을 선택하세요.' };
      if (!year || year < MIN_YEAR || year > CURRENT_YEAR)
        return { ok: false, message: `입학년도는 ${MIN_YEAR} ~ ${CURRENT_YEAR} 사이여야 합니다.` };
      return { ok: true };
    }
    case 4:
      return { ok: true };
    default:
      return { ok: true };
  }
}

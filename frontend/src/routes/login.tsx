import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { Logo } from '../components/Logo';
import { useWorkspaceStore } from '../stores/workspaceStore';
import styles from './login.module.css';

export function Login() {
  const login = useWorkspaceStore((s) => s.login);
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = params.get('next') ?? '/';

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const result = await login(email, password);
    if (!result.ok) {
      setError(
        result.reason === 'empty'
          ? '이메일과 비밀번호를 입력하세요.'
          : '이메일 또는 비밀번호가 올바르지 않습니다.',
      );
      return;
    }
    navigate(next, { replace: true });
  };

  return (
    <div className={styles.shell}>
      <nav className={styles.nav}>
        <div className={styles.brand}>
          <Logo size={26} />
          <span className={styles.brandName}>CourseHub</span>
        </div>
      </nav>

      <svg className={styles.arc} viewBox="0 0 400 400" aria-hidden="true">
        <circle cx="200" cy="200" r="160" fill="#f0a86b" opacity="0.2" />
      </svg>

      <div className={styles.center}>
        <form className={styles.card} onSubmit={onSubmit}>
          <Logo size={36} />
          <h1 className={styles.welcome}>다시 만나서 반가워요</h1>
          <p className={styles.welcomeSub}>계정으로 로그인하세요.</p>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="login-email">
              이메일
            </label>
            <input
              id="login-email"
              type="email"
              className={styles.input}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@school.edu"
              autoComplete="email"
            />
          </div>
          <div className={styles.fieldSpacer} />
          <div className={styles.field}>
            <label className={styles.label} htmlFor="login-pw">
              비밀번호
            </label>
            <input
              id="login-pw"
              type="password"
              className={styles.input}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          <div className={styles.forgotRow}>
            <span className={styles.forgot} title="Tier 3 — 추후 제공">
              비밀번호 찾기
            </span>
          </div>

          {error && <div className={styles.error}>{error}</div>}

          <button type="submit" className={styles.submitBtn}>
            로그인 →
          </button>

          <div className={styles.signupRow}>
            처음이신가요?{' '}
            <Link to="/signup" className={styles.signupLink}>
              회원가입
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router';
import { useWorkspaceStore } from '../stores/workspaceStore';
import { Logo } from './Logo';
import styles from './TopBar.module.css';

interface TopBarProps {
  /** brand 와 spacer 사이에 들어가는 breadcrumb chip 영역 */
  children?: ReactNode;
  /** spacer 와 user menu 사이의 액션 슬롯 */
  right?: ReactNode;
}

export function TopBar({ children, right }: TopBarProps) {
  return (
    <header className={styles.bar}>
      <Link to="/" className={styles.brand}>
        <Logo size={22} />
        <span className={styles.name}>CourseHub</span>
      </Link>
      <div className={styles.sep} />
      {children}
      <div className={styles.spacer} />
      {right}
      <UserMenu />
    </header>
  );
}

/** 아바타 클릭 → 프로필·수강 이력·로그아웃을 모은 드롭다운. (드롭다운 패턴은 SortDropdown과 동일.) */
function UserMenu() {
  const navigate = useNavigate();
  const user = useWorkspaceStore((s) => s.currentUser);
  const logout = useWorkspaceStore((s) => s.logout);
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  if (!user) return null;

  // name 도입 전 가입한 계정은 name=null → 이메일 local-part로 fallback.
  const displayName = user.name?.trim() || user.email.split('@')[0];
  const initial = displayName.charAt(0).toUpperCase();

  const go = (path: string) => {
    setOpen(false);
    navigate(path);
  };

  return (
    <div className={styles.userWrap} ref={wrapRef}>
      <button
        type="button"
        className={styles.avatar}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="사용자 메뉴"
      >
        {initial}
      </button>
      {open && (
        <div className={styles.userMenu} role="menu">
          <div className={styles.userMeta}>
            <div className={styles.userName}>{displayName}</div>
            <div className={styles.userEmail}>{user.email}</div>
          </div>
          <div className={styles.menuSep} />
          <button type="button" role="menuitem" className={styles.menuItem} onClick={() => go('/profile')}>
            프로필
          </button>
          <button type="button" role="menuitem" className={styles.menuItem} onClick={() => go('/history')}>
            수강 이력
          </button>
          <div className={styles.menuSep} />
          <button
            type="button"
            role="menuitem"
            className={[styles.menuItem, styles.menuItemDanger].join(' ')}
            onClick={() => {
              logout();
              navigate('/landing', { replace: true });
            }}
          >
            로그아웃
          </button>
        </div>
      )}
    </div>
  );
}

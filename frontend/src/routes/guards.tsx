import type { ReactElement } from 'react';
import { Navigate, useLocation } from 'react-router';
import { useWorkspaceStore } from '../stores/workspaceStore';

/**
 * 인증된 사용자만 접근.
 * 미인증 시 / 진입은 /landing redirect, 그 외 인증 필요 경로는 /login?next=원경로 redirect.
 * (spec L75-76)
 * authReady가 false면 hydrate 진행 중 — render 보류 (flicker 방지).
 */
export function ProtectedRoute({ children }: { children: ReactElement }) {
  const user = useWorkspaceStore((s) => s.currentUser);
  const authReady = useWorkspaceStore((s) => s.authReady);
  const location = useLocation();
  if (!authReady) return null;
  if (!user) {
    if (location.pathname === '/') {
      return <Navigate to="/landing" replace />;
    }
    const next = encodeURIComponent(`${location.pathname}${location.search}`);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return children;
}

/**
 * operator(role='admin')만 접근. 미인증 시 /login?next= redirect,
 * 인증됐으나 권한 없으면 작업공간(/)으로 redirect (spec L812 권한 없음 차단).
 */
export function AdminRoute({ children }: { children: ReactElement }) {
  const user = useWorkspaceStore((s) => s.currentUser);
  const authReady = useWorkspaceStore((s) => s.authReady);
  const location = useLocation();
  if (!authReady) return null;
  if (!user) {
    const next = encodeURIComponent(`${location.pathname}${location.search}`);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  if (user.role !== 'admin') {
    return <Navigate to="/" replace />;
  }
  return children;
}

/** 미인증 사용자만 접근 (landing/login/signup). 인증된 사용자는 / redirect. */
export function PublicOnlyRoute({ children }: { children: ReactElement }) {
  const user = useWorkspaceStore((s) => s.currentUser);
  const authReady = useWorkspaceStore((s) => s.authReady);
  if (!authReady) return null;
  if (user) {
    return <Navigate to="/" replace />;
  }
  return children;
}

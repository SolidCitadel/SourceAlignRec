import { useEffect } from 'react';
import { createBrowserRouter, RouterProvider } from 'react-router';
import { ReviewModal } from './components/ReviewModal';
import { Admin } from './routes/admin';
import { History } from './routes/history';
import { Landing } from './routes/landing';
import { Login } from './routes/login';
import { Professor } from './routes/professor';
import { Profile } from './routes/profile';
import { Reviews } from './routes/reviews';
import { Signup } from './routes/signup';
import { Styleguide } from './routes/styleguide';
import { Workspace } from './routes/workspace';
import { AdminRoute, ProtectedRoute, PublicOnlyRoute } from './routes/guards';
import { useWorkspaceStore } from './stores/workspaceStore';

const router = createBrowserRouter([
  {
    path: '/',
    element: (
      <ProtectedRoute>
        <Workspace />
      </ProtectedRoute>
    ),
  },
  {
    path: '/landing',
    element: (
      <PublicOnlyRoute>
        <Landing />
      </PublicOnlyRoute>
    ),
  },
  {
    path: '/login',
    element: (
      <PublicOnlyRoute>
        <Login />
      </PublicOnlyRoute>
    ),
  },
  {
    path: '/signup',
    element: (
      <PublicOnlyRoute>
        <Signup />
      </PublicOnlyRoute>
    ),
  },
  {
    path: '/history',
    element: (
      <ProtectedRoute>
        <History />
      </ProtectedRoute>
    ),
  },
  {
    path: '/profile',
    element: (
      <ProtectedRoute>
        <Profile />
      </ProtectedRoute>
    ),
  },
  {
    path: '/offering/:id/reviews',
    element: (
      <ProtectedRoute>
        <Reviews />
      </ProtectedRoute>
    ),
  },
  {
    path: '/professor/:id',
    element: (
      <ProtectedRoute>
        <Professor />
      </ProtectedRoute>
    ),
  },
  {
    path: '/admin',
    element: (
      <AdminRoute>
        <Admin />
      </AdminRoute>
    ),
  },
  { path: '/styleguide', element: <Styleguide /> },
]);

export default function App() {
  const hydrateAuth = useWorkspaceStore((s) => s.hydrateAuth);
  useEffect(() => {
    hydrateAuth();
  }, [hydrateAuth]);

  return (
    <>
      <RouterProvider router={router} />
      <ReviewModal />
    </>
  );
}

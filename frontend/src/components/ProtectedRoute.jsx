import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { getSession } from '../lib/auth';

export default function ProtectedRoute({ roles, children }) {
  const location = useLocation();
  const session = getSession();
  if (!session?.access_token) {
    return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
  }
  if (roles?.length && !roles.includes(session.role)) {
    return <Navigate to="/" replace />;
  }
  return children;
}

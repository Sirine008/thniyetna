import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { getSession } from '../lib/auth';

export default function ProtectedRoute({ roles, children }) {
  const location = useLocation();
  const session = getSession();
  if (!session?.access_token) {
    // keep the query string: a shared citizen route (?from=…&to=…) survives the login
    return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  }
  if (roles?.length && !roles.includes(session.role)) {
    return <Navigate to="/" replace />;
  }
  return children;
}

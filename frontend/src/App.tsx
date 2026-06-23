import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from '@/contexts/AuthContext';
import Layout from '@/components/Layout';
import LoginPage from '@/pages/Login';
import OverviewPage from '@/pages/Overview';
import DevicesPage from '@/pages/Devices';
import MikrotikDetailPage from '@/pages/MikrotikDetail';
import EsxiDetailPage from '@/pages/EsxiDetail';
import VmGuestDetailPage from '@/pages/VmGuestDetail';
import AlertsPage from '@/pages/Alerts';
import SettingsPage from '@/pages/Settings';
import { Loading } from '@/components/ui';

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { token, loading } = useAuth();
  if (loading) return <Loading text="Loading..." centered />;
  if (!token) return <Navigate to="/login" replace />;
  return <Layout>{children}</Layout>;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <Routes>
              <Route path="/" element={<OverviewPage />} />
              <Route path="/devices" element={<DevicesPage />} />
              <Route path="/devices/:id" element={<MikrotikDetailPage />} />
              <Route path="/devices/:id/esxi" element={<EsxiDetailPage />} />
              <Route path="/devices/:id/vm" element={<VmGuestDetailPage />} />
              <Route path="/alerts" element={<AlertsPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}

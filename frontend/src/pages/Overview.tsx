import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Server, Router, Monitor, AlertTriangle,
  ArrowUpRight, ArrowDownRight, Activity,
} from 'lucide-react';
import { Card, StatCard, StatusBadge, Loading, EmptyState } from '@/components/ui';
import { dashboardApi, deviceApi, alertApi } from '@/services/api';

interface OverviewData {
  devices: { total: number; up: number; down: number; unknown: number };
  active_alerts: number;
  critical_alerts: number;
}

interface DeviceItem {
  id: number;
  name: string;
  device_type: string;
  status: string;
  ip_address: string | null;
  last_seen_at: string | null;
}

interface AlertItem {
  id: number;
  device_name: string;
  severity: string;
  state: string;
  message: string;
  created_at: string;
}

export default function OverviewPage() {
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [devices, setDevices] = useState<DeviceItem[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const fetchData = useCallback(async () => {
    try {
      const [ovRes, devRes, alRes] = await Promise.all([
        dashboardApi.overview(),
        deviceApi.list({ is_active: true }),
        alertApi.list({ state: 'firing', limit: 5 }),
      ]);
      setOverview(ovRes.data);
      setDevices(devRes.data);
      setAlerts(alRes.data);
    } catch {
      // silent — auth interceptor handles 401
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000); // refresh every 30s
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) return <Loading text="Loading dashboard..." centered />;

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h2 className="text-xl font-bold text-gray-900">Dashboard Overview</h2>
        <p className="text-sm text-gray-500 mt-1">Real-time network monitoring status</p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Devices"
          value={overview?.devices.total || 0}
          icon={<Server className="w-5 h-5" />}
          color="blue"
        />
        <StatCard
          label="Online"
          value={overview?.devices.up || 0}
          icon={<ArrowUpRight className="w-5 h-5" />}
          color="green"
          subtitle={`${overview?.devices.total ? Math.round(((overview.devices.up || 0) / overview.devices.total) * 100) : 0}% uptime`}
        />
        <StatCard
          label="Offline"
          value={overview?.devices.down || 0}
          icon={<ArrowDownRight className="w-5 h-5" />}
          color="red"
        />
        <StatCard
          label="Active Alerts"
          value={overview?.active_alerts || 0}
          icon={<AlertTriangle className="w-5 h-5" />}
          color={overview?.critical_alerts ? 'red' : 'yellow'}
          subtitle={overview?.critical_alerts ? `${overview.critical_alerts} critical` : 'No critical'}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Device status list */}
        <Card
          className="lg:col-span-2"
          title="Device Status"
          subtitle={`${devices.length} active devices`}
          action={
            <button
              onClick={() => navigate('/devices')}
              className="text-xs text-primary-600 hover:text-primary-700 font-medium"
            >
              View All →
            </button>
          }
        >
          {devices.length === 0 ? (
            <EmptyState
              icon={<Monitor className="w-12 h-12" />}
              title="No devices configured"
              description="Add your first Mikrotik, ESXi, or VM guest device to start monitoring."
              action={
                <button
                  onClick={() => navigate('/settings')}
                  className="text-sm text-primary-600 hover:text-primary-700 font-medium"
                >
                  + Add Device
                </button>
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-gray-500 uppercase tracking-wider">
                    <th className="pb-3 pr-4">Device</th>
                    <th className="pb-3 pr-4">Type</th>
                    <th className="pb-3 pr-4">IP Address</th>
                    <th className="pb-3 pr-4">Status</th>
                    <th className="pb-3">Last Seen</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {devices.slice(0, 10).map((dev) => (
                    <tr
                      key={dev.id}
                      className="hover:bg-gray-50 cursor-pointer transition-colors"
                      onClick={() => navigate(`/devices/${dev.id}`)}
                    >
                      <td className="py-3 pr-4 font-medium text-gray-800">{dev.name}</td>
                      <td className="py-3 pr-4">
                        <span className="inline-flex items-center gap-1.5 text-xs text-gray-600">
                          {dev.device_type === 'mikrotik' && <Router className="w-3.5 h-3.5" />}
                          {dev.device_type === 'esxi' && <Server className="w-3.5 h-3.5" />}
                          {dev.device_type === 'vm_guest' && <Monitor className="w-3.5 h-3.5" />}
                          {dev.device_type}
                        </span>
                      </td>
                      <td className="py-3 pr-4 text-gray-500 font-mono text-xs">{dev.ip_address || '—'}</td>
                      <td className="py-3 pr-4">
                        <StatusBadge status={dev.status} />
                      </td>
                      <td className="py-3 text-gray-400 text-xs">
                        {dev.last_seen_at
                          ? new Date(dev.last_seen_at).toLocaleString()
                          : 'Never'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* Recent alerts */}
        <Card
          title="Recent Alerts"
          subtitle="Latest firing alerts"
          action={
            <button
              onClick={() => navigate('/alerts')}
              className="text-xs text-primary-600 hover:text-primary-700 font-medium"
            >
              View All →
            </button>
          }
        >
          {alerts.length === 0 ? (
            <EmptyState
              icon={<Activity className="w-10 h-10" />}
              title="No active alerts"
              description="All systems running normally."
            />
          ) : (
            <div className="space-y-3">
              {alerts.map((alert) => (
                <div
                  key={alert.id}
                  className="p-3 rounded-lg border border-gray-100 hover:bg-gray-50 cursor-pointer transition-colors"
                  onClick={() => navigate('/alerts')}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-medium text-gray-800">{alert.device_name}</span>
                    <span
                      className={`text-xs font-bold uppercase ${
                        alert.severity === 'critical'
                          ? 'text-red-600'
                          : alert.severity === 'warning'
                          ? 'text-yellow-600'
                          : 'text-blue-600'
                      }`}
                    >
                      {alert.severity}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 line-clamp-2">{alert.message}</p>
                  <p className="text-xs text-gray-400 mt-1">
                    {new Date(alert.created_at).toLocaleString()}
                  </p>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

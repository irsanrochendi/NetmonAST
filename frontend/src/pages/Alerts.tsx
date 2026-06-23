import { useEffect, useState, useCallback } from 'react';
import { AlertTriangle, CheckCircle, Bell, Filter } from 'lucide-react';
import { Card, Badge, Button, Loading, EmptyState } from '@/components/ui';
import { alertApi } from '@/services/api';

interface AlertItem {
  id: number;
  device_name: string;
  severity: string;
  state: string;
  metric_name: string;
  metric_value: number;
  threshold: number;
  message: string;
  acknowledged_by?: string;
  created_at: string;
}

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<{ state?: string; severity?: string }>({});

  const fetchAlerts = useCallback(async () => {
    setLoading(true);
    try {
      const res = await alertApi.list({ ...filter, limit: 100 });
      setAlerts(res.data);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    fetchAlerts();
    const interval = setInterval(fetchAlerts, 15000);
    return () => clearInterval(interval);
  }, [fetchAlerts]);

  const handleAcknowledge = async (id: number) => {
    try {
      await alertApi.acknowledge(id, 'admin');
      fetchAlerts();
    } catch {
      // silent
    }
  };

  const handleResolve = async (id: number) => {
    try {
      await alertApi.resolve(id);
      fetchAlerts();
    } catch {
      // silent
    }
  };

  const severityColor: Record<string, 'danger' | 'warning' | 'info'> = {
    critical: 'danger',
    warning: 'warning',
    info: 'info',
  };

  const stateColor: Record<string, 'danger' | 'warning' | 'success'> = {
    firing: 'danger',
    acknowledged: 'warning',
    resolved: 'success',
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-gray-900">Alerts</h2>
        <p className="text-sm text-gray-500 mt-1">Monitor and manage alert notifications</p>
      </div>

      {/* Filters */}
      <Card>
        <div className="flex flex-wrap items-center gap-3">
          <Filter className="w-4 h-4 text-gray-400" />
          <span className="text-xs text-gray-500 font-medium">Filter:</span>

          <div className="flex gap-1">
            {['all', 'firing', 'acknowledged', 'resolved'].map((s) => (
              <button
                key={s}
                onClick={() => setFilter((f) => ({ ...f, state: s === 'all' ? undefined : s }))}
                className={`px-3 py-1 text-xs rounded-full font-medium transition ${
                  (s === 'all' && !filter.state) || filter.state === s
                    ? 'bg-primary-100 text-primary-700'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </button>
            ))}
          </div>

          <div className="w-px h-6 bg-gray-200" />

          <div className="flex gap-1">
            {['all', 'critical', 'warning', 'info'].map((sev) => (
              <button
                key={sev}
                onClick={() => setFilter((f) => ({ ...f, severity: sev === 'all' ? undefined : sev }))}
                className={`px-3 py-1 text-xs rounded-full font-medium transition ${
                  (sev === 'all' && !filter.severity) || filter.severity === sev
                    ? 'bg-primary-100 text-primary-700'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {sev.charAt(0).toUpperCase() + sev.slice(1)}
              </button>
            ))}
          </div>
        </div>
      </Card>

      {/* Alert list */}
      {loading ? (
        <Loading text="Loading alerts..." centered />
      ) : alerts.length === 0 ? (
        <EmptyState
          icon={<CheckCircle className="w-12 h-12" />}
          title="No alerts"
          description="No alerts match the current filter criteria."
        />
      ) : (
        <div className="space-y-3">
          {alerts.map((alert) => (
            <Card key={alert.id} className="border-l-4" title={undefined}>
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <Badge variant={severityColor[alert.severity] || 'info'} size="md">
                      {alert.severity.toUpperCase()}
                    </Badge>
                    <Badge variant={stateColor[alert.state] || 'neutral'}>
                      {alert.state.toUpperCase()}
                    </Badge>
                    <span className="text-xs text-gray-400">#{alert.id}</span>
                  </div>

                  <p className="text-sm font-medium text-gray-800">{alert.message}</p>

                  <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                    <span>Device: <strong>{alert.device_name}</strong></span>
                    <span>Metric: <code className="bg-gray-100 px-1 rounded">{alert.metric_name}</code></span>
                    <span>Value: <strong>{alert.metric_value.toFixed(2)}</strong> / {alert.threshold.toFixed(2)}</span>
                  </div>

                  <p className="text-xs text-gray-400 mt-1">
                    {new Date(alert.created_at).toLocaleString()}
                    {alert.acknowledged_by && ` · Acknowledged by ${alert.acknowledged_by}`}
                  </p>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2 shrink-0">
                  {alert.state === 'firing' && (
                    <Button size="sm" variant="secondary" onClick={() => handleAcknowledge(alert.id)}>
                      <Bell className="w-3.5 h-3.5" />
                      Ack
                    </Button>
                  )}
                  {(alert.state === 'firing' || alert.state === 'acknowledged') && (
                    <Button size="sm" variant="ghost" onClick={() => handleResolve(alert.id)}>
                      <CheckCircle className="w-3.5 h-3.5" />
                      Resolve
                    </Button>
                  )}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

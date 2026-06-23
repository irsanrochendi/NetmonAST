import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Monitor, Clock } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Card, Loading, EmptyState, StatusBadge, Badge } from '@/components/ui';
import { deviceApi, metricApi } from '@/services/api';

interface DeviceDetail {
  id: number;
  name: string;
  ip_address: string | null;
  status: string;
  agent_token: string | null;
  last_seen_at: string | null;
  created_at: string;
}

interface MetricPoint {
  time: string;
  value: number;
}

export default function VmGuestDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [device, setDevice] = useState<DeviceDetail | null>(null);
  const [cpuData, setCpuData] = useState<MetricPoint[]>([]);
  const [memData, setMemData] = useState<MetricPoint[]>([]);
  const [diskData, setDiskData] = useState<MetricPoint[]>([]);
  const [uptime, setUptime] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [hours, setHours] = useState(24);

  useEffect(() => {
    if (!id) return;
    const fetchAll = async () => {
      setLoading(true);
      try {
        const devRes = await deviceApi.get(Number(id));
        setDevice(devRes.data);

        const [cpuRes, memRes, diskRes, uptimeRes] = await Promise.all([
          metricApi.get(Number(id), { metric_name: 'cpu_usage', hours }),
          metricApi.get(Number(id), { metric_name: 'mem_usage_pct', hours }),
          metricApi.get(Number(id), { metric_name: 'disk_usage_pct', hours }),
          metricApi.get(Number(id), { metric_name: 'uptime_seconds', hours: 1 }),
        ]);

        setCpuData(cpuRes.data[0]?.points.map((p: MetricPoint) => ({
          time: new Date(p.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          value: p.value,
        })) || []);

        setMemData(memRes.data[0]?.points.map((p: MetricPoint) => ({
          time: new Date(p.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          value: p.value,
        })) || []);

        setDiskData(diskRes.data[0]?.points.map((p: MetricPoint) => ({
          time: new Date(p.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          value: p.value,
        })) || []);

        if (uptimeRes.data[0]?.points?.length > 0) {
          setUptime(uptimeRes.data[0].points[uptimeRes.data[0].points.length - 1].value);
        }
      } catch {
        // silent
      } finally {
        setLoading(false);
      }
    };
    fetchAll();
  }, [id, hours]);

  if (loading && !device) return <Loading text="Loading VM..." centered />;
  if (!device) return <EmptyState title="VM not found" />;

  const formatUptime = (seconds: number) => {
    const d = Math.floor(seconds / 86400);
    const h = Math.floor((seconds % 86400) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return `${d}d ${h}h ${m}m`;
  };

  const getLatest = (data: MetricPoint[]) => data[data.length - 1]?.value ?? 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button onClick={() => navigate('/devices')} className="p-2 hover:bg-gray-100 rounded-lg">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="flex items-center gap-3">
          <div className="p-2 bg-cyan-100 rounded-lg">
            <Monitor className="w-6 h-6 text-cyan-600" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-gray-900">{device.name}</h2>
            <div className="flex items-center gap-3 mt-0.5">
              {device.ip_address && <span className="text-sm text-gray-500 font-mono">{device.ip_address}</span>}
              <StatusBadge status={device.status} />
            </div>
          </div>
        </div>
      </div>

      {/* Time range */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-500">Time range:</span>
        {[1, 6, 24, 72].map((h) => (
          <button
            key={h}
            onClick={() => setHours(h)}
            className={`px-3 py-1 text-xs rounded-full font-medium transition ${
              hours === h ? 'bg-primary-100 text-primary-700' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {h}h
          </button>
        ))}
      </div>

      {/* Quick stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <p className="text-xs text-gray-500 uppercase">CPU</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{getLatest(cpuData).toFixed(1)}%</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <p className="text-xs text-gray-500 uppercase">Memory</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{getLatest(memData).toFixed(1)}%</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <p className="text-xs text-gray-500 uppercase">Disk</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{getLatest(diskData).toFixed(1)}%</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-gray-400" />
            <p className="text-xs text-gray-500 uppercase">Uptime</p>
          </div>
          <p className="text-lg font-bold text-gray-900 mt-1">{formatUptime(uptime)}</p>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card title="CPU Usage" className="min-h-[280px]">
          {cpuData.length === 0 ? (
            <EmptyState title="No data" description="Agent not reporting yet." />
          ) : (
            <ResponsiveContainer width="100%" height={230}>
              <AreaChart data={cpuData}>
                <defs>
                  <linearGradient id="vmCpuGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="time" tick={{ fontSize: 11 }} stroke="#9ca3af" />
                <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} stroke="#9ca3af" unit="%" />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Area type="monotone" dataKey="value" stroke="#06b6d4" fill="url(#vmCpuGrad)" strokeWidth={2} name="CPU %" />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Memory Usage" className="min-h-[280px]">
          {memData.length === 0 ? (
            <EmptyState title="No data" />
          ) : (
            <ResponsiveContainer width="100%" height={230}>
              <AreaChart data={memData}>
                <defs>
                  <linearGradient id="vmMemGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="time" tick={{ fontSize: 11 }} stroke="#9ca3af" />
                <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} stroke="#9ca3af" unit="%" />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Area type="monotone" dataKey="value" stroke="#8b5cf6" fill="url(#vmMemGrad)" strokeWidth={2} name="Memory %" />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Disk Usage" className="min-h-[280px]">
          {diskData.length === 0 ? (
            <EmptyState title="No data" />
          ) : (
            <ResponsiveContainer width="100%" height={230}>
              <AreaChart data={diskData}>
                <defs>
                  <linearGradient id="vmDiskGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="time" tick={{ fontSize: 11 }} stroke="#9ca3af" />
                <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} stroke="#9ca3af" unit="%" />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Area type="monotone" dataKey="value" stroke="#f59e0b" fill="url(#vmDiskGrad)" strokeWidth={2} name="Disk %" />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>
    </div>
  );
}

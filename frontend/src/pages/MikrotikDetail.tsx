import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Router, RefreshCw } from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, AreaChart, Area,
} from 'recharts';
import { Card, Loading, EmptyState, StatusBadge } from '@/components/ui';
import { deviceApi, metricApi } from '@/services/api';

interface DeviceDetail {
  id: number;
  name: string;
  device_type: string;
  ip_address: string | null;
  snmp_community?: string;
  status: string;
  last_poll_at: string | null;
  last_seen_at: string | null;
  created_at: string;
}

interface MetricPoint {
  time: string;
  value: number;
}

interface InterfacePoint {
  time: string;
  rx_bytes: number;
  tx_bytes: number;
}

export default function MikrotikDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [device, setDevice] = useState<DeviceDetail | null>(null);
  const [cpuData, setCpuData] = useState<MetricPoint[]>([]);
  const [memData, setMemData] = useState<MetricPoint[]>([]);
  const [interfaces, setInterfaces] = useState<string[]>([]);
  const [selectedIf, setSelectedIf] = useState<string>('');
  const [ifData, setIfData] = useState<InterfacePoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [hours, setHours] = useState(24);

  useEffect(() => {
    if (!id) return;
    const fetchAll = async () => {
      setLoading(true);
      try {
        const devRes = await deviceApi.get(Number(id));
        setDevice(devRes.data);

        const [cpuRes, memRes, ifRes] = await Promise.all([
          metricApi.get(Number(id), { metric_name: 'cpu_usage', hours }),
          metricApi.get(Number(id), { metric_name: 'mem_usage_pct', hours }),
          metricApi.getInterfaces(Number(id), { hours: Math.min(hours, 24) }),
        ]);

        setCpuData(cpuRes.data[0]?.points.map((p: MetricPoint) => ({
          time: new Date(p.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          value: p.value,
        })) || []);

        setMemData(memRes.data[0]?.points.map((p: MetricPoint) => ({
          time: new Date(p.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          value: p.value,
        })) || []);

        const ifNames = ifRes.data.map((i: { interface_name: string }) => i.interface_name);
        setInterfaces(ifNames);
        if (ifNames.length > 0) {
          setSelectedIf(ifNames[0]);
          const firstIf = ifRes.data[0];
          setIfData(firstIf.points.map((p: InterfacePoint) => ({
            time: new Date(p.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            rx_bytes: p.rx_bytes,
            tx_bytes: p.tx_bytes,
          })));
        }
      } catch {
        // auth interceptor handles errors
      } finally {
        setLoading(false);
      }
    };
    fetchAll();
  }, [id, hours]);

  const fetchInterfaceData = async (ifname: string) => {
    if (!id) return;
    setSelectedIf(ifname);
    try {
      const res = await metricApi.getInterfaces(Number(id), { ifname, hours: Math.min(hours, 24) });
      const data = res.data[0];
      if (data) {
        setIfData(data.points.map((p: InterfacePoint) => ({
          time: new Date(p.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          rx_bytes: p.rx_bytes,
          tx_bytes: p.tx_bytes,
        })));
      }
    } catch {
      // silent
    }
  };

  if (loading && !device) return <Loading text="Loading device..." centered />;
  if (!device) return <EmptyState title="Device not found" />;

  const formatBytes = (bytes: number) => {
    if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
    if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(1)} MB`;
    if (bytes >= 1e3) return `${(bytes / 1e3).toFixed(1)} KB`;
    return `${bytes} B`;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button onClick={() => navigate('/devices')} className="p-2 hover:bg-gray-100 rounded-lg">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="flex items-center gap-3">
          <div className="p-2 bg-orange-100 rounded-lg">
            <Router className="w-6 h-6 text-orange-600" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-gray-900">{device.name}</h2>
            <div className="flex items-center gap-3 mt-0.5">
              <span className="text-sm text-gray-500 font-mono">{device.ip_address}</span>
              <StatusBadge status={device.status} />
            </div>
          </div>
        </div>
      </div>

      {/* Time range selector */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-500">Time range:</span>
        {[1, 6, 24, 72].map((h) => (
          <button
            key={h}
            onClick={() => setHours(h)}
            className={`px-3 py-1 text-xs rounded-full font-medium transition ${
              hours === h
                ? 'bg-primary-100 text-primary-700'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {h}h
          </button>
        ))}
        <button
          onClick={() => setHours(hours)}
          className="p-1.5 hover:bg-gray-100 rounded-lg ml-2"
        >
          <RefreshCw className="w-4 h-4 text-gray-500" />
        </button>
      </div>

      {/* CPU & Memory charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="CPU Usage" subtitle="Percentage over time" className="min-h-[300px]">
          {cpuData.length === 0 ? (
            <EmptyState title="No CPU data" description="Metrics will appear after polling starts." />
          ) : (
            <ResponsiveContainer width="100%" height={250}>
              <AreaChart data={cpuData}>
                <defs>
                  <linearGradient id="cpuGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#f97316" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#f97316" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="time" tick={{ fontSize: 11 }} stroke="#9ca3af" />
                <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} stroke="#9ca3af" unit="%" />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Area type="monotone" dataKey="value" stroke="#f97316" fill="url(#cpuGrad)" strokeWidth={2} name="CPU %" />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Memory Usage" subtitle="Percentage over time" className="min-h-[300px]">
          {memData.length === 0 ? (
            <EmptyState title="No memory data" description="Metrics will appear after polling starts." />
          ) : (
            <ResponsiveContainer width="100%" height={250}>
              <AreaChart data={memData}>
                <defs>
                  <linearGradient id="memGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="time" tick={{ fontSize: 11 }} stroke="#9ca3af" />
                <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} stroke="#9ca3af" unit="%" />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Area type="monotone" dataKey="value" stroke="#3b82f6" fill="url(#memGrad)" strokeWidth={2} name="Memory %" />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      {/* Interface traffic */}
      <Card title="Interface Traffic" subtitle="RX/TX bytes per interface">
        {interfaces.length === 0 ? (
          <EmptyState title="No interface data" description="Interface metrics will appear after SNMP polling." />
        ) : (
          <>
            {/* Interface tabs */}
            <div className="flex flex-wrap gap-2 mb-4">
              {interfaces.map((name) => (
                <button
                  key={name}
                  onClick={() => fetchInterfaceData(name)}
                  className={`px-3 py-1.5 text-xs rounded-lg font-medium transition ${
                    selectedIf === name
                      ? 'bg-primary-100 text-primary-700 border border-primary-200'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  {name}
                </button>
              ))}
            </div>

            {/* RX/TX table */}
            <div className="overflow-x-auto mb-4">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-gray-500 uppercase">
                    <th className="pb-2">Metric</th>
                    <th className="pb-2">Latest RX</th>
                    <th className="pb-2">Latest TX</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  <tr>
                    <td className="py-2 font-medium text-gray-700">{selectedIf}</td>
                    <td className="py-2 text-gray-500 font-mono text-xs">
                      {ifData.length > 0 ? formatBytes(ifData[ifData.length - 1]?.rx_bytes || 0) : '—'}
                    </td>
                    <td className="py-2 text-gray-500 font-mono text-xs">
                      {ifData.length > 0 ? formatBytes(ifData[ifData.length - 1]?.tx_bytes || 0) : '—'}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            {/* Traffic chart */}
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={ifData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="time" tick={{ fontSize: 11 }} stroke="#9ca3af" />
                <YAxis tick={{ fontSize: 11 }} stroke="#9ca3af" tickFormatter={(v) => formatBytes(v)} />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} formatter={(v: number) => formatBytes(v)} />
                <Line type="monotone" dataKey="rx_bytes" stroke="#22c55e" strokeWidth={2} dot={false} name="RX" />
                <Line type="monotone" dataKey="tx_bytes" stroke="#ef4444" strokeWidth={2} dot={false} name="TX" />
              </LineChart>
            </ResponsiveContainer>
          </>
        )}
      </Card>
    </div>
  );
}

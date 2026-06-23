import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Server, HardDrive, Monitor } from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, Cell, PieChart, Pie,
} from 'recharts';
import { Card, Loading, EmptyState, StatusBadge } from '@/components/ui';
import { deviceApi, metricApi } from '@/services/api';

interface DeviceDetail {
  id: number;
  name: string;
  ip_address: string | null;
  status: string;
  last_poll_at: string | null;
  created_at: string;
}

interface MetricPoint {
  time: string;
  value: number;
}

export default function EsxiDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [device, setDevice] = useState<DeviceDetail | null>(null);
  const [cpuData, setCpuData] = useState<MetricPoint[]>([]);
  const [memData, setMemData] = useState<MetricPoint[]>([]);
  const [dsData, setDsData] = useState<{ name: string; usage_pct: number; used_gb: number; capacity_gb: number }[]>([]);
  const [loading, setLoading] = useState(true);
  const [hours, setHours] = useState(24);

  useEffect(() => {
    if (!id) return;
    const fetchAll = async () => {
      setLoading(true);
      try {
        const devRes = await deviceApi.get(Number(id));
        setDevice(devRes.data);

        const [cpuRes, memRes] = await Promise.all([
          metricApi.get(Number(id), { metric_name: 'cpu_usage_pct', hours }),
          metricApi.get(Number(id), { metric_name: 'mem_usage_pct', hours }),
        ]);

        setCpuData(cpuRes.data[0]?.points.map((p: MetricPoint) => ({
          time: new Date(p.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          value: p.value,
        })) || []);

        setMemData(memRes.data[0]?.points.map((p: MetricPoint) => ({
          time: new Date(p.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          value: p.value,
        })) || []);

        // Datastore data
        const dsUsage = await metricApi.get(Number(id), { metric_name: 'ds_usage_pct', hours: 1 });
        const dsCapacity = await metricApi.get(Number(id), { metric_name: 'ds_capacity_gb', hours: 1 });
        const dsUsed = await metricApi.get(Number(id), { metric_name: 'ds_used_gb', hours: 1 });

        const dsNames = dsUsage.data[0]?.points.map((p: MetricPoint) => p.time) || [];
        if (dsCapacity.data[0]?.points) {
          const datastores = dsCapacity.data[0].points.map((p: MetricPoint, i: number) => {
            const usagePt = dsUsage.data[0]?.points[i];
            const usedPt = dsUsed.data[0]?.points[i];
            return {
              name: `DS-${i + 1}`,
              usage_pct: usagePt?.value || 0,
              used_gb: usedPt?.value || 0,
              capacity_gb: p.value,
            };
          });
          setDsData(datastores);
        }
      } catch {
        // silent
      } finally {
        setLoading(false);
      }
    };
    fetchAll();
  }, [id, hours]);

  if (loading && !device) return <Loading text="Loading host..." centered />;
  if (!device) return <EmptyState title="Host not found" />;

  const COLORS = ['#3b82f6', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6'];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button onClick={() => navigate('/devices')} className="p-2 hover:bg-gray-100 rounded-lg">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="flex items-center gap-3">
          <div className="p-2 bg-purple-100 rounded-lg">
            <Server className="w-6 h-6 text-purple-600" />
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

      {/* CPU & Memory */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Host CPU Usage" className="min-h-[280px]">
          {cpuData.length === 0 ? (
            <EmptyState title="No CPU data" />
          ) : (
            <ResponsiveContainer width="100%" height={230}>
              <AreaChart data={cpuData}>
                <defs>
                  <linearGradient id="esxiCpuGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="time" tick={{ fontSize: 11 }} stroke="#9ca3af" />
                <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} stroke="#9ca3af" unit="%" />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Area type="monotone" dataKey="value" stroke="#8b5cf6" fill="url(#esxiCpuGrad)" strokeWidth={2} name="CPU %" />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Host Memory Usage" className="min-h-[280px]">
          {memData.length === 0 ? (
            <EmptyState title="No memory data" />
          ) : (
            <ResponsiveContainer width="100%" height={230}>
              <AreaChart data={memData}>
                <defs>
                  <linearGradient id="esxiMemGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="time" tick={{ fontSize: 11 }} stroke="#9ca3af" />
                <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} stroke="#9ca3af" unit="%" />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Area type="monotone" dataKey="value" stroke="#06b6d4" fill="url(#esxiMemGrad)" strokeWidth={2} name="Memory %" />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      {/* Datastores */}
      <Card title="Datastore Usage" subtitle="Storage capacity and utilization">
        {dsData.length === 0 ? (
          <EmptyState
            icon={<HardDrive className="w-10 h-10" />}
            title="No datastore data"
            description="Datastore metrics will appear after ESXi polling."
          />
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={dsData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11 }} stroke="#9ca3af" unit="%" />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} stroke="#9ca3af" width={80} />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Bar dataKey="usage_pct" name="Usage %" radius={[0, 4, 4, 0]}>
                  {dsData.map((_, index) => (
                    <Cell key={index} fill={dsData[index].usage_pct > 80 ? '#ef4444' : COLORS[index % COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>

            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500 uppercase">
                  <th className="pb-2">Datastore</th>
                  <th className="pb-2">Used</th>
                  <th className="pb-2">Total</th>
                  <th className="pb-2">Usage</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {dsData.map((ds, i) => (
                  <tr key={i}>
                    <td className="py-2 font-medium text-gray-700">{ds.name}</td>
                    <td className="py-2 text-gray-500">{ds.used_gb.toFixed(1)} GB</td>
                    <td className="py-2 text-gray-500">{ds.capacity_gb.toFixed(1)} GB</td>
                    <td className="py-2">
                      <span className={`font-medium ${ds.usage_pct > 80 ? 'text-red-600' : 'text-green-600'}`}>
                        {ds.usage_pct.toFixed(1)}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

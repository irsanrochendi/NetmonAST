import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Router, Server, Monitor } from 'lucide-react';
import { Card, Button, Loading, EmptyState, StatusBadge } from '@/components/ui';
import { deviceApi } from '@/services/api';

interface DeviceItem {
  id: number;
  name: string;
  device_type: string;
  ip_address: string | null;
  status: string;
  last_seen_at: string | null;
  location: string | null;
}

export default function DevicesPage() {
  const [devices, setDevices] = useState<DeviceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>('all');
  const navigate = useNavigate();

  useEffect(() => {
    const fetch = async () => {
      setLoading(true);
      try {
        const params = filter !== 'all' ? { device_type: filter } : {};
        const res = await deviceApi.list(params);
        setDevices(res.data);
      } catch {
        // silent
      } finally {
        setLoading(false);
      }
    };
    fetch();
    const interval = setInterval(fetch, 30000);
    return () => clearInterval(interval);
  }, [filter]);

  const typeIcon = (type: string) => {
    switch (type) {
      case 'mikrotik': return <Router className="w-5 h-5 text-orange-500" />;
      case 'esxi': return <Server className="w-5 h-5 text-purple-500" />;
      case 'vm_guest': return <Monitor className="w-5 h-5 text-cyan-500" />;
      default: return <Monitor className="w-5 h-5 text-gray-400" />;
    }
  };

  const detailRoute = (dev: DeviceItem) => {
    switch (dev.device_type) {
      case 'mikrotik': return `/devices/${dev.id}`;
      case 'esxi': return `/devices/${dev.id}`;
      case 'vm_guest': return `/devices/${dev.id}`;
      default: return `/devices/${dev.id}`;
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Devices</h2>
          <p className="text-sm text-gray-500 mt-1">{devices.length} device(s)</p>
        </div>
        <Button size="sm" onClick={() => navigate('/settings')}>
          <Plus className="w-4 h-4" /> Add Device
        </Button>
      </div>

      {/* Filter */}
      <div className="flex gap-1">
        {['all', 'mikrotik', 'esxi', 'vm_guest'].map((t) => (
          <button
            key={t}
            onClick={() => setFilter(t)}
            className={`px-3 py-1.5 text-xs rounded-full font-medium transition ${
              filter === t ? 'bg-primary-100 text-primary-700' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {t === 'all' ? 'All' : t === 'vm_guest' ? 'VM Guest' : t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {loading ? (
        <Loading text="Loading devices..." centered />
      ) : devices.length === 0 ? (
        <EmptyState
          icon={<Server className="w-12 h-12" />}
          title="No devices"
          description="Add your first device in Settings → Devices."
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {devices.map((dev) => (
            <Card
              key={dev.id}
              className="cursor-pointer hover:shadow-md transition-shadow"
              title={undefined}
              onClick={() => navigate(detailRoute(dev))}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-gray-100 rounded-lg">{typeIcon(dev.device_type)}</div>
                  <div>
                    <h3 className="text-sm font-semibold text-gray-800">{dev.name}</h3>
                    <p className="text-xs text-gray-500 font-mono">{dev.ip_address || 'No IP'}</p>
                    {dev.location && <p className="text-xs text-gray-400 mt-0.5">📍 {dev.location}</p>}
                  </div>
                </div>
                <StatusBadge status={dev.status} />
              </div>
              <div className="mt-3 pt-3 border-t border-gray-100 flex items-center justify-between text-xs text-gray-400">
                <span>{dev.device_type}</span>
                <span>{dev.last_seen_at ? new Date(dev.last_seen_at).toLocaleString() : 'Never seen'}</span>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

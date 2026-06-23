import { useEffect, useState } from 'react';
import {
  Plus, Trash2, Edit3, Server, Router, Monitor,
  Bell, Mail, Save, X, ShieldAlert,
} from 'lucide-react';
import { Card, Button, Badge, Loading, EmptyState, StatusBadge } from '@/components/ui';
import { useAuth } from '@/contexts/AuthContext';
import { deviceApi, alertRuleApi, agentApi } from '@/services/api';

interface DeviceItem {
  id: number;
  name: string;
  device_type: string;
  ip_address: string | null;
  status: string;
  is_active: boolean;
}

interface AlertRuleItem {
  id: number;
  name: string;
  device_id: number | null;
  device_type: string | null;
  metric_name: string;
  operator: string;
  threshold: number;
  severity: string;
  enabled: boolean;
}

type Tab = 'devices' | 'alert-rules' | 'notifications';

export default function SettingsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [tab, setTab] = useState<Tab>('devices');
  const [devices, setDevices] = useState<DeviceItem[]>([]);
  const [rules, setRules] = useState<AlertRuleItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showDeviceForm, setShowDeviceForm] = useState(false);
  const [showRuleForm, setShowRuleForm] = useState(false);
  const [editingDevice, setEditingDevice] = useState<DeviceItem | null>(null);

  // Device form state
  const [devForm, setDevForm] = useState({
    name: '', device_type: 'mikrotik', ip_address: '',
    snmp_community: 'public', snmp_port: 161,
    esxi_username: 'root', esxi_password: '', esxi_port: 443,
    location: '', description: '',
  });

  // Rule form state
  const [ruleForm, setRuleForm] = useState({
    name: '', metric_name: 'cpu_usage', operator: '>', threshold: 80,
    severity: 'warning', device_type: '', duration: 0, description: '',
  });

  const fetchData = async () => {
    setLoading(true);
    try {
      const [devRes, ruleRes] = await Promise.all([
        deviceApi.list(),
        alertRuleApi.list(),
      ]);
      setDevices(devRes.data);
      setRules(ruleRes.data);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const resetDevForm = () => {
    setDevForm({
      name: '', device_type: 'mikrotik', ip_address: '',
      snmp_community: 'public', snmp_port: 161,
      esxi_username: 'root', esxi_password: '', esxi_port: 443,
      location: '', description: '',
    });
    setEditingDevice(null);
    setShowDeviceForm(false);
  };

  const handleSaveDevice = async () => {
    try {
      if (editingDevice) {
        await deviceApi.update(editingDevice.id, devForm);
      } else {
        await deviceApi.create(devForm);
      }
      resetDevForm();
      fetchData();
    } catch {
      // silent
    }
  };

  const handleDeleteDevice = async (id: number) => {
    if (!confirm('Delete this device?')) return;
    try {
      await deviceApi.delete(id);
      fetchData();
    } catch {
      // silent
    }
  };

  const handleSaveRule = async () => {
    try {
      const data = { ...ruleForm };
      if (!data.device_type) delete (data as Record<string, unknown>).device_type;
      await alertRuleApi.create(data);
      setShowRuleForm(false);
      setRuleForm({
        name: '', metric_name: 'cpu_usage', operator: '>', threshold: 80,
        severity: 'warning', device_type: '', duration: 0, description: '',
      });
      fetchData();
    } catch {
      // silent
    }
  };

  const handleDeleteRule = async (id: number) => {
    if (!confirm('Delete this alert rule?')) return;
    try {
      await alertRuleApi.delete(id);
      fetchData();
    } catch {
      // silent
    }
  };

  const handleRegisterAgent = async () => {
    const name = prompt('VM name:');
    if (!name) return;
    try {
      const res = await agentApi.register({ name });
      alert(`Agent registered!\n\nToken: ${res.data.agent_token}\n\nSave this token — it won't be shown again.`);
      fetchData();
    } catch {
      // silent
    }
  };

  const tabs: { key: Tab; label: string; icon: React.ReactNode }[] = [
    { key: 'devices', label: 'Devices', icon: <Server className="w-4 h-4" /> },
    { key: 'alert-rules', label: 'Alert Rules', icon: <Bell className="w-4 h-4" /> },
    { key: 'notifications', label: 'Notifications', icon: <Mail className="w-4 h-4" /> },
  ];

  const inputClass = 'w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none';
  const labelClass = 'block text-xs font-medium text-gray-700 mb-1';

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-gray-900">Settings</h2>
        <p className="text-sm text-gray-500 mt-1">Manage devices, alert rules, and notifications</p>
      </div>

      {/* Viewer notice */}
      {!isAdmin && (
        <div className="flex items-center gap-3 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
          <ShieldAlert className="w-5 h-5 text-yellow-600 shrink-0" />
          <div>
            <p className="text-sm font-medium text-yellow-800">Viewer Access</p>
            <p className="text-xs text-yellow-600">You have read-only access. Contact an admin to make changes.</p>
          </div>
        </div>
      )}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-lg w-fit">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md transition ${
              tab === t.key ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-600 hover:text-gray-800'
            }`}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <Loading text="Loading..." centered />
      ) : (
        <>
          {/* ── DEVICES TAB ─────────────────────────────────────── */}
          {tab === 'devices' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <p className="text-sm text-gray-500">{devices.length} device(s) configured</p>
                {isAdmin && (
                  <div className="flex gap-2">
                    <Button size="sm" variant="secondary" onClick={handleRegisterAgent}>
                      <Plus className="w-4 h-4" /> Register VM Agent
                    </Button>
                    <Button size="sm" onClick={() => { setShowDeviceForm(true); resetDevForm(); }}>
                      <Plus className="w-4 h-4" /> Add Device
                    </Button>
                  </div>
                )}
              </div>

              {/* Device form */}
              {showDeviceForm && (
                <Card title={editingDevice ? 'Edit Device' : 'Add New Device'}>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    <div>
                      <label className={labelClass}>Name *</label>
                      <input className={inputClass} value={devForm.name} onChange={(e) => setDevForm({ ...devForm, name: e.target.value })} placeholder="My Router" />
                    </div>
                    <div>
                      <label className={labelClass}>Type *</label>
                      <select className={inputClass} value={devForm.device_type} onChange={(e) => setDevForm({ ...devForm, device_type: e.target.value })}>
                        <option value="mikrotik">Mikrotik</option>
                        <option value="esxi">ESXi Host</option>
                        <option value="vm_guest">VM Guest</option>
                      </select>
                    </div>
                    <div>
                      <label className={labelClass}>IP Address</label>
                      <input className={inputClass} value={devForm.ip_address} onChange={(e) => setDevForm({ ...devForm, ip_address: e.target.value })} placeholder="192.168.1.1" />
                    </div>

                    {devForm.device_type === 'mikrotik' && (
                      <>
                        <div>
                          <label className={labelClass}>SNMP Community</label>
                          <input className={inputClass} value={devForm.snmp_community} onChange={(e) => setDevForm({ ...devForm, snmp_community: e.target.value })} />
                        </div>
                        <div>
                          <label className={labelClass}>SNMP Port</label>
                          <input type="number" className={inputClass} value={devForm.snmp_port} onChange={(e) => setDevForm({ ...devForm, snmp_port: parseInt(e.target.value) || 161 })} />
                        </div>
                      </>
                    )}

                    {devForm.device_type === 'esxi' && (
                      <>
                        <div>
                          <label className={labelClass}>Username</label>
                          <input className={inputClass} value={devForm.esxi_username} onChange={(e) => setDevForm({ ...devForm, esxi_username: e.target.value })} />
                        </div>
                        <div>
                          <label className={labelClass}>Password</label>
                          <input type="password" className={inputClass} value={devForm.esxi_password} onChange={(e) => setDevForm({ ...devForm, esxi_password: e.target.value })} />
                        </div>
                        <div>
                          <label className={labelClass}>Port</label>
                          <input type="number" className={inputClass} value={devForm.esxi_port} onChange={(e) => setDevForm({ ...devForm, esxi_port: parseInt(e.target.value) || 443 })} />
                        </div>
                      </>
                    )}

                    <div>
                      <label className={labelClass}>Location</label>
                      <input className={inputClass} value={devForm.location} onChange={(e) => setDevForm({ ...devForm, location: e.target.value })} placeholder="Rack A1" />
                    </div>
                    <div className="sm:col-span-2">
                      <label className={labelClass}>Description</label>
                      <input className={inputClass} value={devForm.description} onChange={(e) => setDevForm({ ...devForm, description: e.target.value })} />
                    </div>
                  </div>
                  <div className="flex gap-2 mt-4">
                    <Button size="sm" onClick={handleSaveDevice}><Save className="w-4 h-4" /> Save</Button>
                    <Button size="sm" variant="ghost" onClick={resetDevForm}><X className="w-4 h-4" /> Cancel</Button>
                  </div>
                </Card>
              )}

              {/* Device list */}
              {devices.length === 0 ? (
                <EmptyState icon={<Server className="w-12 h-12" />} title="No devices" description="Add your first device to start monitoring." />
              ) : (
                <div className="space-y-2">
                  {devices.map((dev) => (
                    <Card key={dev.id} className="flex items-center justify-between" title={undefined}>
                      <div className="flex items-center gap-3">
                        <div className={`p-2 rounded-lg ${
                          dev.device_type === 'mikrotik' ? 'bg-orange-100' :
                          dev.device_type === 'esxi' ? 'bg-purple-100' : 'bg-cyan-100'
                        }`}>
                          {dev.device_type === 'mikrotik' && <Router className="w-4 h-4 text-orange-600" />}
                          {dev.device_type === 'esxi' && <Server className="w-4 h-4 text-purple-600" />}
                          {dev.device_type === 'vm_guest' && <Monitor className="w-4 h-4 text-cyan-600" />}
                        </div>
                        <div>
                          <p className="text-sm font-medium text-gray-800">{dev.name}</p>
                          <p className="text-xs text-gray-500">{dev.ip_address || 'No IP'} · {dev.device_type}</p>
                        </div>
                        <StatusBadge status={dev.status} />
                      </div>
                      <div className="flex items-center gap-1">
                        <Button size="sm" variant="ghost" onClick={() => { setEditingDevice(dev); setDevForm({ ...dev, snmp_community: 'public', snmp_port: 161, esxi_username: 'root', esxi_password: '', esxi_port: 443 }); setShowDeviceForm(true); }}>
                          <Edit3 className="w-3.5 h-3.5" />
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => handleDeleteDevice(dev.id)}>
                          <Trash2 className="w-3.5 h-3.5 text-red-500" />
                        </Button>
                      </div>
                    </Card>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── ALERT RULES TAB ────────────────────────────────── */}
          {tab === 'alert-rules' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <p className="text-sm text-gray-500">{rules.length} rule(s) configured</p>
                <Button size="sm" onClick={() => setShowRuleForm(true)}>
                  <Plus className="w-4 h-4" /> Add Rule
                </Button>
              </div>

              {showRuleForm && (
                <Card title="Add Alert Rule">
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    <div>
                      <label className={labelClass}>Rule Name *</label>
                      <input className={inputClass} value={ruleForm.name} onChange={(e) => setRuleForm({ ...ruleForm, name: e.target.value })} placeholder="High CPU" />
                    </div>
                    <div>
                      <label className={labelClass}>Metric *</label>
                      <select className={inputClass} value={ruleForm.metric_name} onChange={(e) => setRuleForm({ ...ruleForm, metric_name: e.target.value })}>
                        <option value="cpu_usage">CPU Usage (%)</option>
                        <option value="mem_usage_pct">Memory Usage (%)</option>
                        <option value="disk_usage_pct">Disk Usage (%)</option>
                        <option value="ds_usage_pct">Datastore Usage (%)</option>
                      </select>
                    </div>
                    <div className="flex gap-2">
                      <div className="w-20">
                        <label className={labelClass}>Op</label>
                        <select className={inputClass} value={ruleForm.operator} onChange={(e) => setRuleForm({ ...ruleForm, operator: e.target.value })}>
                          <option value=">">&gt;</option>
                          <option value=">=">&ge;</option>
                          <option value="<">&lt;</option>
                          <option value="<=">&le;</option>
                        </select>
                      </div>
                      <div className="flex-1">
                        <label className={labelClass}>Threshold</label>
                        <input type="number" className={inputClass} value={ruleForm.threshold} onChange={(e) => setRuleForm({ ...ruleForm, threshold: parseFloat(e.target.value) || 0 })} />
                      </div>
                    </div>
                    <div>
                      <label className={labelClass}>Severity</label>
                      <select className={inputClass} value={ruleForm.severity} onChange={(e) => setRuleForm({ ...ruleForm, severity: e.target.value })}>
                        <option value="info">Info</option>
                        <option value="warning">Warning</option>
                        <option value="critical">Critical</option>
                      </select>
                    </div>
                    <div>
                      <label className={labelClass}>Device Type (optional)</label>
                      <select className={inputClass} value={ruleForm.device_type} onChange={(e) => setRuleForm({ ...ruleForm, device_type: e.target.value })}>
                        <option value="">All Devices</option>
                        <option value="mikrotik">Mikrotik Only</option>
                        <option value="esxi">ESXi Only</option>
                        <option value="vm_guest">VM Guest Only</option>
                      </select>
                    </div>
                  </div>
                  <div className="flex gap-2 mt-4">
                    <Button size="sm" onClick={handleSaveRule}><Save className="w-4 h-4" /> Save</Button>
                    <Button size="sm" variant="ghost" onClick={() => setShowRuleForm(false)}><X className="w-4 h-4" /> Cancel</Button>
                  </div>
                </Card>
              )}

              {rules.length === 0 ? (
                <EmptyState icon={<Bell className="w-12 h-12" />} title="No alert rules" description="Create rules to get notified when metrics exceed thresholds." />
              ) : (
                <div className="space-y-2">
                  {rules.map((rule) => (
                    <Card key={rule.id} className="flex items-center justify-between" title={undefined}>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-gray-800">{rule.name}</span>
                          <Badge variant={rule.severity === 'critical' ? 'danger' : rule.severity === 'warning' ? 'warning' : 'info'}>
                            {rule.severity}
                          </Badge>
                          {!rule.enabled && <Badge variant="neutral">Disabled</Badge>}
                        </div>
                        <p className="text-xs text-gray-500 mt-0.5">
                          {rule.metric_name} {rule.operator} {rule.threshold}
                          {rule.device_type && ` · ${rule.device_type}`}
                        </p>
                      </div>
                      <Button size="sm" variant="ghost" onClick={() => handleDeleteRule(rule.id)}>
                        <Trash2 className="w-3.5 h-3.5 text-red-500" />
                      </Button>
                    </Card>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── NOTIFICATIONS TAB ──────────────────────────────── */}
          {tab === 'notifications' && (
            <Card title="Notification Channels" subtitle="Configure how alerts are delivered">
              <div className="space-y-6">
                <div className="p-4 bg-gray-50 rounded-lg">
                  <h4 className="text-sm font-medium text-gray-800 mb-2">📱 Telegram</h4>
                  <p className="text-xs text-gray-500 mb-3">
                    Set <code>TELEGRAM_BOT_TOKEN</code> and <code>TELEGRAM_CHAT_ID</code> in the server <code>.env</code> file.
                  </p>
                  <div className="text-xs text-gray-400">
                    1. Create a bot with @BotFather<br />
                    2. Get your chat ID from @userinfobot<br />
                    3. Add credentials to server .env and restart
                  </div>
                </div>

                <div className="p-4 bg-gray-50 rounded-lg">
                  <h4 className="text-sm font-medium text-gray-800 mb-2">📧 Email (SMTP)</h4>
                  <p className="text-xs text-gray-500 mb-3">
                    Set SMTP credentials in the server <code>.env</code> file.
                  </p>
                  <div className="text-xs text-gray-400">
                    Required: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD<br />
                    Optional: ALERT_FROM_EMAIL (default: netmon@local)
                  </div>
                </div>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

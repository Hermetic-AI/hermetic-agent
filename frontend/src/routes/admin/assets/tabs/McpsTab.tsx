import { useEffect, useState } from 'react';
import { Button } from '../../../components/common/Button';
import { Card, CardBody, CardFooter, CardHeader } from '../../../components/common/Card';
import { Empty } from '../../../components/common/Empty';
import { Modal, ConfirmModal } from '../../../components/common/Modal';
import { Skeleton } from '../../../components/common/Skeleton';
import { Input } from '../../../components/common/Input';
import { mcpConfigsApi } from '../../../services/mcp_configs';
import type { McpConfigAsset, McpType } from '../../../types/assets';
import '../index.css';
import './McpsTab.css';

type McpForm = Omit<McpConfigAsset, 'id' | 'created_at' | 'updated_at' | 'deleted_at' | 'is_deleted' | 'source'>;

const NEW_MCP: McpForm = {
  code: '',
  name: '',
  mcp_type: 'http',
  url: '',
  command: '',
  args: [],
  env: {},
  cwd: '',
  headers: {},
  allowed_tools: [],
  disabled: false,
  config: null,
  status: 'draft',
};

function asArray(value: string): string[] {
  return value.split('\n').map((s) => s.trim()).filter(Boolean);
}

function fromList(list: string[] | null | undefined): string {
  return (list ?? []).join('\n');
}

export function McpsTab() {
  const [items, setItems] = useState<McpConfigAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<McpForm | null>(null);
  const [editingCode, setEditingCode] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<McpConfigAsset | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { loadList(); }, []);

  async function loadList() {
    setLoading(true);
    try {
      const r = await mcpConfigsApi.list();
      setItems(r.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  function openNew() {
    setEditing({ ...NEW_MCP });
    setEditingCode(null);
    setError(null);
  }

  function openEdit(item: McpConfigAsset) {
    setEditing({
      code: item.code,
      name: item.name,
      mcp_type: item.mcp_type,
      url: item.url ?? '',
      command: item.command ?? '',
      args: item.args ?? [],
      env: item.env ?? {},
      cwd: item.cwd ?? '',
      headers: item.headers ?? {},
      allowed_tools: item.allowed_tools ?? [],
      disabled: item.disabled,
      config: item.config,
      status: item.status,
    });
    setEditingCode(item.code);
    setError(null);
  }

  async function handleSave() {
    if (!editing) return;
    if (!editing.code.trim() || !editing.name.trim()) {
      setError('Code and Name are required');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload = buildPayload(editing);
      if (editingCode) {
        await mcpConfigsApi.update(editingCode, payload);
      } else {
        await mcpConfigsApi.create(payload);
      }
      setEditing(null);
      setEditingCode(null);
      await loadList();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!deleting) return;
    setSaving(true);
    try {
      await mcpConfigsApi.delete(deleting.code);
      setDeleting(null);
      await loadList();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="assets-tab">
      <div className="assets-tab-header">
        <h2>MCP Servers ({items.length})</h2>
        <Button variant="primary" onClick={openNew}>+ New MCP Server</Button>
      </div>
      {error && <p className="asset-form-error">{error}</p>}
      {loading ? <Skeleton variant="rectangular" height={120} /> :
       items.length === 0 ? (
         <Empty
           title="No MCP servers yet"
           description="Connect external MCP servers (http/sse/stdio) to expose their tools."
           action={{ label: 'Create first', onClick: openNew }}
         />
       ) : (
         <div className="assets-tab-grid">
           {items.map((item) => (
             <Card key={item.code}>
               <CardHeader>
                 <strong>{item.name}</strong>
                 <span className={`asset-status-badge asset-status-${item.status}`}>{item.status}</span>
               </CardHeader>
               <CardBody>
                 <div className="asset-card-meta">
                   <div className="asset-card-meta-item">
                     <span className="asset-card-meta-label">Code:</span>
                     <span>{item.code}</span>
                   </div>
                   <div className="asset-card-meta-item">
                     <span className="asset-card-meta-label">Type:</span>
                     <span>{item.mcp_type}</span>
                   </div>
                   {item.url && (
                     <div className="asset-card-meta-item">
                       <span className="asset-card-meta-label">URL:</span>
                       <span>{item.url}</span>
                     </div>
                   )}
                   {item.command && (
                     <div className="asset-card-meta-item">
                       <span className="asset-card-meta-label">Command:</span>
                       <span>{item.command}</span>
                     </div>
                   )}
                 </div>
               </CardBody>
               <CardFooter>
                 <div className="asset-card-row">
                   <Button size="small" onClick={() => openEdit(item)}>Edit</Button>
                   <Button size="small" variant="danger" onClick={() => setDeleting(item)}>Delete</Button>
                 </div>
               </CardFooter>
             </Card>
           ))}
         </div>
       )}
      {editing && (
        <McpEditDialog
          item={editing}
          isNew={editingCode === null}
          saving={saving}
          error={error}
          onChange={setEditing}
          onSave={handleSave}
          onClose={() => { setEditing(null); setEditingCode(null); setError(null); }}
        />
      )}
      {deleting && (
        <ConfirmModal
          open
          onClose={() => setDeleting(null)}
          onConfirm={handleDelete}
          title="Delete MCP server"
          message={`Delete MCP server ${deleting.code}? This cannot be undone.`}
          confirmText="Delete"
          variant="danger"
        />
      )}
    </div>
  );
}

function buildPayload(form: McpForm) {
  const base = {
    code: form.code,
    name: form.name,
    mcp_type: form.mcp_type,
    status: form.status,
    disabled: form.disabled,
    allowed_tools: form.allowed_tools && form.allowed_tools.length > 0 ? form.allowed_tools : null,
    config: form.config,
  };
  if (form.mcp_type === 'http' || form.mcp_type === 'sse') {
    return {
      ...base,
      url: form.url || null,
      headers: form.headers && Object.keys(form.headers).length > 0 ? form.headers : null,
      command: null,
      args: null,
      env: null,
      cwd: null,
    };
  }
  return {
    ...base,
    command: form.command || null,
    args: form.args && form.args.length > 0 ? form.args : null,
    env: form.env && Object.keys(form.env).length > 0 ? form.env : null,
    cwd: form.cwd || null,
    url: null,
    headers: null,
  };
}

interface McpEditDialogProps {
  item: McpForm;
  isNew: boolean;
  saving: boolean;
  error: string | null;
  onChange: (next: McpForm) => void;
  onSave: () => void;
  onClose: () => void;
}

function McpEditDialog({ item, isNew, saving, error, onChange, onSave, onClose }: McpEditDialogProps) {
  return (
    <Modal
      open
      onClose={onClose}
      title={isNew ? 'New MCP Server' : `Edit MCP: ${item.code}`}
      size="large"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button variant="primary" onClick={onSave} loading={saving}>Save</Button>
        </>
      }
    >
      <div className="asset-form">
        <div className="asset-form-row">
          <Input
            label="Code"
            value={item.code}
            disabled={!isNew}
            onChange={(e) => onChange({ ...item, code: e.target.value })}
            placeholder="my-mcp"
          />
          <Input
            label="Name"
            value={item.name}
            onChange={(e) => onChange({ ...item, name: e.target.value })}
            placeholder="My MCP"
          />
        </div>
        <label>
          <span style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>Type</span>
          <select
            value={item.mcp_type}
            onChange={(e) => onChange({ ...item, mcp_type: e.target.value as McpType })}
            style={{ width: '100%', padding: '8px 10px', border: '1px solid #d1d1d6', borderRadius: 6, fontSize: 14, background: 'white' }}
          >
            <option value="http">http</option>
            <option value="sse">sse</option>
            <option value="stdio">stdio</option>
          </select>
        </label>
        {(item.mcp_type === 'http' || item.mcp_type === 'sse') ? (
          <>
            <Input
              label="URL"
              value={item.url ?? ''}
              onChange={(e) => onChange({ ...item, url: e.target.value })}
              placeholder="https://example.com/mcp"
            />
            <KeyValueEditor
              label="Headers"
              value={item.headers ?? {}}
              onChange={(next) => onChange({ ...item, headers: next })}
            />
          </>
        ) : (
          <>
            <Input
              label="Command"
              value={item.command ?? ''}
              onChange={(e) => onChange({ ...item, command: e.target.value })}
              placeholder="npx"
            />
            <label>
              <span style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>Args (one per line)</span>
              <textarea
                className="asset-form-textarea"
                style={{ minHeight: 100 }}
                value={fromList(item.args)}
                onChange={(e) => onChange({ ...item, args: asArray(e.target.value) })}
                placeholder={'-y\n@modelcontextprotocol/server-filesystem\n/path'}
              />
            </label>
            <KeyValueEditor
              label="Env"
              value={item.env ?? {}}
              onChange={(next) => onChange({ ...item, env: next })}
            />
            <Input
              label="CWD"
              value={item.cwd ?? ''}
              onChange={(e) => onChange({ ...item, cwd: e.target.value })}
              placeholder="/path/to/cwd"
            />
          </>
        )}
        <label>
          <span style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>Allowed tools (one per line, optional)</span>
          <textarea
            className="asset-form-textarea"
            style={{ minHeight: 80 }}
            value={fromList(item.allowed_tools)}
            onChange={(e) => onChange({ ...item, allowed_tools: asArray(e.target.value) })}
            placeholder="read_file\nwrite_file"
          />
        </label>
        <label>
          <span style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>Status</span>
          <select
            value={item.status}
            onChange={(e) => onChange({ ...item, status: e.target.value as McpConfigAsset['status'] })}
            style={{ width: '100%', padding: '8px 10px', border: '1px solid #d1d1d6', borderRadius: 6, fontSize: 14, background: 'white' }}
          >
            <option value="enabled">enabled</option>
            <option value="disabled">disabled</option>
            <option value="draft">draft</option>
          </select>
        </label>
        {error && <p className="asset-form-error">{error}</p>}
      </div>
    </Modal>
  );
}

interface KeyValueEditorProps {
  label: string;
  value: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
}

function KeyValueEditor({ label, value, onChange }: KeyValueEditorProps) {
  const entries = Object.entries(value);
  return (
    <div>
      <span style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>{label}</span>
      <div className="asset-kv-list">
        {entries.length === 0 && <p className="asset-form-help">No entries. Click "Add" to create one.</p>}
        {entries.map(([k, v], idx) => (
          <div key={`${k}-${idx}`} className="asset-kv-row">
            <input
              value={k}
              onChange={(e) => {
                const next: Record<string, string> = {};
                entries.forEach(([ek, ev], i) => {
                  next[i === idx ? e.target.value : ek] = ev;
                });
                onChange(next);
              }}
              placeholder="key"
            />
            <input
              value={v}
              onChange={(e) => onChange({ ...value, [k]: e.target.value })}
              placeholder="value"
            />
            <button
              type="button"
              className="asset-kv-remove"
              onClick={() => {
                const next = { ...value };
                delete next[k];
                onChange(next);
              }}
            >×</button>
          </div>
        ))}
        <button
          type="button"
          className="asset-kv-add"
          onClick={() => onChange({ ...value, '': '' })}
        >+ Add entry</button>
      </div>
    </div>
  );
}

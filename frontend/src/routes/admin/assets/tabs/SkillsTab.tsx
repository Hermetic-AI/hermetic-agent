import { useEffect, useState } from 'react';
import { Button } from '../../../components/common/Button';
import { Card, CardBody, CardFooter, CardHeader } from '../../../components/common/Card';
import { Empty } from '../../../components/common/Empty';
import { Modal, ConfirmModal } from '../../../components/common/Modal';
import { Skeleton } from '../../../components/common/Skeleton';
import { Input } from '../../../components/common/Input';
import { skillsApi } from '../../../services/skills';
import { skillFilesApi, type SkillFileEntry } from '../../../services/skill_files';
import type { SkillAsset } from '../../../types/assets';
import '../index.css';
import './SkillsTab.css';

type SkillForm = Omit<SkillAsset, 'id' | 'created_at' | 'updated_at' | 'owner_user_id' | 'visibility' | 'version' | 'file_count' | 'file_fingerprint'>;

const NEW_SKILL: SkillForm = {
  code: '',
  name: '',
  description: '',
  status: 'draft',
  triggers: [],
  prompt_template: '',
  mcp_tools: [],
};

function asArray(value: string): string[] {
  return value.split('\n').map((s) => s.trim()).filter(Boolean);
}

function fromList(list: string[] | null | undefined): string {
  return (list ?? []).join('\n');
}

export function SkillsTab() {
  const [items, setItems] = useState<SkillAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<SkillForm | null>(null);
  const [editingCode, setEditingCode] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<SkillAsset | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { loadList(); }, []);

  async function loadList() {
    setLoading(true);
    try {
      const r = await skillsApi.list();
      setItems(r.skills);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  function openNew() {
    setEditing({ ...NEW_SKILL });
    setEditingCode(null);
    setError(null);
  }

  function openEdit(item: SkillAsset) {
    setEditing({
      code: item.code,
      name: item.name,
      description: item.description ?? '',
      status: item.status,
      triggers: item.triggers ?? [],
      prompt_template: item.prompt_template ?? '',
      mcp_tools: (item.mcp_tools as string[] | undefined) ?? [],
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
      const payload = {
        code: editing.code,
        name: editing.name,
        description: editing.description,
        status: editing.status,
        triggers: editing.triggers && editing.triggers.length > 0 ? editing.triggers : null,
        prompt_template: editing.prompt_template || null,
        mcp_tools: editing.mcp_tools && (editing.mcp_tools as string[]).length > 0 ? editing.mcp_tools : null,
      };
      if (editingCode) {
        await skillsApi.update(editingCode, payload);
      } else {
        await skillsApi.create(payload);
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
      await skillsApi.delete(deleting.code);
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
        <h2>Skills ({items.length})</h2>
        <Button variant="primary" onClick={openNew}>+ New Skill</Button>
      </div>
      {error && <p className="asset-form-error">{error}</p>}
      {loading ? <Skeleton variant="rectangular" height={120} /> :
       items.length === 0 ? (
         <Empty
           title="No skills yet"
           description="Create skills to bundle prompt templates, triggers, and file attachments."
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
                   {item.description && (
                     <div className="asset-card-meta-item">
                       <span className="asset-card-meta-label">Desc:</span>
                       <span>{item.description}</span>
                     </div>
                   )}
                   {item.triggers && item.triggers.length > 0 && (
                     <div className="asset-card-meta-item">
                       <span className="asset-card-meta-label">Triggers:</span>
                       <span>{item.triggers.join(', ')}</span>
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
        <SkillEditDialog
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
          title="Delete skill"
          message={`Delete skill ${deleting.code}? This will also remove all attached files.`}
          confirmText="Delete"
          variant="danger"
        />
      )}
    </div>
  );
}

interface SkillEditDialogProps {
  item: SkillForm;
  isNew: boolean;
  saving: boolean;
  error: string | null;
  onChange: (next: SkillForm) => void;
  onSave: () => void;
  onClose: () => void;
}

type SubTab = 'metadata' | 'files';

function SkillEditDialog({ item, isNew, saving, error, onChange, onSave, onClose }: SkillEditDialogProps) {
  const [subTab, setSubTab] = useState<SubTab>('metadata');
  const isExisting = !isNew;
  return (
    <Modal
      open
      onClose={onClose}
      title={isNew ? 'New Skill' : `Edit Skill: ${item.code}`}
      size="large"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>Cancel</Button>
          {subTab === 'metadata' && (
            <Button variant="primary" onClick={onSave} loading={saving}>Save</Button>
          )}
        </>
      }
    >
      <div className="assets-subtabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={subTab === 'metadata'}
          className={`assets-subtab-button ${subTab === 'metadata' ? 'is-active' : ''}`}
          onClick={() => setSubTab('metadata')}
        >Metadata</button>
        <button
          type="button"
          role="tab"
          aria-selected={subTab === 'files'}
          className={`assets-subtab-button ${subTab === 'files' ? 'is-active' : ''}`}
          onClick={() => setSubTab('files')}
          disabled={isExisting === false}
          title={isExisting ? '' : 'Save the skill first to manage files'}
        >Files</button>
      </div>
      {subTab === 'metadata' ? (
        <div className="asset-form">
          <div className="asset-form-row">
            <Input
              label="Code"
              value={item.code}
              disabled={!isNew}
              onChange={(e) => onChange({ ...item, code: e.target.value })}
              placeholder="my-skill"
            />
            <Input
              label="Name"
              value={item.name}
              onChange={(e) => onChange({ ...item, name: e.target.value })}
              placeholder="My Skill"
            />
          </div>
          <Input
            label="Description"
            value={item.description ?? ''}
            onChange={(e) => onChange({ ...item, description: e.target.value })}
            placeholder="Short description"
          />
          <label>
            <span style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>Triggers (one per line)</span>
            <textarea
              className="asset-form-textarea"
              style={{ minHeight: 80 }}
              value={fromList(item.triggers)}
              onChange={(e) => onChange({ ...item, triggers: asArray(e.target.value) })}
              placeholder="summarize\n总结"
            />
          </label>
          <label>
            <span style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>Prompt template</span>
            <textarea
              className="asset-form-textarea"
              value={item.prompt_template ?? ''}
              onChange={(e) => onChange({ ...item, prompt_template: e.target.value })}
              placeholder="You are a helpful assistant..."
            />
          </label>
          <label>
            <span style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>MCP tools (one per line, optional)</span>
            <textarea
              className="asset-form-textarea"
              style={{ minHeight: 80 }}
              value={fromList(item.mcp_tools as string[] | null | undefined)}
              onChange={(e) => onChange({ ...item, mcp_tools: asArray(e.target.value) })}
              placeholder="read_file"
            />
          </label>
          <label>
            <span style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>Status</span>
            <select
              value={item.status}
              onChange={(e) => onChange({ ...item, status: e.target.value as SkillAsset['status'] })}
              style={{ width: '100%', padding: '8px 10px', border: '1px solid #d1d1d6', borderRadius: 6, fontSize: 14, background: 'white' }}
            >
              <option value="enabled">enabled</option>
              <option value="disabled">disabled</option>
              <option value="draft">draft</option>
            </select>
          </label>
          {error && <p className="asset-form-error">{error}</p>}
        </div>
      ) : (
        isExisting ? <FilesSubTab code={item.code} /> :
          <div className="assets-tab-placeholder">Save the skill first, then come back to manage files.</div>
      )}
    </Modal>
  );
}

function FilesSubTab({ code }: { code: string }) {
  const [files, setFiles] = useState<SkillFileEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadPath, setUploadPath] = useState('');
  const [fileInput, setFileInput] = useState<HTMLInputElement | null>(null);
  const [uploading, setUploading] = useState(false);

  useEffect(() => { loadFiles(); }, [code]);

  async function loadFiles() {
    setLoading(true);
    setError(null);
    try {
      const r = await skillFilesApi.list(code);
      setFiles(r.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function handleUpload() {
    if (!fileInput || !fileInput.files || fileInput.files.length === 0) return;
    const path = uploadPath.trim() || fileInput.files[0].name;
    setUploading(true);
    setError(null);
    try {
      const file = fileInput.files[0];
      const buf = await file.arrayBuffer();
      await skillFilesApi.upload(code, path, buf);
      setUploadPath('');
      if (fileInput) fileInput.value = '';
      await loadFiles();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  }

  async function handleDownload(entry: SkillFileEntry) {
    try {
      const blob = await skillFilesApi.download(code, entry.path);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = entry.path.split('/').pop() ?? entry.path;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleDelete(entry: SkillFileEntry) {
    if (!window.confirm(`Delete file ${entry.path}?`)) return;
    try {
      await skillFilesApi.delete(code, entry.path);
      await loadFiles();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div>
      {error && <p className="asset-form-error">{error}</p>}
      {loading ? <Skeleton variant="rectangular" height={80} /> :
        files.length === 0 ? <p className="asset-form-help">No files attached. Upload one below.</p> :
          <div className="assets-files-list">
            {files.map((entry) => (
              <div key={entry.path} className="assets-files-row">
                <span>{entry.path} <span style={{ color: '#6c6c70' }}>({entry.size} B)</span></span>
                <div className="assets-files-row-actions">
                  <Button size="small" variant="secondary" onClick={() => handleDownload(entry)}>Download</Button>
                  <Button size="small" variant="danger" onClick={() => handleDelete(entry)}>Delete</Button>
                </div>
              </div>
            ))}
          </div>
      }
      <div className="assets-files-upload">
        <input
          type="text"
          value={uploadPath}
          onChange={(e) => setUploadPath(e.target.value)}
          placeholder="path/in/skill (defaults to filename)"
        />
        <input
          type="file"
          ref={(el) => setFileInput(el)}
        />
        <Button variant="primary" onClick={handleUpload} loading={uploading} disabled={!fileInput?.files?.length}>
          Upload
        </Button>
      </div>
    </div>
  );
}

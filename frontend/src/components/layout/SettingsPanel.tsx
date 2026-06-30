import { Modal } from '../common';
import { useHealth } from '../../hooks';
import './SettingsPanel.css';

interface SettingsPanelProps {
  open: boolean;
  onClose: () => void;
}

export function SettingsPanel({ open, onClose }: SettingsPanelProps) {
  const { state, detail, ready } = useHealth();
  return (
    <Modal open={open} onClose={onClose} title="Settings" size="medium">
      <div className="settings-panel">
        <div className="settings-row">
          <span className="settings-label">Backend</span>
          <span className={`settings-badge settings-badge-${state}`}>{state}</span>
        </div>
        {detail && (
          <div className="settings-row">
            <span className="settings-label">Detail</span>
            <span className="settings-value">{detail}</span>
          </div>
        )}
        <div className="settings-row">
          <span className="settings-label">Storage</span>
          <span className="settings-value">{ready?.storage ? 'Ready' : 'Not ready'}</span>
        </div>
        <div className="settings-row">
          <span className="settings-label">Bridge</span>
          <span className="settings-value">{ready?.bridge ? 'Ready' : 'Not ready'}</span>
        </div>
        <div className="settings-row">
          <span className="settings-label">Agents</span>
          <span className="settings-value">{ready?.agents?.length ?? 0}</span>
        </div>
      </div>
    </Modal>
  );
}
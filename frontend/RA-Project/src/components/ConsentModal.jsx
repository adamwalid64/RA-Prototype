import React, { useState } from 'react';
import './ConsentModal.css';

const ConsentModal = ({ isOpen, onClose, onSave, initialSettings = null }) => {
  const [settings, setSettings] = useState(initialSettings || {
    allow_anonymization: false,
    share_for_research: false,
    consent_given: false,
  });

  if (!isOpen) return null;

  const handleSave = () => {
    onSave(settings);
    onClose();
  };

  const handleChange = (field) => {
    setSettings(prev => ({
      ...prev,
      [field]: !prev[field]
    }));
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Consent & Privacy Settings</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>

        <div className="modal-body">
          <p className="modal-intro">
            Please review and configure your privacy preferences for data processing.
          </p>

          <div className="setting-group">
            <label className="setting-label">
              <input
                type="checkbox"
                checked={settings.allow_anonymization}
                onChange={() => handleChange('allow_anonymization')}
              />
              <div className="setting-content">
                <strong>Allow Anonymization</strong>
                <span>Enable automatic anonymization of personal identifiers in your data</span>
              </div>
            </label>
          </div>

          <div className="setting-group">
            <label className="setting-label">
              <input
                type="checkbox"
                checked={settings.share_for_research}
                onChange={() => handleChange('share_for_research')}
              />
              <div className="setting-content">
                <strong>Share for Research</strong>
                <span>Allow anonymized data to be used for research purposes</span>
              </div>
            </label>
          </div>

          <div className="setting-group required">
            <label className="setting-label">
              <input
                type="checkbox"
                checked={settings.consent_given}
                onChange={() => handleChange('consent_given')}
                required
              />
              <div className="setting-content">
                <strong>I Consent to Data Processing</strong>
                <span>Required to process your data and generate reflections</span>
              </div>
            </label>
          </div>
        </div>

        <div className="modal-footer">
          <button className="modal-button secondary" onClick={onClose}>
            Cancel
          </button>
          <button 
            className="modal-button primary" 
            onClick={handleSave}
            disabled={!settings.consent_given}
          >
            Save Settings
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConsentModal;

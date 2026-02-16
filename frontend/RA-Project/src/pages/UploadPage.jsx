import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { uploadFile } from '../apiClient';
import PreviewPanel from '../components/PreviewPanel';
import './UploadPage.css';

const UploadPage = () => {
  const [file, setFile] = useState(null);
  const [fileContent, setFileContent] = useState(null);
  const [fileName, setFileName] = useState('');
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [validationErrors, setValidationErrors] = useState([]);
  const fileInputRef = useRef(null);
  const navigate = useNavigate();

  const validateFile = (file) => {
    const errors = [];
    const maxSize = 50 * 1024 * 1024; // 50MB

    if (!file) {
      errors.push('Please select a file');
      return errors;
    }

    // Check file size
    if (file.size > maxSize) {
      errors.push(`File size exceeds ${maxSize / (1024 * 1024)}MB limit`);
    }

    // Check file type (allow JSON, CSV, TXT)
    const allowedTypes = [
      'application/json',
      'text/csv',
      'text/plain',
      'text/json'
    ];
    
    const validExtension = ['.json', '.csv', '.txt'].some(ext => 
      file.name.toLowerCase().endsWith(ext)
    );

    if (!allowedTypes.includes(file.type) && !validExtension) {
      errors.push('File must be JSON, CSV, or TXT format');
    }

    return errors;
  };

  const handleFileChange = async (e) => {
    const selectedFile = e.target.files[0];
    if (!selectedFile) return;

    setError(null);
    setValidationErrors([]);

    const errors = validateFile(selectedFile);
    if (errors.length > 0) {
      setValidationErrors(errors);
      return;
    }

    setFile(selectedFile);
    setFileName(selectedFile.name);

    // Preview file content - limit to first 50KB to prevent freezing
    try {
      const maxPreviewSize = 50 * 1024; // 50KB
      const blob = selectedFile.slice(0, maxPreviewSize);
      const reader = new FileReader();
      reader.onload = (event) => {
        let content = event.target.result;
        // If file is larger than preview size, indicate truncation
        if (selectedFile.size > maxPreviewSize) {
          content += '\n\n... (preview truncated, file continues)';
        }
        setFileContent(content);
      };
      reader.readAsText(blob);
    } catch (err) {
      console.error('Error reading file:', err);
    }
  };

  const handleUpload = async () => {
    if (!file) {
      setError('Please select a file first');
      return;
    }

    const errors = validateFile(file);
    if (errors.length > 0) {
      setValidationErrors(errors);
      return;
    }

    setUploading(true);
    setError(null);

    try {
      const response = await uploadFile(file);
      // Navigate to dashboard with dataset_id
      navigate(`/dashboard/${response.dataset_id}`);
    } catch (err) {
      setError(
        err.response?.data?.message || 
        err.message || 
        'Failed to upload file. Please try again.'
      );
      console.error('Upload error:', err);
    } finally {
      setUploading(false);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) {
      const dataTransfer = new DataTransfer();
      dataTransfer.items.add(droppedFile);
      fileInputRef.current.files = dataTransfer.files;
      handleFileChange({ target: { files: dataTransfer.files } });
    }
  };

  return (
    <div className="upload-page">
      <div className="upload-container">
        <div className="upload-header">
          <h1>Upload Prompt History</h1>
          <p>Upload your conversation history or prompt dataset to begin reflection analysis</p>
        </div>

        {/* ChatGPT Export Instructions */}
        <div className="export-tip">
          <div className="tip-header">
            <span className="tip-icon">💡</span>
            <h3>How to Export Your ChatGPT Data</h3>
          </div>
          <div className="tip-content">
            <p className="tip-intro">To analyze your ChatGPT conversations, you'll need to export your data first:</p>
            <ol className="tip-steps">
              <li>
                <strong>Sign in</strong> to <a href="https://chat.openai.com" target="_blank" rel="noopener noreferrer">chat.openai.com</a>
              </li>
              <li>
                <strong>Click your profile icon</strong> (bottom left on desktop, top right on mobile)
              </li>
              <li>
                <strong>Select "Settings"</strong>
              </li>
              <li>
                <strong>Click "Data Controls"</strong>
              </li>
              <li>
                <strong>Click "Export"</strong> and confirm your request
              </li>
              <li>
                <strong>Check your email</strong> for a download link (arrives within minutes to hours)
              </li>
              <li>
                <strong>Download the ZIP file</strong> before the link expires (24 hours)
              </li>
              <li>
                <strong>Extract the ZIP file</strong> and locate <code>conversations.json</code>
              </li>
              <li>
                <strong>Upload the conversations.json file</strong> here to begin analysis
              </li>
            </ol>
            <p className="tip-note">
              <strong>Note:</strong> The export includes all your personal workspace conversations. 
              Processing usually takes less than 24 hours, and download links expire after 24 hours.
            </p>
          </div>
        </div>

        <div 
          className="upload-area"
          onDragOver={handleDragOver}
          onDrop={handleDrop}
        >
          <input
            ref={fileInputRef}
            type="file"
            id="file-input"
            accept=".json,.csv,.txt"
            onChange={handleFileChange}
            className="file-input"
          />
          
          <label htmlFor="file-input" className="upload-label">
            <div className="upload-icon">📁</div>
            <div className="upload-text">
              <strong>Click to upload</strong> or drag and drop
            </div>
            <div className="upload-hint">
              JSON, CSV, or TXT files (max 50MB)
            </div>
          </label>

          {fileName && (
            <div className="selected-file">
              <span className="file-icon">✓</span>
              <span className="file-name">{fileName}</span>
              <button 
                className="clear-file"
                onClick={() => {
                  setFile(null);
                  setFileName('');
                  setFileContent(null);
                  setValidationErrors([]);
                  if (fileInputRef.current) {
                    fileInputRef.current.value = '';
                  }
                }}
              >
                ×
              </button>
            </div>
          )}
        </div>

        {validationErrors.length > 0 && (
          <div className="validation-errors">
            {validationErrors.map((err, idx) => (
              <div key={idx} className="error-message">⚠️ {err}</div>
            ))}
          </div>
        )}

        {error && (
          <div className="error-message">❌ {error}</div>
        )}

        <button
          className="upload-button"
          onClick={handleUpload}
          disabled={!file || uploading}
        >
          {uploading ? 'Uploading...' : 'Upload & Analyze'}
        </button>

        {fileContent && (
          <PreviewPanel 
            fileContent={fileContent} 
            fileName={fileName}
          />
        )}
      </div>
    </div>
  );
};

export default UploadPage;

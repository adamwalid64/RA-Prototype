import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getResults, exportResults } from '../apiClient';
import './ExportPage.css';

const ExportPage = () => {
  const { datasetId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!datasetId) {
      setError('No dataset ID provided');
      setLoading(false);
      return;
    }

    const fetchData = async () => {
      try {
        const results = await getResults(datasetId);
        setData(results);
      } catch (err) {
        setError(
          err.response?.data?.message || 
          err.message || 
          'Failed to load results'
        );
        console.error('Error fetching results:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [datasetId]);

  const handleExport = async (fileType) => {
    if (!datasetId) return;

    setExporting(true);
    setError(null);

    try {
      const blob = await exportResults(datasetId, fileType);
      
      // Create download link
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `reflection-results-${datasetId}.${fileType}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(
        err.response?.data?.message || 
        err.message || 
        `Failed to export ${fileType.toUpperCase()} file`
      );
      console.error('Export error:', err);
    } finally {
      setExporting(false);
    }
  };

  if (loading) {
    return (
      <div className="export-page">
        <div className="loading-container">
          <div className="spinner"></div>
          <p>Loading export options...</p>
        </div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="export-page">
        <div className="error-container">
          <h2>Error Loading Results</h2>
          <p>{error}</p>
          <button onClick={() => navigate('/')} className="back-button">
            Back to Upload
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="export-page">
      <div className="export-container">
        <div className="export-header">
          <h1>Export Results</h1>
          <p>Download your analysis and reflection data</p>
          {datasetId && (
            <div className="dataset-info">
              <span>Dataset ID: {datasetId}</span>
            </div>
          )}
        </div>

        {error && (
          <div className="export-error">
            ⚠️ {error}
          </div>
        )}

        <div className="export-options">
          <div className="export-option">
            <div className="option-icon">📄</div>
            <div className="option-content">
              <h2>CSV Format</h2>
              <p>Spreadsheet-friendly export with one row per conversation and all available model metrics and scores.</p>
              <button
                onClick={() => handleExport('csv')}
                disabled={exporting}
                className="export-button primary"
              >
                {exporting ? 'Exporting...' : 'Download CSV'}
              </button>
            </div>
          </div>

          <div className="export-option">
            <div className="option-icon">📋</div>
            <div className="option-content">
              <h2>PDF Format</h2>
              <p>Human-readable report with organized conversation-level summaries, sample messages, and full scoring details.</p>
              <button
                onClick={() => handleExport('pdf')}
                disabled={exporting}
                className="export-button secondary"
              >
                {exporting ? 'Exporting...' : 'Download PDF'}
              </button>
            </div>
          </div>
        </div>

        {data && (
          <div className="export-preview">
            <h2>Export Preview</h2>
            <div className="preview-summary">
              <div className="preview-item">
                <strong>Total Prompts:</strong> {data.analysis.total_prompts}
              </div>
              <div className="preview-item">
                <strong>Categories:</strong> {data.analysis.categories.length}
              </div>
              <div className="preview-item">
                <strong>Reflection Items:</strong> {data.reflection.strengths?.length || 0} strengths, {data.reflection.risks?.length || 0} risks, {data.reflection.suggestions?.length || 0} suggestions
              </div>
            </div>
          </div>
        )}

        <div className="export-actions">
          <button 
            onClick={() => navigate(`/dashboard/${datasetId}`)}
            className="action-button secondary"
          >
            Back to Dashboard
          </button>
          <button 
            onClick={() => navigate(`/reflection/${datasetId}`)}
            className="action-button secondary"
          >
            View Reflection
          </button>
        </div>
      </div>
    </div>
  );
};

export default ExportPage;

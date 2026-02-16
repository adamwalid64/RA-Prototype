import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getResults } from '../apiClient';
import './ReflectionPage.css';

const ReflectionPage = () => {
  const { datasetId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
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
          'Failed to load reflection'
        );
        console.error('Error fetching reflection:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [datasetId]);

  if (loading) {
    return (
      <div className="reflection-page">
        <div className="loading-container">
          <div className="spinner"></div>
          <p>Loading reflection...</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="reflection-page">
        <div className="error-container">
          <h2>Error Loading Reflection</h2>
          <p>{error || 'No reflection data available'}</p>
          <button onClick={() => navigate(`/dashboard/${datasetId}`)} className="back-button">
            Back to Dashboard
          </button>
        </div>
      </div>
    );
  }

  const { reflection, analysis } = data;
  const gradingDetails = analysis?.grading_results?.details || [];

  return (
    <div className="reflection-page">
      <div className="reflection-container">
        <div className="reflection-header">
          <h1>Self-Reflection Analysis</h1>
          <p>Personalized insights based on your prompt history</p>
        </div>

        {reflection.overall_summary && (
          <div className="summary-section">
            <h2>Overall Summary</h2>
            <div className="summary-content">
              <p>{reflection.overall_summary}</p>
            </div>
          </div>
        )}

        {reflection && (
          <>
            <div className="reflection-section strengths">
              <div className="section-icon">💪</div>
              <div className="section-content">
                <h2>Overall strengths (aggregate)</h2>
                {reflection.strengths && reflection.strengths.length > 0 ? (
                  <ul className="reflection-list">
                    {reflection.strengths.map((strength, idx) => (
                      <li key={idx}>{strength}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="no-data">No strengths identified yet.</p>
                )}
              </div>
            </div>

            <div className="reflection-section risks">
              <div className="section-icon">⚠️</div>
              <div className="section-content">
                <h2>Overall areas of concern (aggregate)</h2>
                {reflection.risks && reflection.risks.length > 0 ? (
                  <ul className="reflection-list">
                    {reflection.risks.map((risk, idx) => (
                      <li key={idx}>{risk}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="no-data">No concerns identified.</p>
                )}
              </div>
            </div>

            <div className="reflection-section suggestions">
              <div className="section-icon">💡</div>
              <div className="section-content">
                <h2>Overall suggestions (aggregate)</h2>
                {reflection.suggestions && reflection.suggestions.length > 0 ? (
                  <ul className="reflection-list">
                    {reflection.suggestions.map((suggestion, idx) => (
                      <li key={idx}>{suggestion}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="no-data">No suggestions available at this time.</p>
                )}
              </div>
            </div>
          </>
        )}

        {gradingDetails.length > 0 && (
          <div className="reflection-section per-prompt-feedback">
            <div className="section-icon">📋</div>
            <div className="section-content">
              <h2>Per-prompt feedback</h2>
              <p className="no-data">Each prompt below shows the grader’s strength, area to improve, and suggestions for that prompt.</p>
              <div className="per-prompt-list">
                {gradingDetails.map((row, idx) => {
                  const ev = row.evaluation || {};
                  const excerpt = (row.prompt_text || '').slice(0, 100) + ((row.prompt_text || '').length > 100 ? '...' : '');
                  return (
                    <div key={idx} className="per-prompt-item">
                      <h3>Prompt {idx + 1} — Score: {(row.total_score ?? ev.total_score ?? 0)}/15</h3>
                      <p className="prompt-excerpt" title={row.prompt_text}>{excerpt}</p>
                      {ev.strength_summary && <p><strong>Strength:</strong> {ev.strength_summary}</p>}
                      {ev.weakness_summary && <p><strong>Area to improve:</strong> {ev.weakness_summary}</p>}
                      {ev.improvement_suggestions && ev.improvement_suggestions.length > 0 && (
                        <>
                          <p><strong>Suggestions:</strong></p>
                          <ul>
                            {ev.improvement_suggestions.map((s, i) => (
                              <li key={i}>{typeof s === 'string' ? s : String(s)}</li>
                            ))}
                          </ul>
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        <div className="reflection-actions">
          <button 
            onClick={() => navigate(`/dashboard/${datasetId}`)}
            className="action-button secondary"
          >
            Back to Dashboard
          </button>
          <button 
            onClick={() => navigate(`/export/${datasetId}`)}
            className="action-button primary"
          >
            Export Results
          </button>
        </div>
      </div>
    </div>
  );
};

export default ReflectionPage;

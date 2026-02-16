import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getResults, analyzeClassification, getAnalysisProgress, analyzeSRL, analyzeGrading } from '../apiClient';
import { 
  BarChart, 
  Bar, 
  PieChart, 
  Pie, 
  Cell, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  Legend, 
  ResponsiveContainer 
} from 'recharts';
import './DashboardPage.css';

const COLORS = ['#22B800', '#4a4a4a', '#6b6b6b', '#2d2d2d', '#1a1a1a', '#808080'];

const DashboardPage = () => {
  const { datasetId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [classificationData, setClassificationData] = useState(null);
  const [classificationLoading, setClassificationLoading] = useState(false);
  const [classificationError, setClassificationError] = useState(null);
  const [analysisProgress, setAnalysisProgress] = useState({ current: 0, total: 50, message: '', status: 'idle' });
  const [progressMessages, setProgressMessages] = useState([]);
  const [currentAnalysis, setCurrentAnalysis] = useState(null);
  const [srlData, setSrlData] = useState(null);
  const [srlLoading, setSrlLoading] = useState(false);
  const [srlError, setSrlError] = useState(null);
  const [gradingData, setGradingData] = useState(null);
  const [gradingLoading, setGradingLoading] = useState(false);
  const [gradingError, setGradingError] = useState(null);

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

  const handleAnalyzeClassification = async () => {
    setCurrentAnalysis('paulElder');
    setClassificationLoading(true);
    setClassificationError(null);
    setAnalysisProgress({ current: 0, total: 50, message: 'Starting analysis...', status: 'running' });
    setProgressMessages(['Starting analysis...']);
    
    // Poll for progress updates
    const progressInterval = setInterval(async () => {
      try {
        const progress = await getAnalysisProgress(datasetId, 'paul_elder');
        setAnalysisProgress(progress);
        
        // Add new messages to the log
        setProgressMessages(prev => {
          if (progress.message && !prev.includes(progress.message)) {
            const newMessages = [...prev, progress.message];
            // Keep only last 10 messages
            return newMessages.slice(-10);
          }
          return prev;
        });
        
        // Stop polling if complete
        if (progress.status === 'complete') {
          clearInterval(progressInterval);
        }
      } catch (err) {
        console.error('Error fetching progress:', err);
      }
    }, 500); // Poll every 500ms
    
    try {
      const results = await analyzeClassification(datasetId);
      clearInterval(progressInterval);
      setAnalysisProgress({ current: results.analyzed_count, total: results.analyzed_count, message: 'Analysis complete!', status: 'complete' });
      setProgressMessages(prev => [...prev, 'Analysis complete!']);
      setClassificationData(results);
      // Update the main data object with classification results
      setData(prevData => ({
        ...prevData,
        analysis: {
          ...prevData.analysis,
          categories: results.categories,
          breakdown: results.breakdown,
          classification_stats: results.classification_stats
        }
      }));
    } catch (err) {
      clearInterval(progressInterval);
      setClassificationError(
        err.response?.data?.message || 
        err.message || 
        'Failed to analyze classification'
      );
      setAnalysisProgress(prev => ({ ...prev, status: 'idle' }));
      console.error('Error analyzing classification:', err);
    } finally {
      setClassificationLoading(false);
    }
  };

  const handleAnalyzeSRL = async () => {
    setCurrentAnalysis('srl');
    setSrlLoading(true);
    setSrlError(null);
    setAnalysisProgress({ current: 0, total: 50, message: 'Starting SRL analysis...', status: 'running' });
    setProgressMessages(['Starting SRL analysis...']);
    const progressInterval = setInterval(async () => {
      try {
        const progress = await getAnalysisProgress(datasetId, 'srl');
        setAnalysisProgress(progress);
        setProgressMessages(prev => {
          if (progress.message && !prev.includes(progress.message)) {
            return [...prev, progress.message].slice(-10);
          }
          return prev;
        });
        if (progress.status === 'complete') clearInterval(progressInterval);
      } catch (err) { console.error(err); }
    }, 500);
    try {
      const results = await analyzeSRL(datasetId);
      clearInterval(progressInterval);
      setAnalysisProgress({ current: results.analyzed_count, total: results.analyzed_count, message: 'SRL analysis complete!', status: 'complete' });
      setProgressMessages(prev => [...prev, 'SRL analysis complete!']);
      setSrlData(results);
    } catch (err) {
      clearInterval(progressInterval);
      setSrlError(err.response?.data?.message || err.message || 'Failed to run SRL analysis');
      setAnalysisProgress(prev => ({ ...prev, status: 'idle' }));
      console.error(err);
    } finally {
      setSrlLoading(false);
    }
  };

  const handleAnalyzeGrading = async () => {
    setCurrentAnalysis('grading');
    setGradingLoading(true);
    setGradingError(null);
    setAnalysisProgress({ current: 0, total: 50, message: 'Grading prompts...', status: 'running' });
    setProgressMessages(['Grading prompts...']);
    const progressInterval = setInterval(async () => {
      try {
        const progress = await getAnalysisProgress(datasetId, 'grading');
        setAnalysisProgress(progress);
        setProgressMessages(prev => {
          if (progress.message && !prev.includes(progress.message)) {
            return [...prev, progress.message].slice(-10);
          }
          return prev;
        });
        if (progress.status === 'complete') clearInterval(progressInterval);
      } catch (err) { console.error(err); }
    }, 500);
    try {
      const results = await analyzeGrading(datasetId);
      clearInterval(progressInterval);
      setAnalysisProgress({ current: results.analyzed_count, total: results.analyzed_count, message: 'Grading complete!', status: 'complete' });
      setProgressMessages(prev => [...prev, 'Grading complete!']);
      setGradingData(results.grading_results);
      setData(prev => ({
        ...prev,
        reflection: {
          ...prev.reflection,
          strengths: prev.reflection.strengths?.length ? prev.reflection.strengths : (results.grading_results?.aggregate?.strength_summary ? [results.grading_results.aggregate.strength_summary] : []),
          risks: prev.reflection.risks?.length ? prev.reflection.risks : (results.grading_results?.aggregate?.weakness_summary ? [results.grading_results.aggregate.weakness_summary] : []),
          suggestions: results.grading_results?.aggregate?.improvement_suggestions || prev.reflection.suggestions || [],
          overall_summary: prev.reflection.overall_summary || `Average total score: ${results.grading_results?.aggregate?.average_total_score ?? 0}/15.`,
        },
      }));
    } catch (err) {
      clearInterval(progressInterval);
      setGradingError(err.response?.data?.message || err.message || 'Failed to grade prompts');
      setAnalysisProgress(prev => ({ ...prev, status: 'idle' }));
      console.error(err);
    } finally {
      setGradingLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="dashboard-page">
        <div className="loading-container">
          <div className="spinner"></div>
          <p>Loading analysis results...</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="dashboard-page">
        <div className="error-container">
          <h2>Error Loading Results</h2>
          <p>{error || 'No data available'}</p>
          <button onClick={() => navigate('/')} className="back-button">
            Back to Upload
          </button>
        </div>
      </div>
    );
  }

  const { analysis, word_cloud_image, prompt_previews } = data;
  
  // Use classification data if available (from button click), otherwise use analysis data
  const effectiveClassificationData = classificationData || (analysis.classification_stats ? {
    categories: analysis.categories || [],
    breakdown: analysis.breakdown || {},
    classification_stats: analysis.classification_stats,
    analyzed_count: analysis.classification_stats?.total_messages || 0
  } : null);
  
  // Paul-Elder framework category mapping
  const paulElderCategories = {
    'CT1': 'Clarity',
    'CT2': 'Accuracy',
    'CT3': 'Precision',
    'CT4': 'Relevance',
    'CT5': 'Depth',
    'CT6': 'Breadth',
    'CT7': 'Logicalness',
    'CT8': 'Significance',
    'CT9': 'Fairness',
    'Non-CT': 'Non-Critical Thinking'
  };
  
  // Calculate critical thinking percentage
  const classificationStats = effectiveClassificationData?.classification_stats;
  const criticalThinkingPercentage = classificationStats?.critical_thinking_percentage || 0;
  const classifiedCount = classificationStats?.total_messages || 0;
  
  // Prepare data for charts (handle empty categories)
  const categoriesToUse = effectiveClassificationData?.categories || analysis.categories || [];
  const breakdownToUse = effectiveClassificationData?.breakdown || analysis.breakdown || {};
  
  const categoryData = categoriesToUse.map(cat => ({
    name: cat.category,
    percentage: cat.percentage,
    count: cat.count,
  }));

  const breakdownData = Object.entries(breakdownToUse)
    .filter(([_, value]) => value > 0)
    .map(([key, value]) => ({
      name: paulElderCategories[key] || key,
      value: value,
      code: key
    }))
    .sort((a, b) => b.value - a.value);

  return (
    <div className="dashboard-page">
      <div className="dashboard-container">
        <div className="dashboard-header">
          <h1>Analysis Dashboard</h1>
          <p>Dataset ID: {datasetId}</p>
        </div>

        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-label">Total Prompts</div>
            <div className="stat-value">{analysis.total_prompts}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Analysis Date</div>
            <div className="stat-value-small">
              {new Date(analysis.generated_at).toLocaleDateString()}
            </div>
          </div>
        </div>

        {/* Framework Analysis Cards - Side by Side */}
        <div className="framework-cards-container">
          {/* Paul-Elder Card */}
          <div className="framework-card">
            <div className="framework-card-header">
              <h2>Paul-Elder Framework</h2>
              <span className="framework-badge">Active</span>
            </div>
            
            <div className="framework-description-text">
              <p className="framework-intro">
                The <strong>Paul-Elder Critical Thinking Framework</strong> is a comprehensive model for 
                evaluating and improving thinking quality. Developed by Dr. Richard Paul and Dr. Linda Elder, 
                it identifies nine essential intellectual standards that should be applied to reasoning. 
                This analysis evaluates your prompts against these standards:
              </p>
              <ul className="framework-standards">
                <li>
                  <strong>Clarity</strong> - Understandable and free from confusion or ambiguity. 
                  The "gateway" standard—if a statement is unclear, you cannot determine if it's accurate or relevant.
                </li>
                <li>
                  <strong>Accuracy</strong> - Free from errors, mistakes, or distortions; true and correct. 
                  A statement can be clear but inaccurate.
                </li>
                <li>
                  <strong>Precision</strong> - Exact to the necessary level of detail and specific. 
                  A statement can be clear and accurate but lack precision.
                </li>
                <li>
                  <strong>Relevance</strong> - Connected to the question at issue. 
                  A statement can be clear, accurate, and precise but irrelevant to the problem.
                </li>
                <li>
                  <strong>Depth</strong> - Addresses complexities and significant factors rather than treating issues superficially. 
                  Goes beyond surface-level understanding.
                </li>
                <li>
                  <strong>Breadth</strong> - Considers multiple perspectives and points of view rather than 
                  approaching an issue from only one standpoint.
                </li>
                <li>
                  <strong>Logic</strong> - Follows sound reasoning where conclusions follow from premises. 
                  Ideas are coherent and consistent.
                </li>
                <li>
                  <strong>Significance</strong> - Addresses what matters most; avoids trivial or minor considerations. 
                  Focuses on important and meaningful aspects.
                </li>
                <li>
                  <strong>Fairness</strong> - Unbiased and impartial in evaluating reasoning and different viewpoints. 
                  Justifiable and free from vested interest.
                </li>
              </ul>
              <p className="framework-source">
                <em>Source: Foundation for Critical Thinking, Paul-Elder Model of Critical Thinking</em>
              </p>
            </div>
            
            {!effectiveClassificationData && !classificationLoading && (
              <div className="framework-card-action">
                <button 
                  onClick={handleAnalyzeClassification}
                  disabled={classificationLoading}
                  className="action-button primary analyze-button"
                >
                  Analyze 50 Sample Prompts
                </button>
                {classificationError && (
                  <div className="error-message" style={{ color: 'red', marginTop: '10px', fontSize: '0.875rem' }}>
                    {classificationError}
                  </div>
                )}
              </div>
            )}
            
            {(classificationLoading || (analysisProgress.status === 'running' && analysisProgress.current > 0)) && currentAnalysis === 'paulElder' && (
              <div className="progress-section">
                <div className="progress-header">
                  <span>{analysisProgress.message || 'Analyzing prompts...'}</span>
                  <span className="progress-text">
                    {analysisProgress.current} / {analysisProgress.total}
                  </span>
                </div>
                <div className="progress-bar">
                  <div 
                    className="progress-fill" 
                    style={{ width: `${(analysisProgress.total > 0 ? (analysisProgress.current / analysisProgress.total) * 100 : 0)}%` }}
                  ></div>
                </div>
                {progressMessages.length > 0 && (
                  <div className="progress-messages">
                    <div className="progress-messages-header">Console Output:</div>
                    <div className="progress-messages-list">
                      {progressMessages.map((msg, idx) => (
                        <div key={idx} className="progress-message-item">
                          {msg}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {classificationLoading && (
                  <p className="progress-note">This may take a few minutes...</p>
                )}
              </div>
            )}
            
            {effectiveClassificationData && (
              <div className="framework-results">
                <div className="framework-summary">
                  <div className="summary-stat">
                    <div className="summary-label">Critical Thinking</div>
                    <div className="summary-value">{criticalThinkingPercentage.toFixed(1)}%</div>
                  </div>
                  <div className="summary-stat">
                    <div className="summary-label">Prompts Analyzed</div>
                    <div className="summary-value">{classifiedCount}</div>
                    <div className="summary-note">(First 50 prompts)</div>
                  </div>
                </div>
                
                <div className="category-breakdown">
                  <h3>Category Breakdown</h3>
                  <div className="breakdown-list">
                    {categoriesToUse
                      .sort((a, b) => b.percentage - a.percentage)
                      .map((category, idx) => (
                        <div key={idx} className="breakdown-item">
                          <div className="breakdown-header">
                            <span className="breakdown-name">{category.category}</span>
                            <span className="breakdown-percentage">{category.percentage.toFixed(1)}%</span>
                          </div>
                          <div className="breakdown-count">{category.count} prompt{category.count !== 1 ? 's' : ''}</div>
                          {category.examples && category.examples.length > 0 && (
                            <div className="breakdown-examples">
                              <strong>Examples:</strong>
                              <ul>
                                {category.examples.map((example, exIdx) => (
                                  <li key={exIdx} title={example}>
                                    {example.length > 100 ? `${example.substring(0, 100)}...` : example}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* SRL Card */}
          <div className="framework-card srl-card">
            <div className="framework-card-header">
              <h2>Self-Regulated Learning (SRL)</h2>
              <span className="framework-badge">Active</span>
            </div>
            <div className="framework-description-text">
              <p className="framework-intro">
                <strong>SRL analysis</strong> classifies each prompt using three models (self-regulated learning and educational psychology), 
                reporting Zimmerman's phases, COPES (Winne &amp; Hadwin), and Bloom's level. It evaluates your prompts against these dimensions:
              </p>
              <ul className="framework-standards">
                <li>
                  <strong>Forethought</strong> — Task analysis, goal setting, self-motivation (e.g. self-efficacy, outcome expectations). 
                  Indicators: "I want to learn", "My goal is", future tense.
                </li>
                <li>
                  <strong>Performance</strong> — Self-control and self-observation (e.g. self-instruction, task strategies, self-recording). 
                  Indicators: "I'm implementing", clarifying questions during work.
                </li>
                <li>
                  <strong>Self-Reflection</strong> — Self-judgment and self-reaction (e.g. self-evaluation, causal attribution). 
                  Indicators: "That didn't work", "I understand now", past tense.
                </li>
                <li>
                  <strong>Conditions (C)</strong> — Resources or constraints mentioned. Scored 0 or 1 within the assigned Zimmerman phase.
                </li>
                <li>
                  <strong>Operations (O)</strong> — Cognitive processes, tactics, or strategies shown. COPES total is 0–5 per message.
                </li>
                <li>
                  <strong>Products (P)</strong> — Information or new knowledge created by operations.
                </li>
                <li>
                  <strong>Evaluations (E)</strong> — Self-monitoring, assessment, or feedback (internal or from teacher/peer).
                </li>
                <li>
                  <strong>Standards (S)</strong> — Success criteria or criteria against which products are evaluated.
                </li>
                <li>
                  <strong>Bloom's Taxonomy (1956)</strong> — One level per message: Knowledge → Comprehension → Application → Analysis → Synthesis → Evaluation (with confidence and rationale).
                </li>
              </ul>
              <p className="framework-source">
                <em>Sources: Zimmerman (SRL phases); Winne &amp; Hadwin (COPES); Bloom (taxonomy)</em>
              </p>
            </div>
            {!srlData && !srlLoading && (
              <div className="framework-card-action">
                <button
                  onClick={handleAnalyzeSRL}
                  disabled={srlLoading}
                  className="action-button primary analyze-button"
                >
                  Analyze 50 Sample Prompts (SRL)
                </button>
                {srlError && (
                  <div className="error-message" style={{ color: 'red', marginTop: '10px', fontSize: '0.875rem' }}>
                    {srlError}
                  </div>
                )}
              </div>
            )}
            {srlLoading && (
              <div className="progress-section">
                <div className="progress-header">
                  <span>{analysisProgress.message || 'Analyzing...'}</span>
                  <span className="progress-text">{analysisProgress.current} / {analysisProgress.total}</span>
                </div>
                <div className="progress-bar">
                  <div className="progress-fill" style={{ width: `${(analysisProgress.total > 0 ? (analysisProgress.current / analysisProgress.total) * 100 : 0)}%` }}></div>
                </div>
                {progressMessages.length > 0 && (
                  <div className="progress-messages">
                    <div className="progress-messages-header">Console Output:</div>
                    <div className="progress-messages-list">
                      {progressMessages.map((msg, idx) => (
                        <div key={idx} className="progress-message-item">{msg}</div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
            {srlData && (
              <div className="framework-results">
                <div className="framework-summary">
                  <div className="summary-stat">
                    <div className="summary-label">Zimmerman phases</div>
                    <div className="summary-value">{Object.keys(srlData.phase_distribution || {}).join(', ')}</div>
                  </div>
                  <div className="summary-stat">
                    <div className="summary-label">COPES average</div>
                    <div className="summary-value">{srlData.copes_average != null ? srlData.copes_average.toFixed(1) : '—'}/5</div>
                  </div>
                  <div className="summary-stat">
                    <div className="summary-label">Bloom's avg level</div>
                    <div className="summary-value">{srlData.blooms_average_level != null ? srlData.blooms_average_level.toFixed(1) : '—'}/6</div>
                  </div>
                  <div className="summary-stat">
                    <div className="summary-label">Prompts analyzed</div>
                    <div className="summary-value">{srlData.analyzed_count}</div>
                  </div>
                </div>
                <div className="category-breakdown">
                  <h3>Phase distribution</h3>
                  <div className="breakdown-list">
                    {srlData.phase_distribution && Object.entries(srlData.phase_distribution).map(([phase, count]) => (
                      <div key={phase} className="breakdown-item">
                        <span className="breakdown-name">{phase}</span>
                        <span className="breakdown-count">{count} message{count !== 1 ? 's' : ''}</span>
                      </div>
                    ))}
                  </div>
                </div>
                {srlData.message_results && srlData.message_results.length > 0 && (
                  <div className="category-breakdown">
                    <h3>Sample results</h3>
                    <div className="breakdown-list">
                      {srlData.message_results.slice(0, 5).map((row, idx) => (
                        <div key={idx} className="breakdown-item">
                          <div className="breakdown-header">
                            <span className="breakdown-name">{row.zimmerman_phase}</span>
                            <span className="breakdown-percentage">COPES: {row.copes_score}/5 · Bloom's: {row.blooms_name}</span>
                          </div>
                          <div className="breakdown-count" title={row.message}>{row.message}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Prompt Quality (Grading) Card */}
          <div className="framework-card grading-card">
            <div className="framework-card-header">
              <h2>Prompt Quality (Grading)</h2>
              <span className="framework-badge">Active</span>
            </div>
            <div className="framework-description-text">
              <p className="framework-intro">
                This grader evaluates <strong>the prompt itself</strong>—not the model's answer—for how well it enables an LLM to produce high-quality responses by reducing uncertainty, structuring reasoning, staying robust, and matching the task. It does not assume missing context or infer unstated requirements; missing information is reflected in the score. Each dimension is scored <strong>0–3</strong> (0 = Poor/absent, 1 = Weak/partial, 2 = Adequate/functional, 3 = Strong/explicit). Maximum total is 15. The five dimensions used to calculate the analysis are:
              </p>
              <ul className="framework-standards">
                <li><strong>Clarity and Precision</strong> — Does the prompt clearly state the task goal? Provide sufficient, relevant context? Minimize ambiguity? Constrain the model's response space appropriately?</li>
                <li><strong>Structural Design</strong> — Is the prompt logically organized with clear ordering or formatting? Are concerns separated where appropriate? Is there guidance on the structure or form of the desired output?</li>
                <li><strong>Task Breakdown and Cognitive Scaffolding</strong> — Are complex tasks broken into manageable steps? Is intermediate reasoning scaffolded when needed? Is cognitive load aligned with task complexity?</li>
                <li><strong>Prompt Boundaries, Guardrails, and Robustness</strong> — Are instructions, data, and constraints clearly separated? Are delimiters, exclusions, or scoped authority used when appropriate? Is the prompt resilient to misinterpretation or unintended behavior?</li>
                <li><strong>Task–Context Alignment</strong> — Is the level of detail, structure, and constraints appropriate for the task type and complexity—avoiding unnecessary overengineering or under-specification? Missing task context or assumptions is noted and reflected in the score.</li>
              </ul>
            </div>
            {!gradingData && !gradingLoading && (
              <div className="framework-card-action">
                <button
                  onClick={handleAnalyzeGrading}
                  disabled={gradingLoading}
                  className="action-button primary analyze-button"
                >
                  Grade 50 Sample Prompts
                </button>
                {gradingError && (
                  <div className="error-message" style={{ color: 'red', marginTop: '10px', fontSize: '0.875rem' }}>
                    {gradingError}
                  </div>
                )}
              </div>
            )}
            {gradingLoading && (
              <div className="progress-section">
                <div className="progress-header">
                  <span>{analysisProgress.message || 'Grading...'}</span>
                  <span className="progress-text">{analysisProgress.current} / {analysisProgress.total}</span>
                </div>
                <div className="progress-bar">
                  <div className="progress-fill" style={{ width: `${(analysisProgress.total > 0 ? (analysisProgress.current / analysisProgress.total) * 100 : 0)}%` }}></div>
                </div>
                {progressMessages.length > 0 && (
                  <div className="progress-messages">
                    <div className="progress-messages-header">Console Output:</div>
                    <div className="progress-messages-list">
                      {progressMessages.map((msg, idx) => (
                        <div key={idx} className="progress-message-item">{msg}</div>
                      ))}
                    </div>
                  </div>
                )}
                <p className="progress-note">This may take a few minutes...</p>
              </div>
            )}
            {(gradingData || data?.analysis?.grading_results) && (
              <div className="framework-results">
                {(() => {
                  const gr = gradingData || data?.analysis?.grading_results;
                  const agg = gr?.aggregate || {};
                  const details = gr?.details || [];
                  return (
                    <>
                      <div className="framework-summary">
                        <div className="summary-stat">
                          <div className="summary-label">Average total score</div>
                          <div className="summary-value">{agg.average_total_score != null ? agg.average_total_score.toFixed(1) : '—'}/15</div>
                        </div>
                        <div className="summary-stat">
                          <div className="summary-label">Prompts graded</div>
                          <div className="summary-value">{typeof agg.total_prompts === 'number' ? agg.total_prompts : (details.length > 0 ? details.length : '—')}</div>
                        </div>
                      </div>
                      {agg.dimension_averages && Object.keys(agg.dimension_averages).length > 0 && (
                        <div className="category-breakdown">
                          <h3>Dimension averages</h3>
                          <div className="breakdown-list">
                            {Object.entries(agg.dimension_averages).map(([dim, val]) => (
                              <div key={dim} className="breakdown-item">
                                <span className="breakdown-name">{dim.replace(/_/g, ' ')}</span>
                                <span className="breakdown-percentage">{typeof val === 'number' ? val.toFixed(1) : val}/3</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                      <div className="category-breakdown">
                        <h3>Per-prompt feedback</h3>
                        <p className="breakdown-count" style={{ marginBottom: '0.75rem' }}>
                          Each prompt below shows its own strength, area to improve, and suggestions from the grader.
                        </p>
                        <div className="breakdown-list grading-per-prompt-list">
                          {details.map((row, idx) => {
                            const ev = row.evaluation || {};
                            const promptExcerpt = (row.prompt_text || '').slice(0, 120);
                            const promptLabel = promptExcerpt + ((row.prompt_text || '').length > 120 ? '...' : '');
                            return (
                              <div key={idx} className="breakdown-item grading-per-prompt-item">
                                <div className="breakdown-header">
                                  <span className="breakdown-name">Prompt {idx + 1}</span>
                                  <span className="breakdown-percentage">Score: {(row.total_score ?? ev.total_score ?? 0)}/15</span>
                                </div>
                                <div className="grading-prompt-text" title={row.prompt_text}>{promptLabel}</div>
                                {ev.strength_summary && (
                                  <div className="grading-feedback-row"><strong>Strength:</strong> {ev.strength_summary}</div>
                                )}
                                {ev.weakness_summary && (
                                  <div className="grading-feedback-row"><strong>Area to improve:</strong> {ev.weakness_summary}</div>
                                )}
                                {ev.improvement_suggestions && ev.improvement_suggestions.length > 0 && (
                                  <div className="grading-feedback-row">
                                    <strong>Suggestions:</strong>
                                    <ul style={{ margin: '0.25rem 0 0 1rem', paddingLeft: '1rem' }}>
                                      {ev.improvement_suggestions.map((s, i) => (
                                        <li key={i}>{typeof s === 'string' ? s : String(s)}</li>
                                      ))}
                                    </ul>
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    </>
                  );
                })()}
              </div>
            )}
          </div>
        </div>

        {/* Word Cloud Section */}
        {word_cloud_image && (
          <div className="wordcloud-section">
            <h2>Prompt Word Cloud</h2>
            <div className="wordcloud-container">
              <img 
                src={word_cloud_image} 
                alt="Prompt Word Cloud" 
                className="wordcloud-image"
              />
            </div>
          </div>
        )}

        {/* Prompt Previews Section */}
        {prompt_previews && prompt_previews.length > 0 && (
          <div className="prompt-previews-section">
            <h2>Sample Prompts</h2>
            <div className="prompt-list">
              {prompt_previews.map((prompt, idx) => (
                <div key={idx} className="prompt-item">
                  <div className="prompt-header">
                    <span className="prompt-title">{prompt.conversation_title || 'Untitled'}</span>
                    {prompt.message_create_time_iso_utc && (
                      <span className="prompt-date">
                        {new Date(prompt.message_create_time_iso_utc).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                  <div className="prompt-text">{prompt.prompt_text}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Additional Charts Section (Optional - can be removed if not needed) */}
        {categoryData.length > 0 && (
          <div className="charts-section">
            {breakdownData.length > 0 && (
              <div className="chart-container">
                <h2>Paul-Elder Framework Distribution</h2>
                <ResponsiveContainer width="100%" height={400}>
                  <PieChart>
                    <Pie
                      data={breakdownData}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, value }) => `${name}: ${value.toFixed(1)}%`}
                      outerRadius={120}
                      fill="#8884d8"
                      dataKey="value"
                    >
                      {breakdownData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(value) => `${value.toFixed(1)}%`} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        )}

        <div className="dashboard-actions">
          <button 
            onClick={() => navigate(`/reflection/${datasetId}`)}
            className="action-button primary"
          >
            View Reflection
          </button>
          <button 
            onClick={() => navigate(`/export/${datasetId}`)}
            className="action-button secondary"
          >
            Export Results
          </button>
        </div>
      </div>
    </div>
  );
};

export default DashboardPage;

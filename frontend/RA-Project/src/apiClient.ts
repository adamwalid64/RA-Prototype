// API client wrapper for Axios
import axios from 'axios';
import type { 
  UploadResponse, 
  ReflectionResults, 
  ExportResponse 
} from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Upload file and get dataset_id
export const uploadFile = async (file: File): Promise<UploadResponse> => {
  const formData = new FormData();
  formData.append('file', file);
  
  const response = await apiClient.post<UploadResponse>('/api/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  
  return response.data;
};

// Get analysis and reflection results for a dataset
export const getResults = async (datasetId: string): Promise<ReflectionResults> => {
  const response = await apiClient.get<ReflectionResults>(`/api/results/${datasetId}`);
  return response.data;
};

// Analyze classification using Paul-Elder framework (50 sample prompts)
export const analyzeClassification = async (datasetId: string): Promise<{
  dataset_id: string;
  categories: Array<{
    category: string;
    percentage: number;
    count: number;
    examples: string[];
  }>;
  breakdown: { [key: string]: number };
  classification_stats: {
    total_messages: number;
    critical_thinking_count: number;
    non_critical_count: number;
    critical_thinking_percentage: number;
    category_breakdown: { [category: string]: number };
  };
  analyzed_count: number;
  generated_at: string;
}> => {
  const response = await apiClient.post(`/api/analyze-classification/${datasetId}`);
  return response.data;
};

// Analyze SRL (Self-Regulated Learning) - Zimmerman, COPES, Bloom's (50 sample prompts)
export const analyzeSRL = async (datasetId: string): Promise<{
  dataset_id: string;
  phase_distribution: { [phase: string]: number };
  copes_average: number;
  blooms_distribution: { [name: string]: number };
  blooms_average_level: number;
  message_results: Array<{
    message: string;
    zimmerman_phase: string;
    copes_score: number;
    blooms_level: number;
    blooms_name: string;
  }>;
  analyzed_count: number;
  generated_at: string;
}> => {
  const response = await apiClient.post(`/api/analyze-srl/${datasetId}`);
  return response.data;
};

// Analyze prompt quality (grading) - 50 sample prompts
export const analyzeGrading = async (datasetId: string): Promise<{
  dataset_id: string;
  grading_results: {
    aggregate: {
      average_total_score: number;
      dimension_averages: { [key: string]: number };
      strength_summary: string;
      weakness_summary: string;
      improvement_suggestions: string[];
      total_prompts: number;
    };
    details: Array<Record<string, unknown>>;
  };
  analyzed_count: number;
  generated_at: string;
}> => {
  const response = await apiClient.post(`/api/analyze-grading/${datasetId}`);
  return response.data;
};

// Get analysis progress for a specific analysis type (each classifier has its own progress)
export const getAnalysisProgress = async (
  datasetId: string,
  type: 'paul_elder' | 'srl' | 'grading' = 'paul_elder'
): Promise<{
  current: number;
  total: number;
  message: string;
  status: 'idle' | 'running' | 'complete';
}> => {
  const response = await apiClient.get(`/api/analysis-progress/${datasetId}`, {
    params: { type },
  });
  return response.data;
};

// Export results (JSON or PDF)
export const exportResults = async (
  datasetId: string, 
  fileType: 'json' | 'pdf' = 'json'
): Promise<Blob> => {
  const response = await apiClient.get(`/api/export/${datasetId}`, {
    params: { format: fileType },
    responseType: 'blob',
  });
  
  return response.data;
};

// Health check
export const healthCheck = async (): Promise<{ status: string }> => {
  const response = await apiClient.get<{ status: string }>('/api/health');
  return response.data;
};

export default apiClient;

// Shared DTO types for frontend-backend communication

export interface UploadResponse {
  upload_id: string;
  dataset_id: string;
  message: string;
  file_name: string;
  file_size: number;
  uploaded_at: string;
}

export interface PromptCategory {
  category: string;
  percentage: number;
  count: number;
  examples?: string[];
}

export interface ClassificationStats {
  total_messages: number;
  critical_thinking_count: number;
  non_critical_count: number;
  critical_thinking_percentage: number;
  category_breakdown: {
    [category: string]: number;
  };
}

export interface AnalysisResults {
  dataset_id: string;
  total_prompts: number;
  categories: PromptCategory[];
  breakdown: {
    CT1?: number;
    CT2?: number;
    CT3?: number;
    CT4?: number;
    CT5?: number;
    CT6?: number;
    CT7?: number;
    CT8?: number;
    CT9?: number;
    'Non-CT'?: number;
    [key: string]: number;
  };
  generated_at: string;
  classification_stats?: ClassificationStats;
}

export interface ReflectionNarrative {
  strengths: string[];
  risks: string[];
  suggestions: string[];
  overall_summary: string;
}

export interface ReflectionResults {
  dataset_id: string;
  analysis: AnalysisResults;
  reflection: ReflectionNarrative;
}

export interface ExportResponse {
  dataset_id: string;
  download_url: string;
  file_type: 'json' | 'pdf';
  expires_at?: string;
}

export interface ConsentSettings {
  allow_anonymization: boolean;
  share_for_research: boolean;
  consent_given: boolean;
}

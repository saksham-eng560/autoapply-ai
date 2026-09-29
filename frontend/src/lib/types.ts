export type ApplicationStatus =
  | "discovered" | "matched" | "skipped" | "preparing" | "pending_approval" | "approved" | "applied"
  | "acknowledged" | "screening" | "interview" | "assessment" | "final_round" | "offer" | "accepted"
  | "rejected" | "withdrawn" | "failed";

export interface Preferences {
  target_roles: string[];
  target_locations: string[];
  remote_preference: "remote" | "hybrid" | "onsite" | "any";
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string;
  experience_level: string[];
  industries: string[];
  company_size_preference: string[];
  companies_to_avoid: string[];
  companies_to_target: string[];
  max_applications_per_day: number;
  auto_apply_threshold: number;
  job_types: string[];
  notification_channels: string[];
  keywords_exclude: string[];
  posted_within_days: number;
  scan_enabled: boolean;
  scan_interval_hours: number;
  platforms: string[];
  sources: {
    greenhouse_boards: string[];
    lever_companies: string[];
    ashby_boards: string[];
    workday_sites: string[];
    career_pages: string[];
  };
  discord_webhook_url: string | null;
  slack_webhook_url: string | null;
  timezone: string;
  cover_letter_enabled: boolean;
  resume_template?: string;
  auto_draft_replies?: boolean;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  phone: string | null;
  location: string | null;
  linkedin_url: string | null;
  has_password: boolean;
  google_connected: boolean;
  google_email: string | null;
  linkedin_connected: boolean;
  linkedin_session_valid: boolean;
  preferences: Preferences;
  last_scan_at: string | null;
  created_at: string;
}

export interface JobApplicationRef {
  id: string;
  status: ApplicationStatus;
  match_score: number | null;
  match_reasoning: string | null;
  similarity_score: number | null;
}

export interface Job {
  id: string;
  company_name: string;
  company_logo_url: string | null;
  role_title: string;
  location: string | null;
  is_remote: boolean;
  job_type: string | null;
  experience_level: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  source_url: string;
  source_platform: string;
  application_url: string | null;
  easy_apply: boolean;
  extracted_skills: string[];
  posted_date: string | null;
  deadline_date: string | null;
  discovered_at: string;
  is_active: boolean;
  description?: string;
  application?: JobApplicationRef;
}

export interface CustomAnswer {
  question: string;
  answer: string;
  field_type?: string | null;
  confidence?: number | null;
  needs_user_review?: boolean | null;
  options?: string[] | null;
  required?: boolean | null;
  source?: string | null;
  field_id?: string | null;
}

export interface FormFieldReport {
  label: string;
  kind: string;
  type: string;
  value: string;
  required: boolean;
  status: "filled" | "skipped" | "unmapped";
  options?: string[];
  confidence?: number;
  needs_user_review?: boolean;
}

export interface HistoryEntry {
  id: string;
  old_status: ApplicationStatus | null;
  new_status: ApplicationStatus;
  changed_by: string;
  notes: string | null;
  created_at: string;
}

export interface ResumeContent {
  personal_info: { name: string; email: string; phone: string; location: string; linkedin: string; github: string; portfolio: string };
  summary: string;
  education: { institution: string; degree: string; field: string; gpa: string; start_date: string; end_date: string; highlights: string[] }[];
  experience: { company: string; title: string; start_date: string; end_date: string; location: string; bullets: string[] }[];
  projects: { name: string; description: string; technologies: string[]; url: string }[];
  skills: { technical: string[]; languages: string[]; tools: string[]; soft_skills: string[] };
  certifications: { name: string; issuer: string; date: string }[];
  awards: string[];
}

export interface Resume {
  id: string;
  label: string | null;
  original_filename: string | null;
  is_master: boolean;
  version: number;
  parent_resume_id: string | null;
  tailored_for_job_id: string | null;
  changes_made: string[];
  pdf_url: string | null;
  original_file_url: string | null;
  created_at: string;
  updated_at: string;
  parsed_content?: ResumeContent;
  parse_method?: string;
}

export interface ApplicationSummary {
  id: string;
  status: ApplicationStatus;
  match_score: number | null;
  match_reasoning: string | null;
  ats_platform: string | null;
  needs_manual_review: boolean;
  manual_review_reason: string | null;
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
  job: Job | null;
}

export interface Communication {
  id: string;
  application_id: string | null;
  direction: "inbound" | "outbound";
  sender_email: string | null;
  sender_name: string | null;
  subject: string | null;
  detected_intent: string | null;
  intent_confidence: number | null;
  urgency: string | null;
  is_action_required: boolean;
  action_taken: boolean;
  received_at: string | null;
  snippet: string;
  body_text?: string | null;
  extracted_details?: Record<string, string | number> | null;
  suggested_reply?: string | null;
  gmail_thread_id?: string | null;
  gmail_draft_id?: string | null;
  application?: { id: string; company_name: string; role_title: string; status: ApplicationStatus } | null;
}

export interface Interview {
  id: string;
  application_id: string;
  company_name: string | null;
  role_title: string | null;
  interview_type: string | null;
  scheduled_at: string;
  duration_minutes: number;
  timezone: string;
  meeting_link: string | null;
  meeting_platform: string | null;
  physical_location: string | null;
  interviewer_names: string[];
  outcome: string | null;
  google_event_id: string | null;
  google_event_link: string | null;
  prep_notes?: string | null;
  company_research?: string | null;
  likely_questions?: { question: string; answer_outline: string }[];
  feedback?: string | null;
}

export interface ApplicationDetail extends ApplicationSummary {
  job: Job | null;
  match_details: Record<string, unknown> | null;
  similarity_score: number | null;
  cover_letter: string | null;
  custom_answers: CustomAnswer[];
  form_fields: FormFieldReport[];
  tailored_resume: Resume | null;
  tailored_resume_pdf_url: string | null;
  form_screenshot_url: string | null;
  confirmation_screenshot_url: string | null;
  confirmation_number: string | null;
  staged_at: string | null;
  approved_at: string | null;
  rejection_reason: string | null;
  offer_details: Record<string, unknown> | null;
  error_log: string | null;
  retry_count: number;
  notes: string | null;
  history: HistoryEntry[];
  communications: Communication[];
  interviews: Interview[];
}

export interface AgentRun {
  id: string;
  run_type: string;
  status: string;
  trigger: string | null;
  jobs_discovered: number;
  jobs_matched: number;
  applications_prepared: number;
  applications_submitted: number;
  errors_count: number;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  log?: { ts: string; level: string; message: string; data?: Record<string, unknown> }[];
}

export interface AgentStatus {
  has_master_resume: boolean;
  pending_approval: number;
  preparing: number;
  approved: number;
  applied_today: number;
  daily_limit: number;
  running_runs: AgentRun[];
  last_scan_at: string | null;
  next_scan_at: string | null;
  scan_enabled: boolean;
  google_connected: boolean;
  linkedin_connected: boolean;
}

export interface Overview {
  totals: Record<string, number>;
  by_status: Record<string, number>;
  rates: { response_rate: number; interview_rate: number; offer_rate: number; avg_days_to_response: number | null };
  timeline: { date: string; discovered: number; applied: number; responses: number }[];
  match_distribution: { range: string; count: number }[];
  platforms: { platform: string; discovered: number; applied: number; responses: number; interviews: number; response_rate: number; interview_rate: number }[];
  top_keywords: { keyword: string; applications: number; callbacks: number; callback_rate: number; lift: number }[];
  upcoming_interviews: { id: string; company: string; role: string; scheduled_at: string; type: string | null }[];
  recent_runs: { id: string; run_type: string; status: string; started_at: string; jobs_discovered: number; jobs_matched: number; errors_count: number }[];
}

export interface NotificationItem {
  id: string;
  event_type: string;
  title: string;
  body: string | null;
  link: string | null;
  data: Record<string, unknown>;
  is_read: boolean;
  created_at: string;
}

export interface Integrations {
  google: { configured: boolean; connected: boolean; email: string | null; gmail: boolean; calendar: boolean; last_polled_at: string | null; push_enabled: boolean };
  linkedin: { connected: boolean; session_valid: boolean; updated_at: string | null; profile_diff: { has_changes: boolean; changes: { section: string; change: string; linkedin_value: string }[]; summary: string } | null; synced_at: string | null };
  llm: { providers: string[]; model: string | null; embedding_provider: string };
  automation: { proxies: number; captcha: boolean; dry_run: boolean; auto_stage: boolean };
  notifications: { smtp: boolean; discord: boolean; slack: boolean };
  ats_credentials: string[];
}

export interface FieldMapping {
  field_name: string;
  field_value: string;
  field_type: string | null;
  is_secret: boolean;
}

export interface StandardField {
  label: string;
  type: string;
  options?: string[];
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size?: number;
  counts?: Record<string, number>;
}

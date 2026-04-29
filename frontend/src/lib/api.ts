export const API_BASE = "";

export type Dashboard = {
  volume_7d_hours: number;
  volume_28d_hours: number;
  activities_7d: number;
  activities_28d: number;
  discipline_hours_7d: Record<string, number>;
  latest_metrics: Record<string, { date: string; value: number | string; unit?: string; source: string }>;
  calendar_adherence: { planned: number; completed: number; missed: number };
  recovery_flags: string[];
};

export type MetricOption = { value: string; label: string; unit: string };

export type HealthMetric = {
  id: number;
  metric_date: string;
  metric_type: string;
  custom_name?: string;
  value_num?: number;
  value_text?: string;
  unit?: string;
  source: string;
  notes: string;
};

export type PlannedWorkout = {
  id?: number;
  planned_date: string;
  sport: string;
  sport_variant?: string;
  title: string;
  description: string;
  duration_minutes?: number;
  distance_meters?: number;
  intensity: string;
  surface?: string;
  location_suggestion?: string;
  gear_suggestion?: string;
  status?: string;
  source?: string;
};

export type Activity = {
  id: number;
  sport: string;
  sport_variant?: string;
  gear_id?: string;
  name: string;
  start_time: string;
  duration_seconds: number;
  distance_meters?: number;
  avg_hr?: number;
  avg_power?: number;
  source: string;
};

export type TrainingLocation = {
  id?: number;
  name: string;
  training_base: string;
  sport: string;
  sport_variant: string;
  surface?: string;
  distance_meters?: number;
  elevation_meters?: number;
  location_notes: string;
  safety_notes: string;
  link_url?: string;
  tags: string;
  active: boolean;
};

export type LocationFeedback = {
  id?: number;
  location_id: number;
  activity_id?: number;
  planned_workout_id?: number;
  feedback_date: string;
  intended_stimulus: string;
  rating: number;
  conditions: string;
  notes: string;
  use_again: boolean;
};

export type GearItem = {
  id?: number;
  strava_gear_id?: string;
  name: string;
  gear_type: string;
  distance_meters: number;
  retire_distance_meters?: number;
  active: boolean;
  preferred_sport_variants: string;
  preferred_surfaces: string;
  notes: string;
  source: string;
};

export type CoachResponse = {
  title: string;
  summary: string;
  recommendations: string[];
  risks: string[];
  proposed_workouts: PlannedWorkout[];
  used_ollama: boolean;
};

export type OllamaStatus = {
  running: boolean;
  base_url: string;
  configured_model: string;
  embedding_model: string;
  installed_models: string[];
  configured_model_installed: boolean;
  embedding_model_installed: boolean;
  can_start: boolean;
  message: string;
};

export type ModelRecommendation = {
  recommended: string;
  rationale: string;
  alternatives: { model: string; use_case: string }[];
};

export type GarminImportStatus = {
  import_dir: string;
  supported_extensions: string[];
  files_seen: number;
  imported_activities: number;
  imported_metrics: number;
  skipped_files: number;
  failed_files: number;
  message: string;
};

export type ContextExportResponse = {
  path: string;
  bytes_written: number;
  message: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}

export const api = {
  dashboard: () => request<Dashboard>("/api/dashboard"),
  metricOptions: () => request<MetricOption[]>("/api/metrics/options"),
  metrics: () => request<HealthMetric[]>("/api/metrics"),
  addMetric: (payload: Record<string, unknown>) =>
    request<HealthMetric>("/api/metrics", { method: "POST", body: JSON.stringify(payload) }),
  activities: () => request<Activity[]>("/api/activities"),
  locations: () => request<TrainingLocation[]>("/api/locations"),
  addLocation: (payload: TrainingLocation) =>
    request<TrainingLocation>("/api/locations", { method: "POST", body: JSON.stringify(payload) }),
  locationFeedback: () => request<LocationFeedback[]>("/api/locations/feedback"),
  addLocationFeedback: (payload: LocationFeedback) =>
    request<LocationFeedback>("/api/locations/feedback", { method: "POST", body: JSON.stringify(payload) }),
  gear: () => request<GearItem[]>("/api/gear"),
  addGear: (payload: GearItem) =>
    request<GearItem>("/api/gear", { method: "POST", body: JSON.stringify(payload) }),
  workouts: () => request<PlannedWorkout[]>("/api/calendar/workouts"),
  addWorkout: (payload: PlannedWorkout) =>
    request<PlannedWorkout>("/api/calendar/workouts", { method: "POST", body: JSON.stringify(payload) }),
  patchWorkout: (id: number, payload: Record<string, unknown>) =>
    request<PlannedWorkout>(`/api/calendar/workouts/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  coach: (payload: Record<string, unknown>) =>
    request<CoachResponse>("/api/coach", { method: "POST", body: JSON.stringify(payload) }),
  applyWorkouts: (payload: PlannedWorkout[]) =>
    request<{ applied: number }>("/api/coach/apply-workouts", { method: "POST", body: JSON.stringify(payload) }),
  ollamaStatus: () => request<OllamaStatus>("/api/ollama/status"),
  ensureOllama: () => request<OllamaStatus>("/api/ollama/ensure", { method: "POST" }),
  modelRecommendation: () => request<ModelRecommendation>("/api/ollama/recommendation"),
  scanGarminFiles: () =>
    request<GarminImportStatus>("/api/garmin-files/scan", { method: "POST" }),
  exportCoachContext: () =>
    request<ContextExportResponse>("/api/coach/context/export", { method: "POST" }),
  garminStatus: () => request<Record<string, unknown>>("/api/connectors/garmin/status"),
  stravaAuth: () => request<{ configured: boolean; url?: string }>("/api/connectors/strava/auth-url"),
  stravaSync: () => request<{ imported: number }>("/api/connectors/strava/sync", { method: "POST" }),
  stravaSyncGear: () => request<{ synced: number }>("/api/connectors/strava/sync-gear", { method: "POST" })
};

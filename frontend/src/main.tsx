import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ActivityIcon,
  Brain,
  CalendarDays,
  Check,
  Gauge,
  HeartPulse,
  MapPin,
  RefreshCw,
  Send,
  Settings,
  Upload
} from "lucide-react";
import {
  Activity,
  api,
  CoachResponse,
  Dashboard,
  GearItem,
  HealthMetric,
  LocationFeedback,
  MetricOption,
  PlannedWorkout,
  TrainingLocation
} from "./lib/api";
import "./styles/app.css";

const sports = ["swim", "bike", "run", "strength", "climb", "mobility", "rest", "other"];
const sportVariants = ["road_run", "trail_run", "road_ride", "gravel_ride", "mtb_ride", "tt_ride", "pool_swim", "open_water_swim", "strength", "climb", "mobility", "rest", "other"];
const intensities = ["recovery", "easy", "moderate", "tempo", "threshold", "vo2", "race"];

function App() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [metrics, setMetrics] = useState<HealthMetric[]>([]);
  const [metricOptions, setMetricOptions] = useState<MetricOption[]>([]);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [workouts, setWorkouts] = useState<PlannedWorkout[]>([]);
  const [locations, setLocations] = useState<TrainingLocation[]>([]);
  const [locationFeedback, setLocationFeedback] = useState<LocationFeedback[]>([]);
  const [gear, setGear] = useState<GearItem[]>([]);
  const [coach, setCoach] = useState<CoachResponse | null>(null);
  const [coachText, setCoachText] = useState("Review my current training state and propose the next week.");
  const [aggressiveness, setAggressiveness] = useState(0.45);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  async function refresh() {
    const [dash, metricOpts, metricRows, activityRows, workoutRows, locationRows, feedbackRows, gearRows] = await Promise.all([
      api.dashboard(),
      api.metricOptions(),
      api.metrics(),
      api.activities(),
      api.workouts(),
      api.locations(),
      api.locationFeedback(),
      api.gear()
    ]);
    setDashboard(dash);
    setMetricOptions(metricOpts);
    setMetrics(metricRows);
    setActivities(activityRows);
    setWorkouts(workoutRows);
    setLocations(locationRows);
    setLocationFeedback(feedbackRows);
    setGear(gearRows);
  }

  useEffect(() => {
    refresh().catch((error) => setMessage(error.message));
  }, []);

  async function askCoach() {
    setLoading(true);
    setMessage("");
    try {
      const result = await api.coach({
        message: coachText,
        aggressiveness,
        autonomy: "suggest_then_approve"
      });
      setCoach(result);
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Coach request failed");
    } finally {
      setLoading(false);
    }
  }

  async function applyCoachPlan() {
    if (!coach?.proposed_workouts.length) return;
    await api.applyWorkouts(coach.proposed_workouts);
    setCoach(null);
    await refresh();
  }

  const focusMetricCards = useMemo(() => {
    const keys = ["training_readiness", "sleep_score", "hrv_ms", "resting_hr", "vo2_max", "ftp", "endurance_score", "body_battery"];
    return keys.map((key) => [key, dashboard?.latest_metrics[key]] as const).filter(([, value]) => Boolean(value));
  }, [dashboard]);

  return (
    <main>
      <header className="topbar">
        <div>
          <h1>AI Coach</h1>
          <p>Local-first triathlon planning, recovery intelligence, and adaptive coaching.</p>
        </div>
        <button className="iconButton" onClick={() => refresh()}>
          <RefreshCw size={18} />
          Refresh
        </button>
      </header>

      {message && <div className="notice">{message}</div>}

      <section className="grid metricsGrid">
        <StatCard icon={<Gauge />} label="7d Volume" value={`${dashboard?.volume_7d_hours ?? 0}h`} />
        <StatCard icon={<ActivityIcon />} label="28d Volume" value={`${dashboard?.volume_28d_hours ?? 0}h`} />
        <StatCard icon={<CalendarDays />} label="Planned" value={`${dashboard?.calendar_adherence.planned ?? 0}`} />
        <StatCard icon={<HeartPulse />} label="Recovery Flags" value={`${dashboard?.recovery_flags.length ?? 0}`} />
      </section>

      <section className="layout">
        <div className="stack">
          <Panel title="Training Dashboard" icon={<ActivityIcon />}>
            <div className="split">
              <div>
                <h3>Discipline Split</h3>
                <div className="barList">
                  {Object.entries(dashboard?.discipline_hours_7d ?? {}).map(([sport, hours]) => (
                    <div key={sport} className="barRow">
                      <span>{sport}</span>
                      <div><span style={{ width: `${Math.min(100, hours * 18)}%` }} /></div>
                      <strong>{hours}h</strong>
                    </div>
                  ))}
                  {!Object.keys(dashboard?.discipline_hours_7d ?? {}).length && <p className="muted">No recent activities yet.</p>}
                </div>
              </div>
              <div>
                <h3>Key Health Metrics</h3>
                <div className="miniGrid">
                  {focusMetricCards.map(([key, value]) => (
                    <div className="miniCard" key={key}>
                      <span>{labelize(key)}</span>
                      <strong>{String(value?.value)} {value?.unit ?? ""}</strong>
                      <small>{value?.date} · {value?.source}</small>
                    </div>
                  ))}
                  {!focusMetricCards.length && <p className="muted">Manual Garmin-style metrics will appear here.</p>}
                </div>
              </div>
            </div>
            {!!dashboard?.recovery_flags.length && (
              <div className="warningList">
                {dashboard.recovery_flags.map((flag) => <p key={flag}>{flag}</p>)}
              </div>
            )}
          </Panel>

          <CoachPanel
            coachText={coachText}
            setCoachText={setCoachText}
            aggressiveness={aggressiveness}
            setAggressiveness={setAggressiveness}
            loading={loading}
            askCoach={askCoach}
            coach={coach}
            applyCoachPlan={applyCoachPlan}
          />

          <CalendarPanel workouts={workouts} refresh={refresh} />
          <PlacesPanel locations={locations} feedback={locationFeedback} activities={activities} workouts={workouts} refresh={refresh} />
        </div>

        <aside className="stack">
          <ManualMetricPanel options={metricOptions} refresh={refresh} />
          <GearPanel gear={gear} refresh={refresh} />
          <LocalFilesPanel refresh={refresh} />
          <OllamaPanel />
          <ConnectorPanel />
          <ActivityPanel activities={activities} />
          <RecentMetrics metrics={metrics} />
        </aside>
      </section>
    </main>
  );
}

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="statCard">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Panel({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="panel">
      <div className="panelTitle">{icon}<h2>{title}</h2></div>
      {children}
    </section>
  );
}

function ManualMetricPanel({ options, refresh }: { options: MetricOption[]; refresh: () => Promise<void> }) {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [values, setValues] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);

  const visibleOptions = options.filter((option) => option.value !== "custom");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    try {
      const entries = visibleOptions
        .map((option) => ({ option, raw: values[option.value]?.trim() ?? "" }))
        .filter((entry) => entry.raw !== "");

      await Promise.all(entries.map(({ option, raw }) => {
        const numeric = Number(raw);
        const isNumeric = Number.isFinite(numeric) && raw !== "";
        return api.addMetric({
          metric_date: date,
          metric_type: option.value,
          value_num: isNumeric ? numeric : null,
          value_text: isNumeric ? null : raw,
          unit: option.unit,
          source: "manual",
          notes
        });
      }));

      setValues({});
      setNotes("");
      await refresh();
    } finally {
      setSaving(false);
    }
  }

  return (
    <Panel title="Manual Metrics" icon={<HeartPulse />}>
      <form className="form batchMetrics" onSubmit={submit}>
        <label>Date<input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
        <div className="metricEntryGrid">
          {visibleOptions.map((option) => (
            <label key={option.value}>
              <span>{option.label}</span>
              <input
                value={values[option.value] ?? ""}
                onChange={(e) => setValues((current) => ({ ...current, [option.value]: e.target.value }))}
                placeholder={option.unit}
              />
            </label>
          ))}
        </div>
        <label>Notes<textarea value={notes} onChange={(e) => setNotes(e.target.value)} /></label>
        <button className="primary" disabled={saving}>
          <Check size={16} /> {saving ? "Saving..." : "Save Filled Metrics"}
        </button>
      </form>
    </Panel>
  );
}

function CoachPanel(props: {
  coachText: string;
  setCoachText: (value: string) => void;
  aggressiveness: number;
  setAggressiveness: (value: number) => void;
  loading: boolean;
  askCoach: () => Promise<void>;
  coach: CoachResponse | null;
  applyCoachPlan: () => Promise<void>;
}) {
  return (
    <Panel title="Coach" icon={<Brain />}>
      <div className="coachControls">
        <textarea value={props.coachText} onChange={(e) => props.setCoachText(e.target.value)} />
        <label>
          Aggressiveness: {Math.round(props.aggressiveness * 100)}%
          <input type="range" min="0" max="1" step="0.05" value={props.aggressiveness} onChange={(e) => props.setAggressiveness(Number(e.target.value))} />
        </label>
        <button className="primary" onClick={props.askCoach} disabled={props.loading}>
          <Send size={16} /> {props.loading ? "Thinking..." : "Ask Coach"}
        </button>
      </div>
      {props.coach && (
        <div className="coachResult">
          <h3>{props.coach.title}</h3>
          <p>{props.coach.summary}</p>
          <div className="columns">
            <List title="Recommendations" items={props.coach.recommendations} />
            <List title="Risks" items={props.coach.risks} />
          </div>
          {!!props.coach.proposed_workouts.length && (
            <>
              <h3>Proposed Workouts</h3>
              <div className="workoutList">
                {props.coach.proposed_workouts.map((workout, index) => (
                  <div className="workout" key={`${workout.planned_date}-${index}`}>
                    <strong>{workout.planned_date} · {workout.sport_variant ?? workout.sport}</strong>
                    <span>{workout.title} · {workout.duration_minutes} min · {workout.intensity}</span>
                    {(workout.location_suggestion || workout.gear_suggestion) && (
                      <small>{workout.location_suggestion ?? "No location"} · {workout.gear_suggestion ?? "No gear"}</small>
                    )}
                    <p>{workout.description}</p>
                  </div>
                ))}
              </div>
              <button className="primary" onClick={props.applyCoachPlan}><Check size={16} /> Approve Plan</button>
            </>
          )}
          <small>{props.coach.used_ollama ? "Generated by local Ollama." : "Rule-based fallback because Ollama was unavailable."}</small>
        </div>
      )}
    </Panel>
  );
}

function CalendarPanel({ workouts, refresh }: { workouts: PlannedWorkout[]; refresh: () => Promise<void> }) {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [sport, setSport] = useState("bike");
  const [sportVariant, setSportVariant] = useState("road_ride");
  const [title, setTitle] = useState("");
  const [duration, setDuration] = useState(60);
  const [intensity, setIntensity] = useState("easy");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    await api.addWorkout({ planned_date: date, sport, sport_variant: sportVariant, title, description: "", duration_minutes: duration, intensity, status: "planned", source: "manual" });
    setTitle("");
    await refresh();
  }

  async function mark(id: number | undefined, status: string) {
    if (!id) return;
    await api.patchWorkout(id, { status });
    await refresh();
  }

  return (
    <Panel title="Calendar" icon={<CalendarDays />}>
      <form className="inlineForm" onSubmit={submit}>
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        <select value={sport} onChange={(e) => setSport(e.target.value)}>{sports.map((item) => <option key={item}>{item}</option>)}</select>
        <select value={sportVariant} onChange={(e) => setSportVariant(e.target.value)}>{sportVariants.map((item) => <option key={item}>{item}</option>)}</select>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Workout title" />
        <input type="number" value={duration} onChange={(e) => setDuration(Number(e.target.value))} />
        <select value={intensity} onChange={(e) => setIntensity(e.target.value)}>{intensities.map((item) => <option key={item}>{item}</option>)}</select>
        <button className="primary">Add</button>
      </form>
      <div className="calendarList">
        {workouts.map((workout) => (
          <div className={`calendarItem ${workout.status}`} key={workout.id}>
            <div>
              <strong>{workout.planned_date} · {workout.sport_variant ?? workout.sport}</strong>
              <span>{workout.title} · {workout.duration_minutes ?? "?"} min · {workout.intensity}</span>
              {(workout.location_suggestion || workout.gear_suggestion) && (
                <small>{workout.location_suggestion ?? "No location"} · {workout.gear_suggestion ?? "No gear"}</small>
              )}
            </div>
            <div className="buttonRow">
              <button onClick={() => mark(workout.id, "completed")}>Done</button>
              <button onClick={() => mark(workout.id, "missed")}>Missed</button>
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function PlacesPanel({
  locations,
  feedback,
  activities,
  workouts,
  refresh
}: {
  locations: TrainingLocation[];
  feedback: LocationFeedback[];
  activities: Activity[];
  workouts: PlannedWorkout[];
  refresh: () => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [sport, setSport] = useState("run");
  const [sportVariant, setSportVariant] = useState("road_run");
  const [surface, setSurface] = useState("");
  const [tags, setTags] = useState("");
  const [notes, setNotes] = useState("");
  const [feedbackLocationId, setFeedbackLocationId] = useState("");
  const [feedbackDate, setFeedbackDate] = useState(new Date().toISOString().slice(0, 10));
  const [intendedStimulus, setIntendedStimulus] = useState("aerobic endurance");
  const [rating, setRating] = useState(4);
  const [feedbackNotes, setFeedbackNotes] = useState("");
  const [plannedWorkoutId, setPlannedWorkoutId] = useState("");
  const [activityId, setActivityId] = useState("");

  async function addLocation(event: React.FormEvent) {
    event.preventDefault();
    await api.addLocation({
      name,
      training_base: "Newport Beach",
      sport,
      sport_variant: sportVariant,
      surface,
      distance_meters: undefined,
      elevation_meters: undefined,
      location_notes: notes,
      safety_notes: "",
      link_url: undefined,
      tags,
      active: true
    });
    setName("");
    setSurface("");
    setTags("");
    setNotes("");
    await refresh();
  }

  async function addFeedback(event: React.FormEvent) {
    event.preventDefault();
    if (!feedbackLocationId) return;
    await api.addLocationFeedback({
      location_id: Number(feedbackLocationId),
      activity_id: activityId ? Number(activityId) : undefined,
      planned_workout_id: plannedWorkoutId ? Number(plannedWorkoutId) : undefined,
      feedback_date: feedbackDate,
      intended_stimulus: intendedStimulus,
      rating,
      conditions: "",
      notes: feedbackNotes,
      use_again: rating >= 3
    });
    setFeedbackNotes("");
    await refresh();
  }

  return (
    <Panel title="Places + Feedback" icon={<MapPin />}>
      <div className="columns">
        <form className="form" onSubmit={addLocation}>
          <h3>Add Place</h3>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Back Bay loop, pool, trail..." />
          <select value={sport} onChange={(e) => setSport(e.target.value)}>{sports.map((item) => <option key={item}>{item}</option>)}</select>
          <select value={sportVariant} onChange={(e) => setSportVariant(e.target.value)}>{sportVariants.map((item) => <option key={item}>{item}</option>)}</select>
          <input value={surface} onChange={(e) => setSurface(e.target.value)} placeholder="road, trail, gravel, pool" />
          <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="easy, tempo, hills, safe, traffic" />
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Notes for the coach" />
          <button className="primary"><Check size={16} /> Save Place</button>
        </form>
        <form className="form" onSubmit={addFeedback}>
          <h3>Workout Feedback</h3>
          <select value={feedbackLocationId} onChange={(e) => setFeedbackLocationId(e.target.value)}>
            <option value="">Select place</option>
            {locations.map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}
          </select>
          <input type="date" value={feedbackDate} onChange={(e) => setFeedbackDate(e.target.value)} />
          <input value={intendedStimulus} onChange={(e) => setIntendedStimulus(e.target.value)} placeholder="Intended stimulus" />
          <label>Fit Rating: {rating}<input type="range" min="1" max="5" value={rating} onChange={(e) => setRating(Number(e.target.value))} /></label>
          <select value={plannedWorkoutId} onChange={(e) => setPlannedWorkoutId(e.target.value)}>
            <option value="">Optional planned workout</option>
            {workouts.slice(0, 20).map((workout) => <option key={workout.id} value={workout.id}>{workout.planned_date} · {workout.title}</option>)}
          </select>
          <select value={activityId} onChange={(e) => setActivityId(e.target.value)}>
            <option value="">Optional activity</option>
            {activities.slice(0, 20).map((activity) => <option key={activity.id} value={activity.id}>{new Date(activity.start_time).toLocaleDateString()} · {activity.name}</option>)}
          </select>
          <textarea value={feedbackNotes} onChange={(e) => setFeedbackNotes(e.target.value)} placeholder="How well did this place match the workout?" />
          <button className="primary"><Check size={16} /> Save Feedback</button>
        </form>
      </div>
      <div className="compactList placesList">
        {locations.slice(0, 8).map((location) => {
          const ratings = feedback.filter((item) => item.location_id === location.id).map((item) => item.rating);
          const avg = ratings.length ? (ratings.reduce((a, b) => a + b, 0) / ratings.length).toFixed(1) : "new";
          return (
            <div key={location.id}>
              <strong>{location.name} · {location.sport_variant}</strong>
              <span>{location.surface || "surface n/a"} · rating {avg} · {location.tags}</span>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

function GearPanel({ gear, refresh }: { gear: GearItem[]; refresh: () => Promise<void> }) {
  const [name, setName] = useState("");
  const [gearType, setGearType] = useState("shoes");
  const [distanceMiles, setDistanceMiles] = useState("");
  const [retireMiles, setRetireMiles] = useState("");
  const [variants, setVariants] = useState("");
  const [surfaces, setSurfaces] = useState("");
  const [notes, setNotes] = useState("");

  async function addGear(event: React.FormEvent) {
    event.preventDefault();
    await api.addGear({
      name,
      gear_type: gearType,
      distance_meters: Number(distanceMiles || 0) * 1609.344,
      retire_distance_meters: retireMiles ? Number(retireMiles) * 1609.344 : undefined,
      active: true,
      preferred_sport_variants: variants,
      preferred_surfaces: surfaces,
      notes,
      source: "manual"
    });
    setName("");
    setDistanceMiles("");
    setRetireMiles("");
    setVariants("");
    setSurfaces("");
    setNotes("");
    await refresh();
  }

  return (
    <Panel title="Gear" icon={<Settings />}>
      <form className="form" onSubmit={addGear}>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Shoe or bike name" />
        <select value={gearType} onChange={(e) => setGearType(e.target.value)}>
          <option value="shoes">shoes</option>
          <option value="bike">bike</option>
          <option value="other">other</option>
        </select>
        <input value={distanceMiles} onChange={(e) => setDistanceMiles(e.target.value)} placeholder="Current miles" />
        <input value={retireMiles} onChange={(e) => setRetireMiles(e.target.value)} placeholder="Retire miles" />
        <input value={variants} onChange={(e) => setVariants(e.target.value)} placeholder="Preferred variants: road_run, trail_run" />
        <input value={surfaces} onChange={(e) => setSurfaces(e.target.value)} placeholder="Preferred surfaces: road, trail, gravel" />
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Fit, purpose, rotation notes" />
        <button className="primary"><Check size={16} /> Save Gear</button>
      </form>
      <div className="compactList">
        {gear.slice(0, 10).map((item) => (
          <div key={item.id}>
            <strong>{item.name} · {item.gear_type}</strong>
            <span>{(item.distance_meters / 1609.344).toFixed(1)} mi · {item.source} · {item.preferred_sport_variants || "no rules"}</span>
          </div>
        ))}
        {!gear.length && <p className="muted">Sync Strava gear or add shoes and bikes manually.</p>}
      </div>
    </Panel>
  );
}

function ConnectorPanel() {
  const [garmin, setGarmin] = useState<Record<string, unknown> | null>(null);
  const [strava, setStrava] = useState<{ configured: boolean; url?: string } | null>(null);
  const [status, setStatus] = useState("");

  useEffect(() => {
    Promise.all([api.garminStatus(), api.stravaAuth()]).then(([g, s]) => {
      setGarmin(g);
      setStrava(s);
    });
  }, []);

  async function sync() {
    try {
      const result = await api.stravaSync();
      setStatus(`Imported ${result.imported} activities.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Sync failed");
    }
  }

  async function syncGear() {
    try {
      const result = await api.stravaSyncGear();
      setStatus(`Synced ${result.synced} gear items.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Gear sync failed");
    }
  }

  return (
    <Panel title="Connectors" icon={<Settings />}>
      <div className="connector">
        <strong>Strava</strong>
        <span>{strava?.configured ? "Configured" : "Add client id/secret in .env"}</span>
        {strava?.url && <a href={strava.url}>Connect Strava</a>}
        <div className="buttonRow">
          <button onClick={sync}>Sync Activities</button>
          <button onClick={syncGear}>Sync Gear</button>
        </div>
      </div>
      <div className="connector">
        <strong>Garmin</strong>
        <span>{String(garmin?.message ?? "Loading...")}</span>
      </div>
      {status && <p className="muted">{status}</p>}
      <div className="connector">
        <Upload size={18} />
        <span>CSV/FIT/TCX/GPX import boundary is backend-ready; CSV endpoint is active.</span>
      </div>
    </Panel>
  );
}

function LocalFilesPanel({ refresh }: { refresh: () => Promise<void> }) {
  const [scanStatus, setScanStatus] = useState<import("./lib/api").GarminImportStatus | null>(null);
  const [exportStatus, setExportStatus] = useState<import("./lib/api").ContextExportResponse | null>(null);
  const [busy, setBusy] = useState(false);

  async function scan() {
    setBusy(true);
    try {
      setScanStatus(await api.scanGarminFiles());
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function exportContext() {
    setBusy(true);
    try {
      setExportStatus(await api.exportCoachContext());
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Local Files" icon={<Upload />}>
      <div className="connector">
        <strong>Garmin import directory</strong>
        <span>{scanStatus?.import_dir ?? "./garmin_files"}</span>
        <small>Drop Garmin CSV, TCX, GPX, or FIT files here. The app scans this folder on startup.</small>
      </div>
      <div className="buttonRow">
        <button className="primary" onClick={scan} disabled={busy}>
          <Upload size={16} /> Scan Garmin Files
        </button>
        <button onClick={exportContext} disabled={busy}>
          <Brain size={16} /> Export Context
        </button>
      </div>
      {scanStatus && (
        <div className="compactStatus">
          <span>{scanStatus.files_seen} files seen</span>
          <span>{scanStatus.imported_activities} activities imported</span>
          <span>{scanStatus.imported_metrics} metrics imported</span>
          <span>{scanStatus.skipped_files} skipped · {scanStatus.failed_files} failed</span>
        </div>
      )}
      {exportStatus && (
        <div className="compactStatus">
          <span>{exportStatus.message}</span>
          <span>{exportStatus.path}</span>
          <span>{exportStatus.bytes_written} bytes</span>
        </div>
      )}
    </Panel>
  );
}

function OllamaPanel() {
  const [status, setStatus] = useState<import("./lib/api").OllamaStatus | null>(null);
  const [recommendation, setRecommendation] = useState<import("./lib/api").ModelRecommendation | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    const [ollamaStatus, rec] = await Promise.all([api.ollamaStatus(), api.modelRecommendation()]);
    setStatus(ollamaStatus);
    setRecommendation(rec);
  }

  async function ensure() {
    setBusy(true);
    try {
      setStatus(await api.ensureOllama());
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, []);

  return (
    <Panel title="Ollama" icon={<Brain />}>
      <div className={`ollamaStatus ${status?.running ? "online" : "offline"}`}>
        <strong>{status?.running ? "Running" : "Not Running"}</strong>
        <span>{status?.message ?? "Checking Ollama..."}</span>
      </div>
      <div className="connector">
        <strong>Configured model</strong>
        <span>{status?.configured_model ?? "gpt-oss:20b"}</span>
        <small>{status?.configured_model_installed ? "Installed" : "Run the pull command below if missing."}</small>
      </div>
      <code className="command">ollama pull {status?.configured_model ?? "gpt-oss:20b"}</code>
      <code className="command">ollama pull {status?.embedding_model ?? "embeddinggemma"}</code>
      <button className="primary" onClick={ensure} disabled={busy || status?.running === true}>
        <RefreshCw size={16} /> {busy ? "Starting..." : "Start Ollama"}
      </button>
      {recommendation && (
        <div className="recommendation">
          <strong>Recommended: {recommendation.recommended}</strong>
          <p>{recommendation.rationale}</p>
          {recommendation.alternatives.map((item) => (
            <small key={item.model}>{item.model}: {item.use_case}</small>
          ))}
        </div>
      )}
    </Panel>
  );
}

function ActivityPanel({ activities }: { activities: Activity[] }) {
  return (
    <Panel title="Recent Activities" icon={<ActivityIcon />}>
      <div className="compactList">
        {activities.slice(0, 8).map((activity) => (
          <div key={activity.id}>
            <strong>{activity.sport} · {activity.name}</strong>
            <span>{new Date(activity.start_time).toLocaleDateString()} · {Math.round(activity.duration_seconds / 60)} min · {activity.source}</span>
          </div>
        ))}
        {!activities.length && <p className="muted">No activities synced or imported yet.</p>}
      </div>
    </Panel>
  );
}

function RecentMetrics({ metrics }: { metrics: HealthMetric[] }) {
  return (
    <Panel title="Metric Log" icon={<HeartPulse />}>
      <div className="compactList">
        {metrics.slice(0, 10).map((metric) => (
          <div key={metric.id}>
            <strong>{labelize(metric.custom_name || metric.metric_type)}</strong>
            <span>{metric.metric_date} · {metric.value_num ?? metric.value_text} {metric.unit ?? ""}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function List({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <h3>{title}</h3>
      <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>
  );
}

function labelize(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

createRoot(document.getElementById("root")!).render(<App />);

-- GenshinGuideAI v1 核心表结构（SQLite）
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
  id             TEXT PRIMARY KEY,
  name           TEXT NOT NULL,
  created_at     TEXT NOT NULL,
  description    TEXT DEFAULT '',
  schema_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
  id          TEXT PRIMARY KEY,
  project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  path        TEXT NOT NULL,
  sha256      TEXT,
  duration_s  REAL NOT NULL,
  fps         REAL,
  width       INTEGER,
  height      INTEGER,
  captured_at TEXT,
  notes       TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS segments (
  id         TEXT PRIMARY KEY,
  source_id  TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  start_s    REAL NOT NULL,
  end_s      REAL NOT NULL,
  kind       TEXT NOT NULL,
  confidence REAL,
  notes      TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS events (
  id                TEXT PRIMARY KEY,
  project_id        TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  source_id         TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  segment_id        TEXT REFERENCES segments(id) ON DELETE SET NULL,
  seq               INTEGER NOT NULL,
  video_start_s     REAL NOT NULL,
  video_end_s       REAL NOT NULL,
  video_precision   TEXT,
  game_start_s      REAL,
  game_end_s        REAL,
  actor_kind        TEXT,
  actor_name        TEXT,
  action_type       TEXT NOT NULL,
  action_params     TEXT,            -- JSON
  action_method     TEXT,
  map_x             REAL,
  map_y             REAL,
  map_layer         TEXT,
  map_region        TEXT,
  map_anchor        TEXT,
  map_error_m       REAL,
  map_method        TEXT,
  map_confidence    REAL,
  world_x           REAL,
  world_y           REAL,
  world_z           REAL,
  world_error_m     REAL,
  world_method      TEXT,
  world_confidence  REAL,
  state_status      TEXT NOT NULL,
  confidence        REAL NOT NULL,
  notes             TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS evidence (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  kind     TEXT NOT NULL,
  t_s      REAL,
  path     TEXT,
  bbox     TEXT,                     -- JSON [x,y,w,h]
  text     TEXT,
  note     TEXT
);

CREATE TABLE IF NOT EXISTS reviews (
  event_id   TEXT PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
  status     TEXT NOT NULL,
  reviewed_by TEXT,
  reviewed_at TEXT,
  diff       TEXT                    -- JSON
);

CREATE INDEX IF NOT EXISTS idx_events_seq       ON events(project_id, seq);
CREATE INDEX IF NOT EXISTS idx_events_source    ON events(source_id);
CREATE INDEX IF NOT EXISTS idx_events_action    ON events(action_type);
CREATE INDEX IF NOT EXISTS idx_evidence_event   ON evidence(event_id);
CREATE INDEX IF NOT EXISTS idx_segments_source  ON segments(source_id);

-- 方向二/三预留（本期只建表，不写入）
CREATE TABLE IF NOT EXISTS sim_runs (
  id         TEXT PRIMARY KEY,
  project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  params     TEXT,   -- JSON
  rules_ver  TEXT,
  seed       INTEGER,
  status     TEXT,
  result     TEXT    -- JSON
);

CREATE TABLE IF NOT EXISTS exec_runs (
  id         TEXT PRIMARY KEY,
  sim_run_id TEXT REFERENCES sim_runs(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  env        TEXT,
  status     TEXT,
  report     TEXT    -- JSON
);

-- Canonical payload is the lossless source of truth; tables above are query projections.
-- Update through import_project so the payload and projections commit together.
CREATE TABLE IF NOT EXISTS project_payloads (
  project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
  payload TEXT NOT NULL
);

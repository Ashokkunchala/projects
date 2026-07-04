-- Cloudflare D1 Database Schema for AI Cloud Cost Detective

-- Analyses table
CREATE TABLE IF NOT EXISTS analyses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  content_hash TEXT NOT NULL,
  file_type TEXT NOT NULL,
  result TEXT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  expires_at DATETIME
);

CREATE INDEX IF NOT EXISTS idx_analyses_hash ON analyses(content_hash);
CREATE INDEX IF NOT EXISTS idx_analyses_created ON analyses(created_at);

-- Users table (for multi-tenant support)
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  api_key TEXT UNIQUE,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  last_active DATETIME
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_api_key ON users(api_key);

-- Scan history
CREATE TABLE IF NOT EXISTS scan_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  provider TEXT NOT NULL,
  regions TEXT, -- JSON array
  services TEXT, -- JSON array
  resources_found INTEGER DEFAULT 0,
  issues_found INTEGER DEFAULT 0,
  estimated_savings REAL DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_scan_history_user ON scan_history(user_id);
CREATE INDEX IF NOT EXISTS idx_scan_history_provider ON scan_history(provider);

-- Free tier usage tracking
CREATE TABLE IF NOT EXISTS free_tier_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  provider TEXT NOT NULL,
  service TEXT NOT NULL,
  usage_amount REAL DEFAULT 0,
  limit_amount REAL DEFAULT 0,
  unit TEXT,
  recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_free_tier_user ON free_tier_usage(user_id);
CREATE INDEX IF NOT EXISTS idx_free_tier_service ON free_tier_usage(service);

-- Infrastructure diagrams
CREATE TABLE IF NOT EXISTS infra_diagrams (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  name TEXT NOT NULL,
  source_type TEXT NOT NULL, -- terraform, cloudformation, kubernetes
  source_content TEXT NOT NULL,
  diagram_data TEXT, -- JSON with nodes, edges, etc.
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_infra_diagrams_user ON infra_diagrams(user_id);

-- Cost estimates
CREATE TABLE IF NOT EXISTS cost_estimates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  diagram_id INTEGER,
  monthly_total REAL DEFAULT 0,
  breakdown TEXT, -- JSON with service costs
  optimization_potential REAL DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (diagram_id) REFERENCES infra_diagrams(id)
);

-- AI agent cache
CREATE TABLE IF NOT EXISTS agent_cache (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cache_key TEXT UNIQUE NOT NULL,
  result TEXT NOT NULL,
  expires_at DATETIME NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_cache_key ON agent_cache(cache_key);
CREATE INDEX IF NOT EXISTS idx_agent_cache_expires ON agent_cache(expires_at);

-- Chat conversations (NEW)
CREATE TABLE IF NOT EXISTS conversations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  backend_user_id INTEGER NOT NULL DEFAULT 0,
  title TEXT DEFAULT 'New conversation',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(backend_user_id);
CREATE INDEX IF NOT EXISTS idx_conv_updated ON conversations(updated_at);

-- Chat messages (NEW)
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id INTEGER NOT NULL,
  role TEXT NOT NULL, -- 'user' | 'assistant' | 'system'
  content TEXT NOT NULL,
  model_used TEXT,
  tokens_used INTEGER DEFAULT 0,
  metadata TEXT, -- JSON: page, analysis_id, etc.
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_msg_created ON messages(created_at);

-- Cleanup old cache entries (run periodically):
-- DELETE FROM agent_cache WHERE expires_at < datetime('now');
-- DELETE FROM analyses WHERE expires_at < datetime('now');

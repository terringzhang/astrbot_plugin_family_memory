PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;
PRAGMA secure_delete=ON;
PRAGMA busy_timeout=25;
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
INSERT OR IGNORE INTO meta VALUES('schema_version','1');
INSERT OR IGNORE INTO meta VALUES('revision','0');
CREATE TABLE IF NOT EXISTS namespaces(
 agent TEXT NOT NULL, ns TEXT NOT NULL, kind TEXT NOT NULL, owner TEXT NOT NULL,
 PRIMARY KEY(agent,ns));
CREATE TABLE IF NOT EXISTS sources(
 id TEXT PRIMARY KEY, agent TEXT NOT NULL, ns TEXT NOT NULL, actor TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('user','assistant')), event_key TEXT NOT NULL,
 event_time REAL, text TEXT NOT NULL, share_consent INTEGER NOT NULL DEFAULT 0,
 transport_ref TEXT NOT NULL,
 created REAL NOT NULL, UNIQUE(agent,ns,event_key,role),
 FOREIGN KEY(agent,ns) REFERENCES namespaces(agent,ns));
CREATE INDEX IF NOT EXISTS source_scope ON sources(agent,ns,created);
CREATE TABLE IF NOT EXISTS memories(
 id TEXT PRIMARY KEY, agent TEXT NOT NULL, ns TEXT NOT NULL, path TEXT UNIQUE NOT NULL,
 version INTEGER NOT NULL, title TEXT NOT NULL, text TEXT NOT NULL, digest TEXT NOT NULL, doc_hash TEXT NOT NULL,
 status TEXT NOT NULL, kind TEXT NOT NULL, importance REAL NOT NULL, confidence REAL NOT NULL,
 created REAL NOT NULL, event_time REAL, expires REAL, fact_key TEXT, fact_value TEXT,
 FOREIGN KEY(agent,ns) REFERENCES namespaces(agent,ns));
CREATE INDEX IF NOT EXISTS memory_scope ON memories(agent,ns,status,expires);
CREATE INDEX IF NOT EXISTS memory_fact ON memories(agent,ns,fact_key,status);
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(id UNINDEXED,tokens);
CREATE TABLE IF NOT EXISTS tags(
 memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
 tag TEXT NOT NULL, PRIMARY KEY(memory_id,tag));
CREATE INDEX IF NOT EXISTS tag_lookup ON tags(tag,memory_id);
CREATE TABLE IF NOT EXISTS memory_sources(
 memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
 source_id TEXT NOT NULL REFERENCES sources(id), quote TEXT NOT NULL,
 PRIMARY KEY(memory_id,source_id));
CREATE INDEX IF NOT EXISTS source_reference_lookup ON memory_sources(source_id);
CREATE TABLE IF NOT EXISTS entities(
 id TEXT PRIMARY KEY, agent TEXT NOT NULL, ns TEXT NOT NULL, type TEXT NOT NULL,
 name TEXT NOT NULL, external_key TEXT, confidence REAL NOT NULL, source_memory TEXT,
 UNIQUE(agent,ns,external_key));
CREATE INDEX IF NOT EXISTS entity_scope ON entities(agent,ns,type);
CREATE TABLE IF NOT EXISTS aliases(
 entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
 alias TEXT NOT NULL, source_memory TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
 PRIMARY KEY(entity_id,alias,source_memory));
CREATE INDEX IF NOT EXISTS alias_lookup ON aliases(alias,entity_id);
CREATE TABLE IF NOT EXISTS memory_entities(
 memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
 entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
 PRIMARY KEY(memory_id,entity_id));
CREATE TABLE IF NOT EXISTS edges(
 id TEXT PRIMARY KEY, agent TEXT NOT NULL, ns TEXT NOT NULL,
 src TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
 dst TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
 relation TEXT NOT NULL, confidence REAL NOT NULL,
 source_memory TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE);
CREATE INDEX IF NOT EXISTS edge_out ON edges(agent,ns,src);
CREATE INDEX IF NOT EXISTS edge_in ON edges(agent,ns,dst);
CREATE TABLE IF NOT EXISTS audit(
 id INTEGER PRIMARY KEY, memory_id TEXT NOT NULL, version INTEGER NOT NULL,
 action TEXT NOT NULL, actor TEXT NOT NULL, digest TEXT NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS tombstones(
 agent TEXT NOT NULL, ns TEXT NOT NULL, digest TEXT NOT NULL, at REAL NOT NULL,
 PRIMARY KEY(agent,ns,digest));
CREATE TABLE IF NOT EXISTS operations(
 id TEXT PRIMARY KEY, action TEXT NOT NULL, memory_id TEXT NOT NULL,
 path TEXT NOT NULL, state TEXT NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS extraction_jobs(
 id TEXT PRIMARY KEY, agent TEXT NOT NULL, ns TEXT NOT NULL, source_ids TEXT NOT NULL,
 state TEXT NOT NULL, created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS job_scope ON extraction_jobs(agent,ns,state);
CREATE TABLE IF NOT EXISTS processed_sources(
 source_id TEXT PRIMARY KEY REFERENCES sources(id) ON DELETE CASCADE,
 job_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS counters(key TEXT PRIMARY KEY,value REAL NOT NULL);
CREATE TABLE IF NOT EXISTS activation(
 memory_id TEXT PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
 last_used REAL NOT NULL,strength_days REAL NOT NULL,reinforcements INTEGER NOT NULL DEFAULT 0);

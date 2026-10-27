"""Reject unsupported persisted route labels BEFORE modifying existing storage."""
from pathlib import Path
import sqlite3
from .security import Rejected

def guard_labels(root,databases):
    root=Path(root)
    agents=root/'agents'
    if agents.exists() and any(p.is_dir() and p.name not in {'bot1','bot2'} for p in agents.iterdir()):
        raise Rejected('unsupported_persisted_agent_labels')
    for relative,tables in databases:
        path=root/relative
        if not path.exists():continue
        if path.is_symlink():raise Rejected('unsafe_database_path')
        db=sqlite3.connect('file:'+str(path.resolve())+'?mode=ro',uri=True)
        try:
            present={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in tables:
                if table in present and any(row[0] not in {'bot1','bot2'} for row in db.execute('SELECT DISTINCT agent FROM '+table)):
                    raise Rejected('unsupported_persisted_agent_labels')
        finally:db.close()

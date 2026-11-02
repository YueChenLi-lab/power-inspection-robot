"""Only dedicated diagnostic and temporary directories may be cleaned.

SQLite mission events, approvals and evidence have no retention deletion API.
"""
import logging.handlers
from pathlib import Path
import time


def storage_status(db,warning_fraction=.8):
    pages=db.rows('PRAGMA page_count')[0]['page_count'];size=db.rows('PRAGMA page_size')[0]['page_size']
    used=pages*size
    return {'logical_database_bytes':used,'admission_limit_bytes':db.max_bytes,
            'warning':used>=db.max_bytes*warning_fraction,
            'wal_bytes':Path(db.path+'-wal').stat().st_size if Path(db.path+'-wal').exists() else 0}


class Retention:
    def __init__(self,root):
        self.root=Path(root).resolve()
        self.diagnostic=self.root/'diagnostic';self.temporary=self.root/'temporary'
        for p in (self.diagnostic,self.temporary):p.mkdir(parents=True,exist_ok=True)

    def log_handler(self,max_bytes=1024*1024,backups=3):
        return logging.handlers.RotatingFileHandler(self.diagnostic/'runtime.log',maxBytes=max_bytes,backupCount=backups,encoding='utf-8')

    def clean(self,*,max_age_seconds=86400,max_cache_bytes=10*1024*1024):
        if max_age_seconds<0 or max_cache_bytes<0:raise ValueError('negative retention policy')
        now=time.time();deleted=[]
        files=[]
        for directory,pattern in ((self.temporary,'*.tmp'),(self.diagnostic,'*.log.*')):
            for p in directory.glob(pattern):
                if p.is_symlink() or not p.is_file():continue
                if p.resolve().parent!=directory.resolve():continue
                files.append(p)
        for p in files[:]:
            if now-p.stat().st_mtime>max_age_seconds:
                p.unlink();deleted.append(str(p));files.remove(p)
        # Capacity cleanup applies only to temporary cache, never active diagnostics/audit.
        cache=[p for p in files if p.parent==self.temporary]
        total=sum(p.stat().st_size for p in cache)
        for p in sorted(cache,key=lambda p:p.stat().st_mtime):
            if total<=max_cache_bytes:break
            total-=p.stat().st_size;p.unlink();deleted.append(str(p))
        return deleted

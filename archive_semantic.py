"""Scoped, incremental semantic search of visible archived dialogue, not facts."""
import json,re,time
from .security import SECRET,PRIVATE,safe_text
from .privacy import level


class ArchiveSemantic:
    def __init__(self, archive, vectors):
        self.archive,self.vectors=archive,vectors
        with vectors.db:
            vectors.db.execute('CREATE TABLE IF NOT EXISTS archive_vectors(agent TEXT,ns TEXT,digest TEXT,model TEXT,dim INTEGER,vector TEXT,PRIMARY KEY(agent,ns,digest,model))')
            vectors.db.execute('CREATE TABLE IF NOT EXISTS archive_usage(day TEXT PRIMARY KEY,utf8_bytes INTEGER,calls INTEGER)')

    def documents(self,p=None):
        a=self.archive
        with a.lock:
            a.prepare_read(p,'embed')
            if p is None:
                rows=a.db.execute('SELECT m.id,m.agent,m.ns,m.role,m.created,f.text FROM messages m JOIN chat_fts f ON m.id=CAST(f.id AS INTEGER) WHERE _privacy_id(m.id) AND NOT EXISTS(SELECT 1 FROM archive_labels q WHERE q.message_id=m.id) ORDER BY m.id').fetchall()
            else:
                if not p.readable:return []
                marks=','.join('?' for _ in p.readable)
                rows=a.db.execute('SELECT m.id,m.agent,m.ns,m.role,m.created,f.text FROM messages m JOIN chat_fts f ON m.id=CAST(f.id AS INTEGER) WHERE _privacy_id(m.id) AND NOT EXISTS(SELECT 1 FROM archive_labels q WHERE q.message_id=m.id) AND m.agent=? AND m.ns IN ('+marks+') ORDER BY m.id',(p.agent,*p.readable)).fetchall()
        out=[];seen=set()
        for r in rows:
            text=r['text']
            if SECRET.search(text) or level(text)>=2 or text.lstrip().startswith('/') or r['role'] not in {'user','assistant'}:continue
            for start in range(0,len(text),520):
                part=text[start:start+600].strip()
                if len(part)<4:continue
                digest=a.mac(r['agent']+'|'+r['ns']+'|'+part)
                key=(r['agent'],r['ns'],digest)
                if key in seen:continue
                seen.add(key);out.append(dict(id=r['id'],agent=r['agent'],ns=r['ns'],digest=digest,text=part,role=r['role'],archived_at=r['created'],offset=start))
        return out

    async def index_once(self):
        v=self.vectors
        if v.busy():return
        day=time.strftime('%Y-%m-%d',time.gmtime(v.clock()+28800))
        used=v.db.execute('SELECT utf8_bytes,calls FROM archive_usage WHERE day=?',(day,)).fetchone() or (0,0)
        if used[1]>=100:return
        pending=[];size=0
        for r in self.documents():
            if v.db.execute('SELECT 1 FROM archive_vectors WHERE agent=? AND ns=? AND digest=? AND model=? AND dim=?',(r['agent'],r['ns'],r['digest'],v.model,v.dim)).fetchone():continue
            n=len(r['text'].encode())
            if used[0]+size+n>100000:break
            pending.append(r);size+=n
            if len(pending)>=16:break
        if not pending:return
        # Reserve the archive sub-budget before sending, including failed requests.
        with v.db:v.db.execute('INSERT INTO archive_usage VALUES(?,?,1) ON CONFLICT(day) DO UPDATE SET utf8_bytes=utf8_bytes+excluded.utf8_bytes,calls=calls+1',(day,size))
        def save(values):
            valid={(r['agent'],r['ns'],r['digest']) for r in self.documents()}
            with v.db:
                for r,vec in zip(pending,values):
                    key=(r['agent'],r['ns'],r['digest'])
                    if key in valid:v.db.execute('INSERT OR REPLACE INTO archive_vectors VALUES(?,?,?,?,?,?)',(*key,v.model,v.dim,json.dumps(vec,separators=(',',':'))))
        await v.request([r['text'] for r in pending],save,20.,guard=lambda:{(r['agent'],r['ns'],r['digest']) for r in pending}<={(x['agent'],x['ns'],x['digest']) for x in self.documents()})

    async def search(self,p,query):
        v=self.vectors;query=safe_text(query[:512],1024)
        lexical=await __import__('asyncio').to_thread(self.archive.search,p,query)
        if not query or SECRET.search(query):return []
        if self.archive.query_private(p,query):return lexical
        visible=[]
        for r in self.documents(p):
            row=v.db.execute('SELECT vector FROM archive_vectors WHERE agent=? AND ns=? AND digest=? AND model=? AND dim=?',(r['agent'],r['ns'],r['digest'],v.model,v.dim)).fetchone()
            if row:visible.append((r,json.loads(row[0])))
        if not visible:return lexical
        key=v.engine._mac(json.dumps(['archive',v.model,p.agent,p.actor,p.readable,query],ensure_ascii=False))
        cached=v.cache.get(key)
        if cached and cached[0]>v.clock():qvec=cached[1]
        else:
            def save(values):
                v.cache[key]=(v.clock()+3600,values[0]);v.cache.move_to_end(key)
                while len(v.cache)>128:v.cache.popitem(last=False)
            result=await v.request([query],save,3.,guard=lambda:not self.archive.query_private(p,query))
            if result is None:return lexical
            qvec=result[0]
        ranked=[]
        for r,vec in visible:
            score=sum(x*y for x,y in zip(qvec,vec))
            if score>=.65 and p.can_read(r['agent'],r['ns']):
                ranked.append(dict(id=r['id'],role=r['role'],archived_at=r['archived_at'],text=r['text'][:500],offset=r['offset'],similarity=round(score,4),source='historical_dialogue_not_verified_fact'))
        ranked.sort(key=lambda r:-r['similarity'])
        out=[];seen=set()
        for r in ranked+lexical:
            if r['id'] in seen:continue
            seen.add(r['id']);out.append(r)
            if len(out)>=3:break
        return self.archive.describe_times(p,out)

"""Local content policy. No model calls. Grants never enlarge base identity ACLs."""
import hashlib,hmac,json,os,re,threading,time
from pathlib import Path
from .security import Rejected

VERSION=1
CREDENTIAL=re.compile(r'(?i)-----BEGIN [A-Z ]*PRIVATE KEY-----|\bbearer\s+\S{8,}|\bsk-[A-Za-z0-9_-]{8,}|(?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|token|secret|pwd|otp|clientkey|csrf|skey|p_skey|password|cookie|authorization|密码|验证码|私钥|令牌)\s*["\']?\s*(?:[:=：]|是|为)\s*["\']?\S{4,}')
SENSITIVE=re.compile(r'仅你知道|只有你知道|别告诉|不要告诉|不许分享|保密|我的隐私|这是.{0,3}隐私|我的.{0,8}(?:住址|身份证|银行卡|手机号|电话号码|病历|诊断)|我.{0,8}(?:被确诊|确诊为|被诊断|诊断为)|我.{0,4}(?:住在|地址是).{0,50}(?:路|街|巷|栋|单元|室|小区|号)|\b1[3-9]\d{9}\b|\b\d{17}[\dXx]\b|\b\d{16,19}\b|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}',re.I)
PUBLIC=re.compile(r'^(?:公开常识|公开资料)[:：]')

def level(text):
    if CREDENTIAL.search(text):return 3
    if SENSITIVE.search(text):return 2
    return 0 if PUBLIC.search(text) else 1

class PrivacyPolicy:
    def __init__(self,root,key):
        self.root=Path(root);self.path=self.root/'privacy_policy.json';self.key=key
        self.lock=threading.RLock();self.state={'version':VERSION,'revision':0,'grants':{}};self.stamp=None
    def refresh(self):
        with self.lock:
            if self.path.is_symlink():raise Rejected('privacy_policy_symlink')
            stamp=self.path.stat().st_mtime_ns if self.path.exists() else None
            if stamp!=self.stamp:
                self.state=json.loads(self.path.read_text()) if stamp is not None else {'version':VERSION,'revision':0,'grants':{}}
                self.stamp=stamp
            return self.state
    @property
    def revision(self):return self.refresh()['revision']
    def ident(self,agent,ns,subject,text):
        return hmac.new(self.key,json.dumps([agent,ns,subject,text],ensure_ascii=False,separators=(',',':')).encode(),hashlib.sha256).hexdigest()
    def sensitivity(self,agent,ns,subject,text):
        degree=level(text)
        if degree==3:return 3
        return max(degree,self.refresh()['grants'].get(self.ident(agent,ns,subject,text),{}).get('sensitivity',degree))
    def allowed(self,p,agent,ns,subject,text,purpose='read'):
        degree=self.sensitivity(agent,ns,subject,text)
        if degree==3:return False
        record=self.refresh()['grants'].get(self.ident(agent,ns,subject,text),{})
        degree=max(degree,record.get('sensitivity',degree))
        if p is not None and not p.can_read(agent,ns):return False
        if purpose=='embed':return degree<2
        if degree<2:return p is not None
        if p is None or not subject:return False
        if p.actor==subject:return True
        return p.actor in record.get('allowed_readers',[])
    def consent(self,p,record,target_actor,allow):
        if not p.can_read(record['agent'],record['ns']) or p.actor!=record['subject']:raise Rejected('privacy_subject_only')
        if level(record['text'])==3:raise Rejected('credentials_never_shareable')
        if not re.fullmatch('[a-f0-9]{24}',target_actor):raise Rejected('invalid_privacy_recipient')
        with self.lock:
            state=self.refresh();rid=self.ident(record['agent'],record['ns'],record['subject'],record['text'])
            row=state['grants'].get(rid,{'subject_actor':p.actor,'sensitivity':level(record['text']),'allow_external_embedding':False,'allowed_readers':[],'policy_version':VERSION})
            readers=set(row['allowed_readers']);readers.add(target_actor) if allow else readers.discard(target_actor)
            row.update(allowed_readers=sorted(readers),changed=time.time());state['grants'][rid]=row;state['revision']+=1
            self.root.mkdir(parents=True,exist_ok=True,mode=0o700);tmp=self.path.with_suffix('.new')
            fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
            with os.fdopen(fd,'w') as f:json.dump(state,f);f.flush();os.fsync(f.fileno())
            os.replace(tmp,self.path);os.chmod(self.path,0o600);self.stamp=self.path.stat().st_mtime_ns
            return state['revision']

    def restrict(self,p,record):
        if not p.can_read(record['agent'],record['ns']) or p.actor!=record['subject']:raise Rejected('privacy_subject_only')
        if level(record['text'])==3:raise Rejected('credentials_never_shareable')
        with self.lock:
            state=self.refresh();rid=self.ident(record['agent'],record['ns'],record['subject'],record['text'])
            state['grants'][rid]={'subject_actor':p.actor,'sensitivity':2,'allow_external_embedding':False,'allowed_readers':[],'policy_version':VERSION,'changed':time.time()};state['revision']+=1
            self.root.mkdir(parents=True,exist_ok=True,mode=0o700);tmp=self.path.with_suffix('.new');fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
            with os.fdopen(fd,'w') as f:json.dump(state,f);f.flush();os.fsync(f.fileno())
            os.replace(tmp,self.path);os.chmod(self.path,0o600);self.stamp=self.path.stat().st_mtime_ns
            return state['revision']

def filtered_payload(value):
    if isinstance(value,str):return '[敏感凭据已屏蔽]' if level(value)==3 else value
    if isinstance(value,list):return [filtered_payload(x) for x in value]
    if isinstance(value,dict):
        image=value.get('image_url')
        if value.get('type')=='image_url' and isinstance(image,dict) and level(str(image.get('url','')))==3:
            return {'type':'text','text':'[历史带凭据图片链接已屏蔽；请由本人查看原始记录]'}
        return {k:('{}' if k=='arguments' and isinstance(v,str) and level(v)==3 else '[敏感凭据已屏蔽]' if re.fullmatch(r'(?i)api[_ -]?key|access[_ -]?token|refresh[_ -]?token|token|secret|pwd|otp|clientkey|csrf|skey|p_skey|password|cookie|authorization',str(k)) else filtered_payload(v)) for k,v in value.items()}
    return value

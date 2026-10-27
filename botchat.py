"""Deterministic mutual-bot stop latch; never sends messages or reads memory rows."""
import json
import os
import re
import time
from pathlib import Path


class BotChatGuard:
    def __init__(self, root, peers, initially_paused=True):
        self.path = Path(root) / 'botchat_state.json'
        self.peers = frozenset(peers)
        self.paused = initially_paused
        self.generation = 0
        self.reason = 'initial_safety_pause'
        self.blocked = 0
        if self.path.exists():
            try:
                d = json.loads(self.path.read_text(encoding='utf-8'))
                self.paused = d['paused'] is not False
                self.generation = int(d.get('generation', 0))
                self.reason = str(d.get('reason', 'restored'))
            except Exception:
                self.paused = True
                self.reason = 'invalid_state_fail_closed'
        else:
            self.set_paused(initially_paused, self.reason)

    @staticmethod
    def is_closing(text):
        # Check visible output, never hidden reasoning. Quoted policy discussion
        # and explicit negations must not themselves count as a farewell.
        text = re.sub(r'```.*?```|[“「『\"].*?[”」』\"]', '', str(text), flags=re.S)
        phrases = r'晚安|下次再说(?:吧)?|以后再见(?:吧)?|下次再聊|改天再聊|今天先到这里|先聊到这(?:里)?|不聊了|先不聊了|回头再聊|拜拜|再见'
        for m in re.finditer(phrases, text):
            before = text[max(0, m.start()-8):m.start()]
            if re.search(r'(?:不要|别|不想|不能|不是|不说|没说|例如|比如|如果|当).*$', before):
                continue
            return True
        return False

    def set_paused(self, paused, reason):
        # Generation invalidates work admitted before any stop/resume transition.
        generation = self.generation + 1
        state = dict(paused=bool(paused), generation=generation,
                     reason=reason, updated_at=time.time())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        with open(temp, 'w', encoding='utf-8') as f:
            os.chmod(temp, 0o600)
            json.dump(state, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, self.path)
        self.paused = bool(paused)
        self.generation = generation
        self.reason = reason

    def admit(self, umo, text):
        if umo not in self.peers:
            return True
        if self.paused:
            self.blocked += 1
            return False
        if self.is_closing(text):
            self.set_paused(True, 'incoming_farewell')
            self.blocked += 1
            return False
        return True

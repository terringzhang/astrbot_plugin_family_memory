from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass


class Rejected(ValueError):
    """Safe reason code only: never include rejected private content."""


SECRET = re.compile(
    r"(?i)(?:bearer\s+\S{8,}|sk-[A-Za-z0-9_-]{8,}|"
    r"(?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|token|pwd|passphrase|otp|pin|secret|password|cookie|authorization|"
    r"密码|验证码|口令|私钥|令牌)\s*[:=：]?\s*[\"']?\S{4,}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\b\d{17}[\dXx]\b|\b\d{16,19}\b)"
)
PRIVATE = re.compile(r"隐私|保密|别告诉|不要告诉|仅你知道|不许分享|住址|身份证|银行卡|病历|诊断|手机号|电话号码|\b1[3-9]\d{9}\b")
UNCERTAIN = re.compile(r"开玩笑|假如|假设|也许|猜测|不一定|不确定|虚构|角色扮演|可能吧")


def safe_text(value: str, limit: int = 4000) -> str:
    if not isinstance(value, str) or len(value) > limit:
        raise Rejected("invalid_text_size")
    if SECRET.search(value):
        raise Rejected("credential_or_sensitive_identifier")
    if "\x00" in value:
        raise Rejected("invalid_text")
    return value.strip()


@dataclass(frozen=True)
class Principal:
    agent: str
    actor: str
    role: str
    private_ns: str
    readable: tuple[str, ...]
    persona: str = "configured"

    def can_read(self, agent: str, ns: str) -> bool:
        return agent == self.agent and ns in self.readable

    def can_write(self, ns: str) -> bool:
        return ns == self.private_ns or (ns == "family" and self.agent == "xiaoman" and self.role in {"owner", "sister"})


class IdentityPolicy:
    """Only trusted adapter platform/self/sender IDs grant a namespace.

    No nickname, quoted text, LLM output or operator role grants family access.
    Exact verified binding IDs must be explicitly approved in configuration.
    """

    def __init__(self, key: bytes, config: dict):
        self.key, self.config = key, config

    def hashed(self, text: str) -> str:
        return hmac.new(self.key, text.encode(), hashlib.sha256).hexdigest()[:24]

    def resolve(self, platform: str, self_id: str, sender: str, *, private: bool = True) -> Principal:
        if not private or not sender:
            raise Rejected("unsupported_or_unknown_sender")
        cfg = self.config
        if platform == cfg.get("xiaoman_platform", "default"):
            if self_id != str(cfg.get("xiaoman_self_id", "")):
                raise Rejected("unexpected_bot_self_id")
            agent = "xiaoman"
            role = "owner" if sender in cfg.get("owner_qq_ids", []) else "visitor"
            binding = cfg.get("sister_binding", {})
            if (binding.get("approved") is True and binding.get("evidence_ref")
                    and sender == str(binding.get("qq_id", ""))):
                if role == "owner":
                    raise Rejected("ambiguous_identity_binding")
                role = "sister"
        elif platform == cfg.get("elder_platform", "qq_official"):
            # Official adapter self_id representation is not assumed to be AppID.
            expected = cfg.get("elder_self_id", "")
            if expected and self_id != str(expected):
                raise Rejected("unexpected_bot_self_id")
            agent, role = "elder_sister", "visitor"
            if sender in cfg.get("elder_owner_openids", []):
                role = "owner"
            peer=cfg.get('elder_peer_binding',{})
            if peer.get('approved') is True and peer.get('evidence_ref') and sender==str(peer.get('openid','')):
                if role=='owner':raise Rejected('ambiguous_identity_binding')
                role='peer'
        else:
            raise Rejected("unmanaged_platform")
        actor = self.hashed(platform + ":" + sender)
        ns = ("visitor-" if role == "visitor" else "private-") + actor
        readable = (ns, "family") if agent == "xiaoman" and role in {"owner", "sister"} else (ns,)
        if agent == 'elder_sister' and role in {'owner', 'peer'}:
            ns = 'private-' + role + '-' + actor
            # Keep the same owner's existing private material readable without
            # moving rows. Peer approval never grants its former visitor domain.
            readable = (ns, 'private-' + actor) if role == 'owner' else (ns,)
            if cfg.get('elder_private_mutual_read', False):
                peer = cfg.get('elder_peer_binding', {})
                if (role == 'owner' and peer.get('approved') is True
                        and peer.get('evidence_ref') and peer.get('openid')):
                    peer_actor = self.hashed(platform + ':' + str(peer['openid']))
                    readable += ('private-peer-' + peer_actor,)
                elif role == 'peer':
                    for owner_id in cfg.get('elder_owner_openids', []):
                        owner_actor = self.hashed(platform + ':' + str(owner_id))
                        readable += ('private-owner-' + owner_actor, 'private-' + owner_actor)
                readable = tuple(dict.fromkeys(readable))
        return Principal(agent, actor, role, ns, readable)

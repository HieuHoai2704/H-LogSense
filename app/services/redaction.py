"""Conservative display redaction for demo payloads; not a production DLP engine."""
import re

KEY_VALUE = re.compile(r'''(?i)\b(password|passwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|token|authorization)\b(["']?\s*[:=]\s*)(?:"[^"\n]*"|'[^'\n]*'|[^\s,;]+)''')
BEARER = re.compile(r'(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+')
JWT = re.compile(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b')
EMAIL = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
PRIVATE_KEY = re.compile(r'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----.*?-----END (?:[A-Z]+ )?PRIVATE KEY-----', re.S)
AUTH_HEADER = re.compile(r'(?im)\b(Authorization|Cookie|Set-Cookie)\s*:\s*[^\r\n]+')
URL_CREDENTIALS = re.compile(r'(?i)(https?://)[^/\s:@]+:[^/\s@]+@')
SENSITIVE_KEY = re.compile(r'(?i)^(password|passwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|token|authorization)$')


def redact(value):
    """Redact before preview slicing so a token cannot leak across page edges."""
    if isinstance(value, dict):
        return {str(k): '[REDACTED]' if SENSITIVE_KEY.fullmatch(str(k)) else redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if not isinstance(value, str):
        return value
    value = PRIVATE_KEY.sub('[REDACTED PRIVATE KEY]', value)
    value = AUTH_HEADER.sub(lambda m: m[1]+': [REDACTED]', value)
    value = URL_CREDENTIALS.sub(lambda m: m[1]+'[REDACTED]@', value)
    value = BEARER.sub('Bearer [REDACTED]', value)
    value = KEY_VALUE.sub(lambda m: m[1]+m[2]+'[REDACTED]', value)
    value = JWT.sub('[REDACTED TOKEN]', value)
    return EMAIL.sub('[REDACTED EMAIL]', value)

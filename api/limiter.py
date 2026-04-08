# api/limiter.py
# Instancia compartida de slowapi para rate limiting en endpoints costosos (LLM).

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=[])

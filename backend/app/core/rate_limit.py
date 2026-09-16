from slowapi import Limiter
from slowapi.util import get_remote_address

# in-memory storage is fine for a single-process deployment; switch to a
# redis storage_uri here if the app ever runs with multiple workers/instances
limiter = Limiter(key_func=get_remote_address)

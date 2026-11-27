"""Contract for future, individually authorized and tested store integrations."""
from dataclasses import dataclass
from typing import Literal, Protocol

@dataclass(frozen=True)
class Observation:
    product_key: str
    variant_key: str
    color: str
    size: str
    status: Literal['in_stock','out_of_stock','unknown','removed']
    amount_minor: int | None
    currency: str | None
    observed_at: int

class StoreAdapter(Protocol):
    def observe(self, url: str) -> list[Observation]: ...

# Intentionally empty: no live store access is claimed by this release.
ADAPTERS: dict[str, StoreAdapter] = {}

# Only integrations with verified access permission AND a successful live test
# may be configured here. Empty by default; recognized domains are not support.
IMPLEMENTED_STORES = {'Bershka'}
def supported_stores(db):
    import json
    try:
        approved = json.loads(db.get('verified_stores','[]'))
    except (ValueError, TypeError):
        return []
    if not isinstance(approved,list): return []
    return sorted(name for name in IMPLEMENTED_STORES if name in approved)

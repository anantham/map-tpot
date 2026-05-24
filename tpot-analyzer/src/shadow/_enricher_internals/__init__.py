"""Private implementation of `src.shadow.enricher.HybridShadowEnricher`.

Public API lives in `src.shadow.enricher`; this package holds the behavior
mixins. State (self._store, self._config, self._policy, self._selenium,
self._api, self._resolution_cache, etc.) is initialized by the coordinator
class and assumed to exist by every mixin.

Cross-mixin calls all go through `self.method(...)` so Python's MRO resolves
them at runtime once all mixins are combined into HybridShadowEnricher.
"""

import random
import time
from langatlas_pipeline.errors import CircuitOpen, ProviderTransportError


class Throttle:
    """Politeness, not correctness: the university gateway documents no rate limits and
    is shared, slow infrastructure. A minimum interval between calls plus exponential
    backoff with jitter, and a circuit breaker so a down service pauses the run instead
    of being hammered overnight."""

    def __init__(self, *, min_interval: float = 0.5, max_attempts: int = 5,
                 circuit_breaker_failures: int = 5, sleep=None, clock=None):
        self.min_interval = min_interval
        self.max_attempts = max_attempts
        self.circuit_breaker_failures = circuit_breaker_failures
        # Resolved at construction, not at import: a test that patches time.sleep before
        # building the client must actually get the patched function.
        self._sleep = sleep or time.sleep
        self._clock = clock or time.monotonic
        self._last_call = 0.0
        self._consecutive_failures = 0

    def wait(self) -> None:
        gap = self._clock() - self._last_call
        if gap < self.min_interval:
            self._sleep(self.min_interval - gap)
        self._last_call = self._clock()

    def run(self, call):
        """Execute `call`, retrying transport failures. Honors Retry-After when the
        exception carries one."""
        if self._consecutive_failures >= self.circuit_breaker_failures:
            raise CircuitOpen(f"{self._consecutive_failures} consecutive transport failures")
        last: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            self.wait()
            try:
                result = call()
            except Exception as exc:                      # transport-shaped only
                if not _is_transient(exc):
                    raise
                last = exc
                self._consecutive_failures += 1
                if attempt == self.max_attempts:
                    break
                self._sleep(_backoff_seconds(exc, attempt))
            else:
                self._consecutive_failures = 0
                return result
        raise ProviderTransportError(str(last), status=getattr(last, "status", None),
                                     attempts=self.max_attempts)


def _is_transient(exc: Exception) -> bool:
    status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
    if status is not None:
        return status == 429 or status >= 500
    return isinstance(exc, (ProviderTransportError, TimeoutError, ConnectionError))


def _backoff_seconds(exc: Exception, attempt: int) -> float:
    retry_after = getattr(exc, "retry_after", None)
    if retry_after:
        return float(retry_after)
    return min(2 ** (attempt - 1), 30) * (0.5 + random.random())

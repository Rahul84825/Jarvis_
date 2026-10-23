"""Request coalescing (single-flight) mechanism to prevent duplicate concurrent API requests."""

import time
import threading
import logging
from typing import Dict, Any, Callable, Tuple, Optional

logger = logging.getLogger("Jarvis.SingleFlight")


class _FlightCall:
    """Internal coordination record for an active in-flight request."""

    def __init__(self):
        self.event = threading.Event()
        self.result: Any = None
        self.exception: Optional[Exception] = None
        self.waiters: int = 1


class SingleFlightGroup:
    """Coordinates duplicate concurrent requests so only one execution runs,
    while identical callers await the same response without duplicate API calls.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._calls: Dict[str, _FlightCall] = {}

    def execute(
        self,
        key: str,
        fn: Callable[[], Any],
        timeout: float = 30.0
    ) -> Tuple[Any, bool]:
        """Executes fn() for key, coalescing concurrent calls with identical key.
        Returns: (result, was_coalesced: bool)
        """
        with self._lock:
            # Case 1: Another thread is currently executing the same request
            if key in self._calls:
                call = self._calls[key]
                call.waiters += 1
                logger.info(f"[SINGLE_FLIGHT] Coalescing duplicate in-flight request for key '{key[:12]}...' (Waiters: {call.waiters})")
                is_leader = False
            else:
                # Case 2: This thread is the leader and will execute fn()
                call = _FlightCall()
                self._calls[key] = call
                is_leader = True

        if not is_leader:
            # Await leader's completion
            completed = call.event.wait(timeout=timeout)
            if not completed:
                logger.warning(f"[SINGLE_FLIGHT] Waiter timed out waiting for key '{key[:12]}...'. Proceeding to fresh execution.")
                # If leader timed out, run directly
                return fn(), False

            if call.exception is not None:
                raise call.exception
            return call.result, True

        # Leader execution block
        try:
            result = fn()
            call.result = result
            return result, False
        except Exception as e:
            call.exception = e
            raise e
        finally:
            with self._lock:
                if key in self._calls:
                    del self._calls[key]
            # Notify all waiting threads
            call.event.set()

    # Alias for canonical Go/Python singleflight nomenclature
    do = execute

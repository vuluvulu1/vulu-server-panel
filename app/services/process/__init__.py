from .base import ProcessBackend, ProcessError
from .subprocess_backend import SubprocessBackend

# Tek yerden seçilir: VDS'te burası SystemdBackend() olacak.
process_manager: ProcessBackend = SubprocessBackend()

__all__ = ["process_manager", "ProcessError", "ProcessBackend"]

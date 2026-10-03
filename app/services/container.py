"""Uygulama genelinde paylaşılan servis örnekleri (tek yerden bağlanır)."""
from ..config import ADOPTIUM_API, CACHE_DIR, DATA_DIR, MOJANG_MANIFEST_URL, PAPER_API, RUNTIMES_DIR
from .java_manager import JavaManager
from .jobs import JobManager
from .launcher import InstanceLauncher
from .minecraft import MinecraftService
from .paper import PaperManager
from .process import process_manager

jobs = JobManager()
minecraft = MinecraftService(MOJANG_MANIFEST_URL, DATA_DIR)
java = JavaManager(RUNTIMES_DIR, ADOPTIUM_API, jobs)
paper = PaperManager(PAPER_API, CACHE_DIR / "paper", jobs)
launcher = InstanceLauncher(process_manager, java, paper)
from .stats import StatsService

stats = StatsService(process_manager)

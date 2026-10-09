"""Uygulama genelinde paylaşılan servis örnekleri (tek yerden bağlanır)."""
from ..config import (ADOPTIUM_API, CACHE_DIR, DATA_DIR, FABRIC_API, FORGE_MAVEN, MODRINTH_API, MODRINTH_CDN_HOSTS, MOJANG_MANIFEST_URL,
                      NEOFORGE_MAVEN, PAPER_API, RUNTIMES_DIR)
from .fabric import FabricManager
from .forge import ForgeManager
from .java_manager import JavaManager
from .jobs import JobManager
from .launcher import InstanceLauncher
from .minecraft import MinecraftService
from .modpack import ModpackManager
from .modrinth import ModManager
from .paper import PaperManager
from .process import process_manager
from .stats import StatsService

jobs = JobManager()
minecraft = MinecraftService(MOJANG_MANIFEST_URL, DATA_DIR)
java = JavaManager(RUNTIMES_DIR, ADOPTIUM_API, jobs)
paper = PaperManager(PAPER_API, CACHE_DIR / "paper", jobs)
fabric = FabricManager(FABRIC_API, CACHE_DIR / "fabric", jobs)
forge = ForgeManager("forge", FORGE_MAVEN, CACHE_DIR / "forge", jobs)
neoforge = ForgeManager("neoforge", NEOFORGE_MAVEN, CACHE_DIR / "neoforge", jobs)
installers = {"paper": paper, "fabric": fabric, "forge": forge, "neoforge": neoforge}   # panelin kurabildiği yükleyiciler
mods = ModManager(MODRINTH_API, MODRINTH_CDN_HOSTS, jobs)
modpacks = ModpackManager(MODRINTH_API, MODRINTH_CDN_HOSTS, CACHE_DIR / "modpacks", jobs, mods)
launcher = InstanceLauncher(process_manager, java, installers, mods, modpacks)
stats = StatsService(process_manager)

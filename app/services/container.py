"""Uygulama genelinde paylaşılan servis örnekleri (tek yerden bağlanır)."""
from ..config import (BACKUPS_DIR, ADOPTIUM_API, CACHE_DIR, DATA_DIR, FABRIC_API, FORGE_MAVEN, MOJANG_EXTRA_HOSTS, MODRINTH_API, MODRINTH_CDN_HOSTS, MOJANG_MANIFEST_URL,
                      NEOFORGE_MAVEN, PAPER_API, RUNTIMES_DIR)
from .backup import BackupManager
from .fabric import FabricManager
from .forge import ForgeManager
from .java_manager import JavaManager
from .jobs import JobManager
from .launcher import InstanceLauncher
from .minecraft import MinecraftService
from .modpack import ModpackManager
from .modrinth import ModManager
from .paper import PaperManager
from .vanilla import VanillaManager
from .process import process_manager
from .stats import StatsService

jobs = JobManager()
minecraft = MinecraftService(MOJANG_MANIFEST_URL, DATA_DIR)
java = JavaManager(RUNTIMES_DIR, ADOPTIUM_API, jobs)
paper = PaperManager(PAPER_API, CACHE_DIR / "paper", jobs)
fabric = FabricManager(FABRIC_API, CACHE_DIR / "fabric", jobs)
forge = ForgeManager("forge", FORGE_MAVEN, CACHE_DIR / "forge", jobs)
neoforge = ForgeManager("neoforge", NEOFORGE_MAVEN, CACHE_DIR / "neoforge", jobs)
vanilla = VanillaManager(minecraft, CACHE_DIR / "vanilla", jobs, MOJANG_EXTRA_HOSTS)
installers = {"vanilla": vanilla, "paper": paper, "fabric": fabric, "forge": forge, "neoforge": neoforge}   # panelin kurabildiği yükleyiciler
mods = ModManager(MODRINTH_API, MODRINTH_CDN_HOSTS, jobs)
modpacks = ModpackManager(MODRINTH_API, MODRINTH_CDN_HOSTS, CACHE_DIR / "modpacks", jobs, mods)
launcher = InstanceLauncher(process_manager, java, installers, mods, modpacks, minecraft)
stats = StatsService(process_manager)
backups = BackupManager(BACKUPS_DIR, jobs, process_manager)
from .scheduler import Scheduler  # noqa: E402

scheduler = Scheduler(launcher, backups, process_manager)
from .upgrade import Upgrader  # noqa: E402

upgrader = Upgrader(installers, minecraft, backups, mods, jobs, process_manager)
from ..config import MOJANG_PROFILE_API  # noqa: E402
from .players import PlayerManager  # noqa: E402

players = PlayerManager(process_manager, stats, MOJANG_PROFILE_API)

from .modupdate import ModUpdater  # noqa: E402

modupdater = ModUpdater(mods)
from ..config import PLAYIT_API  # noqa: E402
from .playit import PlayitManager  # noqa: E402

playit = PlayitManager(PLAYIT_API, RUNTIMES_DIR / "playit", DATA_DIR / "playit", jobs)

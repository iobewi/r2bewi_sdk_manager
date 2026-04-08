"""
Header commun à tous les modules applicatifs R2BEWI.
Chaque module importe ce dont il a besoin depuis ce fichier.
"""
from __future__ import annotations

import sys
from pathlib import Path

from .log import error, info, ok, section, warn
from . import backup as _backup
from .debian import services as _svc
from .helpers import (
    NODES_DIR,
    get_kind,
    resolve_ip,
    resolve_ssh_user,
    ssh_target,
    which,
)
from .subprocess_utils import push_file, run, run_ssh

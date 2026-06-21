"""backup.py - Backup mixin."""

import subprocess
from datetime import datetime

from i18n import t


class BackupMixin:
    """Mixin: backup commands."""

    def backup(self, message: str = ""):
        """Auto-backup knowledge base to git"""
        if not message:
            message = f"kb backup: {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        try:
            subprocess.run(["git", "add", "."], cwd=str(self.vault_path), capture_output=True)
            result = subprocess.run(["git", "commit", "-m", message], cwd=str(self.vault_path), capture_output=True, text=True)
            if "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
                print(f"[INFO]  {t('backup.nothing')}")
            elif result.returncode == 0:
                print(f"[OK] {t('backup.done')}: {message}")
            else:
                print(f"[WARN]  {result.stderr.strip() or result.stdout.strip()}")
        except Exception as e:
            print(f"[WARN]  {e}")

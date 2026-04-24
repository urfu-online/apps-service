"""
KopiaBackupManager - координатор резервного копирования на основе Kopia.

Использует bash-скрипты из _core/backup/scripts/ для выполнения операций.
"""
import asyncio
import logging
import os
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import re

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.backup import BackupRecord
from app.models.service import Service

logger = logging.getLogger(__name__)


class KopiaBackupManager:
    """Менеджер резервного копирования на основе Kopia."""

    def __init__(
        self,
        db: AsyncSession,
        notifier: Any,
        dry_run: bool = False,
        subprocess_timeout: int = 1800  # 30 минут по умолчанию
    ):
        self.db = db
        self.notifier = notifier
        self.dry_run = dry_run
        self.subprocess_timeout = subprocess_timeout
        # Dynamically resolve scripts path relative to this file's location
        self.scripts_path = Path(__file__).resolve().parent.parent.parent / "_core" / "backup" / "scripts"
        self.kopia_password = os.environ.get("KOPIA_REPOSITORY_PASSWORD")
        if not self.kopia_password and not dry_run:
            logger.warning("KOPIA_REPOSITORY_PASSWORD environment variable is not set")

    async def run_backup(self, service_name: str) -> BackupRecord:
        """
        Выполняет резервное копирование сервиса с помощью Kopia.

        Создаёт временную директорию, копирует туда файлы сервиса,
        запускает kopia_backup.sh, парсит manifest_id, сохраняет запись в БД,
        отправляет уведомление.

        Args:
            service_name: имя сервиса (например, "test-web-app")

        Returns:
            Backup: запись о бэкапе в БД

        Raises:
            ValueError: если сервис не найден или конфигурация бэкапа отключена
            RuntimeError: если скрипт завершился с ошибкой
        """
        # Получаем сервис из БД
        stmt = select(Service).where(Service.name == service_name)
        result = await self.db.execute(stmt)
        service = result.scalar_one_or_none()
        if not service:
            raise ValueError(f"Service '{service_name}' not found")

        if not service.backup_config or not service.backup_config.enabled:
            raise ValueError(f"Backup disabled for service '{service_name}'")

        logger.info(f"Starting backup for service '{service_name}'")

        # Создаём временную директорию
        with tempfile.TemporaryDirectory(prefix=f"kopia_backup_{service_name}_") as tmpdir:
            tmp_path = Path(tmpdir)
            # Копируем файлы сервиса во временную директорию
            await self._copy_service_files(service, tmp_path)

            # Запускаем скрипт kopia_backup.sh
            script_path = self.scripts_path / "kopia_backup.sh"

            # Подготавливаем окружение
            env = os.environ.copy()
            env["KOPIA_REPOSITORY_PASSWORD"] = self.kopia_password or ""
            # Переменные для скрипта
            env["SERVICE_NAME"] = service_name
            env["BACKUP_SOURCE"] = str(tmp_path)

            cmd = ["bash", str(script_path), service_name, str(tmp_path)]

            if self.dry_run:
                logger.info(f"DRY RUN: would execute: {cmd}")
                logger.info("DRY RUN: env contains KOPIA_REPOSITORY_PASSWORD (hidden)")
                # Создаём фиктивный manifest_id для dry-run
                manifest_id = "dry-run-manifest-id"
                snapshot_size = 0
            else:
                # Проверяем существование скрипта только при реальном запуске
                if not script_path.exists():
                    raise FileNotFoundError(f"Script not found: {script_path}")
                
                # Выполняем скрипт
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                
                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(),
                        timeout=self.subprocess_timeout
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    raise RuntimeError(f"Backup script timed out after {self.subprocess_timeout}s")

                if process.returncode != 0:
                    error_msg = stderr.decode().strip()
                    logger.error(f"Backup script failed: {error_msg}")
                    # Пытаемся использовать специализированный метод, если доступен
                    if hasattr(self.notifier, 'send_backup_failed'):
                        await self.notifier.send_backup_failed(service_name, error_msg)
                    else:
                        await self.notifier.send(
                            f"❌ Backup failed for {service_name}\n"
                            f"Error: {error_msg}"
                        )
                    raise RuntimeError(f"Backup script failed: {error_msg}")

                # Парсим вывод скрипта для получения manifest_id и размера
                output = stdout.decode()
                manifest_id = self._parse_manifest_id(output)
                snapshot_size = self._parse_snapshot_size(output)

                logger.info(f"Backup completed, manifest_id: {manifest_id}")

        # Создаём запись в БД (BackupRecord для Kopia)
        backup_record = BackupRecord(
            service_name=service_name,
            snapshot_id=manifest_id,
            status="created",
            created_at=datetime.now(timezone.utc),
            size_bytes=snapshot_size,
            retention_days=service.backup_config.retention_days if service.backup_config else 7,
        )
        self.db.add(backup_record)
        await self.db.commit()
        await self.db.refresh(backup_record)

        # Отправляем уведомление
        if hasattr(self.notifier, 'send_backup_completed'):
            await self.notifier.send_backup_completed(service_name, manifest_id, snapshot_size)
        else:
            await self.notifier.send(
                f"✅ Backup completed for {service_name}\n"
                f"Manifest ID: {manifest_id}\n"
                f"Size: {snapshot_size} bytes"
            )

        return backup_record

    async def enforce_retention(self, service_name: str, retention_days: int):
        """
        Применяет политику хранения для сервиса.

        Вызывает kopia_policy.sh с параметрами --prune --keep-within {retention_days}d.

        Args:
            service_name: имя сервиса
            retention_days: количество дней хранения

        Raises:
            RuntimeError: если скрипт завершился с ошибкой
        """
        script_path = self.scripts_path / "kopia_policy.sh"

        cmd = [
            "bash", str(script_path),
            "--prune",
            "--keep-within", f"{retention_days}d",
            service_name,
        ]

        if self.dry_run:
            logger.info(f"DRY RUN: would execute: {cmd}")
            return

        # Проверяем существование скрипта только при реальном запуске
        if not script_path.exists():
            raise FileNotFoundError(f"Script not found: {script_path}")

        env = os.environ.copy()
        env["KOPIA_REPOSITORY_PASSWORD"] = self.kopia_password or ""

        process = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode().strip()
            logger.error(f"Retention policy script failed: {error_msg}")
            # Используем общий send для ошибок (нет специализированного метода)
            await self.notifier.send(
                f"❌ Retention policy failed for {service_name}\n"
                f"Error: {error_msg}"
            )
            raise RuntimeError(f"Retention policy script failed: {error_msg}")

        logger.info(f"Retention policy applied for {service_name}")
        if hasattr(self.notifier, 'send_retention_pruned'):
            await self.notifier.send_retention_pruned(service_name, retention_days)
        else:
            await self.notifier.send(
                f"🧹 Retention policy applied for {service_name}\n"
                f"Keep within: {retention_days} days"
            )

    async def dry_run_backup(self, service_name: str) -> Dict[str, Any]:
        """
        Имитирует выполнение бэкапа без реального запуска скриптов.

        Логирует команды, которые были бы выполнены.

        Args:
            service_name: имя сервиса

        Returns:
            Dict с информацией о том, что было бы сделано
        """
        logger.info(f"Dry-run backup for service '{service_name}'")

        # Получаем сервис из БД
        stmt = select(Service).where(Service.name == service_name)
        result = await self.db.execute(stmt)
        service = result.scalar_one_or_none()
        if not service:
            return {"error": f"Service '{service_name}' not found"}

        if not service.backup_config or not service.backup_config.enabled:
            return {"error": f"Backup disabled for service '{service_name}'"}

        # Имитируем копирование файлов
        service_path = Path(f"/projects/apps-service-opus/services/{service.visibility.value}/{service.name}")
        if service_path.exists():
            file_count = sum(1 for _ in service_path.rglob("*") if _.is_file())
        else:
            file_count = 0

        # Команда, которая была бы выполнена
        script_path = self.scripts_path / "kopia_backup.sh"
        cmd = ["bash", str(script_path), service_name, "/tmp/dummy"]

        return {
            "service_name": service_name,
            "backup_enabled": True,
            "file_count": file_count,
            "command": " ".join(cmd),
            "kopia_repository": os.environ.get("KOPIA_REPOSITORY", "not set"),
            "dry_run": True,
        }

    async def _copy_service_files(self, service: Service, destination: Path):
        """
        Копирует файлы сервиса во временную директорию.

        В реальной реализации может использовать rsync или прямое копирование.
        Сейчас просто логирует.
        """
        service_path = Path(f"/projects/apps-service-opus/services/{service.visibility.value}/{service.name}")
        if not service_path.exists():
            logger.warning(f"Service path does not exist: {service_path}")
            return

        # В этой версии мы просто создаём пустой файл-маркер, так как скрипт kopia_backup.sh
        # сам умеет копировать файлы из исходного пути.
        # Но для полноты можно скопировать файлы.
        # Упрощённая реализация: используем rsync
        if self.dry_run:
            logger.info(f"DRY RUN: would copy files from {service_path} to {destination}")
            return

        # Используем rsync для копирования
        cmd = [
            "rsync", "-av", "--delete",
            f"{service_path}/",
            f"{destination}/",
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            logger.error(f"Failed to copy service files: {stderr.decode()}")
        else:
            logger.info(f"Copied service files from {service_path}")

    def _parse_manifest_id(self, output: str) -> str:
        """
        Парсит manifest_id из вывода скрипта kopia_backup.sh.

        Ожидается строка вида "Created snapshot with manifest ID: kxxxxxxxxx"
        или "manifest_id: kxxxxxxxxx".

        Returns:
            Извлечённый manifest_id или "unknown" если не найден.
        """
        patterns = [
            r"Created snapshot with manifest ID: (\S+)",
            r"manifest_id: (\S+)",
            r"Manifest ID: (\S+)",
            r"Snapshot ID: (\S+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, output)
            if match:
                return match.group(1)

        # Если не нашли, генерируем фиктивный ID для dry-run или ошибки
        logger.warning(f"Could not parse manifest_id from output: {output[:200]}...")
        return "unknown"

    def _parse_snapshot_size(self, output: str) -> int:
        """
        Парсит размер снапшота из вывода скрипта.

        Ищет строку вида "Snapshot size: 123456 bytes".

        Returns:
            Размер в байтах, 0 если не найден.
        """
        pattern = r"Snapshot size: (\d+) bytes"
        match = re.search(pattern, output)
        if match:
            return int(match.group(1))
        return 0

    async def list_snapshots(self, service_name: str) -> List[Dict[str, Any]]:
        """
        Возвращает список снапшотов для сервиса из таблицы backup_records.

        Args:
            service_name: имя сервиса

        Returns:
            Список словарей с информацией о снапшотах
        """
        from sqlalchemy import select
        from app.models.backup import BackupRecord
        
        stmt = select(BackupRecord).where(
            BackupRecord.service_name == service_name,
            BackupRecord.status != "deleted"
        ).order_by(BackupRecord.created_at.desc())
        result = await self.db.execute(stmt)
        records = result.scalars().all()
        
        return [
            {
                "snapshot_id": record.snapshot_id,
                "service_name": record.service_name,
                "status": record.status,
                "created_at": record.created_at,
                "size_bytes": record.size_bytes,
                "retention_days": record.retention_days,
            }
            for record in records
        ]

    async def restore_snapshot(
        self,
        service_name: str,
        snapshot_id: str,
        target: Optional[str] = None,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Восстанавливает снапшот Kopia.

        Args:
            service_name: имя сервиса
            snapshot_id: ID манифеста Kopia
            target: целевая директория (опционально)
            force: игнорировать проверки (опционально)

        Returns:
            Результат операции
        """
        from sqlalchemy import select
        from app.models.backup import BackupRecord
        
        # Проверяем существование снапшота
        stmt = select(BackupRecord).where(BackupRecord.snapshot_id == snapshot_id)
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            raise ValueError(f"Snapshot {snapshot_id} not found")
        
        # Проверяем, что сервис существует и backup enabled
        stmt = select(Service).where(Service.name == service_name)
        result = await self.db.execute(stmt)
        service = result.scalar_one_or_none()
        if not service:
            raise ValueError(f"Service '{service_name}' not found")
        
        if not service.backup_config or not service.backup_config.enabled:
            if not force:
                raise ValueError(f"Backup disabled for service '{service_name}'")
        
        # Определяем целевой путь
        if target is None:
            # Восстанавливаем в оригинальную директорию сервиса
            target = f"/projects/apps-service-opus/services/{service.visibility.value}/{service.name}"
        
        logger.info(f"Restoring snapshot {snapshot_id} for service '{service_name}' to {target}")
        
        if self.dry_run:
            return {
                "success": True,
                "dry_run": True,
                "message": f"Would restore snapshot {snapshot_id} to {target}",
                "snapshot_id": snapshot_id,
                "target": target,
            }

        # Запускаем скрипт восстановления
        script_path = self.scripts_path / "kopia_restore.sh"
        
        # Проверяем существование скрипта только при реальном запуске
        if not script_path.exists():
            raise FileNotFoundError(f"Script not found: {script_path}")

        env = os.environ.copy()
        env["KOPIA_REPOSITORY_PASSWORD"] = self.kopia_password or ""

        cmd = [
            "bash", str(script_path),
            "--manifest", snapshot_id,
            "--target", target,
        ]
        if not force:
            cmd.append("--no-db")  # По умолчанию не восстанавливаем БД, если не указано force
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode().strip()
            logger.error(f"Restore failed: {error_msg}")
            raise RuntimeError(f"Restore failed: {error_msg}")
        
        output = stdout.decode()
        logger.info(f"Restore completed: {output[:200]}...")
        
        # Обновляем статус записи (можно добавить поле restored_at)
        # record.status = "restored"
        # await self.db.commit()
        
        return {
            "success": True,
            "snapshot_id": snapshot_id,
            "target": target,
            "output": output,
        }

    async def delete_snapshot(self, snapshot_id: str) -> Dict[str, Any]:
        """
        Удаляет снапшот Kopia и запись из БД.

        Args:
            snapshot_id: ID манифеста Kopia

        Returns:
            Результат операции
        """
        from sqlalchemy import select, delete
        from app.models.backup import BackupRecord
        
        # Проверяем существование снапшота
        stmt = select(BackupRecord).where(BackupRecord.snapshot_id == snapshot_id)
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            raise ValueError(f"Snapshot {snapshot_id} not found")
        
        # Проверяем, не используется ли снапшот в активных задачах
        # (здесь можно добавить проверку связей с RestoreJob)
        
        logger.info(f"Deleting snapshot {snapshot_id}")
        
        if self.dry_run:
            return {
                "success": True,
                "dry_run": True,
                "message": f"Would delete snapshot {snapshot_id}",
                "snapshot_id": snapshot_id,
            }
        
        # Удаляем через Kopia CLI
        env = os.environ.copy()
        env["KOPIA_REPOSITORY_PASSWORD"] = self.kopia_password or ""

        # Команда kopia snapshot delete
        cmd = ["kopia", "snapshot", "delete", snapshot_id, "--delete"]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode().strip()
            logger.error(f"Delete failed: {error_msg}")
            raise RuntimeError(f"Delete failed: {error_msg}")
        
        # Удаляем запись из БД
        delete_stmt = delete(BackupRecord).where(BackupRecord.snapshot_id == snapshot_id)
        await self.db.execute(delete_stmt)
        await self.db.commit()
        
        logger.info(f"Snapshot {snapshot_id} deleted")
        
        return {
            "success": True,
            "snapshot_id": snapshot_id,
            "message": "Snapshot deleted",
        }
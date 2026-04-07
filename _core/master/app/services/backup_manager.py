import asyncio
import html
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
import json
import logging
import aiofiles
from croniter import croniter
import subprocess
import os

from app.models.service import Service
from app.services.notifier import TelegramNotifier
from app.config import settings

# Настройка логирования
logger = logging.getLogger(__name__)


class BackupManager:
    """Управление резервным копированием"""
    
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier
        self.backup_base_path = Path(settings.BACKUP_PATH)
        self.backup_base_path.mkdir(parents=True, exist_ok=True)
        
        # Restic репозиторий
        self.restic_repo = settings.RESTIC_REPOSITORY
        self.restic_password = settings.RESTIC_PASSWORD
        self.restic_scripts_path = Path("/projects/apps-service-opus/_core/backup/scripts")
    
    async def backup_service(
        self,
        service: Service,
        reason: str = "manual"
    ) -> Dict[str, Any]:
        """Создание бэкапа сервиса"""
        if not service.backup_config or not service.backup_config.enabled:
            return {"success": False, "message": "Backup disabled for this service"}

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_name = f"{service.name}_{timestamp}"
        backup_path = self.backup_base_path / service.name / backup_name
        backup_path.mkdir(parents=True, exist_ok=True)

        result = {
            "success": True,
            "backup_name": backup_name,
            "files": [],
            "databases": [],
            "errors": []
        }

        try:
            # Бэкап файлов
            if service.backup_config.paths:
                for path in service.backup_config.paths:
                    # Защита от path traversal
                    clean_path = Path(path).resolve()
                    if ".." in str(clean_path.relative_to(Path(path))):
                        result["errors"].append(f"Path traversal detected: {path}")
                        continue

                    source_path = Path("/projects/apps-service-opus/services") / service.visibility.value / service.name / path
                    if source_path.exists():
                        file_result = await self._backup_files(
                            source_path,
                            backup_path / "files" / path.lstrip("./")
                        )
                        result["files"].append(file_result)

            # Бэкап баз данных
            if service.backup_config.databases:
                for db_config in service.backup_config.databases:
                    db_result = await self._backup_database(
                        service,
                        db_config,
                        backup_path / "databases"
                    )
                    result["databases"].append(db_result)

            # Создание метаданных
            await self._save_backup_metadata(
                backup_path,
                service,
                result,
                reason
            )

            # Загрузка в Restic (если настроен)
            if self.restic_repo:
                await self._upload_to_restic(backup_path, service.name)

            # Очистка старых бэкапов
            await self._cleanup_old_backups(service)

            await self.notifier.send(
                f"✅ Backup completed: {service.name}\n"
                f"Name: {backup_name}\n"
                f"Reason: {reason}"
            )

        except Exception as e:
            result["success"] = False
            result["errors"].append(str(e))

            await self.notifier.send(
                f"❌ Backup failed: {service.name}\n"
                f"Error: {e}"
            )

        return result
    
    async def _backup_files(
        self, 
        source: Path, 
        destination: Path
    ) -> Dict[str, Any]:
        """Бэкап файлов с помощью rsync"""
        destination.parent.mkdir(parents=True, exist_ok=True)
        
        cmd = [
            "rsync", "-av", "--delete",
            str(source) + "/",
            str(destination) + "/"
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        return {
            "source": str(source),
            "destination": str(destination),
            "success": process.returncode == 0,
            "error": stderr.decode() if process.returncode != 0 else None
        }
    
    async def _backup_database(
        self, 
        service: Service,
        db_config: Dict,
        destination: Path
    ) -> Dict[str, Any]:
        """Бэкап базы данных"""
        destination.mkdir(parents=True, exist_ok=True)
        
        db_type = db_config.get("type", "postgres")
        container = db_config.get("container")
        database = db_config.get("database")
        
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        dump_file = destination / f"{database}_{timestamp}.sql"
        
        if db_type == "postgres":
            cmd = [
                "docker", "exec", f"{service.name}_{container}_1",
                "pg_dump", "-U", "postgres", database
            ]
        elif db_type == "mysql":
            cmd = [
                "docker", "exec", f"{service.name}_{container}_1",
                "mysqldump", "-u", "root", database
            ]
        else:
            return {
                "database": database,
                "success": False,
                "error": f"Unknown database type: {db_type}"
            }
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            async with aiofiles.open(dump_file, 'wb') as f:
                await f.write(stdout)

            # Сжатие
            gzip_proc = await asyncio.create_subprocess_exec(
                "gzip", str(dump_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, gzip_stderr = await gzip_proc.communicate()

            if gzip_proc.returncode != 0:
                logger.warning(f"gzip failed for {dump_file}: {gzip_stderr.decode()}")

            return {
                "database": database,
                "file": str(dump_file) + ".gz",
                "success": True
            }
        else:
            return {
                "database": database,
                "success": False,
                "error": stderr.decode()
            }
    
    async def _save_backup_metadata(
        self,
        backup_path: Path,
        service: Service,
        result: Dict[str, Any],
        reason: str
    ):
        """Сохранение метаданных бэкапа"""
        metadata = {
            "backup_name": result["backup_name"],
            "service_name": service.name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "files": result["files"],
            "databases": result["databases"],
            "success": result["success"]
        }

        metadata_file = backup_path / "metadata.json"
        async with aiofiles.open(metadata_file, 'w') as f:
            await f.write(json.dumps(metadata, indent=2))
    
    async def _upload_to_restic(self, backup_path: Path, service_name: str):
        """Загрузка бэкапа в Restic репозиторий"""
        try:
            # Подготовка окружения для Restic
            env = os.environ.copy()
            env["RESTIC_REPOSITORY"] = self.restic_repo or "/projects/apps-service-opus/backups"
            env["RESTIC_PASSWORD"] = self.restic_password or "changeit"
            
            # Запуск скрипта бэкапа
            script_path = self.restic_scripts_path / "backup.sh"
            cmd = ["bash", str(script_path), service_name, str(backup_path)]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"Restic backup failed for {service_name}: {stderr.decode()}")
            else:
                logger.info(f"Restic backup completed for {service_name}: {stdout.decode()}")
                
        except Exception as e:
            logger.error(f"Error uploading to Restic for {service_name}: {e}")
    
    async def _cleanup_old_backups(self, service: Service):
        """Очистка старых бэкапов"""
        service_backup_path = self.backup_base_path / service.name
        retention_days = service.backup_config.retention if service.backup_config else 7

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        for backup_dir in sorted(service_backup_path.iterdir()):
            if not backup_dir.is_dir():
                continue

            # Парсим дату из metadata.json вместо имени директории
            metadata_file = backup_dir / "metadata.json"
            try:
                if metadata_file.exists():
                    async with aiofiles.open(metadata_file, 'r') as f:
                        metadata = json.loads(await f.read())
                    backup_date = datetime.fromisoformat(metadata["timestamp"])
                    if backup_date.tzinfo is None:
                        backup_date = backup_date.replace(tzinfo=timezone.utc)
                else:
                    # Fallback: парсим из имени
                    date_part = backup_dir.name.rsplit("_", 1)[-1]
                    backup_date = datetime.strptime(date_part, "%Y%m%d").replace(tzinfo=timezone.utc)

                if backup_date < cutoff_date:
                    import shutil
                    shutil.rmtree(backup_dir)
                    logger.info(f"Deleted old backup: {backup_dir}")
            except Exception as e:
                logger.error(f"Error processing backup date for {backup_dir}: {e}")
    
    async def restore_service(
        self,
        service: Service,
        backup_name: str
    ) -> Dict[str, Any]:
        """Восстановление сервиса из бэкапа"""
        backup_path = self.backup_base_path / service.name / backup_name

        if not backup_path.exists():
            return {"success": False, "message": "Backup not found"}

        # Читаем метаданные
        metadata_file = backup_path / "metadata.json"
        try:
            async with aiofiles.open(metadata_file, 'r') as f:
                metadata = json.loads(await f.read())
        except (json.JSONDecodeError, IOError) as e:
            return {"success": False, "message": f"Invalid metadata: {e}"}

        result = {
            "success": True,
            "restored_files": [],
            "restored_databases": [],
            "errors": []
        }

        # Восстанавливаем файлы
        files_path = backup_path / "files"
        if files_path.exists():
            for backup_file_result in metadata.get("files", []):
                source = Path(backup_file_result["destination"])
                destination = Path(backup_file_result["source"])
                if source.exists():
                    await self._restore_files(str(source), str(destination))
                    result["restored_files"].append(str(destination))
                else:
                    result["errors"].append(f"Source not found: {source}")

        # Восстанавливаем базы данных
        db_path = backup_path / "databases"
        if db_path.exists():
            for db_file in db_path.glob("*.sql.gz"):
                # Распаковка и восстановление БД
                gunzip_proc = await asyncio.create_subprocess_exec(
                    "gunzip", "-k", str(db_file),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await gunzip_proc.communicate()

                sql_file = db_file.with_suffix("")
                if sql_file.exists():
                    # TODO: реализовать восстановление БД в зависимости от типа
                    result["restored_databases"].append(str(sql_file))

        return result
    
    async def _restore_files(self, source: str, destination: str):
        """Восстановление файлов"""
        # Реализация восстановления файлов
        logger.info(f"Would restore files from {source} to {destination}")
    
    async def list_backups(
        self,
        service: Service
    ) -> List[Dict[str, Any]]:
        """Список бэкапов сервиса"""
        service_backup_path = self.backup_base_path / service.name
        backups = []

        if not service_backup_path.exists():
            return backups

        for backup_dir in sorted(
            service_backup_path.iterdir(),
            reverse=True
        ):
            if not backup_dir.is_dir():
                continue

            metadata_file = backup_dir / "metadata.json"
            if metadata_file.exists():
                try:
                    async with aiofiles.open(metadata_file, 'r') as f:
                        metadata = json.loads(await f.read())
                    backups.append(metadata)
                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(f"Skipping corrupt backup {backup_dir}: {e}")

        return backups

    async def schedule_loop(self, services: Dict[str, Service]):
        """Цикл планового резервного копирования"""
        scheduled_runs: Dict[str, datetime] = {}

        while True:
            now = datetime.now(timezone.utc)

            for service in services.values():
                if not service.backup_config or not service.backup_config.enabled:
                    continue

                try:
                    cron = croniter(service.backup_config.schedule, now)
                    next_run = cron.get_next(datetime)

                    # Проверяем, не запускали ли уже этот run
                    run_key = f"{service.name}_{next_run.isoformat()}"
                    if next_run in scheduled_runs.values() and run_key not in [f"{s.name}_{t.isoformat()}" for s, t in scheduled_runs.items()]:
                        continue

                    # Если пора запускать бэкап (окно 60 сек)
                    if (next_run - now).total_seconds() < 60:
                        # Проверяем, не запускали ли уже
                        if scheduled_runs.get(service.name) == next_run:
                            continue
                        scheduled_runs[service.name] = next_run
                        await self.backup_service(service, reason="scheduled")
                except Exception as e:
                    logger.error(f"Error processing backup schedule for {service.name}: {e}")

            await asyncio.sleep(60)  # Проверка каждую минуту
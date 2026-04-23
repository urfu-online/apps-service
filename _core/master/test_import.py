#!/usr/bin/env python3
"""Проверка импортов для Phase 2."""
import sys
import asyncio

async def test_imports():
    """Проверяем, что все модули импортируются без ошибок."""
    print("Testing imports...")
    
    # Импорты из Phase 2
    try:
        from app.services.kopia_backup_manager import KopiaBackupManager
        print("✓ KopiaBackupManager imported")
    except Exception as e:
        print(f"✗ KopiaBackupManager import failed: {e}")
        return False
    
    try:
        from app.services.notifier import AppriseNotifier
        print("✓ AppriseNotifier imported")
    except Exception as e:
        print(f"✗ AppriseNotifier import failed: {e}")
        return False
    
    try:
        from app.core.events import backup_scheduler, get_due_backup_services
        print("✓ backup_scheduler imported")
    except Exception as e:
        print(f"✗ backup_scheduler import failed: {e}")
        return False
    
    try:
        from app.core.database import AsyncSessionLocal, async_engine
        print("✓ Async database imports")
    except Exception as e:
        print(f"✗ Async database import failed: {e}")
        return False
    
    print("All imports successful!")
    return True

if __name__ == "__main__":
    success = asyncio.run(test_imports())
    sys.exit(0 if success else 1)
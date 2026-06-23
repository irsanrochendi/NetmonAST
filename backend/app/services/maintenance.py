"""Maintenance Window service — suppresses alerts during scheduled maintenance."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import MaintenanceWindow

logger = logging.getLogger("maintenance")


class MaintenanceService:
    """Check if a device is currently in maintenance window."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def is_in_maintenance(self, device_id: int) -> bool:
        """Check if a specific device is currently in an active maintenance window."""
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(MaintenanceWindow).where(
                and_(
                    MaintenanceWindow.start_time <= now,
                    MaintenanceWindow.end_time >= now,
                    or_(
                        MaintenanceWindow.device_id == device_id,
                        MaintenanceWindow.device_id.is_(None),  # Global maintenance
                    ),
                )
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_active_windows(self) -> list[MaintenanceWindow]:
        """Get all currently active maintenance windows."""
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(MaintenanceWindow).where(
                and_(
                    MaintenanceWindow.start_time <= now,
                    MaintenanceWindow.end_time >= now,
                )
            )
        )
        return result.scalars().all()

    async def create_window(
        self,
        name: str,
        start_time: datetime,
        end_time: datetime,
        device_id: Optional[int] = None,
        description: Optional[str] = None,
    ) -> MaintenanceWindow:
        """Create a new maintenance window."""
        window = MaintenanceWindow(
            name=name,
            start_time=start_time,
            end_time=end_time,
            device_id=device_id,
            description=description,
        )
        self.session.add(window)
        await self.session.commit()
        await self.session.refresh(window)
        logger.info(
            "Maintenance window created: %s (%s → %s, device_id=%s)",
            name, start_time, end_time, device_id,
        )
        return window

    async def delete_window(self, window_id: int) -> bool:
        """Delete a maintenance window."""
        window = await self.session.get(MaintenanceWindow, window_id)
        if not window:
            return False
        await self.session.delete(window)
        await self.session.commit()
        logger.info("Maintenance window deleted: %s (id=%d)", window.name, window_id)
        return True

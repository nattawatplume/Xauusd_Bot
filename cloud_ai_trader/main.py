"""Application entrypoint for Cloud AI Trader."""
from __future__ import annotations

import asyncio
import logging
import uvicorn

from config import settings
from bridge.api import app, brain

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("ai_trader.main")


async def scheduled_daily_review_loop() -> None:
    """Background task running the daily review once per day at DAILY_REVIEW_HOUR."""
    from datetime import datetime, timezone

    last_reviewed_day = -1
    while True:
        try:
            now = datetime.now(timezone.utc)
            if now.hour == settings.DAILY_REVIEW_HOUR and now.day != last_reviewed_day:
                if brain is not None:
                    log.info("Triggering scheduled daily review at UTC hour %d", now.hour)
                    await brain.run_daily_review()
                    last_reviewed_day = now.day
        except Exception as exc:
            log.error("Error in scheduled review loop: %s", exc)

        await asyncio.sleep(60)  # Check every minute


@app.on_event("startup")
async def start_background_schedulers() -> None:
    asyncio.create_task(scheduled_daily_review_loop())


def main() -> None:
    log.info(
        "Starting Cloud AI Trader on %s:%d (ShadowMode=%s, LLM=%s)",
        settings.HOST,
        settings.PORT,
        settings.SHADOW_MODE,
        settings.LLM_MODEL,
    )
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()

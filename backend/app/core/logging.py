import logging
import sys
from types import FrameType

from loguru import logger


class InterceptHandler(logging.Handler):
    """把 stdlib logging（uvicorn 等）重定向到 loguru。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = str(record.levelno)

        frame: FrameType | None = sys._getframe(6)  # noqa: SLF001
        depth = 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(debug: bool = False) -> None:
    logger.remove()
    logger.configure(extra={"trace_id": "-"})
    logger.add(
        sys.stdout,
        level="DEBUG" if debug else "INFO",
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <7}</level> | "
            "{extra[trace_id]} | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - {message}"
        ),
    )
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

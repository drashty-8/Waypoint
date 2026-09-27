import logging


logger = logging.getLogger(__name__)


def trigger_tagging(photo_id: int) -> None:
    """Placeholder for photo tagging.

    The real version (SCRUM-34) will send the photo to Claude, then fill
    in the row's description and tags and set tagging_status. For now it
    only logs that it was called.
    """
    logger.info("Tagging not implemented yet (SCRUM-34); skipping photo %s", photo_id)

"""Resilient file access.

On platforms with an ephemeral filesystem (Render Free, most serverless PaaS)
the uploaded file bytes on disk are wiped whenever the service restarts/cold-
starts, even though the database row (and the BLOB we store in it) survives.

``materialize_file`` always returns a usable on-disk path:
  * if the file still exists on disk, return it as-is;
  * otherwise restore it from the stored BLOB (``File.data``) back to its
    original ``storage_path`` and return that.
"""
import os
import logging

logger = logging.getLogger(__name__)


def materialize_file(file) -> str:
    path = getattr(file, "storage_path", None)
    if path and os.path.exists(path):
        return path

    data = getattr(file, "data", None)
    if not path or data is None:
        # Nothing we can do — caller will handle the missing file gracefully.
        return path

    try:
        parent = os.path.dirname(path) or "."
        os.makedirs(parent, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        logger.info("Restored file %s (%d bytes) from DB BLOB", path, len(data))
        return path
    except Exception as e:
        logger.warning("Failed to restore file from BLOB (%s): %s", path, e)
        return path

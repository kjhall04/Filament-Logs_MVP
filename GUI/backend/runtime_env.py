import os

from backend.config import WRITABLE_DATA_DIR


def is_serverless_runtime():
    return os.getenv("VERCEL") == "1" or bool(os.getenv("VERCEL_ENV"))


def runtime_storage_summary():
    return {
        "serverless": is_serverless_runtime(),
        "writable_data_dir": WRITABLE_DATA_DIR,
    }

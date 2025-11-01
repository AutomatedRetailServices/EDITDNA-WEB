# tasks.py — Web API task adapter for Render side
# This bridges the web server to the worker.

import os
import json
from redis import Redis
from rq import Queue
from worker import tasks as jobs  # ✅ Correct import path

def job_render(data):
    """Entry point for job execution from web -> worker."""
    return jobs.job_render(data)

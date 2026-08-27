"""Define safe application errors translated at the scheduler boundary."""


class CrawlerWorkflowError(RuntimeError):
    """Safe application-level failure translated at the scheduler boundary."""

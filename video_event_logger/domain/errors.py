class VideoEventLoggerError(Exception):
    """Base application/domain error for expected user-flow failures."""


class NoAnnotationDocumentError(VideoEventLoggerError):
    pass


class MissingIntervalStartError(VideoEventLoggerError):
    pass


class InvalidIntervalError(VideoEventLoggerError):
    pass


class InvalidIntervalIndexError(VideoEventLoggerError):
    pass

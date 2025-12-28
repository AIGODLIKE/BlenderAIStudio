class StudioException(Exception):
    """Base class for exceptions in this module."""


class NotLoggedInException(StudioException):
    """
    Raised when the user is not logged in.
    """

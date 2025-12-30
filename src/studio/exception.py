class StudioException(Exception):
    """Base class for exceptions in this module."""


class NotLoggedInException(StudioException):
    """
    Raised when the user is not logged in.
    """


class InsufficientBalanceException(StudioException):
    """
    Raised when the user's balance is insufficient.
    """


class APIRequestException(StudioException):
    """
    Raised when the API request failed.
    """


class AuthFailedException(StudioException):
    """
    Raised when the authentication failed.
    """


class ToeknExpiredException(StudioException):
    """
    Raised when the token is expired.
    """

class StudioException(Exception):
    """Base class for exceptions in this module."""


class NotLoggedInException(StudioException):
    """
    Raised when the user is not logged in.
    """


class ParameterValidationException(StudioException):
    """
    Raised when the parameter validation failed.
    """


class RedeemCodeException(StudioException):
    """
    Raised when the redeem code is invalid.
    """


class InsufficientBalanceException(StudioException):
    """
    Raised when the user's balance is insufficient.
    """


class DatabaseUpdateException(StudioException):
    """
    Raised when the database update failed.
    """


class InternalException(StudioException):
    """
    Raised when the internal server error.
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

from typing import Any, Literal

ErrorCode = Literal[
    'VALIDATION',
    'UNAUTHORIZED',
    'FORBIDDEN',
    'NOT_FOUND',
    'CONFLICT',
    'LOT_NOT_STARTED',
    'LOT_ENDED',
    'LOT_CANCELLED',
    'BID_TOO_LOW',
    'ALREADY_LEADING',
    'INSUFFICIENT_FUNDS',
    'UPSTREAM_UNAVAILABLE',
    'AUCTIONEER_CANNOT_BID',
    'LOT_NOT_CANCELLABLE',
    'LOT_HAS_BIDS',
    'IMAGE_UNAVAILABLE',
    'ITEM_WITHOUT_IMAGE',
]

HTTP_STATUS: dict[str, int] = {
    'VALIDATION': 400,
    'UNAUTHORIZED': 401,
    'FORBIDDEN': 403,
    'NOT_FOUND': 404,
    'CONFLICT': 409,
    'LOT_NOT_STARTED': 409,
    'LOT_ENDED': 409,
    'LOT_CANCELLED': 409,
    'BID_TOO_LOW': 422,
    'ALREADY_LEADING': 409,
    'INSUFFICIENT_FUNDS': 422,
    'UPSTREAM_UNAVAILABLE': 502,
    'AUCTIONEER_CANNOT_BID': 403,
    'LOT_NOT_CANCELLABLE': 409,
    'LOT_HAS_BIDS': 409,
    'IMAGE_UNAVAILABLE': 503,
    'ITEM_WITHOUT_IMAGE': 422,
}


class AppError(Exception):
    def __init__(self, code: ErrorCode, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    @property
    def status(self) -> int:
        return HTTP_STATUS[self.code]

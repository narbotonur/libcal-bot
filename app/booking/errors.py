class BookingError(Exception):
    pass


class NoSlotsFoundError(BookingError):
    pass


class BookingFormError(BookingError):
    pass


class SiteChangedError(BookingError):
    pass
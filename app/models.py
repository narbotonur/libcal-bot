from pydantic import BaseModel, Field


class BookingRequest(BaseModel):
    date: str
    start_time: str
    hours: int = Field(ge=1, le=3)


class BookingResult(BaseModel):
    success: bool
    message: str
    room_name: str | None = None
    booked_start: str | None = None
    booked_end: str | None = None
    confirmation_text: str | None = None
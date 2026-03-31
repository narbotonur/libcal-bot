import argparse
import re
from app.models import BookingRequest


DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_PATTERN = re.compile(r"^\d{2}:\d{2}$")


def _validate_date(value: str) -> str:
    value = value.strip()
    if not DATE_PATTERN.match(value):
        raise argparse.ArgumentTypeError("Date must be in YYYY-MM-DD format.")
    return value


def _validate_time(value: str) -> str:
    value = value.strip()
    if not TIME_PATTERN.match(value):
        raise argparse.ArgumentTypeError("Time must be in HH:MM format.")
    hh, mm = value.split(":")
    hh_i = int(hh)
    mm_i = int(mm)
    if not (0 <= hh_i <= 23 and mm_i in {0, 30}):
        raise argparse.ArgumentTypeError("Time must be valid and use 30-minute steps, e.g. 14:00 or 14:30.")
    return value


def _validate_hours(value: str) -> int:
    try:
        hours = int(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError("Hours must be an integer.") from e

    if hours < 1 or hours > 3:
        raise argparse.ArgumentTypeError("Hours must be between 1 and 3.")
    return hours


def _interactive_prompt() -> BookingRequest:
    while True:
        date = input("Enter date (YYYY-MM-DD): ").strip()
        if DATE_PATTERN.match(date):
            break
        print("Invalid date format.")

    while True:
        start_time = input("Enter start time (HH:MM, 30-minute step): ").strip()
        if TIME_PATTERN.match(start_time):
            hh, mm = start_time.split(":")
            hh_i = int(hh)
            mm_i = int(mm)
            if 0 <= hh_i <= 23 and mm_i in {0, 30}:
                break
        print("Invalid time. Example: 14:00 or 14:30")

    while True:
        hours_raw = input("Enter hours (1-3): ").strip()
        try:
            hours = int(hours_raw)
            if 1 <= hours <= 3:
                break
        except ValueError:
            pass
        print("Hours must be 1, 2, or 3.")

    return BookingRequest(
        date=date,
        start_time=start_time,
        hours=hours,
    )


def get_booking_request_from_cli() -> BookingRequest:
    parser = argparse.ArgumentParser(description="NU Library room booking bot")
    parser.add_argument("--date", type=_validate_date, help="Date in YYYY-MM-DD format")
    parser.add_argument("--time", type=_validate_time, help="Start time in HH:MM format")
    parser.add_argument("--hours", type=_validate_hours, help="Duration in hours (1-3)")

    args = parser.parse_args()

    if args.date and args.time and args.hours:
        return BookingRequest(
            date=args.date,
            start_time=args.time,
            hours=args.hours,
        )

    return _interactive_prompt()
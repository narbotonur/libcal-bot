from app.config import load_config
from app.cli import get_booking_request_from_cli
from app.booking.libcal_bot import LibCalBot


def validate_user_profile(config):
    missing = []

    if not config.first_name:
        missing.append("USER_FIRST_NAME")
    if not config.last_name:
        missing.append("USER_LAST_NAME")
    if not config.email:
        missing.append("USER_EMAIL")
    if not config.id_card:
        missing.append("USER_ID_CARD")
    if not config.department:
        missing.append("USER_DEPARTMENT")
    if not config.purpose:
        missing.append("USER_PURPOSE")

    if missing:
        raise ValueError(
            "Missing required values in .env: " + ", ".join(missing)
        )


def main():
    config = load_config()
    validate_user_profile(config)

    request = get_booking_request_from_cli()
    bot = LibCalBot(config)
    result = bot.run(request)

    print("\n=== RESULT ===")
    print(f"Success: {result.success}")
    print(f"Message: {result.message}")

    if result.room_name:
        print(f"Room: {result.room_name}")
    if result.booked_start and result.booked_end:
        print(f"Time: {result.booked_start} - {result.booked_end}")
    if result.confirmation_text:
        print("\nConfirmation:")
        print(result.confirmation_text)


if __name__ == "__main__":
    main()
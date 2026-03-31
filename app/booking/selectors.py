class Selectors:
    # ===== GRID / TABLE =====
    GRID_TABLE_CANDIDATES = [
        "table",
        ".s-lc-rm-tg-tb",
        ".table",
    ]

    SPACE_NAME_CELL = "td:first-child"

    # ===== DATE =====
    DATE_PICKER_CANDIDATES = [
        'input[type="date"]',
        'input[name*="date"]',
        'input[id*="date"]',
    ]

    GO_TO_DATE_BUTTON_CANDIDATES = [
        'button:has-text("Go To Date")',
        'a:has-text("Go To Date")',
    ]

    DATEPOPUP_CANDIDATES = [
        ".datepicker",
        ".ui-datepicker",
        ".bootstrap-datetimepicker-widget",
        '[role="dialog"]',
    ]

    CALENDAR_NEXT_CANDIDATES = [
        '.datepicker-days th.next',
        '.next',
        'th.next',
        'button[aria-label*="Next"]',
        'button[title*="Next"]',
    ]

    CALENDAR_PREV_CANDIDATES = [
        '.datepicker-days th.prev',
        '.prev',
        'th.prev',
        'button[aria-label*="Prev"]',
        'button[title*="Prev"]',
    ]

    CALENDAR_MONTH_LABEL_CANDIDATES = [
        '.datepicker-days th.datepicker-switch',
        '.datepicker-switch',
        'th.datepicker-switch',
    ]

    # ===== SLOT SELECTION =====
    SUBMIT_TIMES_CANDIDATES = [
        'button:has-text("Submit Times")',
        'input[value="Submit Times"]',
        'button.btn-info',
    ]

    # ===== POLICY =====
    CONTINUE_CANDIDATES = [
        'button:has-text("Continue")',
        'a:has-text("Continue")',
    ]

    # ===== FORM =====
    FIRST_NAME_CANDIDATES = [
        'input[placeholder="First Name"]',
        'input[name*="first"]',
        'input[id*="first"]',
    ]

    LAST_NAME_CANDIDATES = [
        'input[placeholder="Last Name"]',
        'input[name*="last"]',
        'input[id*="last"]',
    ]

    EMAIL_CANDIDATES = [
        'input[type="email"]',
        'input[name*="email"]',
        'input[id*="email"]',
    ]

    ID_CARD_CANDIDATES = [
        'input[name*="card"]',
        'input[id*="card"]',
        'input[name*="id"]',
        'input[id*="id"]',
    ]

    DEPARTMENT_CANDIDATES = [
        'input[name*="department"]',
        'input[id*="department"]',
        'input[name*="school"]',
        'input[id*="school"]',
    ]

    PURPOSE_CANDIDATES = [
        'textarea[name*="purpose"]',
        'textarea[id*="purpose"]',
        'textarea',
    ]

    SUBMIT_BOOKING_CANDIDATES = [
        'button:has-text("Submit my Booking")',
        'button:has-text("Submit My Booking")',
        'button:has-text("Submit")',
        'input[type="submit"]',
    ]

    SUCCESS_CANDIDATES = [
        'text=/confirmed/i',
        'text=/success/i',
        '.alert-success',
        '.s-lc-rm-success',
    ]
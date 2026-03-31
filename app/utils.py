from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError


def first_visible_locator(page: Page, selectors: list[str], timeout: int = 1500):
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            locator.wait_for(state="visible", timeout=timeout)
            return locator
        except PlaywrightTimeoutError:
            continue
    return None


def click_first_visible(page: Page, selectors: list[str], timeout: int = 1500) -> bool:
    locator = first_visible_locator(page, selectors, timeout)
    if locator is None:
        return False
    locator.click()
    return True


def text_or_empty(locator) -> str:
    try:
        return locator.inner_text().strip()
    except Exception:
        return ""


def normalize_room_name(name: str) -> str:
    return " ".join(name.split()).strip()


def time_to_minutes(value: str) -> int:
    hh, mm = value.split(":")
    return int(hh) * 60 + int(mm)


def minutes_to_time(total_minutes: int) -> str:
    hh = total_minutes // 60
    mm = total_minutes % 60
    return f"{hh:02d}:{mm:02d}"


def add_30_minutes(value: str) -> str:
    return minutes_to_time(time_to_minutes(value) + 30)


def generate_needed_times(start_time: str, hours: int) -> list[str]:
    slots_needed = hours * 2
    times = []
    current = start_time
    for _ in range(slots_needed):
        times.append(current)
        current = add_30_minutes(current)
    return times
import io
import re
from dataclasses import dataclass
from datetime import datetime

from PIL import Image
from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
    Page,
)

from app.booking.errors import (
    BookingFormError,
    NoSlotsFoundError,
    SiteChangedError,
)
from app.booking.selectors import Selectors
from app.models import BookingRequest, BookingResult
from app.utils import (
    add_30_minutes,
    click_first_visible,
    first_visible_locator,
    normalize_room_name,
)


@dataclass
class SlotCandidate:
    room_name: str
    start_time: str
    slot_index: int
    click_x: float
    click_y: float
    hour_width: float  # Добавили ширину часа для смещения кликов
    hours: int         # Добавили количество часов (кликов)


class LibCalBot:
    def __init__(self, config):
        self.config = config

    def run(self, request: BookingRequest) -> BookingResult:
        with sync_playwright() as p:
            # Используем максимальное разрешение
            browser = p.chromium.launch(headless=self.config.headless)
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = context.new_page()
            page.set_default_timeout(self.config.timeout_ms)

            try:
                print("[1/8] Opening booking page...")
                self._open_page(page)

                print("[2/8] Validating booking time range...")
                self._validate_booking_window(request)

                print(f"[3/8] Setting date {request.date}...")
                self._set_date(page, request.date)

                # --- ЛОГИКА: КЛИК ПО 12:00PM И СТРЕЛКИ ---
                print("[Action] Finding 12:00pm header to focus...")
                
                # Ищем заголовок с 12:00pm. В LibCal они обычно в <th> или <span>
                # Используем селектор :has-text, чтобы найти нужную колонку
                time_header = page.locator('th:has-text("12:00pm"), .s-lc-rm-td-time:has-text("12:00pm")').first
                
                try:
                    if time_header.is_visible(timeout=3000):
                        time_header.click()
                        print("Focused on 12:00pm header.")
                    else:
                        # Если не нашли 12:00pm, кликаем просто по первому попавшемуся заголовку времени
                        page.locator('.s-lc-rm-tg-th').first.click()
                except Exception:
                    # Фолбек: клик в левую часть сетки, если поиск текста упал
                    page.mouse.click(400, 300) 

                page.wait_for_timeout(500)

                print("[Action] Pressing ArrowRight 12 times...")
                for _ in range(12):
                    page.keyboard.press("ArrowRight")
                    page.wait_for_timeout(200)
                
                # Ждем, чтобы сайт "прожевал" прокрутку и обновил координаты
                page.wait_for_timeout(1000)
                # -----------------------------------------

                print("[4/8] Finding first suitable room from top to bottom...")
                slot = self._find_best_slot(page, request)

                print(f"[5/8] Selecting room {slot.room_name} at {slot.start_time} for {request.hours} hours...")
                self._select_slot_by_coordinates(page, slot)

                print("[6/8] Clicking Submit Times...")
                self._submit_times(page)

                print("[7/8] Accepting policy page...")
                self._continue_policy(page)

                print("[8/8] Filling and submitting booking form...")
                self.fill_booking_form(page)
                self.submit_final_form(page)

                confirmation_text = self.extract_confirmation(page)
                booked_end = self._calculate_end_time(slot.start_time, request.hours)

                browser.close()
                return BookingResult(
                    success=True,
                    message="Booking submitted successfully.",
                    room_name=slot.room_name,
                    booked_start=slot.start_time,
                    booked_end=booked_end,
                    confirmation_text=confirmation_text,
                )

            except Exception as e:
                try:
                    page.screenshot(path="debug_error.png", full_page=True)
                except Exception:
                    pass

                browser.close()
                return BookingResult(success=False, message=str(e))

    # -------------------------
    # Navigation
    # -------------------------

    def _open_page(self, page: Page) -> None:
        page.goto(self.config.base_url, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")

        grid = self._find_grid_table(page)
        if grid is None:
            raise SiteChangedError("Booking grid table was not found on the page.")

        try:
            page.screenshot(path="debug_01_home.png", full_page=True)
        except Exception:
            pass

    def _validate_booking_window(self, request: BookingRequest) -> None:
        start_minutes = self._hhmm_to_minutes(request.start_time)
        end_minutes = start_minutes + request.hours * 60

        if start_minutes < 9 * 60:
            raise NoSlotsFoundError("Booking cannot start earlier than 09:00.")
        if end_minutes > 19 * 60:
            raise NoSlotsFoundError("Booking must end no later than 19:00.")

    def _set_date(self, page: Page, target_date: str) -> None:
        target = datetime.strptime(target_date, "%Y-%m-%d")
        target_day = target.day
        target_month_year = target.strftime("%B %Y")

        date_input = first_visible_locator(
            page,
            Selectors.DATE_PICKER_CANDIDATES,
            timeout=1500,
        )

        if date_input is not None:
            try:
                date_input.fill(target_date)
                date_input.press("Enter")
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(1000)
                try:
                    page.screenshot(path="debug_02_date_set_direct.png", full_page=True)
                except Exception:
                    pass
                return
            except Exception:
                pass

        clicked = click_first_visible(
            page,
            Selectors.GO_TO_DATE_BUTTON_CANDIDATES,
            timeout=3000,
        )
        if not clicked:
            raise SiteChangedError("Go To Date button not found.")

        page.wait_for_timeout(1000)

        popup = first_visible_locator(page, Selectors.DATEPOPUP_CANDIDATES, timeout=3000)
        if popup is None:
            raise SiteChangedError("Calendar popup not detected.")

        for _ in range(12):
            label_locator = first_visible_locator(
                page,
                Selectors.CALENDAR_MONTH_LABEL_CANDIDATES,
                timeout=1500,
            )

            if label_locator is None:
                raise SiteChangedError("Calendar month label not found.")

            current_label = label_locator.inner_text().strip()
            if current_label.lower() == target_month_year.lower():
                break

            next_btn = first_visible_locator(
                page,
                Selectors.CALENDAR_NEXT_CANDIDATES,
                timeout=1500,
            )
            if next_btn is None:
                raise SiteChangedError("Calendar next-month button not found.")

            next_btn.click()
            page.wait_for_timeout(500)
        else:
            raise SiteChangedError(f"Could not navigate calendar to {target_month_year}.")

        day_clicked = False
        candidates = [
            f'//td[not(contains(@class,"old")) and not(contains(@class,"new")) and normalize-space(text())="{target_day}"]',
            f'//span[not(contains(@class,"old")) and not(contains(@class,"new")) and normalize-space(text())="{target_day}"]',
            f'//button[normalize-space(text())="{target_day}"]',
        ]

        for xpath in candidates:
            loc = page.locator(f"xpath={xpath}").first
            try:
                loc.wait_for(state="visible", timeout=1000)
                loc.click()
                day_clicked = True
                break
            except Exception:
                continue

        if not day_clicked:
            raise SiteChangedError(f"Could not click day {target_day} in calendar popup.")

        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)

        try:
            page.screenshot(path="debug_02_date_set.png", full_page=True)
        except Exception:
            pass

    # -------------------------
    # Grid + image
    # -------------------------

    def _find_grid_table(self, page: Page):
        for selector in Selectors.GRID_TABLE_CANDIDATES:
            locator = page.locator(selector).first
            try:
                locator.wait_for(state="visible", timeout=2000)
                text = locator.inner_text().lower()
                if "space" in text and any(x in text for x in ["9:00am", "10:00am", "11:00am", "12:00pm"]):
                    return locator
            except Exception:
                continue
        return None

    def _extract_header_times(self, grid) -> list[str]:
        text = grid.evaluate(
            """
            (grid) => {
                const nodes = Array.from(grid.querySelectorAll('thead th, th'));
                return nodes.map(n => (n.textContent || '').trim().toLowerCase()).join(' | ');
            }
            """
        )
        tokens = re.findall(r"\b\d{1,2}:\d{2}(?:am|pm)\b", text)
        return [self._convert_ampm_to_24h(t) for t in tokens]

    def _extract_header_positions(self, grid):
        data = grid.evaluate(
            """
            (grid) => {
                const nodes = Array.from(grid.querySelectorAll('thead th, th'));
                return nodes.map((th) => {
                    const txt = (th.textContent || '').trim().toLowerCase();
                    const rect = th.getBoundingClientRect();
                    return {
                        text: txt,
                        left: rect.left,
                        right: rect.right,
                        center: rect.left + rect.width / 2,
                        width: rect.width
                    };
                });
            }
            """
        )

        out = []
        for item in data:
            txt = item["text"]
            if re.match(r"^\d{1,2}:\d{2}(am|pm)$", txt):
                out.append(
                    {
                        "time": self._convert_ampm_to_24h(txt),
                        "left": item["left"],
                        "right": item["right"],
                        "center": item["center"],
                        "width": item["width"],
                    }
                )
        return out

    def _extract_room_rows(self, grid):
        rows = []
        all_rows = grid.locator("tbody tr")
        count = all_rows.count()

        for i in range(count):
            row = all_rows.nth(i)
            try:
                room_name_raw = row.locator(Selectors.SPACE_NAME_CELL).inner_text().strip()
                bbox = row.bounding_box()
            except Exception:
                continue

            room_name = normalize_room_name(room_name_raw)
            if not room_name or not bbox:
                continue

            rows.append(
                {
                    "room_name": room_name,
                    "row_locator": row,
                    "top": bbox["y"],
                    "bottom": bbox["y"] + bbox["height"],
                    "height": bbox["height"],
                    "order": i,
                }
            )
        return rows

    def _convert_ampm_to_24h(self, value: str) -> str:
        match = re.match(r"^(\d{1,2}):(\d{2})(am|pm)$", value.strip().lower())
        if not match:
            raise ValueError(f"Invalid time header format: {value}")

        hh = int(match.group(1))
        mm = int(match.group(2))
        ampm = match.group(3)

        if ampm == "am" and hh == 12: hh = 0
        elif ampm == "pm" and hh != 12: hh += 12

        return f"{hh:02d}:{mm:02d}"

    def _time_to_slot_index(self, header_times: list[str], target_time: str):
        if not header_times: return None
        first_minutes = self._hhmm_to_minutes(header_times[0])
        target_minutes = self._hhmm_to_minutes(target_time)
        diff = target_minutes - first_minutes
        if diff < 0 or diff % 30 != 0: return None
        return diff // 30

    def _hhmm_to_minutes(self, value: str) -> int:
        hh, mm = value.split(":")
        return int(hh) * 60 + int(mm)

    def _take_grid_image(self, grid) -> tuple[Image.Image, dict]:
        bbox = grid.bounding_box()
        if not bbox: raise SiteChangedError("Could not get bounding box for grid.")
        png = grid.screenshot()
        image = Image.open(io.BytesIO(png)).convert("RGB")
        return image, bbox

    def _is_green_pixel(self, r: int, g: int, b: int) -> bool:
        return (45 <= r <= 105 and 135 <= g <= 200 and 45 <= b <= 110)

    def _is_red_pixel(self, r: int, g: int, b: int) -> bool:
        return (150 <= r <= 255 and 20 <= g <= 140 and 20 <= b <= 140)

    def _cell_color_ratio(self, image: Image.Image, x0: int, y0: int, x1: int, y1: int):
        width, height = image.size
        x0, x1 = max(0, min(width - 1, x0)), max(0, min(width, x1))
        y0, y1 = max(0, min(height - 1, y0)), max(0, min(height, y1))
        if x1 <= x0 or y1 <= y0: return 0.0, 0.0
        total, green, red = 0, 0, 0
        step_x, step_y = max(1, (x1 - x0) // 10), max(1, (y1 - y0) // 6)
        for yy in range(y0, y1, step_y):
            for xx in range(x0, x1, step_x):
                r, g, b = image.getpixel((xx, yy))
                total += 1
                if self._is_green_pixel(r, g, b): green += 1
                elif self._is_red_pixel(r, g, b): red += 1
        return (green / total, red / total) if total > 0 else (0.0, 0.0)

    def _extract_available_indices_for_row(self, grid_img: Image.Image, grid_bbox: dict, row, header_positions) -> dict[int, bool]:
        result = {}
        if len(header_positions) < 2: return result
        avg_hour_width = (header_positions[1]["center"] - header_positions[0]["center"])
        half_hour_width = avg_hour_width / 2.0
        first_center = header_positions[0]["center"]
        row_top = int(row["top"] - grid_bbox["y"])
        row_bottom = int(row["bottom"] - grid_bbox["y"])
        y0, y1 = row_top + 2, row_bottom - 2

        for slot_index in range(48):
            center_x_img = (first_center + slot_index * half_hour_width) - grid_bbox["x"]
            x0, x1 = int(center_x_img - half_hour_width / 2 + 2), int(center_x_img + half_hour_width / 2 - 2)
            green_ratio, red_ratio = self._cell_color_ratio(grid_img, x0, y0, x1, y1)
            if green_ratio > 0.20 and red_ratio < 0.08:
                result[slot_index] = True
        return result

    # -------------------------
    # Slot logic
    # -------------------------

    def _find_best_slot(self, page: Page, request: BookingRequest) -> SlotCandidate:
        grid = self._find_grid_table(page)
        if grid is None: raise SiteChangedError("Grid not found.")
        header_times = self._extract_header_times(grid)
        header_positions = self._extract_header_positions(grid)
        if not header_times or not header_positions: raise SiteChangedError("Headers missing.")
        
        start_index = self._time_to_slot_index(header_times, request.start_time)
        if start_index is None: raise NoSlotsFoundError(f"Time {request.start_time} out of range.")

        grid_img, grid_bbox = self._take_grid_image(grid)
        needed_slots = request.hours * 2
        
        # Расчет ширины для клика
        avg_hour_width = header_positions[1]["center"] - header_positions[0]["center"]
        half_hour_width = avg_hour_width / 2.0
        first_center = header_positions[0]["center"]

        for row in sorted(self._extract_room_rows(grid), key=lambda r: r["order"]):
            available_map = self._extract_available_indices_for_row(grid_img, grid_bbox, row, header_positions)
            if all((start_index + o) in available_map for o in range(needed_slots)):
                # Смещение -1 пиксель, чтобы точно не попасть на правую границу
                click_x = first_center + (start_index * half_hour_width) - 1
                click_y = row["top"] + (row["height"] / 2)
                
                # Возвращаем кандидата со всеми необходимыми данными для серии кликов
                return SlotCandidate(
                    room_name=row["room_name"],
                    start_time=request.start_time,
                    slot_index=start_index,
                    click_x=click_x,
                    click_y=click_y,
                    hour_width=avg_hour_width,  # <-- Передаем ширину одного часа
                    hours=request.hours         # <-- Передаем запрошенное количество часов
                )

        raise NoSlotsFoundError(f"No slots found for {request.hours}h starting at {request.start_time}")

    def _select_slot_by_coordinates(self, page: Page, slot: SlotCandidate) -> None:
        print(f"[DEBUG] Starting click sequence for {slot.hours} hours.")
        
        # 1. Находим саму строку комнаты, чтобы она не убегала при скролле
        # Ищем по тексту названия комнаты (например, "5E.425")
        room_row = page.locator(f"text={slot.room_name}").first

        for i in range(slot.hours):
            # Рассчитываем X для каждого часа (13:00 -> 14:00 -> 15:00)
            current_x = slot.click_x + (i * slot.hour_width)
            
            try:
                # ВАЖНО: Перед каждым кликом возвращаем фокус на строку комнаты
                # Это предотвращает "прыжки" страницы вниз к кнопке Submit
                room_row.scroll_into_view_if_needed()
                page.wait_for_timeout(300) 

                # Кликаем по координатам
                page.mouse.move(current_x, slot.click_y)
                page.mouse.click(current_x, slot.click_y)
                
                print(f"      [Step {i+1}/{slot.hours}] Clicked hour slot at X: {current_x:.2f}")
                
                # Ждем чуть дольше, чтобы LibCal успел переварить выбор
                page.wait_for_timeout(1500) 
                
            except Exception as e:
                print(f"      [!] Click {i+1} failed: {e}")
                # Если один клик упал, пробуем продолжать
                continue

        print("[DEBUG] Sequence finished. Looking for Submit button...")
        page.wait_for_timeout(1000)
        
    def _submit_times(self, page: Page) -> None:
        if not click_first_visible(page, Selectors.SUBMIT_TIMES_CANDIDATES, timeout=5000):
            raise SiteChangedError("Submit Times button not found.")
        page.wait_for_load_state("networkidle")

    def _continue_policy(self, page: Page) -> None:
        if click_first_visible(page, Selectors.CONTINUE_CANDIDATES, timeout=5000):
            page.wait_for_load_state("networkidle")

    # -------------------------
    # Form filling (FIXED FOR NU)
    # -------------------------

    def fill_booking_form(self, page: Page) -> None:
        def try_fill(locator_strings, value, timeout=1500):
            for sel in locator_strings:
                try:
                    loc = page.locator(sel).first
                    loc.wait_for(state="visible", timeout=timeout)
                    loc.fill("") # Очистка перед вводом
                    loc.type(value, delay=30) # Эмуляция печати для надежности
                    return True
                except Exception:
                    continue
            return False

        filled = {}
        filled["first_name"] = try_fill(['input[id="fname"]', 'input[name="fname"]', 'input[id*="first"]'], self.config.first_name)
        filled["last_name"] = try_fill(['input[id="lname"]', 'input[name="lname"]', 'input[id*="last"]'], self.config.last_name)
        filled["email"] = try_fill(['input[id="email"]', 'input[type="email"]'], self.config.email)

        # Специфичные для NU селекторы (q1, q2, q3 часто используются в LibCal для доп. полей)
        filled["id_card"] = try_fill([
            'input[id="q1"]', 'input[aria-label*="ID card" i]', 'label:has-text("ID card") + div input'
        ], self.config.id_card)

        filled["department"] = try_fill([
            'input[id="q2"]', 'input[aria-label*="School" i]', 'label:has-text("School") + div input'
        ], self.config.department)

        filled["purpose"] = try_fill([
            'textarea[id="q3"]', 'textarea[aria-label*="Purpose" i]', 'label:has-text("Purpose") + div textarea'
        ], self.config.purpose)

        missing = [k for k, v in filled.items() if not v]
        if missing:
            page.screenshot(path="debug_form_error.png")
            raise BookingFormError(f"Missing fields: {', '.join(missing)}")

    def submit_final_form(self, page: Page) -> None:
        candidates = ['button:has-text("Submit my Booking")', 'button:has-text("Submit")', 'input[type="submit"]']
        for sel in candidates:
            try:
                btn = page.locator(sel).first
                btn.wait_for(state="visible", timeout=2000)
                btn.click()
                page.wait_for_load_state("networkidle")
                return
            except Exception:
                continue
        raise BookingFormError("Submit button not found.")

    def extract_confirmation(self, page: Page) -> str:
        for selector in Selectors.SUCCESS_CANDIDATES:
            locator = page.locator(selector).first
            try:
                locator.wait_for(state="visible", timeout=5000)
                return locator.inner_text().strip()
            except Exception:
                continue
        return page.locator("body").inner_text()[:1000].strip()

    def _calculate_end_time(self, start_time: str, hours: int) -> str:
        current = start_time
        for _ in range(hours * 2): current = add_30_minutes(current)
        return current
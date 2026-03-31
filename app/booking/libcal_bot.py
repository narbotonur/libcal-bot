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
    hour_width: float  # Ширина часа для смещения кликов
    hours: int         # Количество часов (кликов)


class LibCalBot:
    def __init__(self, config):
        self.config = config

    def run(self, request: BookingRequest) -> BookingResult:
        with sync_playwright() as p:
            # Используем стабильное разрешение для корректного расчета координат
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

                # --- ЛОГИКА: ФОКУС И СКРОЛЛ СЕТКИ ---
                print("[Action] Finding 12:00pm header to focus...")
                time_header = page.locator('th:has-text("12:00pm"), .s-lc-rm-td-time:has-text("12:00pm")').first
                
                try:
                    if time_header.is_visible(timeout=3000):
                        time_header.click()
                        print("Focused on 12:00pm header.")
                    else:
                        page.locator('.s-lc-rm-tg-th').first.click()
                except Exception:
                    page.mouse.click(400, 300) 

                page.wait_for_timeout(500)

                print("[Action] Pressing ArrowRight 12 times to reveal evening slots...")
                for _ in range(12):
                    page.keyboard.press("ArrowRight")
                    page.wait_for_timeout(150)
                
                page.wait_for_timeout(1000)
                # -----------------------------------------

                print("[4/8] Finding first suitable room...")
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
    # Navigation & Date
    # -------------------------

    def _open_page(self, page: Page) -> None:
        page.goto(self.config.base_url, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")
        if self._find_grid_table(page) is None:
            raise SiteChangedError("Booking grid table was not found.")

    def _validate_booking_window(self, request: BookingRequest) -> None:
        start_min = self._hhmm_to_minutes(request.start_time)
        end_min = start_min + request.hours * 60
        if start_min < 9 * 60:
            raise NoSlotsFoundError("Booking cannot start earlier than 09:00.")
        if end_min > 19 * 60:
            raise NoSlotsFoundError("Booking must end no later than 19:00.")

    def _set_date(self, page: Page, target_date: str) -> None:
        target = datetime.strptime(target_date, "%Y-%m-%d")
        target_day = target.day
        target_month_year = target.strftime("%B %Y")

        date_input = first_visible_locator(page, Selectors.DATE_PICKER_CANDIDATES, timeout=1500)
        if date_input:
            try:
                date_input.fill(target_date)
                date_input.press("Enter")
                page.wait_for_timeout(1500)
                return
            except Exception:
                pass

        if not click_first_visible(page, Selectors.GO_TO_DATE_BUTTON_CANDIDATES, timeout=3000):
            raise SiteChangedError("Go To Date button not found.")

        page.wait_for_timeout(1000)
        for _ in range(12):
            label_loc = first_visible_locator(page, Selectors.CALENDAR_MONTH_LABEL_CANDIDATES, timeout=1500)
            if not label_loc: raise SiteChangedError("Calendar label not found.")
            if label_loc.inner_text().strip().lower() == target_month_year.lower():
                break
            next_btn = first_visible_locator(page, Selectors.CALENDAR_NEXT_CANDIDATES, timeout=1500)
            next_btn.click()
            page.wait_for_timeout(500)

        day_clicked = False
        xpaths = [
            f'//td[not(contains(@class,"old")) and not(contains(@class,"new")) and normalize-space(text())="{target_day}"]',
            f'//button[normalize-space(text())="{target_day}"]'
        ]
        for xpath in xpaths:
            loc = page.locator(f"xpath={xpath}").first
            try:
                loc.wait_for(state="visible", timeout=1000)
                loc.click()
                day_clicked = True
                break
            except Exception:
                continue
        if not day_clicked: raise SiteChangedError(f"Could not click day {target_day}")
        page.wait_for_timeout(1500)

    # -------------------------
    # Grid & Recognition
    # -------------------------

    def _find_grid_table(self, page: Page):
        for selector in Selectors.GRID_TABLE_CANDIDATES:
            locator = page.locator(selector).first
            try:
                locator.wait_for(state="visible", timeout=2000)
                text = locator.inner_text().lower()
                if "9:00am" in text or "12:00pm" in text: return locator
            except Exception:
                continue
        return None

    def _extract_header_positions(self, grid):
        return grid.evaluate("""(grid) => {
            const nodes = Array.from(grid.querySelectorAll('thead th, th'));
            return nodes.filter(th => /^\\d{1,2}:\\d{2}(am|pm)$/.test(th.textContent.trim().toLowerCase()))
                .map(th => {
                    const rect = th.getBoundingClientRect();
                    return {
                        time: th.textContent.trim().toLowerCase(),
                        center: rect.left + rect.width / 2,
                        width: rect.width
                    };
                });
        }""")

    def _extract_room_rows(self, grid):
        rows = []
        all_rows = grid.locator("tbody tr")
        for i in range(all_rows.count()):
            row = all_rows.nth(i)
            try:
                name = normalize_room_name(row.locator(Selectors.SPACE_NAME_CELL).inner_text())
                bbox = row.bounding_box()
                if name and bbox:
                    rows.append({"room_name": name, "row_locator": row, "top": bbox["y"], "height": bbox["height"], "order": i})
            except: continue
        return rows

    def _convert_ampm_to_24h(self, value: str) -> str:
        m = re.match(r"^(\d{1,2}):(\d{2})(am|pm)$", value.strip().lower())
        hh, mm, ampm = int(m.group(1)), int(m.group(2)), m.group(3)
        if ampm == "am" and hh == 12: hh = 0
        elif ampm == "pm" and hh != 12: hh += 12
        return f"{hh:02d}:{mm:02d}"

    def _hhmm_to_minutes(self, value: str) -> int:
        hh, mm = value.split(":")
        return int(hh) * 60 + int(mm)

    def _is_green_pixel(self, r, g, b): return (45<=r<=105 and 135<=g<=200 and 45<=b<=110)
    def _is_red_pixel(self, r, g, b): return (150<=r<=255 and 20<=g<=140 and 20<=b<=140)

    def _cell_color_ratio(self, image, x0, y0, x1, y1):
        total, green, red = 0, 0, 0
        for yy in range(y0, y1, max(1, (y1-y0)//6)):
            for xx in range(x0, x1, max(1, (x1-x0)//10)):
                r, g, b = image.getpixel((xx, yy))
                total += 1
                if self._is_green_pixel(r, g, b): green += 1
                elif self._is_red_pixel(r, g, b): red += 1
        return (green/total, red/total) if total > 0 else (0,0)

    # -------------------------
    # Core Slot Logic
    # -------------------------

    def _find_best_slot(self, page: Page, request: BookingRequest) -> SlotCandidate:
        grid = self._find_grid_table(page)
        headers = self._extract_header_positions(grid)
        if not headers: raise SiteChangedError("Headers missing.")
        
        first_time_24 = self._convert_ampm_to_24h(headers[0]["time"])
        start_idx = (self._hhmm_to_minutes(request.start_time) - self._hhmm_to_minutes(first_time_24)) // 30
        
        if start_idx < 0: raise NoSlotsFoundError("Start time out of grid range.")

        png = grid.screenshot()
        grid_img = Image.open(io.BytesIO(png)).convert("RGB")
        grid_bbox = grid.bounding_box()
        
        avg_hour_w = headers[1]["center"] - headers[0]["center"]
        half_w = avg_hour_w / 2
        
        for row in sorted(self._extract_room_rows(grid), key=lambda r: r["order"]):
            available = True
            for o in range(request.hours * 2):
                idx = start_idx + o
                cx = (headers[0]["center"] + idx * half_w) - grid_bbox["x"]
                x0, x1 = int(cx - half_w/2 + 3), int(cx + half_w/2 - 3)
                y0, y1 = int(row["top"] - grid_bbox["y"] + 3), int(row["top"] + row["height"] - grid_bbox["y"] - 3)
                g, r = self._cell_color_ratio(grid_img, x0, y0, x1, y1)
                if g < 0.20 or r > 0.08:
                    available = False; break
            
            if available:
                return SlotCandidate(
                    room_name=row["room_name"],
                    start_time=request.start_time,
                    slot_index=start_idx,
                    click_x=headers[0]["center"] + (start_idx * half_w),
                    click_y=row["top"] + (row["height"] / 2),
                    hour_width=avg_hour_w,
                    hours=request.hours
                )
        raise NoSlotsFoundError(f"No free slots for {request.hours}h at {request.start_time}")

    def _select_slot_by_coordinates(self, page: Page, slot: SlotCandidate) -> None:
        print(f"[DEBUG] Selecting slots for {slot.room_name} using relative coordinates...")
        
        # Находим саму строку как объект
        room_row = page.locator(f"text={slot.room_name}").first
        room_row.scroll_into_view_if_needed()
        page.wait_for_timeout(500)

        # Получаем реальные координаты строки на экране прямо сейчас
        box = room_row.bounding_box()
        if not box:
            raise SiteChangedError(f"Could not find bounding box for room {slot.room_name}")

        for i in range(slot.hours):
            # Рассчитываем X относительно ЛЕВОГО КРАЯ ЭКРАНА
            current_x = slot.click_x + (i * slot.hour_width)
            
            # ВАЖНО: Пересчитываем X относительно ЛЕВОГО КРАЯ СТРОКИ
            # Это защитит нас, если таблица сдвинулась по горизонтали
            relative_x = current_x - box["x"]
            
            # Y берем ровно посередине высоты строки (relative_y)
            relative_y = box["height"] / 2

            try:
                # Кликаем ВНУТРЬ элемента room_row по относительным координатам
                # Это исключает попадание в логотип NU, даже если страница прыгает
                room_row.click(position={"x": relative_x, "y": relative_y}, force=True)
                
                print(f"      [Step {i+1}/{slot.hours}] Clicked relative X: {relative_x:.2f} in {slot.room_name}")
                
                # Короткая пауза, чтобы LibCal подсветил ячейку синим
                page.wait_for_timeout(800) 

            except Exception as e:
                print(f"      [!] Relative click {i+1} failed: {e}")
                continue

    def _submit_times(self, page: Page) -> None:
        print("[6/8] Looking for Submit Times button...")
        # После кликов кнопка Submit точно появилась. 
        # Нам нужно проскроллить в самый низ страницы, где она обычно живет.
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(500)

        for selector in Selectors.SUBMIT_TIMES_CANDIDATES:
            btn = page.locator(selector).first
            try:
                if btn.is_visible(timeout=2000):
                    btn.click(force=True)
                    page.wait_for_load_state("networkidle")
                    return
            except:
                continue
        
        raise SiteChangedError("Submit Times button not found after clicking slots.")
    
    def _continue_policy(self, page: Page) -> None:
        if click_first_visible(page, Selectors.CONTINUE_CANDIDATES, timeout=5000):
            page.wait_for_load_state("networkidle")

    # -------------------------
    # Form Filling
    # -------------------------

    def fill_booking_form(self, page: Page) -> None:
        def try_fill(selectors, value):
            for sel in selectors:
                try:
                    loc = page.locator(sel).first
                    loc.wait_for(state="visible", timeout=1000)
                    loc.fill("")
                    loc.type(value, delay=30)
                    return True
                except: continue
            return False

        results = {
            "fname": try_fill(['input[id="fname"]', 'input[name="fname"]'], self.config.first_name),
            "lname": try_fill(['input[id="lname"]', 'input[name="lname"]'], self.config.last_name),
            "email": try_fill(['input[id="email"]', 'input[type="email"]'], self.config.email),
            "id": try_fill(['input[id="q1"]', 'label:has-text("ID card") + div input'], self.config.id_card),
            "dept": try_fill(['input[id="q2"]', 'label:has-text("School") + div input'], self.config.department),
            "reason": try_fill(['textarea[id="q3"]', 'label:has-text("Purpose") + div textarea'], self.config.purpose)
        }
        
        missing = [k for k, v in results.items() if not v]
        if missing: raise BookingFormError(f"Form error. Missing fields: {missing}")

    def submit_final_form(self, page: Page) -> None:
        if not click_first_visible(page, ['button:has-text("Submit my Booking")', 'button:has-text("Submit")'], timeout=3000):
            raise BookingFormError("Final submit button not found.")
        page.wait_for_load_state("networkidle")

    def extract_confirmation(self, page: Page) -> str:
        for sel in Selectors.SUCCESS_CANDIDATES:
            try:
                loc = page.locator(sel).first
                loc.wait_for(state="visible", timeout=5000)
                return loc.inner_text().strip()
            except: continue
        return page.locator("body").inner_text()[:500]

    def _calculate_end_time(self, start_time: str, hours: int) -> str:
        curr = start_time
        for _ in range(hours * 2): curr = add_30_minutes(curr)
        return curr
from datetime import datetime, timedelta
import pytz
from typing import Dict, Any, List, Optional

class ReservationDB:
    def __init__(self, timezone_str: str, slot_duration_minutes: int = 30):
        self.timezone = pytz.timezone(timezone_str)
        self.slot_duration = timedelta(minutes=slot_duration_minutes)
        self.reservations: Dict[datetime, Dict[str, Any]] = {}

    def _normalize_datetime(self, dt: datetime) -> datetime:
        if dt.tzinfo is None:
            dt = self.timezone.localize(dt)
        else:
            dt = dt.astimezone(self.timezone)
        # Normalize to the start of the slot (e.g., 14:00, 14:30)
        minute = (dt.minute // self.slot_duration.seconds * 60) * (self.slot_duration.seconds // 60)
        return dt.replace(minute=minute, second=0, microsecond=0)

    def is_slot_available(self, requested_dt: datetime) -> bool:
        normalized_dt = self._normalize_datetime(requested_dt)
        # Check if the exact slot is booked
        if normalized_dt in self.reservations:
            return False
        
        # Check for overlapping reservations (e.g., if a 14:00 reservation blocks 13:30-14:00)
        # This simple model assumes a reservation at X:00 blocks X:00 to X:30
        # and a reservation at X:30 blocks X:30 to X:00+1
        # For a single table, we just need to check if the requested slot is already a key.
        # The problem statement implies a reservation at X:00 blocks X:00 and the next 30 mins.
        # So, if a slot is booked at 14:00, then 14:00 is unavailable. If someone asks for 14:15, it's also unavailable.
        # The _normalize_datetime handles this by snapping to the start of the 30 min slot.
        
        # Let's refine the check for overlapping. If a slot is booked at `normalized_dt`, it means it's occupied.
        # If someone requests `normalized_dt + 15min`, it will normalize to `normalized_dt` and thus be unavailable.
        # So, the simple `normalized_dt in self.reservations` is sufficient for a single table.
        
        return True

    def book_slot(self, requested_dt: datetime, client_name: str, phone_number: str) -> Optional[datetime]:
        normalized_dt = self._normalize_datetime(requested_dt)
        if self.is_slot_available(normalized_dt):
            self.reservations[normalized_dt] = {
                "client_name": client_name,
                "phone_number": phone_number,
                "booked_at": datetime.now(self.timezone)
            }
            return normalized_dt
        return None

    def get_alternative_slots(self, requested_dt: datetime, num_alternatives: int = 5) -> List[datetime]:
        normalized_dt = self._normalize_datetime(requested_dt)
        alternatives: List[datetime] = []
        
        # Look for slots before and after
        for i in range(1, num_alternatives // 2 + 2):
            # Before
            prev_slot = normalized_dt - (self.slot_duration * i)
            if self.is_slot_available(prev_slot):
                alternatives.append(prev_slot)
            
            # After
            next_slot = normalized_dt + (self.slot_duration * i)
            if self.is_slot_available(next_slot):
                alternatives.append(next_slot)
        
        # Sort and return a limited number of unique alternatives
        alternatives = sorted(list(set(alternatives)))
        return alternatives[:num_alternatives]

    def get_booked_slots(self) -> Dict[datetime, Dict[str, Any]]:
        return self.reservations

    def clear_reservations(self):
        self.reservations = {}

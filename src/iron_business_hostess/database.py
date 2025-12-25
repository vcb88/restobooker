import sqlite3
import pytz
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import os

class ReservationDB:
    def __init__(self, timezone_str: str, tables: List[Dict[str, Any]], slot_duration_minutes: int = 30, db_path: str = "reservations.db"):
        self.timezone = pytz.timezone(timezone_str)
        self.slot_duration = timedelta(minutes=slot_duration_minutes)
        self.db_path = db_path
        self.tables_config = tables
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Таблица столиков
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tables (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    capacity INTEGER,
                    zone TEXT
                )
            ''')
            # Таблица для бронирований
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_id INTEGER,
                    slot_datetime TEXT,
                    client_name TEXT,
                    phone_number TEXT,
                    guests_count INTEGER,
                    booked_at TEXT,
                    status TEXT DEFAULT 'confirmed', -- confirmed, cancelled
                    FOREIGN KEY(table_id) REFERENCES tables(id),
                    UNIQUE(table_id, slot_datetime)
                )
            ''')
            
            # Предварительное заполнение столиков
            cursor.execute("DELETE FROM tables")
            for t in self.tables_config:
                cursor.execute(
                    "INSERT INTO tables (id, name, capacity, zone) VALUES (?, ?, ?, ?)",
                    (t['id'], t['name'], t['capacity'], t['zone'])
                )
            conn.commit()

    def _normalize_datetime(self, dt: datetime) -> datetime:
        if dt.tzinfo is None:
            dt = self.timezone.localize(dt)
        else:
            dt = dt.astimezone(self.timezone)
        minute = (dt.minute // 30) * 30
        return dt.replace(minute=minute, second=0, microsecond=0)

    def find_available_table(self, requested_dt: datetime, guests_count: int = 2) -> Optional[int]:
        normalized_dt = self._normalize_datetime(requested_dt).isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Найти подходящий столик (вместимость >= кол-во гостей), который не занят в это время
            query = '''
                SELECT id FROM tables 
                WHERE capacity >= ? 
                AND id NOT IN (
                    SELECT table_id FROM reservations 
                    WHERE slot_datetime = ? AND status = 'confirmed'
                )
                ORDER BY capacity ASC
                LIMIT 1
            '''
            cursor.execute(query, (guests_count, normalized_dt))
            result = cursor.fetchone()
            return result[0] if result else None

    def book_slot(self, requested_dt: datetime, client_name: str, phone_number: str, guests_count: int = 2) -> Optional[Dict[str, Any]]:
        table_id = self.find_available_table(requested_dt, guests_count)
        if not table_id:
            return None

        normalized_dt = self._normalize_datetime(requested_dt)
        dt_str = normalized_dt.isoformat()
        booked_at_str = datetime.now(self.timezone).isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO reservations (table_id, slot_datetime, client_name, phone_number, guests_count, booked_at) VALUES (?, ?, ?, ?, ?, ?)",
                (table_id, dt_str, client_name, phone_number, guests_count, booked_at_str)
            )
            
            cursor.execute("SELECT name, zone FROM tables WHERE id = ?", (table_id,))
            table_info = cursor.fetchone()
            conn.commit()
            
            return {
                "datetime": normalized_dt,
                "table_name": table_info[0],
                "zone": table_info[1]
            }

    def get_alternative_slots(self, requested_dt: datetime, guests_count: int = 2, num_alternatives: int = 5) -> List[datetime]:
        normalized_dt = self._normalize_datetime(requested_dt)
        alternatives: List[datetime] = []
        
        offset = 1
        while len(alternatives) < num_alternatives and offset < 24:
            # Проверяем слоты вокруг
            for direction in [-1, 1]:
                check_slot = normalized_dt + (self.slot_duration * offset * direction)
                if self.find_available_table(check_slot, guests_count):
                    alternatives.append(check_slot)
                if len(alternatives) >= num_alternatives:
                    break
            offset += 1
        
        return sorted(alternatives)

    def update_reservation_time(self, phone_number: str, old_dt: Optional[datetime], new_dt: datetime) -> Optional[Dict[str, Any]]:
        """Переносит существующую бронь на новое время"""
        normalized_new_dt = self._normalize_datetime(new_dt)
        new_dt_str = normalized_new_dt.isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Найти существующую активную бронь
            if old_dt:
                old_dt_str = self._normalize_datetime(old_dt).isoformat()
                cursor.execute(
                    "SELECT id, guests_count FROM reservations WHERE phone_number = ? AND slot_datetime = ? AND status = 'confirmed'",
                    (phone_number, old_dt_str)
                )
            else:
                cursor.execute(
                    "SELECT id, guests_count FROM reservations WHERE phone_number = ? AND status = 'confirmed' ORDER BY slot_datetime DESC LIMIT 1",
                    (phone_number,)
                )
            
            row = cursor.fetchone()
            if not row:
                return None
            
            res_id, guests_count = row

            # 2. Проверить доступность нового слота
            table_id = self.find_available_table(normalized_new_dt, guests_count)
            if not table_id:
                return None

            # 3. Обновить бронь
            cursor.execute(
                "UPDATE reservations SET slot_datetime = ?, table_id = ?, booked_at = ? WHERE id = ?",
                (new_dt_str, table_id, datetime.now(self.timezone).isoformat(), res_id)
            )
            
            cursor.execute("SELECT name, zone FROM tables WHERE id = ?", (table_id,))
            table_info = cursor.fetchone()
            conn.commit()

            return {
                "datetime": normalized_new_dt,
                "table_name": table_info[0],
                "zone": table_info[1],
                "guests_count": guests_count
            }

    def cancel_reservation(self, phone_number: str, requested_dt: Optional[datetime] = None) -> bool:
        """Отменяет последнее бронирование по номеру телефона (или конкретное по времени)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if requested_dt:
                dt_str = self._normalize_datetime(requested_dt).isoformat()
                cursor.execute(
                    "UPDATE reservations SET status = 'cancelled' WHERE phone_number = ? AND slot_datetime = ? AND status = 'confirmed'",
                    (phone_number, dt_str)
                )
            else:
                cursor.execute(
                    "UPDATE reservations SET status = 'cancelled' WHERE id = (SELECT id FROM reservations WHERE phone_number = ? AND status = 'confirmed' ORDER BY slot_datetime DESC LIMIT 1)",
                    (phone_number,)
                )
            conn.commit()
            return cursor.rowcount > 0

import sqlite3
from typing import Dict, List, Optional, Any
import src.config as config

class Storage:
    def __init__(self, db_path=None):
        self.db_path = db_path or config.DB_PATH
        config.ensure_data_dir()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        cursor = self.conn.cursor()
        cursor.executescript('''
            CREATE TABLE IF NOT EXISTS extracted_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id TEXT NOT NULL,
                field_name TEXT NOT NULL,
                value TEXT,
                raw_value TEXT,
                selector_used TEXT,
                confidence REAL DEFAULT 0.0,
                validation_status TEXT DEFAULT 'pending',
                scrape_cycle INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS selector_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id TEXT NOT NULL,
                field_name TEXT NOT NULL,
                selector TEXT NOT NULL,
                version INTEGER DEFAULT 1,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS repair_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id TEXT NOT NULL,
                field_name TEXT NOT NULL,
                old_selector TEXT,
                new_selector TEXT,
                method TEXT,
                confidence REAL,
                justification TEXT,
                success BOOLEAN DEFAULT 0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id TEXT NOT NULL,
                field_name TEXT,
                alert_type TEXT NOT NULL,
                message TEXT NOT NULL,
                resolved BOOLEAN DEFAULT 0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS scrape_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id TEXT NOT NULL,
                status TEXT NOT NULL,
                fields_total INTEGER,
                fields_success INTEGER,
                fields_failed INTEGER,
                fields_repaired INTEGER,
                cycle_number INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        self.conn.commit()

    def save_extracted_data(self, site_id: str, field_name: str, value: str, raw_value: str, selector_used: str, confidence: float, validation_status: str, scrape_cycle: int):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO extracted_data (site_id, field_name, value, raw_value, selector_used, confidence, validation_status, scrape_cycle)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (site_id, field_name, value, raw_value, selector_used, confidence, validation_status, scrape_cycle))
        self.conn.commit()

    def get_last_good_value(self, site_id: str, field_name: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM extracted_data
            WHERE site_id = ? AND field_name = ? AND validation_status = 'pass'
            ORDER BY timestamp DESC LIMIT 1
        ''', (site_id, field_name))
        row = cursor.fetchone()
        return dict(row) if row else None

    def save_selector(self, site_id: str, field_name: str, selector: str, version: int = 1):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE selector_history SET is_active = 0
            WHERE site_id = ? AND field_name = ?
        ''', (site_id, field_name))
        cursor.execute('''
            INSERT INTO selector_history (site_id, field_name, selector, version, is_active)
            VALUES (?, ?, ?, ?, 1)
        ''', (site_id, field_name, selector, version))
        self.conn.commit()

    def get_active_selector(self, site_id: str, field_name: str) -> Optional[str]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT selector FROM selector_history
            WHERE site_id = ? AND field_name = ? AND is_active = 1
            ORDER BY id DESC LIMIT 1
        ''', (site_id, field_name))
        row = cursor.fetchone()
        return row['selector'] if row else None

    def get_all_active_selectors(self, site_id: str) -> Dict[str, str]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT field_name, selector FROM selector_history
            WHERE site_id = ? AND is_active = 1
        ''', (site_id,))
        return {row['field_name']: row['selector'] for row in cursor.fetchall()}

    def log_repair(self, site_id: str, field_name: str, old_selector: str, new_selector: str, method: str, confidence: float, justification: str, success: bool = False):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO repair_log (site_id, field_name, old_selector, new_selector, method, confidence, justification, success)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (site_id, field_name, old_selector, new_selector, method, confidence, justification, success))
        self.conn.commit()

    def add_alert(self, site_id: str, field_name: str, alert_type: str, message: str):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO alerts (site_id, field_name, alert_type, message)
            VALUES (?, ?, ?, ?)
        ''', (site_id, field_name, alert_type, message))
        self.conn.commit()

    def resolve_alerts(self, site_id: str, field_name: Optional[str] = None):
        cursor = self.conn.cursor()
        if field_name:
            cursor.execute('''
                UPDATE alerts SET resolved = 1
                WHERE site_id = ? AND field_name = ? AND resolved = 0
            ''', (site_id, field_name))
        else:
            cursor.execute('''
                UPDATE alerts SET resolved = 1
                WHERE site_id = ? AND resolved = 0
            ''', (site_id,))
        self.conn.commit()

    def get_active_alerts(self) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM alerts WHERE resolved = 0 ORDER BY timestamp DESC')
        return [dict(row) for row in cursor.fetchall()]

    def save_scrape_status(self, site_id: str, status: str, fields_total: int, fields_success: int, fields_failed: int, fields_repaired: int, cycle_number: int):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO scrape_status (site_id, status, fields_total, fields_success, fields_failed, fields_repaired, cycle_number)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (site_id, status, fields_total, fields_success, fields_failed, fields_repaired, cycle_number))
        self.conn.commit()

    def get_latest_scrape_status(self, site_id: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM scrape_status
            WHERE site_id = ?
            ORDER BY timestamp DESC LIMIT 1
        ''', (site_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_repair_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM repair_log ORDER BY timestamp DESC LIMIT ?', (limit,))
        return [dict(row) for row in cursor.fetchall()]

    def get_extracted_data(self, site_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        if site_id:
            cursor.execute('SELECT * FROM extracted_data WHERE site_id = ? ORDER BY timestamp DESC LIMIT ?', (site_id, limit))
        else:
            cursor.execute('SELECT * FROM extracted_data ORDER BY timestamp DESC LIMIT ?', (limit,))
        return [dict(row) for row in cursor.fetchall()]

    def get_selector_history(self, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        if site_id:
            cursor.execute('SELECT * FROM selector_history WHERE site_id = ? ORDER BY created_at DESC', (site_id,))
        else:
            cursor.execute('SELECT * FROM selector_history ORDER BY created_at DESC')
        return [dict(row) for row in cursor.fetchall()]

    def get_next_cycle_number(self, site_id: str) -> int:
        cursor = self.conn.cursor()
        cursor.execute('SELECT MAX(cycle_number) as max_cycle FROM scrape_status WHERE site_id = ?', (site_id,))
        row = cursor.fetchone()
        return (row['max_cycle'] or 0) + 1

    def reset_database(self):
        cursor = self.conn.cursor()
        tables = ['extracted_data', 'selector_history', 'repair_log', 'alerts', 'scrape_status']
        for table in tables:
            cursor.execute(f'DROP TABLE IF EXISTS {table}')
        self.conn.commit()
        self._create_tables()

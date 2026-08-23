from typing import Dict, List, Optional
from src.storage import Storage

class SelectorStore:
    def __init__(self, storage: Storage):
        self.storage = storage

    def initialize_defaults(self, site_id: str, selectors_dict: Dict[str, str]):
        active_selectors = self.storage.get_all_active_selectors(site_id)
        if not active_selectors:
            for field_name, selector in selectors_dict.items():
                self.storage.save_selector(site_id, field_name, selector, version=1)

    def get_selector(self, site_id: str, field_name: str) -> Optional[str]:
        return self.storage.get_active_selector(site_id, field_name)

    def get_all_selectors(self, site_id: str) -> Dict[str, str]:
        return self.storage.get_all_active_selectors(site_id)

    def update_selector(self, site_id: str, field_name: str, new_selector: str):
        cursor = self.storage.conn.cursor()
        cursor.execute('''
            SELECT version FROM selector_history
            WHERE site_id = ? AND field_name = ? AND is_active = 1
            ORDER BY id DESC LIMIT 1
        ''', (site_id, field_name))
        row = cursor.fetchone()
        current_version = row['version'] if row else 0
        self.storage.save_selector(site_id, field_name, new_selector, version=current_version + 1)

    def get_history(self, site_id: Optional[str] = None) -> List[Dict]:
        return self.storage.get_selector_history(site_id)

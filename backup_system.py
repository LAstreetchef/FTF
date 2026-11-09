import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

class FileBackupSystem:
    """File backup of events. New files go in instance/backups, which is not committed.

    The historical snapshot committed under data_backups/ is still readable.
    """

    def __init__(self, backup_dir: str = "instance/backups", archive_dir: str = "data_backups"):
        self.backup_dir = backup_dir
        self.archive_dir = archive_dir
        self.ensure_backup_directory()
    
    def ensure_backup_directory(self):
        """Create backup directory if it doesn't exist"""
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)
            logging.info(f"Created backup directory: {self.backup_dir}")
    
    def create_event_backup(self, events: List[Dict]) -> Optional[str]:
        """Create a timestamped backup of events data"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"events_backup_{timestamp}.json"
        filepath = os.path.join(self.backup_dir, filename)
        
        backup_data = {
            "timestamp": datetime.now().isoformat(),
            "backup_type": "automatic",
            "event_count": len(events),
            "events": events
        }
        
        try:
            with open(filepath, 'w') as f:
                json.dump(backup_data, f, indent=2, default=str)
            
            logging.info(f"✅ File backup created: {filename} with {len(events)} events")
            
            # Also create/update the "latest" backup for easy access
            latest_filepath = os.path.join(self.backup_dir, "events_backup_latest.json")
            with open(latest_filepath, 'w') as f:
                json.dump(backup_data, f, indent=2, default=str)
            
            return filepath
            
        except Exception as e:
            logging.error(f"Failed to create file backup: {e}")
            return None
    
    def get_latest_backup(self) -> Optional[Dict]:
        """Get the most recent backup, preferring instance/backups over the committed archive."""
        for directory in (self.backup_dir, self.archive_dir):
            data = self._read_latest_in(directory)
            if data:
                return data
        logging.info("No backup files found")
        return None

    def _read_latest_in(self, directory: str) -> Optional[Dict]:
        latest_filepath = os.path.join(directory, "events_backup_latest.json")
        if os.path.exists(latest_filepath):
            try:
                with open(latest_filepath, "r") as f:
                    backup_data = json.load(f)
                logging.info(
                    "Found latest backup in %s with %s events",
                    directory,
                    backup_data.get("event_count", 0),
                )
                return backup_data
            except Exception as e:
                logging.error(f"Failed to read latest backup in {directory}: {e}")
        return self._find_most_recent_backup(directory)

    def _find_most_recent_backup(self, directory: Optional[str] = None) -> Optional[Dict]:
        """Find the most recent timestamped backup file"""
        directory = directory or self.backup_dir
        if not os.path.exists(directory):
            return None

        backup_files = [f for f in os.listdir(directory)
                       if f.startswith('events_backup_') and f.endswith('.json')
                       and 'latest' not in f]

        if not backup_files:
            return None

        # Sort by filename (timestamp) to get the most recent
        backup_files.sort(reverse=True)
        most_recent = backup_files[0]
        filepath = os.path.join(directory, most_recent)
        
        try:
            with open(filepath, 'r') as f:
                backup_data = json.load(f)
            logging.info(f"Found backup file: {most_recent} with {backup_data.get('event_count', 0)} events")
            return backup_data
        except Exception as e:
            logging.error(f"Failed to read backup file {most_recent}: {e}")
            return None
    
    def list_backups(self) -> List[str]:
        """List all available backup files"""
        if not os.path.exists(self.backup_dir):
            return []
        
        backup_files = [f for f in os.listdir(self.backup_dir) 
                       if f.startswith('events_backup_') and f.endswith('.json')]
        backup_files.sort(reverse=True)  # Most recent first
        return backup_files
    
    def cleanup_old_backups(self, keep_count: int = 10):
        """Keep only the most recent N backup files"""
        backup_files = [f for f in os.listdir(self.backup_dir) 
                       if f.startswith('events_backup_') and f.endswith('.json') 
                       and 'latest' not in f]
        
        backup_files.sort(reverse=True)  # Most recent first
        
        if len(backup_files) > keep_count:
            files_to_delete = backup_files[keep_count:]
            for filename in files_to_delete:
                filepath = os.path.join(self.backup_dir, filename)
                try:
                    os.remove(filepath)
                    logging.info(f"Deleted old backup: {filename}")
                except Exception as e:
                    logging.error(f"Failed to delete backup {filename}: {e}")


def backup_events_to_file(events):
    """Convenience function to backup events using the file system"""
    backup_system = FileBackupSystem()
    
    # Convert SQLAlchemy objects to dictionaries
    events_data = []
    for event in events:
        event_dict = {}
        for column in event.__table__.columns:
            value = getattr(event, column.name)
            if hasattr(value, 'isoformat'):
                value = value.isoformat()
            event_dict[column.name] = value
        events_data.append(event_dict)
    
    backup_system.create_event_backup(events_data)
    backup_system.cleanup_old_backups()  # Keep only last 10 backups


def restore_events_from_file():
    """Convenience function to restore events from file backup"""
    backup_system = FileBackupSystem()
    backup_data = backup_system.get_latest_backup()
    
    if backup_data and 'events' in backup_data:
        return backup_data['events']
    
    return None
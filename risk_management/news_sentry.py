import requests
import logging
from datetime import datetime, timezone


class NewsSentry:
    def __init__(self, config):
        self.config = config
        self.url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        self.impact_levels = config.get('impact_levels', ['High'])

    def is_market_volatile(self, symbol):
        try:
            response = requests.get(self.url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            if response.status_code != 200:
                return False
            events = response.json()
            now = datetime.now(timezone.utc)
            currencies = [symbol[:3], symbol[3:]]
            if "XAU" in symbol:
                currencies.append("USD")
            for event in events:
                if all(k in event for k in ('impact', 'country', 'date', 'time')) and event['impact'] in self.impact_levels and event['country'] in currencies:
                    try:
                        event_time = datetime.strptime(f"{event['date']} {event['time']}", "%m-%d-%Y %I:%M%p").replace(tzinfo=timezone.utc)
                        time_to_event = (event_time - now).total_seconds() / 60
                        if -15 < time_to_event < 30:
                            return True
                    except Exception:
                        continue
            return False
        except Exception as exc:
            logging.error(f"News Sentry Failure: {exc}")
            return False

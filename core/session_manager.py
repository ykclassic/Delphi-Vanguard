import datetime


class SessionManager:
    def get_current_session(self):
        now = datetime.datetime.now(datetime.timezone.utc).hour
        sessions = []
        if 0 <= now < 9:
            sessions.append("Tokyo 🇯🇵")
        if 8 <= now < 17:
            sessions.append("London 🇬🇧")
        if 13 <= now < 22:
            sessions.append("New York 🇺🇸")
        if 21 <= now <= 23 or 0 <= now < 6:
            sessions.append("Sydney 🇦🇺")
        return " & ".join(sessions) if sessions else "Market Closed"

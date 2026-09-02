import os
import yaml
import requests
from core.monitor import SignalMonitor


def load_config():
    with open("config/settings.yaml", "r") as f:
        config = yaml.safe_load(f)
    webhook_env = os.getenv("DISCORD_WEBHOOK_URL")
    if webhook_env:
        config['discord']['webhook_url'] = webhook_env
    return config


def run_monitor():
    config = load_config()
    monitor = SignalMonitor(config)
    updates = monitor.check_outcomes()
    if updates and config['discord'].get('webhook_url'):
        payload = {"embeds": [{"title": "🎯 Trade Outcome Update", "description": "\n".join(updates), "color": 3447003, "footer": {"text": "Delphi Vanguard baseline monitor"}}]}
        requests.post(config['discord']['webhook_url'], json=payload)
        print(f"Logged {len(updates)} outcomes.")
    else:
        print("No new outcomes detected.")


if __name__ == "__main__":
    run_monitor()

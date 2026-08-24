import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
MUSIC_DIR = os.getenv("MUSIC_DIR", os.path.join(os.path.dirname(__file__), "music"))

if not DISCORD_TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN が設定されていません。.env ファイルに DISCORD_TOKEN=... を追加してください。"
    )

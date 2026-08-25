import discord
from discord.ext import commands

# --- Linux環境用 Opus手動ロード処理 ---
if not discord.opus.is_loaded():
    opus_libs = ['libopus.so.0', 'libopus.so', 'libopus-0.dll']
    for lib in opus_libs:
        try:
            discord.opus.load_opus(lib)
            print(f"Opus successfully loaded: {lib}")
            break
        except Exception:
            continue
# ------------------------------------
import os
import sys
import ctypes
import ctypes.util
import asyncio
import discord
from discord.ext import commands
import imageio_ffmpeg

# --- Linux/Railway環境で Opus を強制的にロードする仕組み ---
if not discord.opus.is_loaded():
    # 1. システムパスからの検出を試みる
    opus_path = ctypes.util.find_library('opus') or ctypes.util.find_library('libopus')
    if opus_path:
        try:
            discord.opus.load_opus(opus_path)
        except Exception:
            pass

    # 2. ctypes でシステムライブラリ（libopus.so）を直接探索してロード
    if not discord.opus.is_loaded():
        for libname in ['libopus.so.0', 'libopus.so', 'libopus.so.0.8.0']:
            try:
                # Cライブラリを直接開いてロードさせる
                ctypes.CDLL(libname)
                discord.opus.load_opus(libname)
                break
            except Exception:
                continue

FFMPEG_EXECUTABLE = imageio_ffmpeg.get_ffmpeg_exe()

from config import DISCORD_TOKEN, COMMAND_PREFIX
import config

MUSIC_DIR = os.path.abspath(getattr(config, "MUSIC_DIR", "music"))

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

ALLOWED_EXTENSIONS = (".mp3", ".MP3")


class GuildMusicState:
    def __init__(self):
        self.queue: list[str] = []
        self.current: str | None = None
        self.voice_client: discord.VoiceClient | None = None

    def is_playing(self) -> bool:
        return bool(self.voice_client and self.voice_client.is_playing())


music_states: dict[int, GuildMusicState] = {}


def get_state(guild_id: int) -> GuildMusicState:
    if guild_id not in music_states:
        music_states[guild_id] = GuildMusicState()
    return music_states[guild_id]


def list_music_files() -> list[str]:
    if not os.path.isdir(MUSIC_DIR):
        return []
    files = [f for f in os.listdir(MUSIC_DIR) if f.lower().endswith(ALLOWED_EXTENSIONS)]
    return sorted(files)


def find_music_file(keyword: str) -> str | None:
    files = list_music_files()
    keyword_lower = keyword.lower()

    for f in files:
        if f.lower() == keyword_lower:
            return f
    for f in files:
        if os.path.splitext(f)[0].lower() == keyword_lower:
            return f
    matches = [f for f in files if keyword_lower in f.lower()]
    if len(matches) == 1:
        return matches[0]
    return None


async def ensure_voice(ctx: commands.Context) -> discord.VoiceClient | None:
    state = get_state(ctx.guild.id)

    if ctx.author.voice is None or ctx.author.voice.channel is None:
        await ctx.send("先にボイスチャンネルに参加してください。")
        return None

    channel = ctx.author.voice.channel

    try:
        if state.voice_client is None or not state.voice_client.is_connected():
            state.voice_client = await channel.connect(timeout=20.0, reconnect=True)
        elif state.voice_client.channel != channel:
            await state.voice_client.move_to(channel)
    except Exception as e:
        await ctx.send(f"ボイスチャンネル接続エラー: `{e}`")
        return None

    return state.voice_client


def play_next(ctx: commands.Context):
    state = get_state(ctx.guild.id)

    if not state.queue:
        state.current = None
        return

    next_file = state.queue.pop(0)
    state.current = next_file
    filepath = os.path.join(MUSIC_DIR, next_file)

    ffmpeg_options = {
        'before_options': '-nostdin',
        'options': '-vn'
    }

    try:
        source = discord.FFmpegPCMAudio(filepath, executable=FFMPEG_EXECUTABLE, **ffmpeg_options)
    except Exception as e:
        asyncio.run_coroutine_threadsafe(ctx.send(f"音声作成エラー: `{e}`"), bot.loop)
        return

    def after_playing(error):
        if error:
            asyncio.run_coroutine_threadsafe(ctx.send(f"⚠️ 再生中エラー: `{error}`"), bot.loop)
        fut = asyncio.run_coroutine_threadsafe(
            _notify_and_play_next(ctx), bot.loop
        )
        try:
            fut.result()
        except Exception:
            pass

    try:
        if state.voice_client and state.voice_client.is_connected():
            state.voice_client.play(source, after=after_playing)
        else:
            asyncio.run_coroutine_threadsafe(ctx.send("⚠️ ボイス接続が切断されました。"), bot.loop)
    except Exception as e:
        err_msg = str(e) if str(e) else repr(e)
        asyncio.run_coroutine_threadsafe(ctx.send(f"⚠️ play実行時エラー: `{err_msg}`"), bot.loop)


async def _notify_and_play_next(ctx: commands.Context):
    state = get_state(ctx.guild.id)
    if state.queue:
        await ctx.send(f"次の曲を再生します: **{state.queue[0]}**")
    play_next(ctx)


@bot.event
async def on_ready():
    print(f"ログイン完了: {bot.user}")
    print(f"Opus ロード成功フラグ: {discord.opus.is_loaded()}")


@bot.command(name="list")
async def list_songs(ctx: commands.Context):
    files = list_music_files()
    if not files:
        await ctx.send(f"`{MUSIC_DIR}` にMP3ファイルが見つかりません。")
        return
    listing = "\n".join(f"- {f}" for f in files)
    await ctx.send(f"**利用可能な曲一覧**\n{listing}")


@bot.command(name="play")
async def play(ctx: commands.Context, *, keyword: str):
    vc = await ensure_voice(ctx)
    if vc is None:
        return

    filename = find_music_file(keyword)
    if filename is None:
        await ctx.send(f"曲が見つかりません: `{keyword}`")
        return

    state = get_state(ctx.guild.id)
    state.queue.clear()

    if vc.is_playing() or vc.is_paused():
        vc.stop()
        state.queue.insert(0, filename)
    else:
        state.queue.insert(0, filename)
        play_next(ctx)
        await ctx.send(f"再生開始: **{filename}**")
        return

    await ctx.send(f"曲を切り替えます: **{filename}**")


@bot.command(name="stop")
async def stop(ctx: commands.Context):
    state = get_state(ctx.guild.id)
    state.queue.clear()
    if state.voice_client:
        state.voice_client.stop()
    state.current = None
    await ctx.send("再生を停止しました。")


@bot.command(name="leave")
async def leave(ctx: commands.Context):
    state = get_state(ctx.guild.id)
    if state.voice_client:
        await state.voice_client.disconnect()
        state.voice_client = None
        state.queue.clear()
        state.current = None
        await ctx.send("切断しました。")


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)

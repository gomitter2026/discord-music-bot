import asyncio
import os
import re
import traceback

import discord
from discord.ext import commands

# --- Linux/Railway環境で libopus を自動ロードさせる設定 ---
if not discord.opus.is_loaded():
    opus_libs = ['libopus.so.0', 'libopus.so', 'libopus-0.dll', 'opus.dll', 'opus']
    for lib in opus_libs:
        try:
            discord.opus.load_opus(lib)
            print(f"Opus loaded successfully using: {lib}")
            break
        except OSError:
            continue

from config import DISCORD_TOKEN, COMMAND_PREFIX
import config

# --- 絶対パスで music フォルダの場所を確実に固定 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
raw_music_dir = str(getattr(config, "MUSIC_DIR", "music")).lstrip(".").lstrip("/")
MUSIC_DIR = os.path.join(BASE_DIR, raw_music_dir)

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

ALLOWED_EXTENSIONS = (".mp3",)


class GuildMusicState:
    """サーバー(ギルド)ごとの再生状態を保持するクラス"""

    def __init__(self):
        self.queue: list[str] = []       # 再生待ちファイル名のリスト
        self.current: str | None = None  # 現在再生中のファイル名
        self.voice_client: discord.VoiceClient | None = None

    def is_playing(self) -> bool:
        return bool(self.voice_client and self.voice_client.is_playing())


# ギルドID -> GuildMusicState
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
    """曲名の部分一致・拡張子省略に対応してファイルを探す"""
    files = list_music_files()
    keyword_lower = keyword.lower()

    # 完全一致(拡張子込み)
    for f in files:
        if f.lower() == keyword_lower:
            return f
    # 完全一致(拡張子なし)
    for f in files:
        if os.path.splitext(f)[0].lower() == keyword_lower:
            return f
    # 部分一致
    matches = [f for f in files if keyword_lower in f.lower()]
    if len(matches) == 1:
        return matches[0]
    return None


async def ensure_voice(ctx: commands.Context) -> discord.VoiceClient | None:
    """コマンド実行者のボイスチャンネルにBotを接続する"""
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
        print(f"Voice Connection Error: {e}")
        return None

    return state.voice_client


def play_next(ctx: commands.Context):
    """再生終了時に呼ばれ、キューがあれば次の曲を再生する"""
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
        source = discord.FFmpegPCMAudio(filepath, **ffmpeg_options)
    except Exception as e:
        print(f"FFmpeg Error: {e}")
        asyncio.run_coroutine_threadsafe(ctx.send(f"音声作成エラー: `{e}`"), bot.loop)
        return

    def after_playing(error):
        if error:
            print(f"再生中エラー詳細: {error}")
            asyncio.run_coroutine_threadsafe(ctx.send(f"⚠️ 再生中にエラーが発生しました: `{error}`"), bot.loop)
        fut = asyncio.run_coroutine_threadsafe(
            _notify_and_play_next(ctx), bot.loop
        )
        try:
            fut.result()
        except Exception as e:
            print(f"次曲再生時エラー: {e}")

    try:
        if state.voice_client and state.voice_client.is_connected():
            state.voice_client.play(source, after=after_playing)
        else:
            asyncio.run_coroutine_threadsafe(ctx.send("⚠️ ボイス接続が切断されていたため再生を開始できませんでした。"), bot.loop)
    except Exception as e:
        err_msg = str(e) if str(e) else repr(e)
        print(f"play実行エラー: {err_msg}")
        asyncio.run_coroutine_threadsafe(ctx.send(f"⚠️ play実行時エラー: `{err_msg}`"), bot.loop)


async def _notify_and_play_next(ctx: commands.Context):
    state = get_state(ctx.guild.id)
    if state.queue:
        await ctx.send(f"次の曲を再生します: **{state.queue[0]}**")
    play_next(ctx)


@bot.event
async def on_ready():
    print(f"ログインしました: {bot.user} (ID: {bot.user.id})")
    print(f"音源フォルダ(絶対パス): {MUSIC_DIR}")
    print(f"検出されたファイル: {list_music_files()}")


@bot.command(name="list", help="musicフォルダ内の曲一覧を表示します")
async def list_songs(ctx: commands.Context):
    files = list_music_files()
    if not files:
        await ctx.send(f"`{MUSIC_DIR}` にMP3ファイルが見つかりませんでした。")
        return
    listing = "\n".join(f"- {f}" for f in files)
    await ctx.send(f"**利用可能な曲一覧**\n{listing}")


@bot.command(name="play", help="指定した曲を1曲再生します(現在の再生を中断)")
async def play(ctx: commands.Context, *, keyword: str):
    vc = await ensure_voice(ctx)
    if vc is None:
        return

    filename = find_music_file(keyword)
    if filename is None:
        await ctx.send(f"曲が見つかりませんでした: `{keyword}`\n`{COMMAND_PREFIX}list` で一覧を確認してください。")
        return

    state = get_state(ctx.guild.id)
    state.queue.clear()

    if vc.is_playing() or vc.is_paused():
        vc.stop()
        state.queue.insert(0, filename)
    else:
        state.queue.insert(0, filename)
        play_next(ctx)
        await ctx.send(f"再生開始処理を実行中: **{filename}**")
        return

    await ctx.send(f"再生を切り替えます: **{filename}**")


@bot.command(name="qadd", aliases=["queue"], help="曲をキューに追加します")
async def qadd(ctx: commands.Context, *, keyword: str):
    filename = find_music_file(keyword)
    if filename is None:
        await ctx.send(f"曲が見つかりませんでした: `{keyword}`\n`{COMMAND_PREFIX}list` で一覧を確認してください。")
        return

    vc = await ensure_voice(ctx)
    if vc is None:
        return

    state = get_state(ctx.guild.id)
    state.queue.append(filename)

    if not vc.is_playing() and not vc.is_paused():
        play_next(ctx)
        await ctx.send(f"再生開始: **{filename}**")
    else:
        await ctx.send(f"キューに追加しました: **{filename}**(現在 {len(state.queue)} 曲待ち)")


@bot.command(name="playall", help="musicフォルダの曲を全てキューに入れて順番に再生します")
async def playall(ctx: commands.Context):
    files = list_music_files()
    if not files:
        await ctx.send("再生できる曲がありません。")
        return

    vc = await ensure_voice(ctx)
    if vc is None:
        return

    state = get_state(ctx.guild.id)
    state.queue.extend(files)

    if not vc.is_playing() and not vc.is_paused():
        play_next(ctx)

    await ctx.send(f"{len(files)} 曲をキューに追加しました。順番に再生します。")


@bot.command(name="skip", help="今の曲をスキップして次の曲を再生します")
async def skip(ctx: commands.Context):
    state = get_state(ctx.guild.id)
    if state.voice_client and (state.voice_client.is_playing() or state.voice_client.is_paused()):
        state.voice_client.stop()
        await ctx.send("スキップしました。")
    else:
        await ctx.send("現在再生中の曲がありません。")


@bot.command(name="pause", help="再生を一時停止します")
async def pause(ctx: commands.Context):
    state = get_state(ctx.guild.id)
    if state.voice_client and state.voice_client.is_playing():
        state.voice_client.pause()
        await ctx.send("一時停止しました。")
    else:
        await ctx.send("再生中の曲がありません。")


@bot.command(name="resume", help="一時停止した再生を再開します")
async def resume(ctx: commands.Context):
    state = get_state(ctx.guild.id)
    if state.voice_client and state.voice_client.is_paused():
        state.voice_client.resume()
        await ctx.send("再生を再開しました。")
    else:
        await ctx.send("一時停止中の曲がありません。")


@bot.command(name="stop", help="再生を停止してキューをクリアします")
async def stop(ctx: commands.Context):
    state = get_state(ctx.guild.id)
    state.queue.clear()
    if state.voice_client:
        state.voice_client.stop()
    state.current = None
    await ctx.send("停止してキューをクリアしました。")


@bot.command(name="nowplaying", aliases=["np"], help="現在再生中の曲を表示します")
async def nowplaying(ctx: commands.Context):
    state = get_state(ctx.guild.id)
    if state.current:
        remaining = len(state.queue)
        await ctx.send(f"再生中: **{state.current}**(待ち {remaining} 曲)")
    else:
        await ctx.send("現在再生中の曲はありません。")


@bot.command(name="leave", help="ボイスチャンネルから切断します")
async def leave(ctx: commands.Context):
    state = get_state(ctx.guild.id)
    if state.voice_client:
        await state.voice_client.disconnect()
        state.voice_client = None
        state.queue.clear()
        state.current = None
        await ctx.send("切断しました。")
    else:
        await ctx.send("ボイスチャンネルに接続していません。")


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)

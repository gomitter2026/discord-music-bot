import os
import asyncio
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

MUSIC_DIR = './music'
queue = []
current_song = None

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

def get_music_files():
    """musicフォルダ内の音声ファイルを取得"""
    if not os.path.exists(MUSIC_DIR):
        os.makedirs(MUSIC_DIR)
        return []
    valid_exts = ('.mp3', '.wav', '.flac', '.m4a', '.ogg')
    return [f for f in os.listdir(MUSIC_DIR) if f.lower().endswith(valid_exts)]

def find_file(query):
    """部分一致でファイルを検索"""
    files = get_music_files()
    for f in files:
        if query.lower() in f.lower():
            return f
    return None

async def play_next(ctx):
    """キューの次の曲を再生"""
    global current_song
    if len(queue) > 0:
        current_song = queue.pop(0)
        file_path = os.path.join(MUSIC_DIR, current_song)
        source = discord.FFmpegPCMAudio(file_path)
        
        ctx.voice_client.play(
            source, 
            after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)
        )
        await ctx.send(f"🎵 再生中: **{current_song}**")
    else:
        current_song = None
        await ctx.send("再生キューが空になりました。")

async def ensure_voice(ctx):
    """VC接続確認"""
    if not ctx.author.voice:
        await ctx.send("ボイスチャンネルに入った状態で実行してください！")
        return False
    channel = ctx.author.voice.channel
    if ctx.voice_client is None:
        await channel.connect()
    elif ctx.voice_client.channel != channel:
        await ctx.voice_client.move_to(channel)
    return True

@bot.event
async def on_ready():
    print(f'ログイン完了: {bot.user}')

# 1. 曲一覧表示
@bot.command(name='list')
async def list_music(ctx):
    files = get_music_files()
    if not files:
        await ctx.send("`music` フォルダに曲がありません。")
        return
    file_list = "\n".join([f"• {f}" for f in files])
    await ctx.send(f"📂 **musicフォルダ内の曲一覧:**\n{file_list}")

# 2. 指定曲を割り込み再生
@bot.command(name='play')
async def play_song(ctx, *, query: str):
    if not await ensure_voice(ctx): return
    filename = find_file(query)
    if not filename:
        await ctx.send(f"曲が見つかりませんでした: `{query}`")
        return

    if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
        ctx.voice_client.stop() # 現状の再生を即中断

    queue.insert(0, filename) # 先頭に差し込んで再生
    await play_next(ctx)

# 3. キューに追加
@bot.command(name='qadd', aliases=['queue'])
async def queue_add(ctx, *, query: str):
    if not await ensure_voice(ctx): return
    filename = find_file(query)
    if not filename:
        await ctx.send(f"曲が見つかりませんでした: `{query}`")
        return

    queue.append(filename)
    await ctx.send(f"📥 キューに追加しました: **{filename}**")
    if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
        await play_next(ctx)

# 4. 全曲キュー追加＆再生
@bot.command(name='playall')
async def play_all(ctx):
    if not await ensure_voice(ctx): return
    files = get_music_files()
    if not files:
        await ctx.send("`music` フォルダに曲がありません。")
        return

    if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
        ctx.voice_client.stop()

    queue.clear()
    queue.extend(files)
    await ctx.send(f"🔁 `music` フォルダ内の全 {len(files)} 曲をキューに追加しました。")
    await play_next(ctx)

# 5. スキップ
@bot.command(name='skip')
async def skip_song(ctx):
    if ctx.voice_client and (ctx.voice_client.is_playing() or ctx.voice_client.is_paused()):
        ctx.voice_client.stop() # stopすると自動的に after 経由で play_next が呼ばれる
        await ctx.send("⏭️ 次の曲へスキップします。")
    else:
        await ctx.send("現在曲は再生されていません。")

# 6. 一時停止＆再開
@bot.command(name='pause')
async def pause_song(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ 再生を一時停止しました。")

@bot.command(name='resume')
async def resume_song(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ 再生を再開しました。")

# 7. 停止＆キュークリア
@bot.command(name='stop')
async def stop_music(ctx):
    global current_song
    queue.clear()
    current_song = None
    if ctx.voice_client:
        ctx.voice_client.stop()
    await ctx.send("⏹️ 再生を停止し、キューをクリアしました。")

# 8. 現在再生中の曲を表示
@bot.command(name='nowplaying', aliases=['np'])
async def now_playing(ctx):
    if current_song:
        await ctx.send(f"🎶 現在再生中: **{current_song}**")
    else:
        await ctx.send("現在再生中の曲はありません。")

# 9. 切断
@bot.command(name='leave')
async def leave_vc(ctx):
    global current_song
    queue.clear()
    current_song = None
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("👋 切断しました。")
    else:
        await ctx.send("Botはボイスチャンネルに接続していません。")

TOKEN = os.getenv('DISCORD_TOKEN')
if TOKEN:
    bot.run(TOKEN)

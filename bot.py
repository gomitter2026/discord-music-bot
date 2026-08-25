import os
import discord
from discord.ext import commands

# --- Botの基本設定 ---
# 必要なインテントの設定（音声・メッセージなど）
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# --- イベント処理 ---
@bot.event
async def on_ready():
    print(f'ログイン完了: {bot.user}')
    print(f'Opus ロード状況: {discord.opus.is_loaded()}')

# --- コマンド例（必要に応じてご自身のコードをここに記述） ---
@bot.command()
async def ping(ctx):
    await ctx.send('pong!')

# --- Botの起動 ---
# 環境変数 DISCORD_TOKEN を取得して実行
TOKEN = os.getenv('DISCORD_TOKEN')
if TOKEN:
    bot.run(TOKEN)
else:
    print("エラー: DISCORD_TOKEN が設定されていません。")

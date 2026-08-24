# Discord Music Bot

MP3音源をボイスチャンネルで再生するDiscord Bot(discord.py製)です。

## 機能

| コマンド | 説明 |
|---|---|
| `!list` | musicフォルダ内の曲一覧を表示 |
| `!play <曲名>` | 指定した曲を1曲再生(今の再生を中断して切り替え) |
| `!qadd <曲名>` (別名 `!queue`) | 曲をキューに追加(順番に再生) |
| `!playall` | musicフォルダの曲を全部キューに入れて連続再生 |
| `!skip` | 次の曲へスキップ |
| `!pause` / `!resume` | 一時停止・再開 |
| `!stop` | 停止してキューをクリア |
| `!nowplaying` (別名 `!np`) | 現在再生中の曲を表示 |
| `!leave` | ボイスチャンネルから切断 |

曲名はファイル名の完全一致・拡張子省略・部分一致に対応しています(例: `song.mp3` でも `song` でもOK)。

---

## 1. Discord Bot の準備

1. [Discord Developer Portal](https://discord.com/developers/applications) にアクセスし、新しいApplicationを作成
2. 左メニューの **Bot** タブでBotを作成し、**Token** を控える(後で `.env` に使用)
3. 同じBotタブで以下をONにする(重要):
   - **MESSAGE CONTENT INTENT**
4. **OAuth2 > URL Generator** で以下を選択してサーバー招待用URLを作成
   - Scopes: `bot`
   - Bot Permissions: `Send Messages`, `Connect`, `Speak`, `Read Message History`
5. 生成されたURLからBotを自分のサーバーに招待

---

## 2. VPSでの環境構築(Ubuntu想定)

```bash
# 必要パッケージをインストール
sudo apt update
sudo apt install -y python3 python3-pip python3-venv ffmpeg git

# プロジェクトを配置(このフォルダをVPSにアップロード)
cd /opt
sudo mkdir discord-music-bot && sudo chown $USER:$USER discord-music-bot
# ここに bot.py, config.py, requirements.txt, music/ などを転送(scp, git, sftpなど)

cd discord-music-bot

# 仮想環境を作成して依存関係をインストール
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 環境変数を設定
cp .env.example .env
nano .env   # DISCORD_TOKEN を書き込む

# musicフォルダにMP3ファイルを配置
# 例: /opt/discord-music-bot/music/曲名.mp3

# 動作確認
python bot.py
```

`ログインしました: BotName (ID: ...)` と表示されれば起動成功です。

---

## 3-A. Railwayでデプロイする(推奨・簡単)

Railwayは自動で24時間稼働・自動再起動してくれるので、VPSより管理が楽です。ただし**ファイルシステムが基本エフェメラル**(再デプロイのたびにリセットされる)なので、MP3ファイルは**Volume(永続ストレージ)**に置く必要があります。

### 手順

1. **GitHubリポジトリを作成**し、このプロジェクト一式(`bot.py`, `config.py`, `requirements.txt`, `nixpacks.toml`, `Procfile`, `railway.json` など)をpush
   - `music/` フォルダの中身(実際のMP3)は**リポジトリに含めない**(Volumeを使うため)
2. [Railway](https://railway.app/) にログインし、**New Project > Deploy from GitHub repo** で先ほどのリポジトリを選択
3. デプロイされたサービスの **Settings > Volumes** で新規Volumeを作成
   - Mount Path: `/app/music`
   - これでコンテナが再起動してもMP3ファイルが消えなくなります
4. **Variables** タブで環境変数を設定
   - `DISCORD_TOKEN` = Botトークン
   - `MUSIC_DIR` = `/app/music`
   - `COMMAND_PREFIX` = `!`(任意)
5. MP3ファイルをVolumeにアップロード。方法はいくつかあります:
   - **Railway CLIを使う方法**(おすすめ):
     ```bash
     npm install -g @railway/cli
     railway login
     railway link   # プロジェクトを選択
     railway ssh    # コンテナに入る
     ```
     `railway ssh` で入った後、`scp` や `curl` でファイルを配置するか、ローカルから直接転送したい場合は一時的に以下のようなアップロード用スクリプトを使うのが簡単です:
     - ローカルのmusicフォルダをzip化 → 一時的にGoogle Driveなどに置く → コンテナ内で `wget`/`curl` でダウンロードして展開
   - **簡易的な方法**: 曲数が少なく容量が小さい場合は、`music/` フォルダごとGitリポジトリに含めてしまってもOK(Volumeなしで運用)。ただしGitHubは1ファイル100MBまで、リポジトリ全体は数GB程度が目安です。
6. デプロイが成功すると自動的にBotが起動します。**Deployments** タブのログで `ログインしました: BotName` と表示されればOKです。

### 注意点

- Railwayの無料プランには実行時間・クレジットの制限があります。24時間稼働を安定させたい場合は有料プラン(Hobbyプラン/Developer Planなど)の利用を検討してください。最新の料金体系は [Railwayの料金ページ](https://railway.com/pricing) で確認してください。
- Botはボイスチャンネルに接続するだけでHTTPポートを公開する必要はないので、Railwayの「Public Networking」設定は不要です。
- 曲を追加・入れ替えたい場合は、Volumeを使っていれば `railway ssh` でコンテナに入りファイルを操作、Gitリポジトリ方式ならファイルをpushして再デプロイします。

---

## 3-B. VPSで常時稼働させる(systemdサービス化)

VPS再起動後も自動起動・クラッシュ時に自動再起動させるため、systemdサービスとして登録します。

`/etc/systemd/system/discord-music-bot.service` を作成:

```ini
[Unit]
Description=Discord Music Bot
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/opt/discord-music-bot
ExecStart=/opt/discord-music-bot/venv/bin/python bot.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

有効化:

```bash
sudo systemctl daemon-reload
sudo systemctl enable discord-music-bot
sudo systemctl start discord-music-bot

# ログ確認
sudo journalctl -u discord-music-bot -f
```

---

## 4. 曲を追加する

`music/` フォルダにMP3ファイルを置くだけです。Bot再起動は不要(`!list` で反映を確認できます)。

```
music/
├── 曲A.mp3
├── 曲B.mp3
└── 曲C.mp3
```

---

## 動画の画面共有について(補足)

Discordの「画面共有(Go Live)」機能はユーザーアカウント専用の仕組みで、Bot用の公式APIはありません。
今回のBotでは動画ファイルの**音声だけ**を抽出してボイスチャンネルに流すことは可能ですが(FFmpegが対応形式なら `!play` でmp4等も指定可)、映像そのものを画面共有として配信する機能は実装していません。

---

## 注意事項

- 著作権を有する、または利用許諾のある音源のみを再生してください。
- Botトークンは `.env` に保管し、`.gitignore` によりリポジトリには含まれません。他人と共有しないでください。


import io
from ftplib import FTP
import discord
from discord.ext import tasks, commands
import os
import json

from flask import Flask, Response
from threading import Thread

app = Flask('')


@app.route('/')
def home():
    html_content = '''
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>マインクラフトサーバー監視Bot</title>
        <style>
            body { 
                font-family: Arial, sans-serif; 
                text-align: center; 
                padding: 50px; 
                background-color: #f0f0f0;
            }
            .container {
                max-width: 600px;
                margin: 0 auto;
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
            }
            .status { 
                font-size: 18px; 
                margin: 20px 0; 
                padding: 15px;
                border-radius: 5px;
                background-color: #e8f5e8;
            }
            .online { color: green; }
            .offline { color: red; }
            h1 { color: #333; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎮 マインクラフトサーバー監視Bot</h1>
            <div class="status">
                <p class="online">✅ Discordボット稼働中</p>
                <p>📊 サーバー状態はDiscordで確認できます</p>
            </div>
            <hr>
            <p><strong>Discord チャンネルID:</strong> 1385555472605511780</p>
            <p><strong>監視間隔:</strong> 1分ごと</p>
            <p><strong>機能:</strong> プレイヤー数・サーバー状態の自動監視</p>
            <p><strong>サーバーポート:</strong> 5000</p>
        </div>
    </body>
    </html>
    '''
    return Response(html_content, mimetype='text/html')


def run():
    app.run(host='0.0.0.0', port=5000)


def keep_alive():
    t = Thread(target=run)
    t.start()


keep_alive()

# -- FTP接続情報（安全のため、環境変数やReplit Secretsに入れてください） --
FTP_HOST = "162.43.90.173"
FTP_PORT = 10021
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
LOG_PATH = "/minecraft/logs/latest.log"  # 実際のログファイルパスに変更してね

# -- Discord Bot情報 --
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# 環境変数の確認
if not FTP_USER or not FTP_PASS or not DISCORD_TOKEN:
    print("エラー: 必要な環境変数が設定されていません")
    print("FTP_USER, FTP_PASS, DISCORD_TOKEN を Replit Secrets で設定してください")
    exit(1)

CHANNEL_ID = 1385555472605511780  # 通知したいチャンネルIDに変更してね

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

last_status = None  # 状態変化の判定用
last_player_count = None  # プレイヤー数変化の判定用

MESSAGE_ID_FILE = "message_id.json"


def save_message_id(message_id):
    with open(MESSAGE_ID_FILE, "w") as f:
        json.dump({"message_id": message_id}, f)


def load_message_id():
    try:
        with open(MESSAGE_ID_FILE, "r") as f:
            data = json.load(f)
            return data.get("message_id")
    except FileNotFoundError:
        return None


def create_status_embed(status: str, player_count: int) -> discord.Embed:
    color_map = {
        "🟢起動中": discord.Color.green(),
        "🔴停止中": discord.Color.red(),
        "プレイヤー接続中": discord.Color.blurple(),
        "⚫️状態不明": discord.Color.greyple(),
        "⚫️ログなし（未起動または停止中）": discord.Color.dark_grey(),
    }

    embed = discord.Embed(title="マイクラサーバー状態",
                          description=f"**現在の状態：** `{status}`",
                          color=color_map.get(status, discord.Color.orange()))
    embed.add_field(name="👥 プレイヤー数", value=str(player_count), inline=False)
    return embed


def count_players(log_content):
    connected = set()
    disconnected = set()

    for line in log_content.splitlines():
        if "Player connected:" in line:
            # 例: Player connected: HonestLamp91678, ...
            parts = line.split("Player connected:")
            if len(parts) > 1:
                name = parts[1].split(",")[0].strip()
                connected.add(name)
        elif "Player disconnected:" in line:
            parts = line.split("Player disconnected:")
            if len(parts) > 1:
                name = parts[1].split(",")[0].strip()
                disconnected.add(name)

    # 実際に接続中のプレイヤー = 接続したけど切断していない人
    current_players = connected - disconnected
    return len(current_players)


def fetch_log():
    with FTP() as ftp:
        ftp.connect(FTP_HOST, FTP_PORT)
        ftp.login(FTP_USER, FTP_PASS)
        bio = io.BytesIO()
        ftp.retrbinary(f"RETR {LOG_PATH}", bio.write)
        bio.seek(0)
        return bio.read().decode("utf-8")


def parse_status(log_content):
    if not log_content.strip():
        return "⚫️ログなし（未起動または停止中）"

    lines = log_content.strip().splitlines()
    last_line = lines[-1].lower()

    if "stop" in last_line:
        return "🔴停止中"

    if any("server started." in line.lower() for line in lines):
        return "🟢起動中"

    return "⚫️状態不明"


@tasks.loop(minutes=1)
async def check_server_status():
    global last_status, last_player_count
    try:
        log_content = fetch_log()
        status = parse_status(log_content)
        player_count = count_players(log_content)

        if status != last_status or player_count != last_player_count:
            last_status = status
            last_player_count = player_count
            channel = bot.get_channel(CHANNEL_ID)
            embed = create_status_embed(status, player_count)

            message_id = load_message_id()
            if message_id:
                try:
                    message = await channel.fetch_message(message_id)
                    await message.edit(embed=embed)
                except discord.NotFound:
                    # メッセージが見つからない場合は新しく送信
                    new_message = await channel.send(embed=embed)
                    save_message_id(new_message.id)
            else:
                # 初回送信
                new_message = await channel.send(embed=embed)
                save_message_id(new_message.id)

    except Exception as e:
        print(f"エラー: {e}")


@bot.event
async def on_ready():
    print(f"Bot起動: {bot.user}")
    check_server_status.start()


bot.run(DISCORD_TOKEN)

from flask import Flask
from threading import Thread

app = Flask('')


@app.route('/')
def home():
    return "I'm alive!"


def run():
    app.run(host='0.0.0.0', port=3000)


def keep_alive():
    t = Thread(target=run)
    t.start()


keep_alive()


# ...以下、あなたのBotコード...

import io
from ftplib import FTP
import discord
from discord.ext import tasks, commands
import os

# -- FTP接続情報（安全のため、環境変数やReplit Secretsに入れてください） --
FTP_HOST = "162.43.90.173"
FTP_PORT = 10021
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
LOG_PATH = "/minecraft/logs/latest.log"  # 実際のログファイルパスに変更してね

# -- Discord Bot情報 --
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = 1385555472605511780  # 通知したいチャンネルIDに変更してね

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

last_status = None  # 状態変化の判定用


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


# ✅ まず関数を定義（上の方に書く）
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


# ✅ その後、ループやイベントで使う
@tasks.loop(minutes=1)
async def check_server_status():
    global last_status
    try:
        log_content = fetch_log()
        status = parse_status(log_content)
        player_count = count_players(log_content)

        if status != last_status or player_count != getattr(
                check_server_status, "last_player_count", None):
            last_status = status
            check_server_status.last_player_count = player_count
            channel = bot.get_channel(CHANNEL_ID)
            embed = create_status_embed(status, player_count)

            if not hasattr(bot, "status_message"):
                bot.status_message = await channel.send(embed=embed)
            else:
                await bot.status_message.edit(embed=embed)

    except Exception as e:
        print(f"エラー: {e}")


@bot.event
async def on_ready():
    print(f"Bot起動: {bot.user}")
    check_server_status.start()


bot.run(DISCORD_TOKEN)

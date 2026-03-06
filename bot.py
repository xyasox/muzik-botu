import subprocess
import sys
import os

# Gerekli Python paketlerini yukle
subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "PyNaCl", "discord.py[voice]", "yt-dlp"])

# ffmpeg'i sisteme yukle
def ffmpeg_yukle():
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True)
        if result.returncode == 0:
            print("[ffmpeg] Zaten yuklu!")
            return
    except FileNotFoundError:
        pass

    print("[ffmpeg] Yukleniyor...")
    try:
        subprocess.check_call(["apt-get", "install", "-y", "ffmpeg"])
        print("[ffmpeg] apt-get ile yuklendi!")
        return
    except Exception as e:
        print(f"[ffmpeg] apt-get basarisiz: {e}")

    try:
        subprocess.check_call(["apt", "install", "-y", "ffmpeg"])
        print("[ffmpeg] apt ile yuklendi!")
        return
    except Exception as e:
        print(f"[ffmpeg] apt basarisiz: {e}")

    # Manuel indir
    try:
        print("[ffmpeg] Manuel indiriliyor...")
        subprocess.check_call([
            "wget", "-q",
            "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz",
            "-O", "/tmp/ffmpeg.tar.xz"
        ])
        subprocess.check_call(["tar", "-xf", "/tmp/ffmpeg.tar.xz", "-C", "/tmp/"])
        subprocess.check_call(["cp", "/tmp/ffmpeg-master-latest-linux64-gpl/bin/ffmpeg", "/usr/local/bin/ffmpeg"])
        subprocess.check_call(["chmod", "+x", "/usr/local/bin/ffmpeg"])
        print("[ffmpeg] Manuel yukleme basarili!")
    except Exception as e:
        print(f"[ffmpeg] Manuel yukleme basarisiz: {e}")

ffmpeg_yukle()

import discord
from discord.ext import commands
import yt_dlp
import asyncio
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from collections import deque

DISCORD_TOKEN         = os.environ.get("DISCORD_TOKEN")
SPOTIFY_CLIENT_ID     = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states    = True
bot = commands.Bot(command_prefix="!", intents=intents)

try:
    sp = spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
        )
    )
except Exception:
    sp = None
    print("Spotify baglantisi kurulamadi.")

queues      = {}
volumes     = {}
now_playing = {}

YDL_OPTS_SC = {
    "format": "bestaudio/best",
    "quiet": False,
    "no_warnings": False,
    "noplaylist": True,
    "default_search": "scsearch",
    "source_address": "0.0.0.0",
}

YDL_OPTS_YT = {
    "format": "bestaudio/best",
    "quiet": False,
    "no_warnings": False,
    "noplaylist": True,
    "source_address": "0.0.0.0",
    "cookiefile": "cookies.txt",
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    },
}

FFMPEG_OPTS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

def get_queue(guild_id):
    if guild_id not in queues:
        queues[guild_id] = deque()
    return queues[guild_id]

def get_volume(guild_id):
    return volumes.get(guild_id, 0.5)

async def ara(sorgu):
    loop = asyncio.get_event_loop()
    is_youtube = "youtube.com" in sorgu or "youtu.be" in sorgu
    opts = YDL_OPTS_YT if is_youtube else YDL_OPTS_SC
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            bilgi = await loop.run_in_executor(None, lambda: ydl.extract_info(sorgu, download=False))
            if "entries" in bilgi:
                bilgi = bilgi["entries"][0]
            print(f"[OK] Bulundu: {bilgi.get('title')}")
            return {"title": bilgi.get("title", "Bilinmiyor"), "url": bilgi["url"]}
    except Exception as hata:
        print(f"[Hata] {hata}")
        return None

async def spotify_sarkila(spotify_url):
    if sp is None:
        return []
    sorgular = []
    loop = asyncio.get_event_loop()
    try:
        if "track" in spotify_url:
            sarki = await loop.run_in_executor(None, lambda: sp.track(spotify_url))
            sorgular.append(f"{sarki['artists'][0]['name']} - {sarki['name']}")
        elif "playlist" in spotify_url:
            sonuclar = await loop.run_in_executor(None, lambda: sp.playlist_tracks(spotify_url))
            for ogre in sonuclar["items"][:25]:
                t = ogre.get("track")
                if t:
                    sorgular.append(f"{t['artists'][0]['name']} - {t['name']}")
        elif "album" in spotify_url:
            sonuclar = await loop.run_in_executor(None, lambda: sp.album_tracks(spotify_url))
            for t in sonuclar["items"][:25]:
                sorgular.append(f"{t['artists'][0]['name']} - {t['name']}")
    except Exception as hata:
        print(f"[Spotify Hata] {hata}")
    return sorgular

def siradakini_cal(guild_id, voice_client):
    kuyruk = get_queue(guild_id)
    if not kuyruk:
        now_playing.pop(guild_id, None)
        return
    sarki = kuyruk.popleft()
    now_playing[guild_id] = sarki["title"]
    kaynak = discord.PCMVolumeTransformer(
        discord.FFmpegPCMAudio(sarki["url"], **FFMPEG_OPTS),
        volume=get_volume(guild_id),
    )
    def bitti(hata):
        if hata:
            print(f"[Oynatma Hatasi] {hata}")
        siradakini_cal(guild_id, voice_client)
    voice_client.play(kaynak, after=bitti)

@bot.event
async def on_ready():
    try:
        await bot.tree.sync()
    except Exception as e:
        print(f"Slash komut sync hatasi: {e}")
    print(f"Bot aktif: {bot.user.name}")
    print(f"{len(bot.guilds)} sunucuda calisiyor.")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="!yardim"))

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("Boyle bir komut yok. `!yardim` yaz.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Eksik bilgi. Ornek: `!cal Tarkan Simarik`")
    else:
        print(f"[Komut Hatasi] {error}")

@bot.hybrid_command(name="cal", description="Muzik calar.")
async def cal(ctx, *, sorgu: str):
    if not ctx.author.voice:
        return await ctx.send("Once bir ses kanalina gir!")
    await ctx.defer()
    vc = ctx.voice_client
    if not vc:
        vc = await ctx.author.voice.channel.connect()
    elif vc.channel != ctx.author.voice.channel:
        await vc.move_to(ctx.author.voice.channel)
    guild_id = ctx.guild.id
    kuyruk = get_queue(guild_id)
    if "spotify.com" in sorgu:
        if sp is None:
            return await ctx.send("Spotify baglantisi kurulamadi.")
        await ctx.send("Spotify'dan sarkiler aliniyor...")
        sorgular = await spotify_sarkila(sorgu)
        if not sorgular:
            return await ctx.send("Spotify'dan sarki alinamadi.")
        eklenen = 0
        for s in sorgular:
            bilgi = await ara(s)
            if bilgi:
                kuyruk.append(bilgi)
                eklenen += 1
        await ctx.send(f"{eklenen} sarki kuyruga eklendi!")
    else:
        await ctx.send(f"Aranıyor: `{sorgu}`...")
        bilgi = await ara(sorgu)
        if not bilgi:
            return await ctx.send("Sarki bulunamadi.")
        kuyruk.append(bilgi)
        await ctx.send(f"Kuyruga eklendi: **{bilgi['title']}**")
    if not vc.is_playing() and not vc.is_paused():
        siradakini_cal(guild_id, vc)
        await ctx.send(f"Simdi caliniyor: **{now_playing.get(guild_id, '?')}**")

@bot.hybrid_command(name="dur", description="Duraklatir.")
async def dur(ctx):
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await ctx.send("Duraklatildi. `!devam` ile devam et.")
    else:
        await ctx.send("Su an calan bir sey yok.")

@bot.hybrid_command(name="devam", description="Devam ettirir.")
async def devam(ctx):
    vc = ctx.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await ctx.send("Devam ediyor!")
    else:
        await ctx.send("Duraklatilmis bir sey yok.")

@bot.hybrid_command(name="atla", description="Sonraki sarkiya gecer.")
async def atla(ctx):
    vc = ctx.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
        await ctx.send("Atlandi!")
    else:
        await ctx.send("Calan bir sey yok.")

@bot.hybrid_command(name="durdur", description="Durdurur ve cıkar.")
async def durdur(ctx):
    queues.pop(ctx.guild.id, None)
    now_playing.pop(ctx.guild.id, None)
    vc = ctx.voice_client
    if vc:
        await vc.disconnect()
        await ctx.send("Durduruldu ve kanaldan cıkıldı.")
    else:
        await ctx.send("Bot zaten kanalda degil.")

@bot.hybrid_command(name="ses", description="Ses seviyesi (0-100).")
async def ses(ctx, seviye: int):
    if not (0 <= seviye <= 100):
        return await ctx.send("0-100 arasi bir sayi gir.")
    volumes[ctx.guild.id] = seviye / 100
    vc = ctx.voice_client
    if vc and vc.source:
        vc.source.volume = seviye / 100
    cubuk = "\u2588" * int(seviye/10) + "\u2591" * (10 - int(seviye/10))
    await ctx.send(f"Ses: [{cubuk}] **{seviye}%**")

@bot.hybrid_command(name="kuyruk", description="Kuyrugu gosterir.")
async def kuyruk_goster(ctx):
    kuyruk = get_queue(ctx.guild.id)
    su_an = now_playing.get(ctx.guild.id)
    if not su_an and not kuyruk:
        return await ctx.send("Kuyruk bos. `!cal <sarki>` ile ekle.")
    satirlar = []
    if su_an:
        satirlar.append(f"Simdi: **{su_an}**")
        satirlar.append("-" * 30)
    for i, s in enumerate(list(kuyruk)[:10], 1):
        satirlar.append(f"{i}. {s['title']}")
    if len(kuyruk) > 10:
        satirlar.append(f"... ve {len(kuyruk)-10} sarki daha.")
    await ctx.send("\n".join(satirlar))

@bot.hybrid_command(name="simdi", description="Su an calani gosterir.")
async def simdi(ctx):
    su_an = now_playing.get(ctx.guild.id)
    await ctx.send(f"Simdi caliniyor: **{su_an}**" if su_an else "Su an calan bir sarki yok.")

@bot.hybrid_command(name="temizle", description="Kuyrugu temizler.")
async def temizle(ctx):
    queues.pop(ctx.guild.id, None)
    await ctx.send("Kuyruk temizlendi!")

@bot.hybrid_command(name="yardim", description="Komutlari listeler.")
async def yardim(ctx):
    embed = discord.Embed(title="Muzik Botu Komutlari", color=discord.Color.blue())
    embed.add_field(name="Muzik Cal", value="`!cal <sarki>` `!cal <YouTube linki>` `!cal <Spotify linki>`", inline=False)
    embed.add_field(name="Kontroller", value="`!dur` `!devam` `!atla` `!durdur`", inline=False)
    embed.add_field(name="Ses & Kuyruk", value="`!ses <0-100>` `!kuyruk` `!simdi` `!temizle`", inline=False)
    embed.set_footer(text="Ornek: !cal Tarkan Simarik")
    await ctx.send(embed=embed)

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("DISCORD_TOKEN bulunamadi!")
    else:
        bot.run(DISCORD_TOKEN)

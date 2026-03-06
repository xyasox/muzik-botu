import subprocess
import sys
subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "PyNaCl", "discord.py[voice]", "yt-dlp"])

import discord
from discord.ext import commands
import yt_dlp
import asyncio
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import os
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

YDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": False,
    "no_warnings": False,
    "noplaylist": False,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "extractor_retries": 5,
    "cookiefile": "cookies.txt",
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "geo_bypass": True,
    "age_limit": None,
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
    "postprocessors": [],
    "prefer_insecure": False,
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

async def youtube_ara(sorgu):
    loop = asyncio.get_event_loop()

    # Farkli format secenekleri dene
    format_secenekleri = [
        "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best",
        "worstaudio/bestaudio/best",
        "bestaudio*",
        "best",
    ]

    for fmt in format_secenekleri:
        try:
            opts = dict(YDL_OPTS)
            opts["format"] = fmt
            with yt_dlp.YoutubeDL(opts) as ydl:
                bilgi = await loop.run_in_executor(
                    None, lambda: ydl.extract_info(sorgu, download=False)
                )
                if "entries" in bilgi:
                    bilgi = bilgi["entries"][0]
                url = bilgi.get("url") or bilgi.get("webpage_url")
                if url:
                    print(f"[YouTube OK] Format: {fmt} | {bilgi.get('title')}")
                    return {"title": bilgi.get("title", "Bilinmiyor"), "url": url}
        except Exception as hata:
            print(f"[YouTube Hata] Format {fmt}: {hata}")
            continue

    return None

async def spotify_sarkila(spotify_url):
    if sp is None:
        return []
    sorgular = []
    loop = asyncio.get_event_loop()
    try:
        if "track" in spotify_url:
            sarki   = await loop.run_in_executor(None, lambda: sp.track(spotify_url))
            sanatci = sarki["artists"][0]["name"]
            ad      = sarki["name"]
            sorgular.append(f"{sanatci} - {ad}")
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
    ses_seviyesi = get_volume(guild_id)
    kaynak = discord.PCMVolumeTransformer(
        discord.FFmpegPCMAudio(sarki["url"], **FFMPEG_OPTS),
        volume=ses_seviyesi,
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
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.listening, name="!yardim")
    )

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("Boyle bir komut yok. Komutlar icin `!yardim` yaz.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Eksik bilgi girdin. Ornek: `!cal Tarkan Simarik`")
    else:
        print(f"[Komut Hatasi] {error}")

@bot.hybrid_command(name="cal", description="YouTube veya Spotify'dan muzik calar.")
async def cal(ctx, *, sorgu: str):
    if not ctx.author.voice:
        return await ctx.send("Once bir ses kanalina gir, sonra komutu kullan!")
    await ctx.defer()
    vc = ctx.voice_client
    if not vc:
        vc = await ctx.author.voice.channel.connect()
    elif vc.channel != ctx.author.voice.channel:
        await vc.move_to(ctx.author.voice.channel)
    guild_id = ctx.guild.id
    kuyruk   = get_queue(guild_id)
    if "spotify.com" in sorgu:
        if sp is None:
            return await ctx.send("Spotify baglantisi kurulamadi.")
        await ctx.send("Spotify'dan sarkiler aliniyor, lutfen bekle...")
        sorgular = await spotify_sarkila(sorgu)
        if not sorgular:
            return await ctx.send("Spotify'dan sarki alinamadi. Linki kontrol et.")
        eklenen = 0
        for s in sorgular:
            bilgi = await youtube_ara(s)
            if bilgi:
                kuyruk.append(bilgi)
                eklenen += 1
        await ctx.send(f"{eklenen} sarki kuyruga eklendi!")
    else:
        bilgi = await youtube_ara(sorgu)
        if not bilgi:
            return await ctx.send("Sarki bulunamadi. Farkli bir sey dene.")
        kuyruk.append(bilgi)
        await ctx.send(f"Kuyruga eklendi: **{bilgi['title']}**")
    if not vc.is_playing() and not vc.is_paused():
        siradakini_cal(guild_id, vc)
        await ctx.send(f"Simdi caliniyor: **{now_playing.get(guild_id, '?')}**")

@bot.hybrid_command(name="dur", description="Muzigi duraklatir.")
async def dur(ctx):
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await ctx.send("Duraklatildi. Devam ettirmek icin `!devam` yaz.")
    else:
        await ctx.send("Su an calan bir sey yok.")

@bot.hybrid_command(name="devam", description="Duraklatilmis muzigi devam ettirir.")
async def devam(ctx):
    vc = ctx.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await ctx.send("Devam ediyor!")
    else:
        await ctx.send("Duraklatilmis bir sey yok.")

@bot.hybrid_command(name="atla", description="Mevcut sarkiyi atlar.")
async def atla(ctx):
    vc = ctx.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
        await ctx.send("Atlandi! Siradaki sarkiya geciliyor...")
    else:
        await ctx.send("Calan bir sey yok.")

@bot.hybrid_command(name="durdur", description="Muzigi durdurur ve ses kanalindan cikar.")
async def durdur(ctx):
    guild_id = ctx.guild.id
    queues.pop(guild_id, None)
    now_playing.pop(guild_id, None)
    vc = ctx.voice_client
    if vc:
        await vc.disconnect()
        await ctx.send("Muzik durduruldu ve kanaldan cikildi.")
    else:
        await ctx.send("Bot zaten bir ses kanalinda degil.")

@bot.hybrid_command(name="ses", description="Ses seviyesini ayarlar (0 ile 100 arasi).")
async def ses(ctx, seviye: int):
    if not (0 <= seviye <= 100):
        return await ctx.send("Lutfen 0 ile 100 arasinda bir sayi gir. Ornek: `!ses 75`")
    guild_id = ctx.guild.id
    volumes[guild_id] = seviye / 100
    vc = ctx.voice_client
    if vc and vc.source:
        vc.source.volume = seviye / 100
    dolu  = int(seviye / 10)
    bos   = 10 - dolu
    cubuk = "\u2588" * dolu + "\u2591" * bos
    await ctx.send(f"Ses: [{cubuk}] **{seviye}%**")

@bot.hybrid_command(name="kuyruk", description="Muzik kuyrugunu gosterir.")
async def kuyruk_goster(ctx):
    kuyruk = get_queue(ctx.guild.id)
    su_an  = now_playing.get(ctx.guild.id)
    if not su_an and not kuyruk:
        return await ctx.send("Kuyruk bos. Muzik eklemek icin `!cal <sarki adi>` kullan.")
    satirlar = []
    if su_an:
        satirlar.append(f"Simdi caliniyor: **{su_an}**")
        satirlar.append("-" * 30)
    for i, sarki in enumerate(list(kuyruk)[:10], 1):
        satirlar.append(f"{i}. {sarki['title']}")
    if len(kuyruk) > 10:
        satirlar.append(f"... ve {len(kuyruk) - 10} sarki daha.")
    satirlar.append(f"\nToplam kuyrukta: **{len(kuyruk)} sarki**")
    await ctx.send("\n".join(satirlar))

@bot.hybrid_command(name="simdi", description="Su an calan sarkiyi gosterir.")
async def simdi(ctx):
    su_an = now_playing.get(ctx.guild.id)
    if su_an:
        await ctx.send(f"Simdi caliniyor: **{su_an}**")
    else:
        await ctx.send("Su an calan bir sarki yok.")

@bot.hybrid_command(name="temizle", description="Muzik kuyrugunu temizler.")
async def temizle(ctx):
    queues.pop(ctx.guild.id, None)
    await ctx.send("Kuyruk temizlendi! Tum sarkiler silindi.")

@bot.hybrid_command(name="yardim", description="Tum komutlari listeler.")
async def yardim(ctx):
    embed = discord.Embed(
        title="Muzik Botu — Komut Listesi",
        description="Asagidaki komutlari kullanabilirsin:",
        color=discord.Color.blue()
    )
    embed.add_field(name="Muzik Cal", value=(
        "`!cal <sarki adi>` — Sarki ara ve cal\n"
        "`!cal <YouTube linki>` — YouTube'dan cal\n"
        "`!cal <Spotify linki>` — Spotify'dan cal\n"
    ), inline=False)
    embed.add_field(name="Kontroller", value=(
        "`!dur` — Duraklat\n"
        "`!devam` — Devam et\n"
        "`!atla` — Sonraki sarkiya gec\n"
        "`!durdur` — Durdur ve cik\n"
    ), inline=False)
    embed.add_field(name="Ses ve Kuyruk", value=(
        "`!ses <0-100>` — Ses seviyesini ayarla\n"
        "`!kuyruk` — Kuyrugu goster\n"
        "`!simdi` — Su an calanı goster\n"
        "`!temizle` — Kuyrugu temizle\n"
    ), inline=False)
    embed.set_footer(text="Ornek: !cal Tarkan Simarik")
    await ctx.send(embed=embed)

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("DISCORD_TOKEN bulunamadi! Railway'de Variables kismina ekle.")
    else:
        bot.run(DISCORD_TOKEN)

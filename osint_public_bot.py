import asyncio
import base64
import hashlib
import ipaddress
import json
import math
import os
import random
import re
import secrets
import socket
import ssl
import string
import time
import urllib.parse
import uuid as uuidlib
from datetime import datetime, timezone
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

TOKEN = os.environ.get("DISCORD_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")
GUILD_ID = int(os.environ.get("DISCORD_GUILD_ID", "0") or "0")

bot = commands.Bot(command_prefix="!", intents=discord.Intents.default() | discord.Intents(members=True))
SESSION = None
START = time.time()

DNS_TYPES = ["A", "AAAA", "CNAME", "MX", "NS", "TXT", "SOA", "CAA", "PTR", "SRV", "ANY"]
COMMON_PORTS = [21, 22, 23, 25, 53, 80, 110, 111, 135, 139, 143, 443, 445, 465, 587, 993, 995,
                1433, 1521, 2049, 2082, 2083, 2086, 2087, 3000, 3306, 3389, 5432, 5900, 6379,
                8000, 8080, 8443, 8888, 9000, 9090, 9200, 27017]
DNSBL = ["zen.spamhaus.org", "bl.spamcop.net", "spam.spamrats.com", "dnsbl.dronebl.org",
         "b.barracudacentral.org", "ubl.unsubscore.com", "psbl.surriel.com", "dnsbl.sorbs.net"]


def f(v):
    return str(v) if v not in (None, "") else "n/a"


def box(title, rows):
    out = ["```", title, "-" * 46]
    for r in rows:
        out.append(str(r))
    out.append("```")
    return "\n".join(out)[:1990]


async def jget(url, timeout=15):
    try:
        async with SESSION.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout,
                               allow_redirects=True) as r:
            if r.status != 200:
                return None
            return await r.json(content_type=None)
    except Exception:
        return None


async def jpost(url, payload, timeout=15):
    try:
        async with SESSION.post(url, data=json.dumps(payload),
                                headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"},
                                timeout=timeout) as r:
            if r.status != 200:
                return None
            return await r.json(content_type=None)
    except Exception:
        return None


async def tget(url, timeout=15):
    try:
        async with SESSION.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout,
                               allow_redirects=True) as r:
            return r.status, await r.text()
    except Exception:
        return 0, ""


async def guard(interaction):
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True)
    except Exception:
        pass


async def reply(interaction, text):
    try:
        await interaction.followup.send(text)
    except Exception:
        pass


def tcp_ms(host, port, timeout=4.0):
    t0 = time.perf_counter()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return int((time.perf_counter() - t0) * 1000)
    except Exception:
        return None
    finally:
        try:
            s.close()
        except Exception:
            pass


def is_ip(s):
    try:
        ipaddress.ip_address(s)
        return True
    except Exception:
        return False


def clean_target(t):
    t = (t or "").strip()
    t = re.sub(r"^[a-z]+://", "", t, flags=re.I)
    t = t.split("/")[0].split("?")[0].split("@")[-1].split(":")[0]
    return t


async def dns_lookup(name, rtype):
    j = await jget("https://dns.google/resolve?name=" + urllib.parse.quote(name) + "&type=" + rtype)
    return j or {}


@bot.event
async def on_ready():
    global SESSION
    if SESSION is None:
        SESSION = aiohttp.ClientSession()
    try:
        if GUILD_ID:
            g = discord.Object(id=GUILD_ID)
            bot.tree.copy_global_to(guild=g)
            await bot.tree.sync(guild=g)
        else:
            await bot.tree.sync()
    except Exception:
        pass


@bot.tree.command(name="about", description="what this bot is")
async def about_cmd(interaction: discord.Interaction):
    await guard(interaction)
    await reply(interaction, "open OSINT baseplate - keyless, no backend. drop your token in and go.\n"
                            "every lookup uses free public APIs. run /help for the command list.")


@bot.tree.command(name="help", description="list every command")
async def help_cmd(interaction: discord.Interaction):
    await guard(interaction)
    names = sorted({c.name for c in bot.tree.walk_commands()})
    chunk = []
    out = []
    for n in names:
        chunk.append("/" + n)
        if len(chunk) == 8:
            out.append(" ".join(chunk))
            chunk = []
    if chunk:
        out.append(" ".join(chunk))
    await reply(interaction, box("COMMANDS (" + str(len(names)) + ")", out))


@bot.tree.command(name="sources", description="free data sources wired in")
async def sources_cmd(interaction: discord.Interaction):
    await guard(interaction)
    src = ["ipwho.is / ip-api.com   -> ip geo, isp, asn", "bgpview.io / rdap.org  -> asn info",
           "dns.google             -> dns + reverse dns", "rdap.org               -> whois/rdap",
           "nominatim.openstreet   -> geocode + reverse", "crt.sh                 -> subdomains",
           "api.macvendors.com     -> mac vendor", "api.github.com         -> github",
           "api.mojang.com         -> minecraft", "gravatar.com           -> gravatar",
           "reddit.com             -> reddit", "api.chess.com          -> chess",
           "users.roblox.com       -> roblox", "registry.npmjs.org     -> npm",
           "pypi.org               -> pypi", "crates.io              -> crates",
           "openlibrary.org        -> isbn + books", "dictionaryapi.dev      -> definitions",
           "restcountries.com      -> country data", "coingecko.com          -> crypto price",
           "frankfurter.app        -> fx rates", "qrserver.com           -> qr codes"]
    await reply(interaction, box("SOURCES", src))


@bot.tree.command(name="stats", description="uptime and latency")
async def stats_cmd(interaction: discord.Interaction):
    await guard(interaction)
    up = int(time.time() - START)
    cmds = len(list(bot.tree.walk_commands()))
    lat = round(bot.latency * 1000)
    await reply(interaction, box("STATS", ["uptime   " + str(up) + "s", "commands " + str(cmds),
                                           "latency  " + str(lat) + "ms", "guilds   " + str(len(bot.guilds))]))


@bot.tree.command(name="ping", description="bot latency")
async def ping_cmd(interaction: discord.Interaction):
    await guard(interaction)
    await reply(interaction, "pong " + str(round(bot.latency * 1000)) + "ms")


@bot.tree.command(name="ip", description="ip geolocation, isp, asn and reverse dns")
@app_commands.describe(address="ipv4 or ipv6")
async def ip_cmd(interaction: discord.Interaction, address: str):
    await guard(interaction)
    try:
        ip = clean_target(address)
        if not is_ip(ip):
            await reply(interaction, "not a valid ip address")
            return
        j = await jget("https://ipwho.is/" + urllib.parse.quote(ip))
        if not j or j.get("success") is False:
            j = await jget("https://ip-api.com/json/" + urllib.parse.quote(ip) +
                           "?fields=status,country,regionName,city,isp,org,as,timezone,lat,lon,query")
            if j and j.get("status") == "success":
                rows = ["ip       " + f(j.get("query")), "country  " + f(j.get("country")),
                        "region   " + f(j.get("regionName")), "city     " + f(j.get("city")),
                        "isp      " + f(j.get("isp")), "org      " + f(j.get("org")),
                        "asn      " + f(j.get("as")), "tz       " + f(j.get("timezone")),
                        "coords   " + f(j.get("lat")) + ", " + f(j.get("lon"))]
                await reply(interaction, box("IP " + ip, rows))
                return
            await reply(interaction, "ip lookup failed - try again later")
            return
        c = j.get("connection") or {}
        tz = j.get("timezone") or {}
        rows = ["ip       " + f(j.get("ip")), "type     " + f(j.get("type")),
                "country  " + f(j.get("country")) + " " + f((j.get("flag") or {}).get("emoji")),
                "region   " + f(j.get("region")), "city     " + f(j.get("city")),
                "isp      " + f(c.get("isp")), "org      " + f(c.get("org")), "asn      " + f(c.get("asn")),
                "tz       " + f(tz.get("id")), "coords   " + f(j.get("latitude")) + ", " + f(j.get("longitude"))]
        names = await rdns(ip)
        if names:
            rows.append("rdns     " + ", ".join(names[:4]))
        await reply(interaction, box("IP " + ip, rows))
    except Exception:
        await reply(interaction, "ip lookup failed")


@bot.tree.command(name="asn", description="asn information")
@app_commands.describe(number="asn number e.g. 15169 or AS15169")
async def asn_cmd(interaction: discord.Interaction, number: str):
    await guard(interaction)
    try:
        n = re.sub(r"[^0-9]", "", number)
        if not n:
            await reply(interaction, "give me an asn number like 15169")
            return
        j = await jget("https://api.bgpview.io/asn/" + n)
        d = (j or {}).get("data") or {}
        if d:
            rows = ["asn      AS" + f(d.get("asn")), "name     " + f(d.get("name")),
                    "desc     " + f(d.get("description_full") or d.get("description_short")),
                    "country  " + f(d.get("country_code")), "rir      " + f(d.get("rir_allocation", {}).get("rir")),
                    "prefixes " + str(len(d.get("prefixes") or [])),
                    "upstream " + str(len(d.get("upstreams") or [])),
                    "peers    " + str(len(d.get("peers") or []))]
            await reply(interaction, box("ASN " + n, rows))
            return
        j = await jget("https://rdap.org/autnum/" + n)
        if j and isinstance(j, dict) and j.get("handle"):
            rows = ["asn      " + f(j.get("handle")), "name     " + f(j.get("name")),
                    "start    " + f(j.get("startAutnum")), "end      " + f(j.get("endAutnum")),
                    "country  " + f(j.get("country"))]
            await reply(interaction, box("ASN " + n, rows))
            return
        await reply(interaction, "no asn data found for " + n)
    except Exception:
        await reply(interaction, "asn lookup failed")


@bot.tree.command(name="rdns", description="reverse dns for an ip")
@app_commands.describe(address="ipv4")
async def rdns_cmd(interaction: discord.Interaction, address: str):
    await guard(interaction)
    try:
        ip = clean_target(address)
        if not is_ip(ip):
            await reply(interaction, "not a valid ip")
            return
        names = await rdns(ip)
        await reply(interaction, box("RDNS " + ip, names or ["no ptr records"]))
    except Exception:
        await reply(interaction, "rdns failed")


@bot.tree.command(name="dns", description="resolve a dns record")
@app_commands.describe(domain="domain name", record="record type")
@app_commands.choices(record=[app_commands.Choice(name=t, value=t) for t in DNS_TYPES])
async def dns_cmd(interaction: discord.Interaction, domain: str, record: Optional[app_commands.Choice[str]] = None):
    await guard(interaction)
    try:
        rt = record.value if record else "A"
        d = clean_target(domain)
        j = await dns_lookup(d, rt)
        ans = j.get("Answer") or []
        rows = ["query    " + d + " " + rt, "status   " + str(j.get("Status"))]
        for a in ans[:15]:
            rows.append("  " + f(a.get("name")) + "  " + str(a.get("data")))
        if not ans:
            rows.append("  no records")
        await reply(interaction, box("DNS", rows))
    except Exception:
        await reply(interaction, "dns lookup failed")


@bot.tree.command(name="dnsall", description="resolve all common dns records")
@app_commands.describe(domain="domain name")
async def dnsall_cmd(interaction: discord.Interaction, domain: str):
    await guard(interaction)
    try:
        d = clean_target(domain)
        rows = []
        for rt in ["A", "AAAA", "MX", "NS", "TXT", "SOA", "CNAME", "CAA"]:
            j = await dns_lookup(d, rt)
            for a in (j.get("Answer") or [])[:4]:
                rows.append(rt.ljust(6) + f(a.get("data"))[:70])
        await reply(interaction, box("DNS ALL " + d, rows or ["no records"]))
    except Exception:
        await reply(interaction, "dns lookup failed")


async def _rtype(interaction, domain, rt):
    await guard(interaction)
    try:
        d = clean_target(domain)
        j = await dns_lookup(d, rt)
        ans = j.get("Answer") or []
        rows = [d + " " + rt]
        for a in ans[:20]:
            rows.append("  " + f(a.get("data")))
        await reply(interaction, box(rt, rows or ["no records"]))
    except Exception:
        await reply(interaction, "lookup failed")


@bot.tree.command(name="mx", description="mail exchanger records")
@app_commands.describe(domain="domain name")
async def mx_cmd(interaction: discord.Interaction, domain: str):
    await _rtype(interaction, domain, "MX")


@bot.tree.command(name="ns", description="nameserver records")
@app_commands.describe(domain="domain name")
async def ns_cmd(interaction: discord.Interaction, domain: str):
    await _rtype(interaction, domain, "NS")


@bot.tree.command(name="txt", description="txt records")
@app_commands.describe(domain="domain name")
async def txt_cmd(interaction: discord.Interaction, domain: str):
    await _rtype(interaction, domain, "TXT")


@bot.tree.command(name="spf", description="parse spf record for a domain")
@app_commands.describe(domain="domain name")
async def spf_cmd(interaction: discord.Interaction, domain: str):
    await guard(interaction)
    try:
        d = clean_target(domain)
        j = await dns_lookup(d, "TXT")
        rec = ""
        for a in (j.get("Answer") or []):
            data = a.get("data", "")
            if "v=spf1" in data:
                rec = data
                break
        rows = ["domain " + d, "spf    " + (rec.strip('"') if rec else "none found")]
        await reply(interaction, box("SPF", rows))
    except Exception:
        await reply(interaction, "spf lookup failed")


@bot.tree.command(name="rdap", description="registration data for domain, ip or asn")
@app_commands.describe(target="domain, ip or asn")
async def rdap_cmd(interaction: discord.Interaction, target: str):
    await guard(interaction)
    try:
        t = clean_target(target)
        if re.match(r"^as\d+$", t, re.I):
            path = "autnum/" + t[2:]
        elif is_ip(t):
            path = "ip/" + t
        else:
            path = "domain/" + t
        j = await jget("https://rdap.org/" + path)
        if isinstance(j, list):
            j = next((x for x in j if isinstance(x, dict)), {})
        if not isinstance(j, dict) or not j:
            await reply(interaction, "no rdap data for " + t)
            return
        rows = ["target   " + t, "handle   " + f(j.get("handle")), "name     " + f(j.get("name") or j.get("ldhName"))]
        if isinstance(j.get("status"), list) and j["status"]:
            rows.append("status   " + ", ".join(j["status"][:4]))
        for ev in (j.get("events") or [])[:6]:
            rows.append(str(ev.get("eventAction", "event")).ljust(9) + str(ev.get("eventDate", ""))[:19])
        for n in (j.get("nameservers") or [])[:5]:
            rows.append("ns       " + f(n.get("ldhName")))
        await reply(interaction, box("RDAP " + t, rows))
    except Exception:
        await reply(interaction, "rdap lookup failed")


@bot.tree.command(name="geo", description="geocode a place to coordinates")
@app_commands.describe(place="place or address")
async def geo_cmd(interaction: discord.Interaction, place: str):
    await guard(interaction)
    try:
        j = await jget("https://nominatim.openstreetmap.org/search?format=json&limit=3&q=" +
                       urllib.parse.quote(place), timeout=12)
        if not j:
            await reply(interaction, "geocode failed")
            return
        rows = []
        for r in j[:3]:
            rows.append(f(r.get("display_name"))[:60] + " -> " + f(r.get("lat")) + ", " + f(r.get("lon")))
        await reply(interaction, box("GEO " + place, rows or ["no matches"]))
    except Exception:
        await reply(interaction, "geocode failed")


@bot.tree.command(name="reverse", description="reverse geocode coordinates to an address")
@app_commands.describe(lat="latitude", lon="longitude")
async def reverse_cmd(interaction: discord.Interaction, lat: float, lon: float):
    await guard(interaction)
    try:
        j = await jget("https://nominatim.openstreetmap.org/reverse?format=json&lat=" + str(lat) + "&lon=" + str(lon),
                       timeout=12)
        if not j:
            await reply(interaction, "reverse geocode failed")
            return
        await reply(interaction, box("REVERSE " + str(lat) + "," + str(lon),
                                     [f(j.get("display_name"))[:70],
                                      "country  " + f((j.get("address") or {}).get("country"))]))
    except Exception:
        await reply(interaction, "reverse geocode failed")


@bot.tree.command(name="headers", description="http response headers of a url")
@app_commands.describe(url="full url")
async def headers_cmd(interaction: discord.Interaction, url: str):
    await guard(interaction)
    try:
        if not url.startswith("http"):
            url = "https://" + url
        async with SESSION.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15,
                               allow_redirects=True) as r:
            rows = ["status   " + str(r.status), "final    " + str(r.url)]
            for k, v in list(r.headers.items())[:20]:
                rows.append(k.lower().ljust(16) + str(v)[:60])
        await reply(interaction, box("HEADERS", rows))
    except Exception:
        await reply(interaction, "request failed")


@bot.tree.command(name="urlinfo", description="follow redirects and pull final status and title")
@app_commands.describe(url="full url")
async def urlinfo_cmd(interaction: discord.Interaction, url: str):
    await guard(interaction)
    try:
        if not url.startswith("http"):
            url = "https://" + url
        async with SESSION.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15,
                               allow_redirects=True) as r:
            text = (await r.text())[:4000]
            m = re.search(r"(?is)<title[^>]*>(.*?)</title>", text)
            rows = ["status   " + str(r.status), "final    " + str(r.url),
                    "title    " + (re.sub(r"\s+", " ", m.group(1)).strip()[:70] if m else "n/a"),
                    "server   " + str(r.headers.get("Server", "n/a"))]
        await reply(interaction, box("URL INFO", rows))
    except Exception:
        await reply(interaction, "request failed")


@bot.tree.command(name="robots", description="fetch a domain robots.txt")
@app_commands.describe(domain="domain name")
async def robots_cmd(interaction: discord.Interaction, domain: str):
    await guard(interaction)
    try:
        d = clean_target(domain)
        st, txt = await tget("https://" + d + "/robots.txt", timeout=12)
        if st != 200 or not txt:
            await reply(interaction, "no robots.txt (" + str(st) + ")")
            return
        await reply(interaction, "```" + txt[:1900] + "```")
    except Exception:
        await reply(interaction, "fetch failed")


@bot.tree.command(name="subdomains", description="subdomain enum via crt.sh")
@app_commands.describe(domain="domain name")
async def subdomains_cmd(interaction: discord.Interaction, domain: str):
    await guard(interaction)
    try:
        d = clean_target(domain)
        j = await jget("https://crt.sh/?q=%25." + urllib.parse.quote(d) + "&output=json", timeout=25)
        if not j:
            await reply(interaction, "no cert data found")
            return
        names = set()
        for e in j:
            for n in str(e.get("name_value", "")).splitlines():
                n = n.strip().lower()
                if n and "@" not in n and re.match(r"^[a-z0-9.*-]+$", n) and n.endswith(d):
                    names.add(n)
        rows = sorted(names)[:60]
        await reply(interaction, box("SUBDOMAINS " + d + " (" + str(len(names)) + ")", rows or ["none"]))
    except Exception:
        await reply(interaction, "enum failed")


@bot.tree.command(name="portcheck", description="tcp connect check on a single port")
@app_commands.describe(host="host or ip", port="tcp port")
async def portcheck_cmd(interaction: discord.Interaction, host: str, port: int):
    await guard(interaction)
    try:
        h = clean_target(host)
        ms = await asyncio.get_running_loop().run_in_executor(None, tcp_ms, h, port)
        if ms is None:
            await reply(interaction, box("PORTCHECK", [h + ":" + str(port), "closed or filtered"]))
        else:
            await reply(interaction, box("PORTCHECK", [h + ":" + str(port), "open - " + str(ms) + "ms"]))
    except Exception:
        await reply(interaction, "check failed")


@bot.tree.command(name="portscan", description="tcp connect scan of common ports")
@app_commands.describe(host="host or ip")
async def portscan_cmd(interaction: discord.Interaction, host: str):
    await guard(interaction)
    try:
        h = clean_target(host)
        loop = asyncio.get_running_loop()

        async def chk(p):
            return p, await loop.run_in_executor(None, tcp_ms, h, p, 2.0)

        res = await asyncio.gather(*[chk(p) for p in COMMON_PORTS])
        open_ports = [str(p) for p, ms in res if ms is not None]
        await reply(interaction, box("PORTSCAN " + h, ["open: " + (", ".join(open_ports) or "none"),
                                                       "scanned " + str(len(COMMON_PORTS)) + " ports"]))
    except Exception:
        await reply(interaction, "scan failed")


@bot.tree.command(name="pinghost", description="tcp latency probe to a host")
@app_commands.describe(host="host or ip", port="tcp port")
async def pinghost_cmd(interaction: discord.Interaction, host: str, port: Optional[int] = 443):
    await guard(interaction)
    try:
        h = clean_target(host)
        p = int(port or 443)
        ms = await asyncio.get_running_loop().run_in_executor(None, tcp_ms, h, p)
        if ms is None:
            await reply(interaction, "unreachable on tcp " + str(p))
        else:
            await reply(interaction, "reachable " + h + ":" + str(p) + " in " + str(ms) + "ms")
    except Exception:
        await reply(interaction, "probe failed")


@bot.tree.command(name="blacklist", description="check an ip against dnsbl lists")
@app_commands.describe(address="ipv4")
async def blacklist_cmd(interaction: discord.Interaction, address: str):
    await guard(interaction)
    try:
        ip = clean_target(address)
        if not is_ip(ip) or ":" in ip:
            await reply(interaction, "give me an ipv4")
            return
        rev = ".".join(reversed(ip.split(".")))

        async def chk(z):
            j = await dns_lookup(rev + "." + z, "A")
            return z, bool(j.get("Answer"))

        res = await asyncio.gather(*[chk(z) for z in DNSBL])
        listed = [z for z, hit in res if hit]
        rows = ["ip " + ip, "listed on: " + (", ".join(listed) if listed else "clean"),
                "checked " + str(len(DNSBL)) + " lists"]
        await reply(interaction, box("DNSBL", rows))
    except Exception:
        await reply(interaction, "check failed")


@bot.tree.command(name="mac", description="mac address vendor lookup")
@app_commands.describe(address="mac like 00:1A:2B:3C:4D:5E")
async def mac_cmd(interaction: discord.Interaction, address: str):
    await guard(interaction)
    try:
        a = re.sub(r"[^0-9A-Fa-f]", "", address)
        if len(a) < 6:
            await reply(interaction, "invalid mac")
            return
        vendor = await tget("https://api.macvendors.com/" + address, timeout=12)
        rows = ["mac      " + address, "oui      " + a[:6].upper(), "vendor   " + (vendor[1][:60] if vendor[0] == 200 else "unknown")]
        await reply(interaction, box("MAC", rows))
    except Exception:
        await reply(interaction, "lookup failed")


@bot.tree.command(name="ssl", description="tls certificate info for a host")
@app_commands.describe(host="hostname")
async def ssl_cmd(interaction: discord.Interaction, host: str):
    await guard(interaction)
    try:
        h = clean_target(host)

        def cert():
            ctx = ssl.create_default_context()
            with socket.create_connection((h, 443), timeout=10) as s:
                with ctx.wrap_socket(s, server_hostname=h) as ss:
                    return ss.getpeercert()

        c = await asyncio.get_running_loop().run_in_executor(None, cert)
        if not c:
            await reply(interaction, "no certificate")
            return
        subj = dict(x[0] for x in c.get("subject", []))
        iss = dict(x[0] for x in c.get("issuer", []))
        rows = ["host     " + h, "subject  " + f(subj.get("commonName")), "issuer   " + f(iss.get("organizationName")),
                "valid    " + f(c.get("notBefore")), "expires  " + f(c.get("notAfter"))]
        sans = [v for k, v in c.get("subjectAltName", []) if k == "DNS"][:6]
        if sans:
            rows.append("san      " + ", ".join(sans))
        await reply(interaction, box("TLS " + h, rows))
    except Exception:
        await reply(interaction, "tls lookup failed")


@bot.tree.command(name="github", description="public github profile")
@app_commands.describe(username="github username")
async def github_cmd(interaction: discord.Interaction, username: str):
    await guard(interaction)
    try:
        j = await jget("https://api.github.com/users/" + urllib.parse.quote(username))
        if not j or j.get("message"):
            await reply(interaction, "no github user with that name")
            return
        rows = ["login    " + f(j.get("login")), "name     " + f(j.get("name")), "id       " + f(j.get("id")),
                "repos    " + f(j.get("public_repos")), "followers " + f(j.get("followers")),
                "created  " + f(j.get("created_at")), "company  " + f(j.get("company")),
                "location " + f(j.get("location")), "blog     " + f(j.get("blog")), "url      " + f(j.get("html_url"))]
        await reply(interaction, box("GITHUB", rows))
    except Exception:
        await reply(interaction, "github lookup failed")


@bot.tree.command(name="minecraft", description="minecraft account uuid and skin")
@app_commands.describe(username="minecraft username")
async def minecraft_cmd(interaction: discord.Interaction, username: str):
    await guard(interaction)
    try:
        j = await jget("https://api.mojang.com/users/profiles/minecraft/" + urllib.parse.quote(username))
        if not j:
            await reply(interaction, "no minecraft account with that name")
            return
        uid = j.get("id", "")
        rows = ["name     " + f(j.get("name")), "uuid     " + uid,
                "skin     https://crafatar.com/renders/body/" + uid]
        hist = await jget("https://api.mojang.com/user/profiles/" + uid + "/names")
        if isinstance(hist, list):
            rows.append("history  " + ", ".join(h.get("name", "") for h in hist[:6]))
        await reply(interaction, box("MINECRAFT", rows))
    except Exception:
        await reply(interaction, "minecraft lookup failed")


@bot.tree.command(name="gravatar", description="gravatar profile for an email")
@app_commands.describe(email="email address")
async def gravatar_cmd(interaction: discord.Interaction, email: str):
    await guard(interaction)
    try:
        h = hashlib.md5(email.strip().lower().encode()).hexdigest()
        j = await jget("https://gravatar.com/" + h + ".json")
        rows = ["email    " + email, "hash     " + h, "image    https://gravatar.com/avatar/" + h]
        if j and j.get("entry"):
            e = j["entry"][0]
            rows += ["name     " + f(e.get("displayName")), "about    " + f(e.get("aboutMe"))[:50],
                     "location " + f(e.get("currentLocation"))]
        await reply(interaction, box("GRAVATAR", rows))
    except Exception:
        await reply(interaction, "gravatar lookup failed")


@bot.tree.command(name="reddit", description="public reddit account summary")
@app_commands.describe(username="reddit username")
async def reddit_cmd(interaction: discord.Interaction, username: str):
    await guard(interaction)
    try:
        j = await jget("https://www.reddit.com/user/" + urllib.parse.quote(username) + "/about.json")
        d = ((j or {}).get("data") or {})
        if not d or not d.get("name"):
            await reply(interaction, "no reddit user with that name (or reddit blocked the request)")
            return
        rows = ["name     " + f(d.get("name")), "id       " + f(d.get("id")), "karma    " + f(d.get("total_karma")),
                "created  " + str(datetime.fromtimestamp(d.get("created_utc", 0), timezone.utc))[:19],
                "verified " + f(d.get("verified"))]
        await reply(interaction, box("REDDIT", rows))
    except Exception:
        await reply(interaction, "reddit lookup failed")


@bot.tree.command(name="chess", description="chess.com player profile and ratings")
@app_commands.describe(username="chess.com username")
async def chess_cmd(interaction: discord.Interaction, username: str):
    await guard(interaction)
    try:
        j = await jget("https://api.chess.com/pub/player/" + urllib.parse.quote(username.lower()))
        if not j or not j.get("username"):
            await reply(interaction, "no chess.com player with that name")
            return
        rows = ["user     " + f(j.get("username")), "name     " + f(j.get("name")),
                "country  " + f(j.get("country")), "joined   " + str(datetime.fromtimestamp(j.get("joined", 0), timezone.utc))[:10],
                "last     " + str(datetime.fromtimestamp(j.get("last_online", 0), timezone.utc))[:10],
                "status   " + f(j.get("status")), "url      " + f(j.get("url"))]
        st = await jget("https://api.chess.com/pub/player/" + urllib.parse.quote(username.lower()) + "/stats")
        if st:
            for k in ("chess_blitz", "chess_rapid", "chess_bullet"):
                r = (st.get(k) or {}).get("last", {}).get("rating")
                if r:
                    rows.append(k + " " + str(r))
        await reply(interaction, box("CHESS", rows))
    except Exception:
        await reply(interaction, "chess lookup failed")


@bot.tree.command(name="roblox", description="roblox account by username")
@app_commands.describe(username="roblox username")
async def roblox_cmd(interaction: discord.Interaction, username: str):
    await guard(interaction)
    try:
        j = await jpost("https://users.roblox.com/v1/usernames/users", {"usernames": [username], "excludeBannedUsers": False})
        data = (j or {}).get("data") or []
        if not data:
            await reply(interaction, "no roblox user with that name")
            return
        d = data[0]
        uid = d.get("id")
        rows = ["name     " + f(d.get("displayName")), "username " + f(d.get("name")),
                "id       " + f(d.get("id")), "avatar   https://www.roblox.com/headshot-thumbnail/image?userId=" + str(uid) + "&width=150&height=150&format=png"]
        await reply(interaction, box("ROBLOX", rows))
    except Exception:
        await reply(interaction, "roblox lookup failed")


@bot.tree.command(name="npm", description="npm package metadata")
@app_commands.describe(package="package name")
async def npm_cmd(interaction: discord.Interaction, package: str):
    await guard(interaction)
    try:
        j = await jget("https://registry.npmjs.org/" + urllib.parse.quote(package))
        if not j or not j.get("name"):
            await reply(interaction, "no npm package with that name")
            return
        latest = j.get("dist-tags", {}).get("latest", "")
        v = j.get("versions", {}).get(latest, {})
        rows = ["name     " + f(j.get("name")), "latest   " + f(latest), "desc     " + f(j.get("description"))[:55],
                "license  " + f(v.get("license")), "homepage " + f(j.get("homepage"))[:55],
                "modified " + f(j.get("time", {}).get("modified"))]
        await reply(interaction, box("NPM", rows))
    except Exception:
        await reply(interaction, "npm lookup failed")


@bot.tree.command(name="pypi", description="pypi package metadata")
@app_commands.describe(package="package name")
async def pypi_cmd(interaction: discord.Interaction, package: str):
    await guard(interaction)
    try:
        j = await jget("https://pypi.org/pypi/" + urllib.parse.quote(package) + "/json")
        if not j or not j.get("info"):
            await reply(interaction, "no pypi package with that name")
            return
        i = j["info"]
        rows = ["name     " + f(i.get("name")), "version  " + f(i.get("version")), "author   " + f(i.get("author")),
                "summary  " + f(i.get("summary"))[:55], "home     " + f(i.get("home_page"))[:55],
                "requires " + f(i.get("requires_python"))]
        await reply(interaction, box("PYPI", rows))
    except Exception:
        await reply(interaction, "pypi lookup failed")


@bot.tree.command(name="crates", description="crates.io package metadata")
@app_commands.describe(package="crate name")
async def crates_cmd(interaction: discord.Interaction, package: str):
    await guard(interaction)
    try:
        j = await jget("https://crates.io/api/v1/crates/" + urllib.parse.quote(package))
        c = (j or {}).get("crate")
        if not c:
            await reply(interaction, "no crate with that name")
            return
        rows = ["name     " + f(c.get("name")), "version  " + f(c.get("max_version")),
                "downloads " + f(c.get("downloads")), "desc     " + f(c.get("description"))[:55],
                "repo     " + f(c.get("repository"))[:55]]
        await reply(interaction, box("CRATES", rows))
    except Exception:
        await reply(interaction, "crates lookup failed")


@bot.tree.command(name="isbn", description="isbn metadata")
@app_commands.describe(isbn="isbn-10 or isbn-13")
async def isbn_cmd(interaction: discord.Interaction, isbn: str):
    await guard(interaction)
    try:
        code = re.sub(r"[^0-9Xx]", "", isbn)
        j = await jget("https://openlibrary.org/isbn/" + code + ".json")
        if not j:
            await reply(interaction, "no book found for that isbn")
            return
        rows = ["isbn     " + code, "title    " + f(j.get("title")),
                "publish  " + f(j.get("publish_date")), "publishers " + f(", ".join(j.get("publishers") or [])),
                "pages    " + f(j.get("number_of_pages"))]
        await reply(interaction, box("ISBN", rows))
    except Exception:
        await reply(interaction, "isbn lookup failed")


@bot.tree.command(name="book", description="search openlibrary for a book")
@app_commands.describe(query="title or author")
async def book_cmd(interaction: discord.Interaction, query: str):
    await guard(interaction)
    try:
        j = await jget("https://openlibrary.org/search.json?limit=5&q=" + urllib.parse.quote(query))
        docs = (j or {}).get("docs") or []
        rows = []
        for d in docs[:5]:
            rows.append((f(d.get("title")) + " - " + f((d.get("author_name") or ["?"])[0]))[:70])
        await reply(interaction, box("BOOKS " + query, rows or ["no results"]))
    except Exception:
        await reply(interaction, "book search failed")


@bot.tree.command(name="define", description="dictionary definition")
@app_commands.describe(word="word to define")
async def define_cmd(interaction: discord.Interaction, word: str):
    await guard(interaction)
    try:
        j = await jget("https://api.dictionaryapi.dev/api/v2/entries/en/" + urllib.parse.quote(word))
        if not isinstance(j, list) or not j:
            await reply(interaction, "no definition found")
            return
        e = j[0]
        rows = ["word     " + f(e.get("word")), "phonetic " + f(e.get("phonetic"))]
        for m in (e.get("meanings") or [])[:3]:
            rows.append(m.get("partOfSpeech", "?").ljust(9) + f((m.get("definitions") or [{}])[0].get("definition"))[:60])
        await reply(interaction, box("DEFINE", rows))
    except Exception:
        await reply(interaction, "definition failed")


@bot.tree.command(name="country", description="country info by code or name")
@app_commands.describe(code="country code like US or a name")
async def country_cmd(interaction: discord.Interaction, code: str):
    await guard(interaction)
    try:
        q = code.strip()
        url = ("https://restcountries.com/v3.1/alpha/" + q) if len(q) in (2, 3) else \
            ("https://restcountries.com/v3.1/name/" + urllib.parse.quote(q))
        j = await jget(url + "?fields=name,capital,region,subregion,population,currencies,languages,cca2,cca3,tld,idd,timezones,latlng,area,borders,flag")
        if not isinstance(j, list) or not j:
            await reply(interaction, "country not found")
            return
        c = j[0]
        cur = list((c.get("currencies") or {}).keys())
        lang = list((c.get("languages") or {}).values())
        rows = ["name     " + f((c.get("name") or {}).get("common")), "code     " + f(c.get("cca2")) + " / " + f(c.get("cca3")),
                "capital  " + f((c.get("capital") or ["?"])[0]), "region   " + f(c.get("region")) + " / " + f(c.get("subregion")),
                "pop      " + f(c.get("population")), "area     " + f(c.get("area")) + " km2",
                "currency " + f(", ".join(cur)), "langs    " + f(", ".join(lang))[:50],
                "tld      " + f(", ".join(c.get("tld") or [])), "tz       " + f(", ".join(c.get("timezones") or [])[:40])]
        await reply(interaction, box("COUNTRY", rows))
    except Exception:
        await reply(interaction, "country lookup failed")


@bot.tree.command(name="crypto", description="live crypto price from coingecko")
@app_commands.describe(coin="coingecko id e.g. bitcoin", vs="vs currency e.g. usd")
async def crypto_cmd(interaction: discord.Interaction, coin: str, vs: Optional[str] = "usd"):
    await guard(interaction)
    try:
        j = await jget("https://api.coingecko.com/api/v3/simple/price?ids=" + urllib.parse.quote(coin) +
                       "&vs_currencies=" + urllib.parse.quote((vs or "usd").lower()))
        d = (j or {}).get(coin.lower())
        if not d:
            await reply(interaction, "no price for " + coin)
            return
        rows = [coin + " -> " + k.upper() + " " + f(v) for k, v in d.items()]
        await reply(interaction, box("CRYPTO", rows))
    except Exception:
        await reply(interaction, "crypto lookup failed")


@bot.tree.command(name="btc", description="bitcoin price")
async def btc_cmd(interaction: discord.Interaction):
    await guard(interaction)
    try:
        j = await jget("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd,eur,gbp")
        b = (j or {}).get("bitcoin")
        if not b:
            await reply(interaction, "btc price unavailable")
            return
        await reply(interaction, box("BITCOIN", [k.upper().ljust(6) + f(v) for k, v in b.items()]))
    except Exception:
        await reply(interaction, "btc price failed")


@bot.tree.command(name="eth", description="ethereum price")
async def eth_cmd(interaction: discord.Interaction):
    await guard(interaction)
    try:
        j = await jget("https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd,eur,gbp")
        b = (j or {}).get("ethereum")
        if not b:
            await reply(interaction, "eth price unavailable")
            return
        await reply(interaction, box("ETHEREUM", [k.upper().ljust(6) + f(v) for k, v in b.items()]))
    except Exception:
        await reply(interaction, "eth price failed")


@bot.tree.command(name="fx", description="currency conversion via frankfurter")
@app_commands.describe(amount="amount", source="from currency", target="to currency")
async def fx_cmd(interaction: discord.Interaction, amount: float, source: str, target: str):
    await guard(interaction)
    try:
        s = source.upper()
        t = target.upper()
        j = await jget("https://api.frankfurter.app/latest?amount=" + str(amount) + "&from=" + s + "&to=" + t)
        r = ((j or {}).get("rates") or {}).get(t)
        if r is None:
            await reply(interaction, "conversion failed")
            return
        await reply(interaction, box("FX", [str(amount) + " " + s + " = " + str(r) + " " + t,
                                            "date " + f((j or {}).get("date"))]))
    except Exception:
        await reply(interaction, "fx failed")


@bot.tree.command(name="base64", description="base64 encode or decode")
@app_commands.describe(text="text", mode="encode or decode")
@app_commands.choices(mode=[app_commands.Choice(name="encode", value="encode"),
                            app_commands.Choice(name="decode", value="decode")])
async def base64_cmd(interaction: discord.Interaction, text: str, mode: Optional[app_commands.Choice[str]] = None):
    await guard(interaction)
    try:
        if mode and mode.value == "decode":
            out = base64.b64decode(text + "===").decode("utf-8", "replace")
        else:
            out = base64.b64encode(text.encode()).decode()
        await reply(interaction, "```" + out[:1900] + "```")
    except Exception:
        await reply(interaction, "base64 failed")


@bot.tree.command(name="hex", description="text to hex or hex to text")
@app_commands.describe(text="text", mode="encode or decode")
@app_commands.choices(mode=[app_commands.Choice(name="encode", value="encode"),
                            app_commands.Choice(name="decode", value="decode")])
async def hex_cmd(interaction: discord.Interaction, text: str, mode: Optional[app_commands.Choice[str]] = None):
    await guard(interaction)
    try:
        if mode and mode.value == "decode":
            out = bytes.fromhex(re.sub(r"[^0-9a-fA-F]", "", text)).decode("utf-8", "replace")
        else:
            out = text.encode().hex()
        await reply(interaction, "```" + out[:1900] + "```")
    except Exception:
        await reply(interaction, "hex failed")


@bot.tree.command(name="bintext", description="text to binary or binary to text")
@app_commands.describe(text="text", mode="encode or decode")
@app_commands.choices(mode=[app_commands.Choice(name="encode", value="encode"),
                            app_commands.Choice(name="decode", value="decode")])
async def bintext_cmd(interaction: discord.Interaction, text: str, mode: Optional[app_commands.Choice[str]] = None):
    await guard(interaction)
    try:
        if mode and mode.value == "decode":
            bits = re.sub(r"[^01]", "", text)
            out = "".join(chr(int(bits[i:i + 8], 2)) for i in range(0, len(bits) - 7, 8))
        else:
            out = " ".join(format(b, "08b") for b in text.encode())
        await reply(interaction, "```" + out[:1900] + "```")
    except Exception:
        await reply(interaction, "bintext failed")


@bot.tree.command(name="rot13", description="rot13 cipher")
@app_commands.describe(text="text")
async def rot13_cmd(interaction: discord.Interaction, text: str):
    await guard(interaction)
    await reply(interaction, "```" + __import__("codecs").encode(text, "rot13")[:1900] + "```")


@bot.tree.command(name="textcase", description="transform text case")
@app_commands.describe(text="text", mode="transform")
@app_commands.choices(mode=[app_commands.Choice(name="upper", value="upper"),
                            app_commands.Choice(name="lower", value="lower"),
                            app_commands.Choice(name="title", value="title"),
                            app_commands.Choice(name="reverse", value="reverse"),
                            app_commands.Choice(name="swap", value="swap")])
async def textcase_cmd(interaction: discord.Interaction, text: str, mode: Optional[app_commands.Choice[str]] = None):
    await guard(interaction)
    try:
        m = mode.value if mode else "upper"
        out = {"upper": text.upper(), "lower": text.lower(), "title": text.title(),
               "reverse": text[::-1], "swap": text.swapcase()}[m]
        await reply(interaction, "```" + out[:1900] + "```")
    except Exception:
        await reply(interaction, "textcase failed")


@bot.tree.command(name="textstats", description="count characters, words, lines")
@app_commands.describe(text="text")
async def textstats_cmd(interaction: discord.Interaction, text: str):
    await guard(interaction)
    rows = ["chars    " + str(len(text)), "words    " + str(len(text.split())),
            "lines    " + str(text.count("\n") + 1), "digits   " + str(sum(c.isdigit() for c in text)),
            "letters  " + str(sum(c.isalpha() for c in text)), "spaces   " + str(text.count(" "))]
    await reply(interaction, box("TEXTSTATS", rows))


@bot.tree.command(name="hash", description="hash text with md5/sha family")
@app_commands.describe(text="text", algorithm="hash algorithm")
@app_commands.choices(algorithm=[app_commands.Choice(name=a, value=a) for a in
                                 ["md5", "sha1", "sha224", "sha256", "sha384", "sha512"]])
async def hash_cmd(interaction: discord.Interaction, text: str, algorithm: Optional[app_commands.Choice[str]] = None):
    await guard(interaction)
    try:
        a = algorithm.value if algorithm else "sha256"
        out = hashlib.new(a, text.encode()).hexdigest()
        await reply(interaction, "`" + a.upper() + "`\n```" + out + "```")
    except Exception:
        await reply(interaction, "hash failed")


@bot.tree.command(name="json", description="validate and pretty print json")
@app_commands.describe(text="json text")
async def json_cmd(interaction: discord.Interaction, text: str):
    await guard(interaction)
    try:
        obj = json.loads(text)
        await reply(interaction, "```" + json.dumps(obj, indent=2)[:1900] + "```")
    except Exception as e:
        await reply(interaction, "invalid json: " + str(e)[:100])


@bot.tree.command(name="regex", description="test a regex against text")
@app_commands.describe(pattern="regex pattern", text="text to test")
async def regex_cmd(interaction: discord.Interaction, pattern: str, text: str):
    await guard(interaction)
    try:
        hits = re.findall(pattern, text)[:20]
        rows = ["pattern  " + pattern, "matches  " + str(len(hits))]
        for h in hits:
            rows.append("  " + str(h)[:60])
        await reply(interaction, box("REGEX", rows))
    except Exception as e:
        await reply(interaction, "regex error: " + str(e)[:100])


@bot.tree.command(name="uuid", description="generate random uuid v4s")
@app_commands.describe(count="how many")
async def uuid_cmd(interaction: discord.Interaction, count: Optional[int] = 1):
    await guard(interaction)
    n = max(1, min(int(count or 1), 20))
    await reply(interaction, "```" + "\n".join(str(uuidlib.uuid4()) for _ in range(n)) + "```")


@bot.tree.command(name="pw", description="generate strong random passwords")
@app_commands.describe(length="length", count="how many")
async def pw_cmd(interaction: discord.Interaction, length: Optional[int] = 16, count: Optional[int] = 1):
    await guard(interaction)
    try:
        L = max(6, min(int(length or 16), 100))
        n = max(1, min(int(count or 1), 15))
        alpha = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
        out = ["".join(secrets.choice(alpha) for _ in range(L)) for _ in range(n)]
        await reply(interaction, "```" + "\n".join(out) + "```")
    except Exception:
        await reply(interaction, "pw failed")


@bot.tree.command(name="pwcheck", description="password entropy and strength")
@app_commands.describe(password="password to check")
async def pwcheck_cmd(interaction: discord.Interaction, password: str):
    await guard(interaction)
    try:
        pool = 0
        if re.search(r"[a-z]", password):
            pool += 26
        if re.search(r"[A-Z]", password):
            pool += 26
        if re.search(r"[0-9]", password):
            pool += 10
        if re.search(r"[^a-zA-Z0-9]", password):
            pool += 33
        ent = round(len(password) * math.log2(pool)) if pool else 0
        label = "very weak" if ent < 28 else "weak" if ent < 36 else "fair" if ent < 60 else "strong" if ent < 128 else "very strong"
        await reply(interaction, box("PWCHECK", ["length   " + str(len(password)), "entropy  " + str(ent) + " bits",
                                                 "pool     " + str(pool), "strength " + label]))
    except Exception:
        await reply(interaction, "pwcheck failed")


@bot.tree.command(name="rand", description="random integers in a range")
@app_commands.describe(lo="low", hi="high", count="how many")
async def rand_cmd(interaction: discord.Interaction, lo: Optional[int] = 1, hi: Optional[int] = 100, count: Optional[int] = 1):
    await guard(interaction)
    try:
        a, b = int(lo if lo is not None else 1), int(hi if hi is not None else 100)
        if a > b:
            a, b = b, a
        n = max(1, min(int(count or 1), 30))
        await reply(interaction, "```" + " ".join(str(random.randint(a, b)) for _ in range(n)) + "```")
    except Exception:
        await reply(interaction, "rand failed")


def _safe_eval(expr):
    allowed = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
    allowed.update({"abs": abs, "round": round, "min": min, "max": max, "pow": pow, "sum": sum})
    expr = re.sub(r"[^0-9+\-*/().,%^ a-zA-Z_]", "", expr).replace("^", "**")
    return eval(expr, {"__builtins__": {}}, allowed)


@bot.tree.command(name="calc", description="safe arithmetic calculator")
@app_commands.describe(expression="e.g. 2+2*10 or sqrt(2)")
async def calc_cmd(interaction: discord.Interaction, expression: str):
    await guard(interaction)
    try:
        await reply(interaction, "```" + str(_safe_eval(expression))[:200] + "```")
    except Exception:
        await reply(interaction, "invalid expression")


@bot.tree.command(name="roman", description="integer to roman numeral")
@app_commands.describe(number="1 to 3999")
async def roman_cmd(interaction: discord.Interaction, number: int):
    await guard(interaction)
    try:
        n = int(number)
        if not 1 <= n <= 3999:
            await reply(interaction, "give a number between 1 and 3999")
            return
        vals = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
                (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
        out = ""
        for v, s in vals:
            while n >= v:
                out += s
                n -= v
        await reply(interaction, "`" + str(number) + "` = **" + out + "**")
    except Exception:
        await reply(interaction, "roman failed")


@bot.tree.command(name="unix", description="convert epoch to human time")
@app_commands.describe(timestamp="epoch seconds")
async def unix_cmd(interaction: discord.Interaction, timestamp: Optional[int] = None):
    await guard(interaction)
    try:
        ts = int(timestamp) if timestamp is not None else int(time.time())
        await reply(interaction, box("UNIX", [str(ts) + "  =  " + str(datetime.fromtimestamp(ts, timezone.utc))[:19] + " UTC",
                                              "discord  <t:" + str(ts) + ":F>"]))
    except Exception:
        await reply(interaction, "unix failed")


@bot.tree.command(name="timestamp", description="convert a date to epoch")
@app_commands.describe(date="YYYY-MM-DD")
async def timestamp_cmd(interaction: discord.Interaction, date: str):
    await guard(interaction)
    try:
        dt = datetime.strptime(date.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        await reply(interaction, box("TIMESTAMP", [date + "  =  " + str(int(dt.timestamp())) + " epoch"]))
    except Exception:
        await reply(interaction, "use format YYYY-MM-DD")


@bot.tree.command(name="now", description="current utc time")
async def now_cmd(interaction: discord.Interaction):
    await guard(interaction)
    await reply(interaction, box("NOW", [str(datetime.now(timezone.utc))[:19] + " UTC", "epoch " + str(int(time.time()))]))


@bot.tree.command(name="urlencode", description="percent encode text")
@app_commands.describe(text="text")
async def urlencode_cmd(interaction: discord.Interaction, text: str):
    await guard(interaction)
    await reply(interaction, "```" + urllib.parse.quote(text)[:1900] + "```")


@bot.tree.command(name="urldecode", description="percent decode text")
@app_commands.describe(text="text")
async def urldecode_cmd(interaction: discord.Interaction, text: str):
    await guard(interaction)
    await reply(interaction, "```" + urllib.parse.unquote(text)[:1900] + "```")


@bot.tree.command(name="subnet", description="cidr math")
@app_commands.describe(cidr="cidr like 192.168.1.0/24")
async def subnet_cmd(interaction: discord.Interaction, cidr: str):
    await guard(interaction)
    try:
        net = ipaddress.ip_network(cidr.strip(), strict=False)
        hosts = list(net.hosts())
        rows = ["network  " + str(net.network_address), "netmask  " + str(net.netmask),
                "broadcast " + str(net.broadcast_address), "hosts    " + str(max(0, net.num_addresses - 2)),
                "first    " + (str(hosts[0]) if hosts else "n/a"),
                "last     " + (str(hosts[-1]) if hosts else "n/a")]
        await reply(interaction, box("SUBNET", rows))
    except Exception:
        await reply(interaction, "invalid cidr")


@bot.tree.command(name="ipv6", description="validate and expand an ipv6 address")
@app_commands.describe(address="ipv6 address")
async def ipv6_cmd(interaction: discord.Interaction, address: str):
    await guard(interaction)
    try:
        ip = ipaddress.IPv6Address(address.strip())
        rows = ["compressed " + ip.compressed, "expanded " + ip.exploded, "is_private " + str(ip.is_private),
                "is_global " + str(ip.is_global), "reverse " + ip.reverse_pointer]
        await reply(interaction, box("IPV6", rows))
    except Exception:
        await reply(interaction, "invalid ipv6")


@bot.tree.command(name="qr", description="generate a qr code image url for text")
@app_commands.describe(text="text to encode")
async def qr_cmd(interaction: discord.Interaction, text: str):
    await guard(interaction)
    url = "https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=" + urllib.parse.quote(text)
    await reply(interaction, "qr for `" + text[:60] + "`\n" + url)


@bot.tree.command(name="avatar", description="show a user avatar")
@app_commands.describe(user="user mention or id")
async def avatar_cmd(interaction: discord.Interaction, user: Optional[discord.User] = None):
    await guard(interaction)
    u = user or interaction.user
    await reply(interaction, box("AVATAR", [str(u), str(u.display_avatar.url)]))


@bot.tree.command(name="userinfo", description="discord user information")
@app_commands.describe(user="user mention or id")
async def userinfo_cmd(interaction: discord.Interaction, user: Optional[discord.User] = None):
    await guard(interaction)
    u = user or interaction.user
    rows = ["user     " + str(u), "id       " + str(u.id), "bot      " + str(u.bot),
            "created  " + str(u.created_at)[:19], "avatar   " + str(u.display_avatar.url)]
    await reply(interaction, box("USERINFO", rows))


@bot.tree.command(name="serverinfo", description="current server information")
async def serverinfo_cmd(interaction: discord.Interaction):
    await guard(interaction)
    g = interaction.guild
    if not g:
        await reply(interaction, "this is a dm")
        return
    rows = ["name     " + g.name, "id       " + str(g.id), "members  " + str(g.member_count),
            "owner    " + str(g.owner_id), "created  " + str(g.created_at)[:19], "boost    " + str(g.premium_tier)]
    await reply(interaction, box("SERVERINFO", rows))


@bot.tree.command(name="whoami", description="your discord identity")
async def whoami_cmd(interaction: discord.Interaction):
    await guard(interaction)
    u = interaction.user
    await reply(interaction, box("WHOAMI", [str(u), "id " + str(u.id), "created " + str(u.created_at)[:19]]))


@bot.tree.command(name="ipv4info", description="quick ipv4 validation and class info")
@app_commands.describe(address="ipv4")
async def ipv4info_cmd(interaction: discord.Interaction, address: str):
    await guard(interaction)
    try:
        ip = ipaddress.IPv4Address(address.strip())
        rows = ["ip " + str(ip), "private " + str(ip.is_private), "global " + str(ip.is_global),
                "loopback " + str(ip.is_loopback), "reverse " + ip.reverse_pointer]
        await reply(interaction, box("IPV4", rows))
    except Exception:
        await reply(interaction, "invalid ipv4")


if __name__ == "__main__":
    bot.run(TOKEN)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MR. 414N - Pencari nomor yang tersebar di internet (multi-mesin pencari).

Setup (sekali saja):
  pip install requests beautifulsoup4

Opsional (Google API resmi, kalau punya):
  export GOOGLE_API_KEY="..."
  export GOOGLE_CSE_ID="..."

Pakai:
  python3 nomor.py                       # akan ditanya nomornya
  python3 nomor.py 08xxxxxxxxxx
  python3 nomor.py 08xxxxxxxxxx --max-queries 40 --delay 1.5
  python3 nomor.py 08xxxxxxxxxx --engines ddg,bing,mojeek,google
  python3 nomor.py 08xxxxxxxxxx --link-only   # hanya generate link pencarian

BY. MR414N-ID
"""
import os
import re
import sys
import json
import time
import random
import colorsys
import argparse
from urllib.parse import quote_plus, urlparse, parse_qs, unquote

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# User-Agent khusus untuk Google agar lebih jarang kena CAPTCHA
MOBILE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-S901B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
}

# --------------------------------------------------------------------------
# TAMPILAN
# --------------------------------------------------------------------------
def rainbow(text, offset=0.0):
    out = []
    n = max(len(text), 1)
    for i, ch in enumerate(text):
        if ch == " ":
            out.append(ch)
            continue
        h = ((i / n) + offset) % 1.0
        r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb(h, 1, 1)]
        out.append(f"\033[38;2;{r};{g};{b}m{ch}")
    return "".join(out) + RESET


TUX = r"""
        .--.
       |o_o |
       |:_/ |
      //   \ \
     (|     | )
    /'\_   _/`\
    \___)=(___/
"""

FONT = {
    "M": ["█   █", "██ ██", "█ █ █", "█   █", "█   █"],
    "R": ["████ ", "█   █", "████ ", "█  █ ", "█   █"],
    ".": ["  ", "  ", "  ", "  ", "█ "],
    " ": ["  ", "  ", "  ", "  ", "  "],
    "4": ["█  █ ", "█  █ ", "█████", "   █ ", "   █ "],
    "1": [" █ ", "██ ", " █ ", " █ ", "███"],
    "N": ["█   █", "██  █", "█ █ █", "█  ██", "█   █"],
}


def big_text(text):
    rows = []
    for r in range(5):
        rows.append(" ".join(FONT[c][r] for c in text))
    return rows


def banner():
    os.system("cls" if os.name == "nt" else "clear")
    print("\033c", end="")
    for line in TUX.strip("\n").split("\n"):
        print("\033[97m" + line + RESET)
    print()
    for i, row in enumerate(big_text("MR. 414N")):
        print(rainbow(row, offset=i * 0.04))
    print(DIM + "  pencari nomor di multi mesin pencari" + RESET)
    print()


# --------------------------------------------------------------------------
# NORMALISASI & GENERATOR VARIASI
# --------------------------------------------------------------------------
def normalize(raw):
    d = re.sub(r"\D", "", raw)
    if d.startswith("0062"):
        d = d[4:]
    elif d.startswith("62"):
        d = d[2:]
    if d.startswith("0"):
        d = d[1:]
    return d


def compositions(n, sizes=(2, 3, 4, 5), max_parts=6):
    def rec(rem, parts):
        if rem == 0:
            yield tuple(parts)
            return
        if len(parts) >= max_parts:
            return
        for s in sizes:
            if s <= rem:
                parts.append(s)
                yield from rec(rem - s, parts)
                parts.pop()
    yield from rec(n, [])


def split_groups(digits, comp):
    out, i = [], 0
    for s in comp:
        out.append(digits[i:i + s])
        i += s
    return out


SEPS = [(" ", 0.0), ("-", 0.0), (".", 1.0), ("/", 2.0), ("_", 3.0)]


def build_variations(core, limit=2000, partial=True):
    local = "0" + core
    scored = {}

    def add(s, score):
        if s not in scored or scored[s] > score:
            scored[s] = score

    # Prefix & format yang banyak dipakai
    forms = [
        ("", local, 0.0),           # 089675139742 (+ grouping)
        ("", core, 2.0),            # 89675139742 (+ grouping)
        ("+62", core, 0.0),         # +6289675139742
        ("+62 ", core, 0.0),        # +62 89675139742
        ("+62-", core, 0.0),        # +62-89675139742
        ("62", core, 0.5),          # 6289675139742
        ("62 ", core, 0.5),         # 62 89675139742
        ("62-", core, 0.5),         # 62-89675139742
        ("(+62) ", core, 1.5),      # (+62) 89675139742
        ("(+62)", core, 1.5),       # (+62)89675139742
        ("(62) ", core, 2.0),       # (62) 89675139742
        ("(62)", core, 2.0),        # (62)89675139742
        ("0062", core, 3.0),        # 006289675139742
        ("0062 ", core, 3.0),       # 0062 89675139742
        ("0062-", core, 3.0),       # 0062-89675139742
        ("+62(0)", core, 3.0),      # +62(0)89675139742
        ("+620", core, 3.5),        # +62089675139742
        ("+62 0", core, 3.5),       # +62 089675139742
        ("+62 (0)", core, 3.5),     # +62 (0)89675139742
    ]

    for prefix, body, pen in forms:
        add(prefix + body, pen + 0.2)
        if prefix:
            add(prefix + " " + body, pen + 0.4)
            add(prefix + "-" + body, pen + 0.6)
        for comp in compositions(len(body)):
            base = pen + len(comp) * 0.7 + sum(0 if s in (3, 4) else 1.2 for s in comp)
            groups = split_groups(body, comp)
            for sep, spen in SEPS:
                g = sep.join(groups)
                if not prefix:
                    add(g, base + spen)
                else:
                    add(prefix + " " + g, base + spen + 0.1)
                    add(prefix + sep + g, base + spen + 0.3)
                    add(prefix + g, base + spen + 1.0)

    main = [s for s, _ in sorted(scored.items(), key=lambda x: (x[1], len(x[0]), x[0]))]

    plat = [
        f"wa.me/62{core}", f"wa.me/+62{core}", f"https://wa.me/62{core}",
        f"api.whatsapp.com/send?phone=62{core}",
        f"api.whatsapp.com/send/?phone=62{core}",
        f"web.whatsapp.com/send?phone=62{core}",
        f"whatsapp://send?phone=62{core}",
        f"tel:+62{core}", f"tel:0{core}", f"tel:62{core}", f"sms:+62{core}",
        f"t.me/+62{core}", f"wa.me/0{core}", f"wa.me/{core}",
    ]

    masked, seen_m = [], set()
    for mc in "x*X#•_":
        for k in (4, 5, 3):
            for m in (4, 3, 2):
                hidden = len(local) - k - m
                if hidden < 1:
                    continue
                head, tail, mid = local[:k], local[-m:], mc * hidden
                cands = [
                    head + mid + tail,
                    f"{head}-{mid}-{tail}",
                    f"{head} {mid} {tail}",
                    f"+62{local[1:k]}{mid}{tail}",
                    f"+62 {local[1:k]}-{mid}-{tail}",
                    f"62{local[1:k]}{mid}{tail}",
                ]
                for c in cands:
                    if c not in seen_m:
                        seen_m.add(c)
                        masked.append(c)

    part = []
    if partial:
        for n in (8, 7):
            t = core[-n:]
            part.append(t)
            part.append(f"{t[:4]} {t[4:]}" if n == 8 else f"{t[:3]} {t[3:]}")
            part.append(f"{t[:4]}-{t[4:]}" if n == 8 else f"{t[:3]}-{t[3:]}")

    # === Format prioritas: TANPA PREFIX HARUS NOMOR 1 ===
    pretty = [local]  # 089675139742 ditaruh paling atas

    if len(local) >= 10:
        seg4 = [local[:4], local[4:8], local[8:]]
        seg4 = [s for s in seg4 if s]
        pretty.append("-".join(seg4))             # 0896-7513-9742
        pretty.append(" ".join(seg4))             # 0896 7513 9742
        pretty.append(".".join(seg4))             # 0896.7513.9742
        pretty.append("/".join(seg4))             # 0896/7513/9742

        seg3 = [core[:3], core[3:7], core[7:]]
        seg3 = [s for s in seg3 if s]
        dash3 = "-".join(seg3)
        pretty.extend([
            dash3,                                 # 896-7513-9742
            " ".join(seg3),                        # 896 7513 9742
            f"+62 {core}",                         # +62 89675139742
            f"+62-{core}",                         # +62-89675139742
            f"+62.{core}",                         # +62.89675139742
            f"+62 {dash3}",                        # +62 896-7513-9742
            f"+62-{dash3}",                        # +62-896-7513-9742
            f"62 {core}",                          # 62 89675139742
            f"62-{core}",                          # 62-89675139742
            f"62 {dash3}",                         # 62 896-7513-9742
            f"(+62) {core}",                       # (+62) 89675139742
            f"(62) {core}",                        # (62) 89675139742
            f"(0{core[:3]}) {core[3:7]}-{core[7:]}",  # (0896) 7513-9742
            f"0062 {core}",                        # 0062 89675139742
        ])

    reserve = len(plat) + min(len(masked), 120) + len(part)
    result, taken = [], set()
    
    # Masukkan `pretty` paling awal agar tanpa prefix dieksekusi pertama kali
    for src in (pretty, main[:max(limit - reserve - len(pretty), 50)], plat, masked[:120], part):
        for v in src:
            if v and v not in taken:
                taken.add(v)
                result.append(v)
    return result[:limit]


# --------------------------------------------------------------------------
# MESIN PENCARI (SCRAPING + GOOGLE API FALLBACK)
# --------------------------------------------------------------------------
def _clean_ddg_href(href):
    if href.startswith("//duckduckgo.com/l/"):
        qs = parse_qs(urlparse("https:" + href).query)
        return unquote(qs.get("uddg", [""])[0])
    if href.startswith("/l/"):
        qs = parse_qs(urlparse("https://duckduckgo.com" + href).query)
        return unquote(qs.get("uddg", [""])[0])
    return href


def search_ddg(query, num=10):
    try:
        r = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query, "kl": "id-id"},
            headers=HEADERS, timeout=20,
        )
        if r.status_code != 200: return []
        soup = BeautifulSoup(r.text, "html.parser")
        out = []
        for a in soup.select("a.result__a"):
            href = _clean_ddg_href(a.get("href", ""))
            if not href.startswith("http"): continue
            title = a.get_text(" ", strip=True)
            snip = ""
            parent = a.find_parent("div", class_="result")
            if parent:
                sn = parent.select_one(".result__snippet")
                if sn: snip = sn.get_text(" ", strip=True)
            out.append({"url": href, "title": title, "snippet": snip})
            if len(out) >= num: break
        return out
    except Exception:
        return []


def search_bing(query, num=10):
    try:
        r = requests.get(
            "https://www.bing.com/search",
            params={"q": query, "setlang": "id", "cc": "ID"},
            headers=HEADERS, timeout=20,
        )
        if r.status_code != 200: return []
        soup = BeautifulSoup(r.text, "html.parser")
        out = []
        for li in soup.select("li.b_algo"):
            a = li.select_one("h2 a")
            if not a: continue
            href = a.get("href", "")
            if not href.startswith("http"): continue
            title = a.get_text(" ", strip=True)
            sn = li.select_one(".b_caption p") or li.select_one(".b_snippet")
            snip = sn.get_text(" ", strip=True) if sn else ""
            out.append({"url": href, "title": title, "snippet": snip})
            if len(out) >= num: break
        return out
    except Exception:
        return []


def search_mojeek(query, num=10):
    try:
        r = requests.get(
            "https://www.mojeek.com/search",
            params={"q": query},
            headers=HEADERS, timeout=20,
        )
        if r.status_code != 200: return []
        soup = BeautifulSoup(r.text, "html.parser")
        out = []
        for li in soup.select("li.result"):
            a = li.select_one("a.title") or li.select_one("h2 a")
            if not a: continue
            href = a.get("href", "")
            if not href.startswith("http"): continue
            title = a.get_text(" ", strip=True)
            sn = li.select_one("p.s")
            snip = sn.get_text(" ", strip=True) if sn else ""
            out.append({"url": href, "title": title, "snippet": snip})
            if len(out) >= num: break
        return out
    except Exception:
        return []


def search_google(query, num=10):
    # --- Mode 1: Google API resmi ---
    key = os.environ.get("GOOGLE_API_KEY")
    cx = os.environ.get("GOOGLE_CSE_ID")
    if key and cx:
        try:
            r = requests.get(
                "https://www.googleapis.com/customsearch/v1",
                params={"key": key, "cx": cx, "q": query, "num": min(num, 10)},
                timeout=25,
            )
            if r.status_code == 200:
                items = r.json().get("items", [])
                return [
                    {"url": it.get("link", ""),
                     "title": it.get("title", ""),
                     "snippet": it.get("snippet", "")}
                    for it in items[:num] if it.get("link")
                ]
        except Exception:
            pass

    # --- Mode 2: Scraping dengan trik Mobile User-Agent ---
    try:
        r = requests.get(
            "https://www.google.com/search",
            params={"q": query, "num": num, "hl": "id"},
            headers=MOBILE_HEADERS, timeout=20,
            allow_redirects=True,
        )
        if r.status_code != 200: return []
        if "/sorry/" in r.url or "captcha" in r.text[:5000].lower() or "unusual traffic" in r.text[:5000].lower():
            return [] 
            
        soup = BeautifulSoup(r.text, "html.parser")
        out, seen = [], set()
        for div in soup.select("div.kCrYT, div.g, div.MjjYud"):
            a = div.find("a", href=True)
            if not a: continue
            href = a["href"]
            real = None
            if href.startswith("/url?q="):
                real = unquote(href.split("/url?q=")[1].split("&")[0])
            elif href.startswith("http") and "google." not in href:
                real = href
                
            if not real or not real.startswith("http"): continue
            if "google." in real or "gstatic.com" in real: continue
            if real in seen: continue
            
            seen.add(real)
            title_el = div.find("h3")
            title = title_el.get_text(" ", strip=True) if title_el else a.get_text(" ", strip=True)
            snippet_el = div.find("div", class_="VwiC3b")
            snip = snippet_el.get_text(" ", strip=True) if snippet_el else ""
            
            out.append({"url": real, "title": title, "snippet": snip})
            if len(out) >= num: break
        return out
    except Exception:
        return []


def search_yandex(query, num=10):
    try:
        r = requests.get(
            "https://yandex.com/search/",
            params={"text": query, "lr": "10000"},
            headers=HEADERS, timeout=20,
        )
        if r.status_code != 200: return []
        soup = BeautifulSoup(r.text, "html.parser")
        out = []
        for li in soup.select("li.serp-item, .Organic"):
            a = li.select_one("a.OrganicTitle-Link") or li.select_one("a.Link") or li.select_one("a")
            if not a: continue
            href = a.get("href", "")
            if href.startswith("/"): href = "https://yandex.com" + href
            if not href.startswith("http"): continue
            title = a.get_text(" ", strip=True)
            sn = li.select_one(".OrganicTextContentSpan") or li.select_one(".Organic-ContentWrapper")
            snip = sn.get_text(" ", strip=True) if sn else ""
            out.append({"url": href, "title": title, "snippet": snip})
            if len(out) >= num: break
        return out
    except Exception:
        return []


ENGINES = {
    "ddg":    ("DuckDuckGo", search_ddg,    "https://duckduckgo.com/?q={}"),
    "bing":   ("Bing",       search_bing,   "https://www.bing.com/search?q={}"),
    "mojeek": ("Mojeek",     search_mojeek, "https://www.mojeek.com/search?q={}"),
    "google": ("Google",     search_google, "https://www.google.com/search?q={}"),
    "yandex": ("Yandex",     search_yandex, "https://yandex.com/search/?text={}"),
}


# --------------------------------------------------------------------------
# DETEKSI SOSIAL MEDIA & VERIFIKASI
# --------------------------------------------------------------------------
SOCIAL_HOSTS = {
    "facebook.com": "Facebook", "fb.com": "Facebook", "fb.watch": "Facebook",
    "instagram.com": "Instagram", "x.com": "X/Twitter", "twitter.com": "X/Twitter",
    "tiktok.com": "TikTok", "linkedin.com": "LinkedIn", "t.me": "Telegram",
    "threads.net": "Threads", "youtube.com": "YouTube", "youtu.be": "YouTube",
    "reddit.com": "Reddit", "pinterest.com": "Pinterest", "kaskus.co.id": "Kaskus",
    "wa.me": "WhatsApp", "api.whatsapp.com": "WhatsApp", "web.whatsapp.com": "WhatsApp",
}

POST_PATTERNS = [
    r"/posts/", r"/permalink", r"story_fbid", r"/photo", r"/videos?/", r"/reel/",
    r"/watch", r"/groups/[^/]+/(posts|permalink)", r"/marketplace/item",
    r"/p/[\w-]+", r"/status/\d+", r"/video/\d+", r"[?&]v=", r"/pulse/",
    r"/feed/update", r"/post/", r"/comments/", r"^https?://t\.me/[\w]+/\d+",
    r"/share/[pvr]/",
]


def host_of(url):
    h = urlparse(url).netloc.lower()
    for pre in ("www.", "m.", "web.", "mobile.", "id-id."):
        if h.startswith(pre):
            h = h[len(pre):]
    return h


def social_name(url):
    h = host_of(url)
    for dom, name in SOCIAL_HOSTS.items():
        if h == dom or h.endswith("." + dom):
            return name
    return None


def is_post(url):
    return any(re.search(p, url) for p in POST_PATTERNS)


def verify(core, text):
    digits = re.sub(r"\D", "", text)
    local, intl = "0" + core, "62" + core
    if core in digits or local in digits or intl in digits:
        return "EXACT"
    if core[-8:] in digits:
        return "SEBAGIAN"
    if local[:4] in digits and core[-4:] in digits:
        return "DISENSOR"
    if re.search(re.escape(local[:4]) + r"[\W_xX*#•]{2,}" + re.escape(core[-4:]), text):
        return "DISENSOR"
    return None


# --------------------------------------------------------------------------
# TAMPIL HASIL
# --------------------------------------------------------------------------
LABEL_COLOR = {
    "EXACT": "\033[92m", "SEBAGIAN": "\033[93m",
    "DISENSOR": "\033[96m", "UNVERIFIED": "\033[97m",
}
LABEL_TEXT = {
    "EXACT": "✔ nomor terlihat di cuplikan",
    "SEBAGIAN": "~ sebagian nomor terlihat",
    "DISENSOR": "~ nomor disensor",
    "UNVERIFIED": "• dari hasil pencarian (belum terverifikasi)",
}


def show(entry, idx):
    tag = entry["platform"] or host_of(entry["url"])
    if entry["platform"]:
        kind = "POSTINGAN" if entry["post"] else "PROFIL/LAINNYA"
    else:
        kind = "SITUS"
    col = LABEL_COLOR[entry["match"]]

    engs = ", ".join(ENGINES[k][0] for k in entry.get("engines", []) if k in ENGINES)
    via_str = f"via: {engs}"
    if len(entry["via"]) > 1:
        via_str += f" • {len(entry['via'])} variasi"

    print(f"{BOLD}[{idx}] {tag} • {kind}{RESET}")
    print(f"    {entry['title'][:90]}")
    print(f"    {entry['url']}")
    print(f"    {col}{LABEL_TEXT[entry['match']]}{RESET}  {DIM}{via_str}{RESET}")
    snip = entry["snippet"].replace("\n", " ")
    if snip:
        print(f"    {DIM}{snip[:140]}{RESET}")
    print()


def section(title, entries, start=1):
    print(rainbow("═" * 40))
    print(BOLD + f" {title}  ({len(entries)})" + RESET)
    print(rainbow("═" * 40))
    if not entries:
        print(DIM + "  (tidak ada)\n" + RESET)
        return start
    for i, e in enumerate(entries, start):
        show(e, i)
    return start + len(entries)


def canon(url):
    p = urlparse(url)
    host = host_of(url)
    path = p.path.rstrip("/")
    keep = []
    for part in p.query.split("&"):
        k = part.split("=")[0].lower()
        if part and not k.startswith("utm_") and k not in (
            "fbclid", "gclid", "igshid", "ref", "hl", "mibextid"
        ):
            keep.append(part)
    return host + path + ("?" + "&".join(keep) if keep else "")


# --------------------------------------------------------------------------
# PENCARIAN UTAMA
# --------------------------------------------------------------------------
def run_search(core, a):
    variations = build_variations(core, a.limit, partial=not a.no_partial)

    engines_use = [e.strip() for e in (a.engines or "").split(",") if e.strip() in ENGINES]
    if not engines_use:
        engines_use = ["ddg", "bing", "mojeek", "google"]

    print(f"Variasi    : {len(variations)} format nomor")
    print(f"Mesin      : {', '.join(ENGINES[e][0] for e in engines_use)}")
    if "google" in engines_use:
        if os.environ.get("GOOGLE_API_KEY") and os.environ.get("GOOGLE_CSE_ID"):
            print(DIM + "  → Google: pakai API resmi (andal)" + RESET)
        else:
            print(DIM + "  → Google: scraping Mobile (rawan CAPTCHA)" + RESET)

    # ---------------- MODE LINK ----------------
    if a.link_only or requests is None or BeautifulSoup is None:
        if not a.link_only and (requests is None or BeautifulSoup is None):
            print("ℹ requests / beautifulsoup4 belum tersedia → mode link.\n")
        links = []
        for v in variations:
            q = quote_plus('"' + v + '"')
            for eng_key in engines_use:
                links.append(ENGINES[eng_key][2].format(q))
        fn = f"link_{core}.txt"
        with open(fn, "w", encoding="utf-8") as f:
            f.write("\n".join(links))
        print(f"\n{len(links)} link pencarian dibuat ({len(variations)} variasi × {len(engines_use)} mesin).")
        print(f"Contoh 8 pertama:\n")
        for l in links[:8]:
            print(l + "\n")
        print(f"Semua link disimpan di: {fn}")
        return

    # ---------------- MODE SCRAPING ----------------
    todo = variations[:a.max_queries]
    total_req = len(todo) * len(engines_use)
    if len(variations) > len(todo):
        print(f"Batas      : {len(todo)} variasi pertama (--max-queries)")
    print(f"Total req  : {total_req} pencarian")
    print(f"Jeda       : ~{a.delay:.1f}s antar request")
    print(DIM + "Mencari satu per satu, hasil dikirim setelah semua selesai\n" + RESET)

    found = {}
    done = 0
    fail_streak = {e: 0 for e in engines_use}

    try:
        for n, v in enumerate(todo, 1):
            # Loose search (tanpa kutip) khusus untuk Google & Bing agar hasil lebih luas
            query_exact = '"' + v + '"'
            query_loose = v
            
            loose = len(re.sub(r"\D", "", v)) < len(core)

            for eng_key in engines_use:
                eng_name, eng_fn, _ = ENGINES[eng_key]
                if fail_streak.get(eng_key, 0) >= 5:
                    continue 
                
                print(f"\r{DIM}[{n}/{len(todo)}] {v[:26]:<26} | {eng_name:<11} | link: {len(found)}{RESET}\033[K", end="", flush=True)
                
                q_use = query_loose if eng_key in ("google", "bing") else query_exact
                
                results = eng_fn(q_use, num=10)
                if not results:
                    fail_streak[eng_key] = fail_streak.get(eng_key, 0) + 1
                else:
                    fail_streak[eng_key] = 0

                for it in results:
                    url = it.get("url", "")
                    if not url: continue
                    title = it.get("title", "")
                    snip = it.get("snippet", "")
                    text = " ".join([title, snip, url])
                    m = verify(core, text)
                    
                    if loose and not m: continue
                    
                    key_u = canon(url)
                    if key_u in found:
                        e = found[key_u]
                        if v not in e["via"]: e["via"].append(v)
                        if eng_key not in e["engines"]: e["engines"].append(eng_key)
                        if m and e["match"] == "UNVERIFIED": e["match"] = m
                        continue
                    found[key_u] = {
                        "url": url, "title": title, "snippet": snip,
                        "match": m or "UNVERIFIED",
                        "platform": social_name(url),
                        "post": is_post(url) and bool(social_name(url)),
                        "via": [v],
                        "engines": [eng_key],
                    }
                time.sleep(random.uniform(a.delay * 0.5, a.delay * 1.2))
            done = n
    except KeyboardInterrupt:
        print("\nDihentikan lebih awal, menampilkan hasil yang sudah terkumpul.")
    print("\n")

    # ---------------- KIRIM SEMUA SEKALIGUS ----------------
    order = {"EXACT": 0, "SEBAGIAN": 1, "DISENSOR": 2, "UNVERIFIED": 3}
    res = list(found.values())
    social = sorted([e for e in res if e["platform"]],
                    key=lambda e: (not e["post"], order[e["match"]]))
    others = sorted([e for e in res if not e["platform"]],
                    key=lambda e: order[e["match"]])

    i = section("SOSIAL MEDIA / MESSAGING", social)
    section("SITUS LAIN", others, i)

    print(rainbow("═" * 40))
    print(BOLD + " SUMBER PENCARIAN" + RESET)
    print(rainbow("═" * 40))
    per_engine = {e: 0 for e in engines_use}
    for entry in res:
        for eng in entry.get("engines", []):
            if eng in per_engine:
                per_engine[eng] += 1
    for eng_key, count in per_engine.items():
        status = " (auto-skip/CAPTCHA)" if fail_streak.get(eng_key, 0) >= 5 else ""
        print(f"  {ENGINES[eng_key][0]:<12} {count:>3} link{status}")
    print()

    print(f"Selesai: {done} variasi × {len(engines_use)} mesin → "
          f"{len(social)} sosial media, {len(others)} situs lain (tanpa duplikat).")

    fn = f"hasil_{core}.json"
    with open(fn, "w", encoding="utf-8") as f:
        json.dump({"sosmed": social, "situs_lain": others, "per_engine": per_engine}, f, ensure_ascii=False, indent=2)
    print(f"Disimpan di: {fn}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("nomor", nargs="?")
    ap.add_argument("--limit", type=int, default=2000,
                    help="jumlah variasi nomor yang dibuat (default 2000)")
    ap.add_argument("--max-queries", type=int, default=40,
                    help="batas variasi yang benar-benar dicari (default 40)")
    ap.add_argument("--delay", type=float, default=1.5,
                    help="jeda dasar antar request, detik (default 1.5)")
    ap.add_argument("--engines", type=str, default="ddg,bing,mojeek,google",
                    help="mesin pencari (comma): ddg,bing,mojeek,google,yandex")
    ap.add_argument("--no-partial", action="store_true",
                    help="matikan pencarian 7-8 digit terakhir")
    ap.add_argument("--link-only", action="store_true",
                    help="hanya generate link pencarian (tanpa scraping)")
    a = ap.parse_args()

    nomor = a.nomor
    while True:
        banner()
        raw = nomor or input(rainbow("Masukkan nomor » ") + " ").strip()
        nomor = None
        core = normalize(raw)
        if not core:
            print("Nomor tidak valid.\n")
            continue
        if not core.startswith("8") or not (9 <= len(core) <= 12):
            print("⚠ Nomor tidak terlihat seperti nomor seluler Indonesia, tetap dilanjutkan.\n")
        print(f"Nomor inti : {core}  (0{core} / +62{core})")

        run_search(core, a)

        ans = input("\n" + rainbow("Mau mencari lagi? (y/n) » ") + " ").strip().lower()
        if ans not in ("y", "ya"):
            print("Sampai jumpa.")
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDibatalkan.")
        sys.exit(0)

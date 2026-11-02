#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MR. 414N - Pencari nomor yang tersebar di internet (lewat mesin pencarian Google)

Setup (sekali saja):
  pip install requests
  export GOOGLE_API_KEY="..."   # dari Google Cloud Console (Custom Search API)
  export GOOGLE_CSE_ID="..."    # dari programmablesearchengine.google.com
                                # (pilih "Search the entire web")

Pakai:
  python3 mr414n.py                       # akan ditanya nomornya
  python3 mr414n.py 08xxxxxxxxxx
  python3 mr414n.py 08xxxxxxxxxx --max-queries 100 --delay 2
  python3 mr414n.py 08xxxxxxxxxx --link-only   # tanpa API: daftar link pencarian Google

Cara kerja: variasi dicari SATU PER SATU (tanpa OR) di latar belakang dengan jeda,
dimulai dari nomor aslinya. Setelah semua selesai, link dikirim sekaligus, tanpa duplikat.
"""
import os
import re
import sys
import json
import time
import random
import colorsys
import argparse
from urllib.parse import quote_plus, urlparse

try:
    import requests
except ImportError:
    requests = None

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


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
    print("\033c", end="")  # pastikan layar benar-benar bersih
    for line in TUX.strip("\n").split("\n"):
        print("\033[97m" + line + RESET)
    print()
    for i, row in enumerate(big_text("MR. 414N")):
        print(rainbow(row, offset=i * 0.04))
    print(DIM + "  pencari nomor yang tersebar di internet" + RESET)
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


def build_variations(core, limit=1000, partial=True):
    local = "0" + core
    scored = {}

    def add(s, score):
        if s not in scored or scored[s] > score:
            scored[s] = score

    # (awalan, digit yang dikelompokkan, penalti)
    forms = [
        ("", local, 0.0),
        ("", core, 2.0),
        ("+62", core, 0.0),
        ("62", core, 0.5),
        ("(+62)", core, 2.0),
        ("0062", core, 3.0),
        ("+62(0)", core, 3.0),
        ("+620", core, 3.5),
        ("+62 0", core, 3.5),
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

    # format platform / link
    plat = [
        f"wa.me/62{core}", f"wa.me/+62{core}", f"https://wa.me/62{core}",
        f"api.whatsapp.com/send?phone=62{core}", f"api.whatsapp.com/send/?phone=62{core}",
        f"web.whatsapp.com/send?phone=62{core}", f"whatsapp://send?phone=62{core}",
        f"tel:+62{core}", f"tel:0{core}", f"tel:62{core}", f"sms:+62{core}",
        f"t.me/+62{core}", f"wa.me/0{core}", f"wa.me/{core}",
    ]

    # nomor disensor
    masked, seen = [], set()
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
                    if c not in seen:
                        seen.add(c)
                        masked.append(c)

    # pencarian sebagian (ekor nomor)
    part = []
    if partial:
        for n in (8, 7):
            t = core[-n:]
            part.append(t)
            part.append(f"{t[:4]} {t[4:]}" if n == 8 else f"{t[:3]} {t[3:]}")
            part.append(f"{t[:4]}-{t[4:]}" if n == 8 else f"{t[:3]}-{t[3:]}")

    reserve = len(plat) + min(len(masked), 120) + len(part)
    result, taken = [], set()
    for src in (main[:max(limit - reserve, 50)], plat, masked[:120], part):
        for v in src:
            if v not in taken:
                taken.add(v)
                result.append(v)
    return result[:limit]


# --------------------------------------------------------------------------
# QUERY
# --------------------------------------------------------------------------
def chunk_or(variations, size=6, maxchars=700):
    chunks, cur, length = [], [], 0
    for v in variations:
        q = f'"{v}"'
        if cur and (len(cur) >= size or length + len(q) + 4 > maxchars):
            chunks.append(" OR ".join(cur))
            cur, length = [], 0
        cur.append(q)
        length += len(q) + 4
    if cur:
        chunks.append(" OR ".join(cur))
    return chunks


SOCIAL_GROUPS = [
    ("Facebook", ["facebook.com"]),
    ("Instagram", ["instagram.com"]),
    ("X/Twitter", ["x.com", "twitter.com"]),
    ("TikTok", ["tiktok.com"]),
    ("LinkedIn", ["linkedin.com"]),
    ("Telegram/Threads", ["t.me", "threads.net"]),
    ("YouTube", ["youtube.com"]),
    ("Reddit", ["reddit.com"]),
]

SOCIAL_HOSTS = {
    "facebook.com": "Facebook", "fb.com": "Facebook", "fb.watch": "Facebook",
    "instagram.com": "Instagram", "x.com": "X/Twitter", "twitter.com": "X/Twitter",
    "tiktok.com": "TikTok", "linkedin.com": "LinkedIn", "t.me": "Telegram",
    "threads.net": "Threads", "youtube.com": "YouTube", "youtu.be": "YouTube",
    "reddit.com": "Reddit", "pinterest.com": "Pinterest", "kaskus.co.id": "Kaskus",
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
    # pola disensor tanpa digit di tengah, mis. 0896****9742
    if re.search(re.escape(local[:4]) + r"[\W_xX*#•]{2,}" + re.escape(core[-4:]), text):
        return "DISENSOR"
    return None


def google_api(q, key, cx, start=1):
    r = requests.get(
        "https://www.googleapis.com/customsearch/v1",
        params={"key": key, "cx": cx, "q": q, "num": 10, "start": start},
        timeout=25,
    )
    if r.status_code != 200:
        try:
            msg = r.json().get("error", {}).get("message", r.text[:200])
        except Exception:
            msg = r.text[:200]
        return None, f"HTTP {r.status_code}: {msg}"
    return r.json().get("items", []), None


# --------------------------------------------------------------------------
# TAMPIL HASIL
# --------------------------------------------------------------------------
LABEL_COLOR = {"EXACT": "\033[92m", "SEBAGIAN": "\033[93m", "DISENSOR": "\033[96m", "GOOGLE": "\033[97m"}
LABEL_TEXT = {
    "EXACT": "✔ nomor terlihat di cuplikan",
    "SEBAGIAN": "~ sebagian nomor terlihat",
    "DISENSOR": "~ nomor disensor",
    "GOOGLE": "dari hasil Google",
}


def show(entry, idx):
    tag = entry["platform"] or host_of(entry["url"])
    if entry["platform"]:
        kind = "POSTINGAN" if entry["post"] else "PROFIL/LAINNYA"
    else:
        kind = "SITUS"
    col = LABEL_COLOR[entry["match"]]
    print(f"{BOLD}[{idx}] {tag} • {kind}{RESET}")
    print(f"    {entry['title'][:90]}")
    print(f"    {entry['url']}")
    print(f"    {col}{LABEL_TEXT[entry['match']]}{RESET}  {DIM}via: {entry['via'][0]}"
          + (f" (+{len(entry['via']) - 1} variasi lain)" if len(entry['via']) > 1 else "") + RESET)
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
    """Kunci anti-duplikat: abaikan skema, www/m, parameter pelacak, dan garis miring akhir."""
    p = urlparse(url)
    host = host_of(url)
    path = p.path.rstrip("/")
    q = p.query
    keep = []
    for part in q.split("&"):
        k = part.split("=")[0].lower()
        if part and not k.startswith("utm_") and k not in ("fbclid", "gclid", "igshid", "ref", "hl"):
            keep.append(part)
    return host + path + ("?" + "&".join(keep) if keep else "")


def run_search(core, a, key, cx):
    variations = build_variations(core, a.limit, partial=not a.no_partial)
    print(f"Variasi    : {len(variations)} format (dicari satu per satu)")

    # ---------------- MODE LINK ----------------
    if a.link_only or not (key and cx) or requests is None:
        if not a.link_only:
            print("ℹ GOOGLE_API_KEY / GOOGLE_CSE_ID / requests belum tersedia → mode link.\n")
        links = [f"https://www.google.com/search?q={quote_plus(chr(34) + v + chr(34))}" for v in variations]
        fn = f"link_{core}.txt"
        with open(fn, "w", encoding="utf-8") as f:
            f.write("\n".join(links))
        print(f"{len(links)} link pencarian Google (1 variasi per link). Contoh 5 pertama:\n")
        for l in links[:5]:
            print(l + "\n")
        print(f"Semua link disimpan di: {fn}")
        return

    # ---------------- MODE API: satu variasi per pencarian, di latar belakang ----------------
    todo = variations[:a.max_queries]
    if len(variations) > len(todo):
        print(f"Batas      : {len(todo)} pencarian pertama (--max-queries); variasi tersisa dilewati")
    print(f"Jeda       : sekitar {a.delay:.1f} detik antar pencarian")
    print(DIM + "Mencari di latar belakang, hasil dikirim setelah semua selesai (Ctrl+C untuk berhenti lebih awal)\n" + RESET)

    found = {}          # kunci canon -> entry
    done = 0
    errors = 0
    try:
        for n, v in enumerate(todo, 1):
            print(f"\r{DIM}[{n}/{len(todo)}] {v[:34]:<34} | link unik: {len(found)}{RESET}\033[K", end="", flush=True)
            loose = len(re.sub(r"\D", "", v)) < len(core)   # disensor / sebagian
            q = '"' + v + '"'
            stop = False
            for p in range(a.pages):
                items, err = google_api(q, key, cx, start=1 + p * 10)
                if err:
                    errors += 1
                    print(f"\n⚠ {err}")
                    low = err.lower()
                    if "429" in err or "quota" in low or "limit" in low:
                        stop = True
                    break
                if not items:
                    break
                for it in items:
                    url = it.get("link", "")
                    if not url:
                        continue
                    title = it.get("title", "")
                    snip = it.get("snippet", "")
                    text = " ".join([title, snip, url, json.dumps(it.get("pagemap", {}), ensure_ascii=False)[:1500]])
                    m = verify(core, text)
                    if loose and not m:
                        continue          # variasi disensor/sebagian: hanya terima yang terbukti cocok
                    key_u = canon(url)
                    if key_u in found:
                        e = found[key_u]
                        if v not in e["via"]:
                            e["via"].append(v)
                        if m and e["match"] == "GOOGLE":
                            e["match"] = m
                        continue
                    found[key_u] = {
                        "url": url, "title": title, "snippet": snip, "match": m or "GOOGLE",
                        "platform": social_name(url),
                        "post": is_post(url) and bool(social_name(url)),
                        "via": [v],
                    }
                if p + 1 < a.pages:
                    time.sleep(random.uniform(a.delay * 0.5, a.delay))
            done = n
            if stop:
                print("\nKuota/batas Google tercapai, pencarian dihentikan.")
                break
            if n < len(todo):
                time.sleep(random.uniform(a.delay, a.delay * 1.6))
    except KeyboardInterrupt:
        print("\nDihentikan lebih awal, menampilkan hasil yang sudah terkumpul.")
    print("\n")

    # ---------------- KIRIM SEMUA SEKALIGUS ----------------
    order = {"EXACT": 0, "SEBAGIAN": 1, "DISENSOR": 2, "GOOGLE": 3}
    res = list(found.values())
    social = sorted([e for e in res if e["platform"]], key=lambda e: (not e["post"], order[e["match"]]))
    others = sorted([e for e in res if not e["platform"]], key=lambda e: order[e["match"]])

    i = section("SOSIAL MEDIA", social)
    section("SITUS LAIN", others, i)

    print(f"Selesai: {done} variasi dicari → {len(social)} link sosial media, {len(others)} situs lain (tanpa duplikat).")
    fn = f"hasil_{core}.json"
    with open(fn, "w", encoding="utf-8") as f:
        json.dump({"sosmed": social, "situs_lain": others}, f, ensure_ascii=False, indent=2)
    print(f"Disimpan di: {fn}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("nomor", nargs="?")
    ap.add_argument("--limit", type=int, default=1000, help="jumlah variasi yang dibuat (default 1000)")
    ap.add_argument("--max-queries", type=int, default=100, help="batas pencarian API per nomor (default 100)")
    ap.add_argument("--delay", type=float, default=2.0, help="jeda dasar antar pencarian, detik (default 2)")
    ap.add_argument("--pages", type=int, default=1, help="halaman per pencarian (10 hasil/halaman)")
    ap.add_argument("--no-partial", action="store_true", help="matikan pencarian 7-8 digit terakhir")
    ap.add_argument("--link-only", action="store_true", help="tanpa API, hasilkan link pencarian Google saja")
    a = ap.parse_args()

    key = os.environ.get("GOOGLE_API_KEY")
    cx = os.environ.get("GOOGLE_CSE_ID")
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

        run_search(core, a, key, cx)

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

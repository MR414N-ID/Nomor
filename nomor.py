#!/usr/bin/env python3
"""Cari nomor HP (08xx / 62xx / +62xx, boleh pakai strip/spasi/titik) yang
muncul di hasil pencarian web untuk sebuah keyword.

Pakai : python nomor.py "keyword"        (atau jalankan tanpa argumen)
        python nomor.py "keyword" -p 3   (3 halaman hasil per pencarian)
Butuh : pip install requests
        (Termux: pkg install python && pip install requests)
BY. MR414N-ID

Catatan: Google memblokir scraping otomatis, jadi tools ini memakai
DuckDuckGo + Bing, lalu membuka tiap halaman hasilnya dan mengambil nomor.
"""
import argparse
import base64
import html
import re
import shutil
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
}

# Variasi query supaya hasil lebih beragam (08 / +62 / WA)
VARIAN = ["{k}", "{k} 08", "{k} +62", "{k} kontak whatsapp"]

# Domain yang dilewati saat membuka halaman
SKIP_DOMAIN = ("duckduckgo.com", "bing.com", "google.com", "microsoft.com")

MAX_BYTES = 600_000   # batas unduh per halaman
MAX_HALAMAN = 40      # batas halaman yang dibuka per pencarian

C = {"r": "\033[91m", "g": "\033[92m", "y": "\033[93m", "c": "\033[96m",
     "d": "\033[90m", "w": "\033[97m", "x": "\033[0m", "B": "\033[1m"}

# ---------------------------------------------------------------- pola nomor
# 08xx / 62 8xx / +62 8xx, pemisah: spasi . - ( )
PHONE_RE = re.compile(r"(?<!\d)(?:\+?62|0)[\s.\-()]{0,2}8(?:[\s.\-]?\d){8,11}(?!\d)")
# link WhatsApp: wa.me/62812..., api.whatsapp.com/send?phone=62812...
WA_RE = re.compile(r"(?:wa\.me/|phone=|tel:)\+?([\d\s.\-()]{9,20})", re.I)
# tanggal seperti 08-12-2020 jangan dianggap nomor
DATE_RE = re.compile(r"\b\d{1,2}[-./ ]\d{1,2}[-./ ](?:19|20)\d{2}\b")
# prefix operator seluler Indonesia yang valid (Telkomsel, Indosat, XL, Axis, Tri, Smartfren, dll)
VALID_RE = re.compile(r"^08(?:1[1-9]|2[1-3]|3[1-38]|5[1-9]|7[7-9]|8[1-9]|9[5-9])\d{6,9}$")


def normalisasi(raw):
    """Ubah ke format 08xxxxxxxxxx. Return None kalau bukan nomor seluler valid."""
    if DATE_RE.search(raw):
        return None
    d = re.sub(r"\D", "", raw)
    if d.startswith("62"):
        d = "0" + d[2:]
    return d if VALID_RE.match(d) else None


def ekstrak(teks):
    """Ambil semua nomor unik dari teks/HTML."""
    teks = html.unescape(teks)
    ketemu = set()
    # nomor di link wa.me / tel: (ada di atribut, jadi diambil sebelum tag dibuang)
    for m in WA_RE.finditer(teks):
        n = normalisasi(m.group(1))
        if n:
            ketemu.add(n)
    # buang style & script (kecuali JSON-LD yang sering memuat telepon), lalu tag
    teks = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", teks)
    teks = re.sub(r"(?is)<script(?![^>]*ld\+json)[^>]*>.*?</script>", " ", teks)
    teks = re.sub(r"<[^>]+>", " ", teks)
    for m in PHONE_RE.finditer(teks):
        n = normalisasi(m.group(0))
        if n:
            ketemu.add(n)
    return ketemu


def tampil(n):
    return f"{n} (+62{n[1:]})"


# ------------------------------------------------------------- mesin pencari
def _ddg_url(href):
    href = html.unescape(href)
    if href.startswith("//"):
        href = "https:" + href
    q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
    return q["uddg"][0] if "uddg" in q else href


def cari_ddg(q, halaman):
    hasil = []
    for i in range(halaman):
        try:
            r = requests.post("https://html.duckduckgo.com/html/",
                              data={"q": q, "s": i * 30, "dc": i * 30 + 1},
                              headers=HEADERS, timeout=15)
        except requests.RequestException:
            break
        if r.status_code != 200:
            break
        ms = list(re.finditer(r'class="result__a"[^>]*href="([^"]+)"', r.text))
        if not ms:
            break
        for j, m in enumerate(ms):
            akhir = ms[j + 1].start() if j + 1 < len(ms) else len(r.text)
            hasil.append((_ddg_url(m.group(1)), r.text[m.start():akhir]))
        time.sleep(1)
    return hasil


def _bing_url(href):
    href = html.unescape(href)
    if "bing.com/ck/a" in href:
        u = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("u", [""])[0]
        if u.startswith("a1"):
            u = u[2:]
            try:
                return base64.urlsafe_b64decode(u + "=" * (-len(u) % 4)).decode()
            except Exception:
                return href
    return href


def cari_bing(q, halaman):
    hasil = []
    for i in range(halaman):
        try:
            r = requests.get("https://www.bing.com/search",
                             params={"q": q, "first": i * 10 + 1, "setlang": "id"},
                             headers=HEADERS, timeout=15)
        except requests.RequestException:
            break
        if r.status_code != 200:
            break
        blok = re.findall(r'(?s)<li class="b_algo".*?</li>', r.text)
        if not blok:
            break
        for b in blok:
            m = re.search(r'<a[^>]+href="(https?://[^"]+)"', b)
            if m:
                hasil.append((_bing_url(m.group(1)), b))
        time.sleep(1)
    return hasil


# ----------------------------------------------------------- buka halaman web
def ambil_halaman(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, stream=True)
        tipe = r.headers.get("Content-Type", "").lower()
        if r.status_code != 200 or not ("text" in tipe or "html" in tipe or "json" in tipe):
            r.close()
            return ""
        buf = b""
        for chunk in r.iter_content(65536):
            buf += chunk
            if len(buf) > MAX_BYTES:
                break
        r.close()
        return buf.decode(r.encoding or "utf-8", errors="ignore")
    except Exception:
        return ""


# ------------------------------------------------------------------- utama
def cari(keyword, halaman):
    cols = shutil.get_terminal_size((50, 20)).columns
    garis = "=" * min(cols, 44)
    nomor = {}          # nomor -> set(url sumber)
    daftar = {}         # url -> potongan snippet dari mesin pencari

    print(C["y"] + f"[*] Mencari nomor untuk '{keyword}' ..." + C["x"])
    for v in VARIAN:
        q = v.format(k=keyword)
        print(f"{C['d']}    query: {q}{C['x']}", flush=True)
        for fn in (cari_ddg, cari_bing):
            for url, snip in fn(q, halaman):
                host = urllib.parse.urlparse(url).netloc.lower()
                if any(d in host for d in SKIP_DOMAIN):
                    continue
                daftar.setdefault(url, "")
                daftar[url] += snip
    # nomor yang sudah kelihatan di snippet hasil pencarian
    for url, snip in daftar.items():
        for n in ekstrak(snip):
            nomor.setdefault(n, set()).add(url)

    urls = list(daftar)[: MAX_HALAMAN * len(VARIAN)]
    total = len(urls)
    print(C["y"] + f"\n[*] Membuka {total} halaman hasil...\n" + C["x"])
    selesai = 0
    with ThreadPoolExecutor(max_workers=20) as ex:
        fut = {ex.submit(ambil_halaman, u): u for u in urls}
        for f in as_completed(fut):
            selesai += 1
            u = fut[f]
            try:
                teks = f.result()
            except Exception:
                teks = ""
            for n in ekstrak(teks):
                baru = n not in nomor
                nomor.setdefault(n, set()).add(u)
                if baru:
                    print(f"\r\033[K{C['g']}[nomor]{C['x']} {tampil(n)}  <- {u}", flush=True)
            print(f"\r{C['d']}[{selesai}/{total}] dibuka...{C['x']}", end="", flush=True)

    # ===== RINGKASAN DI BAWAH =====
    urut = sorted(nomor.items(), key=lambda x: (-len(x[1]), x[0]))
    print("\r\033[K", end="")
    print(f"\n{C['c']}{garis}{C['x']}")
    print(f"{C['g']}{C['B']}Searching selesai sukses [ {len(urut)} nomor ]{C['x']}")
    print(f"{C['d']}(dari {total} halaman yang dibuka){C['x']}")
    print(f"{C['c']}{garis}{C['x']}")
    if urut:
        for n, src in urut:
            s = sorted(src)
            extra = f"  (+{len(s) - 1} sumber lain)" if len(s) > 1 else ""
            print(f"{C['y']}{tampil(n)}{C['x']} : {s[0]}{extra}")
        print(f"{C['c']}{garis}{C['x']}")
        nama = re.sub(r"[^\w\-]+", "_", keyword)[:40]
        with open(f"nomor_{nama}.txt", "w", encoding="utf-8") as fh:
            fh.write(f"Searching selesai sukses [ {len(urut)} nomor ]\n")
            for n, src in urut:
                fh.write(f"{tampil(n)} : {' | '.join(sorted(src))}\n")
        print(f"{C['g']}Tersimpan di nomor_{nama}.txt{C['x']}")
    else:
        print(f"{C['r']}Tidak ada nomor ditemukan.{C['x']}")


def main():
    ap = argparse.ArgumentParser(description="Cari nomor HP di hasil pencarian web")
    ap.add_argument("keyword", nargs="*", help="kata kunci pencarian")
    ap.add_argument("-p", "--halaman", type=int, default=2,
                    help="jumlah halaman hasil per pencarian (default 2)")
    a = ap.parse_args()

    keyword = " ".join(a.keyword).strip()
    while True:
        if not keyword:
            try:
                keyword = input(f"{C['g']}[?] Masukkan keyword {C['w']}>> {C['x']}").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not keyword:
                break
        cari(keyword, max(1, a.halaman))
        keyword = ""
        try:
            lagi = input(f"\n{C['y']}Cari lagi? (y/n) {C['w']}>> {C['x']}").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if lagi != "y":
            break
    print(C["c"] + "\nTerima kasih!  —  BY. MR414N-ID" + C["x"])


if __name__ == "__main__":
    main()

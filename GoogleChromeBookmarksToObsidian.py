import os
import re
import uuid
import hashlib
import requests
import tldextract
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from markdownify import markdownify as md
from pathlib import Path
from datetime import datetime

BOOKMARKS_FILE = 'bookmarks_6_7_25.html'
OUTPUT_FOLDER = 'GoogleObsidian\\_GoogleBookmarks'
THUMB_FOLDER = '../__resources/_thumbs'
HEADERS = {"User-Agent": "Mozilla/5.0"}

def sanitize_filename(name, max_length=100):
    if not name:
        return "untitled"
    name = re.sub(r'[<>:"/\\|?*\n\r]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    name = name[:max_length].rstrip('. ')
    reserved = {'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'LPT1'}
    if name.upper() in reserved:
        name = f"_{name}"
    return name or "untitled"

def ensure_unique_filename(directory, base_name, extension=".md"):
    i = 0
    candidate = f"{base_name}{extension}"
    while os.path.exists(os.path.join(directory, candidate)):
        i += 1
        candidate = f"{base_name} ({i}){extension}"
    return os.path.join(directory, candidate)

def to_iso(timestamp):
    try:
        return datetime.utcfromtimestamp(int(timestamp)).isoformat() + "Z"
    except:
        return None

def fetch_preview(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.content, "html.parser")

        title = soup.title.string.strip() if soup.title else None
        desc, thumb, keywords = '', None, []

        for tag in soup.find_all("meta"):
            name, prop = tag.get("name", "").lower(), tag.get("property", "").lower()
            content = tag.get("content", "")
            if name in ["description", "og:description"] or prop in ["description", "og:description"]:
                desc = content
            if name == "keywords":
                keywords += [t.strip() for t in content.split(",") if t.strip()]
            if prop == "article:tag":
                keywords.append(content.strip())
            if prop in ["og:image", "twitter:image"]:
                thumb = content.strip()

        return {
            "title": title,
            "description": desc,
            "thumbnail": thumb,
            "tags": list(set(keywords))
        }
    except Exception as e:
        print(f"[!] Preview fetch failed for {url}: {e}")
        return {}

def save_thumbnail(url, folder):
    if not url:
        return None
    try:
        os.makedirs(folder, exist_ok=True)
        fname = hashlib.md5(url.encode()).hexdigest() + os.path.splitext(urlparse(url).path)[-1]
        fpath = os.path.join(folder, fname)
        if not os.path.exists(fpath):
            img = requests.get(url, headers=HEADERS, timeout=10)
            with open(fpath, 'wb') as f:
                f.write(img.content)
        return fpath
    except Exception as e:
        print(f"[!] Thumbnail download failed: {e}")
        return None

def write_yaml_list(key, values):
    lines = [f"{key}:"]
    for v in values:
        lines.append(f"  - \"{v}\"")
    return "\n".join(lines)

def process_bookmark(tag, path):
    href = tag.get("href")
    if not href:
        return
    name = tag.get_text().strip() or tldextract.extract(href).domain
    print(">>       Bookmark: " + name)
    add_date = tag.get("add_date")
    last_modified = tag.get("last_modified")

    page_data = fetch_preview(href)
    title = page_data.get("title") or name
    description = page_data.get("description", "")
    tags = page_data.get("tags", [])
    thumbnail = save_thumbnail(page_data.get("thumbnail"), os.path.join(path, THUMB_FOLDER))

    safe_title = sanitize_filename(title)
    md_file = ensure_unique_filename(path, safe_title)

    frontmatter = {
        'id': str(uuid.uuid4()),
        'title': title,
        'url': href,
        'created': to_iso(add_date),
        'modified': to_iso(last_modified)
    }

    with open(md_file, 'w', encoding='utf-8') as f:
        f.write('---\n')
        for k, v in frontmatter.items():
            if v:
                f.write(f'{k}: "{v}"\n')
        if tags:
            f.write(write_yaml_list('tags', tags) + '\n')
        f.write('---\n\n')
        if thumbnail:
            rel_thumb = os.path.relpath(thumbnail, start=path)
            f.write(f'![thumbnail]({rel_thumb})\n\n')
        if description:
            f.write(md(description) + '\n')

def process_node(node, path):
    folder_to_enter = None
    for tag in node:
        if tag.name == "h3":
            folder_to_enter = sanitize_filename(tag.get_text())
            print(">> Folder: " + folder_to_enter)

        elif tag.name == "dl":
            if folder_to_enter:
                new_path = os.path.join(path, folder_to_enter)
                os.makedirs(new_path, exist_ok=True)
                process_node(tag.children, new_path)
                folder_to_enter = None  # Reset after using
            else:
                # orphan <dl> without folder label — recurse in place
                process_node(tag.children, path)

        elif tag.name == "a":
            process_bookmark(tag, path)

        elif tag.name == "dt":
            # descend into contents of <DT>, if any
            process_node(tag.children, path)


def main():
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    with open(BOOKMARKS_FILE, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')
    root = soup.find("dl")
    process_node(root.children, OUTPUT_FOLDER)
    print(f"[✓] Markdown files created in: {OUTPUT_FOLDER}")

if __name__ == "__main__":
    main()

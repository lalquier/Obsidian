import os
import re
import json
import hashlib
import requests
import tqdm
from datetime import datetime
from urllib.parse import urlparse
from bs4 import BeautifulSoup

# NLTK
try:
    from nltk.corpus import stopwords
    from nltk.tokenize import word_tokenize
    import nltk
    stop_words = set(stopwords.words("english"))
except LookupError:
    import nltk
    nltk.download("punkt")
    nltk.download("stopwords")
    from nltk.corpus import stopwords
    from nltk.tokenize import word_tokenize
    stop_words = set(stopwords.words("english"))

# === CONFIG ===
folder_path = "E:\\Documents\\Local Files\\_Wiki\\HomeNotes\\SharedVault\\_Pocket"  # ← CHANGE THIS
cache_folder = os.path.join(folder_path, "..\\__resources\\preview_cache")
thumb_folder = os.path.join(cache_folder, "..\\__resources\\thumbnails")
os.makedirs(thumb_folder, exist_ok=True)

TAG_MAP = {
    "py": "python",
    "ai": "artificial-intelligence",
    "ml": "machine-learning",
    "js": "javascript",
    "dev": "development",
    "howto": "guide",
    "todo": "task",
    "cli": "command-line",
    "ux": "user-experience",
}

# === Regex Patterns ===
timestamp_line_pattern = re.compile(r'(^date_added:\s*|^- \*\*Date Added\*\*:\s*)(\d{10})', re.MULTILINE)
url_body_pattern = re.compile(r'- \*\*URL\*\*: \[(.+?)\]\((.+?)\)')
title_line_pattern = re.compile(r'^title:\s*(.+)', re.MULTILINE)
frontmatter_block_pattern = re.compile(r'^---\s*.*?---\s*', re.DOTALL | re.MULTILINE)

# === Utility Functions ===
def convert_timestamp(ts):
    return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%dT%H:%M:%SZ")

def current_utc_iso():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

def hash_string(s):
    return hashlib.md5(s.encode('utf-8')).hexdigest()

def slugify(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')

def sanitize_yaml_string(s):
    escaped = s.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'

def url_to_cache_path(url):
    return os.path.join(cache_folder, f"{hash_string(url)}.json")

def download_thumbnail(url):
    try:
        if not url:
            return None
        ext = os.path.splitext(urlparse(url).path)[1].lower()
        if ext not in ['.jpg', '.jpeg', '.png', '.webp']:
            ext = '.jpg'
        local_name = hash_string(url) + ext
        local_path = os.path.join(thumb_folder, local_name)
        if not os.path.exists(local_path):
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, timeout=5, headers=headers)
            with open(local_path, "wb") as f:
                f.write(r.content)
        return os.path.relpath(local_path, folder_path).replace("\\", "/")
    except Exception:
        return None

def extract_meta_keywords(soup):
    tag = soup.find("meta", attrs={"name": "keywords"})
    if tag and "content" in tag.attrs:
        return [kw.strip().lower() for kw in tag["content"].split(',') if kw.strip()]
    return []

def extract_tags_from_text(text, max_tags=5):
    if not text:
        return []
    try:
        words = word_tokenize(text.lower())
        filtered = [w for w in words if w.isalpha() and w not in stop_words]
        freq = {}
        for word in filtered:
            freq[word] = freq.get(word, 0) + 1
        sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, _ in sorted_words[:max_tags]]
    except Exception:
        return []

def normalize_tags(tags):
    normalized = []
    seen = set()
    for tag in tags:
        norm = TAG_MAP.get(tag.lower(), tag.lower())
        if norm not in seen:
            normalized.append(norm)
            seen.add(norm)
    return normalized

def fetch_preview(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, timeout=5, headers=headers)
        soup = BeautifulSoup(r.text, "html.parser")

        title = soup.title.string.strip() if soup.title else "No title found"

        desc = soup.find("meta", attrs={"name": "description"})
        og_desc = soup.find("meta", attrs={"property": "og:description"})
        description = (
            desc["content"].strip() if desc and "content" in desc.attrs else
            og_desc["content"].strip() if og_desc and "content" in og_desc.attrs else
            "No description available"
        )

        og_img = soup.find("meta", attrs={"property": "og:image"})
        thumb_url = og_img["content"].strip() if og_img and "content" in og_img.attrs else None
        thumb_path = download_thumbnail(thumb_url) if thumb_url else None

        return {
            "title": title,
            "description": description,
            "thumbnail": thumb_path,
            "original_thumbnail_url": thumb_url,
            "meta_keywords": extract_meta_keywords(soup)
        }
    except Exception as e:
        return {
            "title": "Preview unavailable",
            "description": f"Error fetching preview: {e}",
            "thumbnail": None,
            "original_thumbnail_url": None,
            "meta_keywords": []
        }

def fetch_or_load_preview(url):
    cache_path = url_to_cache_path(url)
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    preview = fetch_preview(url)
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(preview, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return preview

# === MAIN ===
for filename in tqdm.tqdm(os.listdir(folder_path)):
    if filename.endswith(".md"):
        file_path = os.path.join(folder_path, filename)
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Parse title
        title_match = title_line_pattern.search(content)
        title = title_match.group(1).strip() if title_match else "Untitled"
        safe_title = sanitize_yaml_string(title)
        slug = slugify(title)

        # Parse timestamp
        timestamp_match = timestamp_line_pattern.search(content)
        raw_ts = timestamp_match.group(2) if timestamp_match else str(int(datetime.now().timestamp()))
        created_ts = convert_timestamp(raw_ts)
        modified_ts = current_utc_iso()

        # Parse URL and preview
        url_match = url_body_pattern.search(content)
        url = url_match.group(2) if url_match else ""
        preview = fetch_or_load_preview(url) if url else {}

        # Tags
        meta_tags = preview.get("meta_keywords", [])
        extracted_tags = extract_tags_from_text(preview.get("description", ""))
        all_tags = normalize_tags(meta_tags + extracted_tags)

        # Build frontmatter
        frontmatter = {
            "title": title,
            "aliases": [title],
            "id": f"{raw_ts}-{slug}",
            "type": "webclip",
            "context": "article",
            "source": url,
            "tags": all_tags,
            "created": created_ts,
            "modified": modified_ts,
        }
        if preview.get("thumbnail"):
            frontmatter["preview_image"] = preview["thumbnail"]

        yaml_lines = ["---"]
        for k, v in frontmatter.items():
            if isinstance(v, list):
                yaml_lines.append(f"{k}: [{', '.join(v)}]")
            else:
                yaml_lines.append(f"{k}: {sanitize_yaml_string(str(v))}")
        yaml_lines.append("---")

        # Replace or insert frontmatter
        if frontmatter_block_pattern.search(content):
            content = frontmatter_block_pattern.sub("\n".join(yaml_lines), content)
        else:
            content = "\n".join(yaml_lines) + "\n" + content

        # Fix timestamps
        content = timestamp_line_pattern.sub(
            lambda m: f"{m.group(1)}{convert_timestamp(m.group(2))}",
            content
        )

        # Build preview block (for body)
        preview_block = "\n## Preview\n"
        if preview.get("thumbnail"):
            preview_block += f"\n![Preview thumbnail]({preview['thumbnail']})\n"
        preview_block += (
            f"\n**Page Title**: {preview.get('title', 'N/A')}\n"
            f"**Description**: {preview.get('description', 'N/A')}\n"
        )

        # Replace existing preview or append it
        if "## Preview" in content:
            content = re.sub(r'## Preview.*?(?=\n#|\Z)', preview_block, content, flags=re.DOTALL)
        else:
            content += "\n\n" + preview_block

        # Save new content
        new_filename = f"{slug}.md"
        new_path = os.path.join(folder_path, new_filename)

        with open(new_path, "w", encoding="utf-8") as f:
            f.write(content)

        # Rename file if necessary
        if new_filename != filename:
            os.remove(file_path)

print("✅ Markdown files updated: frontmatter synced, tags normalized, filenames matched.")

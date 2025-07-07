import os
import re
from pathlib import Path
import yaml
 
import argparse 
import sys
from ruamel.yaml import YAML
from ruamel.yaml.parser import ParserError

# CONFIGURATION 
video_tag = "#video"
index_mode = True  # ✅ Set to False to apply tagging instead of creating index

# Common video domains
video_domains = [
    "youtube.com", "youtu.be",
    "vimeo.com",
    "dailymotion.com",
    "twitch.tv",
    "facebook.com/watch",
    "video.google.com",
]

# Regex to find markdown or raw links
video_url_pattern = re.compile(r"https?://[^\s\]]+")
valid_url_pattern = re.compile(r'^https?://[^\s\'"()<>]+$')

# Store index results
video_index = []

# --- Load configuration ---
def load_config(config_file):
    yaml = YAML() 
    with open(config_file, 'r', encoding='utf-8') as f:
        return yaml.load(f)

def is_video_url(url):
    return any(domain in url for domain in video_domains)

def extract_note_title(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        if lines and lines[0].strip() == "---":
            yaml_lines = []
            for line in lines[1:]:
                if line.strip() == "---":
                    break
                yaml_lines.append(line)

            yaml_data = yaml.safe_load("".join(yaml_lines))
            if isinstance(yaml_data, dict) and "title" in yaml_data:
                return str(yaml_data["title"])

        # fallback to file name
        return filepath.stem
    except Exception as e:
        print(f"⚠️ Error reading {filepath}: {e}")
        return filepath.stem

def process_file(vault_path, filepath):
    print(filepath)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    video_links = [url for url in video_url_pattern.findall(content) if is_video_url(url)]
    if not video_links:
        return

    if index_mode:
        note_title = extract_note_title(filepath)
        rel_path = filepath.relative_to(vault_path)
        video_index.append((note_title, str(rel_path), video_links))
    else:
        if video_tag not in content:
            content += f"\n\n{video_tag}"
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Tagged: {filepath}")

def create_index_file(vault_path):
    print(">> Creating index")
    index_path = os.path.join(vault_path, "VideosWatchlist.md")
    with open(index_path, 'w+', encoding='utf-8') as f:
        f.write("# 📺 Index of Notes with Video Links\n\n")
        for title, rel_path, links in video_index:
            if rel_path != 'VideosWatchlist.md':
                rel_path = rel_path.replace("\\","/")
                f.write(f"## [[{rel_path}|{title}]]\n")

                # Clean and normalize links
                cleaned_links = []
                for link in links:
                    link = link.strip().replace("\n", "").replace(")", "").replace("(", "").replace('"', '').replace("'", "").replace('>', "").replace('**', "")
                    if valid_url_pattern.match(link):
                        cleaned_links.append(link)
 
                cleaned_links = [link.replace("https://t.umblr.com/redirect?z=","").replace("http://","https://").strip() for link in cleaned_links]

                unique_links = sorted(set(cleaned_links))  # Deduplicate and sort

                for link in unique_links:
                    print(">> Found link: " + link)
                    f.write(f"```vid\n")
                    f.write(f"{link}\n")
                    f.write(f"```\n")
                f.write("\n")
    print(f"✅ Created index at: {index_path}")


def process_vault(config):
    vault_path = config['vault_path'] 

    # print(vault_path)

    # Traverse vault
    for root, _, files in os.walk(vault_path):
        for file in files:
            if file.endswith(".md"):
                process_file(vault_path, Path(root) / file)

    if index_mode:
        create_index_file(vault_path)

# --- Entry point ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fix YAML frontmatter in Obsidian notes.")
    parser.add_argument("--config", default="_config.yaml", help="Path to YAML config file")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
        process_vault(config)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
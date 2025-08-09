#!/usr/bin/env python3
"""
export_chatgpt_conversations_to_obsidian.py

Usage:
  python export_chatgpt_conversations_to_obsidian.py /path/to/conversations.json /path/to/ChatGPT-Conversations.md
"""

import os
import sys 
import json

from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from ruamel.yaml import YAML
from ruamel.yaml.parser import ParserError
import argparse 

CHAT_URL_PREFIX = "https://chatgpt.com/c/"  # required "new column" based on ID

# --- Load configuration ---
def load_config(config_file):
    yaml = YAML() 
    with open(config_file, 'r', encoding='utf-8') as f:
        return yaml.load(f)
    
def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def parse_datetime(dt: Any) -> Optional[datetime]:
    """
    Tries hard to parse a date from ChatGPT export variants:
    - UNIX seconds (int/float)
    - ISO strings
    - None -> returns None
    """
    if dt is None:
        return None
    # numeric epoch seconds?
    if isinstance(dt, (int, float)):
        try:
            return datetime.fromtimestamp(dt, tz=timezone.utc)
        except Exception:
            pass
    # string ISO?
    if isinstance(dt, str):
        # Attempt a few common patterns
        for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ",
                    "%Y-%m-%dT%H:%M:%SZ",
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d"):
            try:
                d = datetime.strptime(dt, fmt)
                # assume UTC if naive
                if d.tzinfo is None:
                    d = d.replace(tzinfo=timezone.utc)
                return d.astimezone(timezone.utc)
            except ValueError:
                continue
        # last resort: fromisoformat (handles many variants, may be naive)
        try:
            d = datetime.fromisoformat(dt)
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return d.astimezone(timezone.utc)
        except Exception:
            return None
    return None


def safe_get(d: Dict[str, Any], *keys: str, default=None):
    for k in keys:
        if isinstance(d, dict) and k in d:
            d = d[k]
        else:
            return default
    return d


def extract_conversations(root: Any) -> Iterable[Dict[str, Any]]:
    """
    ChatGPT exports have used multiple shapes over time.
    We try a few:
    - List of conversation dicts
    - Dict with 'conversations' key
    """
    if isinstance(root, list):
        for item in root:
            if isinstance(item, dict):
                yield item
    elif isinstance(root, dict):
        # common shape: {"conversations": [...]}
        convs = root.get("conversations")
        if isinstance(convs, list):
            for item in convs:
                if isinstance(item, dict):
                    yield item
        else:
            # maybe it's just a single conversation dict container—try best-effort
            yield root


def get_conv_fields(conv: Dict[str, Any]) -> Tuple[Optional[str], str, Optional[datetime]]:
    """
    Returns (id, title, created_dt)

    Tries multiple keys for resilience:
    - id: 'id' | 'conversation_id' | 'conversationId'
    - title: 'title' | nested 'conversation.title'
    - created: 'create_time' | 'createTime' | 'created' | 'update_time' | 'updateTime'
    """
    # id
    conv_id = (
        conv.get("id")
        or conv.get("conversation_id")
        or conv.get("conversationId")
        or safe_get(conv, "conversation", "id")
    )
    if conv_id is not None:
        conv_id = str(conv_id)

    # title
    title = (
        conv.get("title")
        or safe_get(conv, "conversation", "title")
        or "Untitled Conversation"
    )
    if not isinstance(title, str):
        title = str(title)

    # created/updated
    dt_raw = (
        conv.get("create_time")
        or conv.get("createTime")
        or conv.get("created")
        or conv.get("update_time")
        or conv.get("updateTime")
        or safe_get(conv, "conversation", "create_time")
        or safe_get(conv, "conversation", "createTime")
        or safe_get(conv, "conversation", "update_time")
        or safe_get(conv, "conversation", "updateTime")
    )
    created_dt = parse_datetime(dt_raw)

    return conv_id, title, created_dt


def escape_md_pipes(text: str) -> str:
    return text.replace("|", r"\|")


def format_dt_for_table(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    # ISO, local-ish readable; keep UTC for determinism
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def build_markdown(rows: List[Dict[str, str]], title: str) -> str:
    now = datetime.now(timezone.utc)
    frontmatter = [
        "---",
        f'title: "{title}"',
        "type: index",
        "source: chatgpt_export",
        f"created: {now.strftime('%Y-%m-%d')}",
        f"updated: {now.strftime('%Y-%m-%d')}",
        "tags: [index, chatgpt, conversations]",
        "---",
        "",
        "# ChatGPT Conversations",
        "",
        "> This file was generated from `conversations.json`.",
        "",
    ]

    # Markdown table for Dataview friendliness
    # header = "| Date | Title | URL | ID |"
    # sep = "|---|---|---|---|"
    # lines = [header, sep]
    lines = []
    for r in rows:
        lines.append(
            f"- [ ] {r['date']} - [{escape_md_pipes(r['title'])}]({r['url']})"
        )

    return "\n".join(frontmatter + lines) + "\n"


def main(config: Dict[str, Any]) -> None: 
    vault_path = config.get('vault_path', '.') # e.g. "/path/to/ObsidianVault"
    if not vault_path:
        print("Vault path is not set in the config.")
        sys.exit(1)
        
    chat_gpt_dump_path = Path(config.get('chat_gpt_dump_path', 'ChatGPT-Discussions.json'))
    if not chat_gpt_dump_path:
        print("ChatGPT dump path is not set.")
        sys.exit(1) 

    print(f"Loading ChatGPT conversations from {chat_gpt_dump_path}")
    data = load_json(Path(chat_gpt_dump_path))

    # Extract and normalize rows
    extracted: List[Tuple[Optional[str], str, Optional[datetime]]] = []
    for conv in extract_conversations(data):
        conv_id, title, created_dt = get_conv_fields(conv)
        # skip if there's no ID
        if not conv_id:
            continue
        extracted.append((conv_id, title, created_dt))

    # Sort by date desc, then title
    extracted.sort(key=lambda t: (t[2] or datetime.min.replace(tzinfo=timezone.utc), t[1]), reverse=True)

    rows: List[Dict[str, str]] = []
    for conv_id, title, created_dt in extracted:
        url = f"{CHAT_URL_PREFIX}{conv_id}"
        rows.append({
            "id": conv_id,
            "title": title.strip() if title else "Untitled Conversation",
            "date": format_dt_for_table(created_dt),
            "url": url
        })

    md = build_markdown(rows, title="ChatGPT Conversations Index")
 
    index_path = os.path.join(vault_path, "ChatGPT_Conversations_Index.md")
    with open(index_path, 'w+', encoding='utf-8') as f:
        f.write(md)
    print(f"Wrote {len(rows)} conversations to {index_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create an MD note from ChatGPT recovery metadata.")
    parser.add_argument("--config", default="_config.yaml", help="Path to YAML config file") 
    args = parser.parse_args()

    config = load_config(args.config)
    main(config)
    
    # try:
    #     config = load_config(args.config)
    #     main(config)
    # except Exception as e:
    #     print(f"❌ Error: {e}")
    #     sys.exit(1)
  

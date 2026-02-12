#!/usr/bin/env python3
"""Update already-published note.com articles with latest prototype text."""

import json, re, uuid, sys, time
from pathlib import Path

# Reuse from auto_post
sys.path.insert(0, str(Path(__file__).parent))
from note_auto_post import CHAPTERS, extract_chapter, text_to_html, PROTO_DIR, LOGIN_FILE

from curl_cffi import requests as cffi_requests

def login():
    creds = LOGIN_FILE.read_text().strip().split('\n')
    email, password = creds[0], creds[1]
    
    session = cffi_requests.Session(impersonate="chrome")
    
    # Get login page for cookies
    session.get("https://note.com/login", impersonate="chrome")
    
    # Login
    resp = session.post("https://note.com/api/v1/sessions/sign_in", 
        json={"login": email, "password": password},
        headers={
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://note.com",
            "Referer": "https://note.com/login",
        },
        impersonate="chrome"
    )
    assert resp.status_code == 201, f"Login failed: {resp.status_code} {resp.text[:200]}"
    print(f"Login OK")
    return session

def get_note_id(session, key):
    """Get numeric ID from note key"""
    resp = session.get(f"https://note.com/api/v3/notes/{key}",
        headers={"Origin": "https://note.com"},
        impersonate="chrome"
    )
    if resp.status_code != 200:
        print(f"Failed to get note {key}: {resp.status_code}")
        return None, None
    data = resp.json()["data"]
    return data["id"], data["name"]

def update_note(session, note_key, ch_idx):
    """Update a published note with latest chapter text"""
    # Get numeric ID
    note_id, current_title = get_note_id(session, note_key)
    if not note_id:
        return False
    
    # Extract latest text
    ch_info = CHAPTERS[ch_idx]
    text = extract_chapter(ch_info)
    if not text:
        print(f"Failed to extract chapter {ch_idx}")
        return False
    
    html_body = text_to_html(text)
    body_length = len(text)
    title = ch_info["title"]
    
    # PUT update
    resp = session.put(f"https://note.com/api/v1/text_notes/{note_id}",
        json={
            "free_body": html_body,
            "status": "published",
            "name": title,
            "body_length": body_length,
            "price": 0,
        },
        headers={
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://editor.note.com",
            "Referer": "https://editor.note.com/",
        },
        impersonate="chrome"
    )
    print(f"Update {note_key} (id={note_id}): {resp.status_code}")
    if resp.status_code == 200:
        print(f"  Title: {title}")
        print(f"  Body length: {body_length}")
        return True
    else:
        print(f"  Error: {resp.text[:200]}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python note_update.py <note_key> <chapter_index>")
        print("  e.g. python note_update.py nc8b3c9695481 0  # update 序章")
        sys.exit(1)
    
    note_key = sys.argv[1]
    ch_idx = int(sys.argv[2])
    
    session = login()
    update_note(session, note_key, ch_idx)

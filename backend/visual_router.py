"""Unified multi-source visual router.

Priority order per scene:
1. Pexels video (vision-scored)
2. Pixabay video (vision-scored)
3. Pexels photo (with Ken Burns) if no good video
4. Wikipedia image (real photos of cities, people, objects)
5. Wikimedia Commons (historical archive — DDR, finance history)
6. Internet Archive (Prelinger, NASA — old footage)
7. FAL Flux (last resort for abstract concepts / infographics)
"""
import os, json, urllib.request, urllib.parse
from pathlib import Path
from typing import Optional

UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'


def search_pexels_video(query: str, api_key: str, limit: int = 5) -> list:
    """Returns list of candidates with thumbnail + download URL."""
    url = f'https://api.pexels.com/videos/search?query={urllib.parse.quote(query)}&per_page={limit}'
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Authorization': api_key})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
        results = []
        for v in d.get('videos', []):
            if v.get('duration', 0) < 4: continue
            # Pick best mp4 landscape
            best = None
            for f in v.get('video_files', []):
                if f.get('file_type') != 'video/mp4': continue
                if f.get('width', 0) < f.get('height', 0): continue
                if not best or f.get('width', 0) > best.get('width', 0):
                    best = f
            if best and best.get('width', 0) >= 640:
                results.append({
                    'source': 'pexels-video',
                    'id': str(v['id']),
                    'thumbnail': v.get('image'),
                    'url': best['link'],
                    'duration': v.get('duration', 0),
                    'width': best.get('width'), 'height': best.get('height')
                })
        return results
    except Exception as e:
        return []


def search_pexels_photo(query: str, api_key: str, limit: int = 5) -> list:
    url = f'https://api.pexels.com/v1/search?query={urllib.parse.quote(query)}&per_page={limit}&orientation=landscape'
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Authorization': api_key})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
        return [{
            'source': 'pexels-photo',
            'id': str(p['id']),
            'thumbnail': p['src'].get('medium'),
            'url': p['src'].get('large2x') or p['src'].get('large'),
            'duration': 0
        } for p in d.get('photos', [])]
    except: return []


def search_pixabay_video(query: str, api_key: str, limit: int = 5) -> list:
    url = f'https://pixabay.com/api/videos/?key={api_key}&q={urllib.parse.quote(query)}&per_page={limit}'
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
        results = []
        for h in d.get('hits', []):
            if h.get('duration', 0) < 4: continue
            vids = h.get('videos', {})
            pick = vids.get('large') or vids.get('medium') or vids.get('small')
            if pick and pick.get('url'):
                results.append({
                    'source': 'pixabay-video',
                    'id': str(h.get('id')),
                    'thumbnail': None,
                    'url': pick['url'],
                    'duration': h.get('duration', 0)
                })
        return results
    except: return []


# Поиск Commons отдаёт ЛЮБЫЕ файлы (PDF/DjVu-сканы документов, тестовые
# мишени), а Special:FilePath рендерит первую страницу PDF как картинку —
# так в видео попал скан сенатского документа вместо заголовка FT.
_WIKIMEDIA_OK_EXT = ('.jpg', '.jpeg', '.png')
_WIKIMEDIA_JUNK = ('scan', 'page_', '_page', 'document', 'test_pattern',
                   'color_target', 'chart_', 'specimen', 'manuscript')


def search_wikipedia_image(query: str, limit: int = 3) -> list:
    """Search Wikimedia Commons for relevant images. Free, no API key."""
    url = f'https://commons.wikimedia.org/w/api.php?action=query&list=search&srnamespace=6&srsearch={urllib.parse.quote(query)}&srlimit={limit * 3}&format=json'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 Bot/1.0'})
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
        results = []
        for item in d.get('query', {}).get('search', []):
            fn = item['title'].replace('File:','').replace(' ','_')
            low = fn.lower()
            if not low.endswith(_WIKIMEDIA_OK_EXT):
                continue
            if any(j in low for j in _WIKIMEDIA_JUNK):
                continue
            fn_enc = urllib.parse.quote(fn)
            results.append({
                'source': 'wikimedia',
                'id': fn,
                'thumbnail': f'https://commons.wikimedia.org/wiki/Special:FilePath/{fn_enc}?width=320',
                'url': f'https://commons.wikimedia.org/wiki/Special:FilePath/{fn_enc}?width=1920',
                'duration': 0
            })
            if len(results) >= limit:
                break
        return results
    except: return []


def search_archive_org(query: str, mediatype: str = 'movies', limit: int = 3) -> list:
    """Search Internet Archive for historical footage. Free, no API key."""
    url = f'https://archive.org/advancedsearch.php?q=mediatype:{mediatype}+AND+({urllib.parse.quote(query)})&fl=identifier,title&rows={limit}&output=json'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
        results = []
        for doc in d.get('response', {}).get('docs', []):
            ident = doc.get('identifier','')
            results.append({
                'source': 'archive-org',
                'id': ident,
                'thumbnail': f'https://archive.org/services/img/{ident}',
                'url': f'https://archive.org/download/{ident}/{ident}.mp4',  # heuristic
                'duration': 0
            })
        return results
    except: return []


def collect_candidates(query: str, visual_type: str = 'video', max_per_source: int = 3) -> list:
    """Walk through all sources, return combined candidate list."""
    candidates = []
    
    pexels = os.environ.get('PEXELS_API_KEY','')
    pixabay = os.environ.get('PIXABAY_API_KEY','')
    
    if visual_type in ('video','any'):
        if pexels: candidates.extend(search_pexels_video(query, pexels, max_per_source))
        if pixabay: candidates.extend(search_pixabay_video(query, pixabay, max_per_source))
    
    if visual_type in ('photo','any') or len(candidates) < 2:
        if pexels: candidates.extend(search_pexels_photo(query, pexels, max_per_source))
    
    if visual_type == 'archive' or visual_type == 'historical':
        candidates.extend(search_wikipedia_image(query, max_per_source))
        candidates.extend(search_archive_org(query, 'movies', max_per_source))
    
    return candidates

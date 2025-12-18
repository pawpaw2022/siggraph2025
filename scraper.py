"""
SIGGRAPH Asia 2025 Technical Papers Scraper
Fetches paper titles, authors, and thumbnails from the conference schedule.
"""

import re
import json
from pathlib import Path
from urllib.request import urlopen, Request
from collections import defaultdict
from html import unescape, escape as html_escape

URLS_JSON_PATH = Path("url.json")


def _load_existing_meta():
    """
    Load existing url.json if present.

    Expected formats:
    - list of {id, title, session, url, abstract?}
    - dict of {id: {url, abstract, ...}}
    """
    if not URLS_JSON_PATH.exists():
        return {}

    try:
        with open(URLS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}

    meta_map = {}
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            pid = item.get("id")
            url = item.get("url", "")
            abstract = item.get("abstract", "")
            if isinstance(pid, str):
                meta_map[pid] = {
                    "url": url if isinstance(url, str) else "",
                    "abstract": abstract if isinstance(abstract, str) else "",
                }
    elif isinstance(data, dict):
        for pid, item in data.items():
            if isinstance(pid, str) and isinstance(item, dict):
                url = item.get("url", "")
                abstract = item.get("abstract", "")
                meta_map[pid] = {
                    "url": url if isinstance(url, str) else "",
                    "abstract": abstract if isinstance(abstract, str) else "",
                }
    return meta_map


def write_urls_json(papers_by_session):
    """
    Write url.json scaffold for all papers.

    - Keeps any existing non-empty urls already in url.json.
    - Output format is a list for easy manual editing.
    """
    existing = _load_existing_meta()

    entries = []
    for session_name, papers in papers_by_session.items():
        for paper in papers:
            pid = f"papers_{paper['id']}"
            prev = existing.get(pid, {})
            entries.append(
                {
                    "id": pid,
                    "title": paper["title"],
                    "session": session_name,
                    "url": (prev.get("url") or ""),
                    "abstract": (prev.get("abstract") or ""),
                }
            )

    with open(URLS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

    empty_count = sum(1 for e in entries if not e.get("url"))
    print(f"Wrote {URLS_JSON_PATH} ({len(entries)} entries, {empty_count} empty urls)")


def load_urls_for_html():
    """Return mapping papers_#### -> url (non-empty only)."""
    meta_map = _load_existing_meta()
    out = {}
    for pid, meta in meta_map.items():
        url = (meta or {}).get("url", "")
        if isinstance(url, str) and url.strip():
            out[pid] = url.strip()
    return out


def load_abstracts_for_html():
    """Return mapping papers_#### -> abstract (may be empty; we only include non-empty)."""
    meta_map = _load_existing_meta()
    out = {}
    for pid, meta in meta_map.items():
        abstract = (meta or {}).get("abstract", "")
        if isinstance(abstract, str) and abstract.strip():
            out[pid] = abstract.strip()
    return out


# Conference dates to fetch
DATES = [
    "2025-12-13",
    "2025-12-14", 
    "2025-12-15",
    "2025-12-16",
    "2025-12-17",
    "2025-12-18",
    "2025-12-19",
]

BASE_URL = "https://sa2025.conference-schedule.org/wp-content/linklings_snippets/wp_program_view_all_{date}.txt"
IMAGE_BASE = "https://sa2025.conference-schedule.org"


def fetch_schedule_data():
    """Fetch schedule data from all conference days."""
    all_html = ""
    
    for date in DATES:
        url = BASE_URL.format(date=date)
        print(f"Fetching {date}...")
        try:
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urlopen(req, timeout=30) as response:
                content = response.read().decode('utf-8')
                all_html += content
                print(f"  Got {len(content):,} characters")
        except Exception as e:
            print(f"  Error fetching {date}: {e}")
            
    return all_html


def extract_technical_papers(html_content):
    """Extract Technical Papers from the HTML content."""
    
    papers = []
    seen_titles = set()
    
    # Papers have this structure:
    # <td class="representative-image-td">...<img class="representative-img" src="...">...</td>
    # <td class="title-speakers-td">
    #   <a href="...id=papers_XXXX&sess=sessYYY">Paper Title</a>
    #   <div class="presenter-name"><a>Author</a></div>
    # </td>
    
    paper_pattern = r'<td class="representative-image-td">(.*?)</td>\s*<td class="title-speakers-td">(.*?)</td>'
    
    for match in re.finditer(paper_pattern, html_content, re.DOTALL):
        img_content = match.group(1)
        title_content = match.group(2)
        
        # Extract paper ID, session ID, and title from the link
        link_match = re.search(
            r'href="[^"]*id=papers_(\d+)&sess=(sess\d+)"[^>]*>([^<]+)</a>',
            title_content
        )
        if not link_match:
            continue
        
        paper_id = link_match.group(1)
        session_id = link_match.group(2)
        title = unescape(link_match.group(3).strip())
        
        # Skip duplicates
        if title in seen_titles:
            continue
        seen_titles.add(title)
        
        # Extract image
        img_match = re.search(r'representative-img"[^>]*src="([^"]+)"', img_content)
        image = None
        if img_match:
            image = img_match.group(1)
            if image.startswith('/'):
                image = IMAGE_BASE + image
        
        # Extract authors
        authors = re.findall(
            r'<div class="presenter-name"[^>]*>.*?<a[^>]*>([^<]+)</a>',
            title_content,
            re.DOTALL
        )
        authors = [unescape(a.strip()) for a in authors]
        
        papers.append({
            'id': paper_id,
            'session_id': session_id,
            'title': title,
            'authors': authors,
            'image': image,
        })
    
    return papers


def group_papers_by_session(papers):
    """Group papers by session, using actual session topic names."""
    
    # Session ID to topic name mapping (from SIGGRAPH Asia 2025 schedule)
    SESSION_NAMES = {
        # Monday, December 15
        "sess104": "3D Reconstruction & Intelligent Geometry",
        "sess105": "Dynamic Generative Video: From Synthesis to Real-Time Editing",
        "sess106": "Global Illumination & Real-Time Rendering",
        "sess107": "High-Performance Simulation Algorithms",
        "sess108": "Mesh Processing",
        "sess109": "Camera Control and Directed Storytelling in Video Generation",
        "sess110": "Material & Texture Modeling",
        "sess111": "Neural & Implicit Representations for Geometry and Physics",
        "sess112": "Creating Digital Humans",
        "sess113": "Smart Process Planning for Manufacturing",
        "sess114": "Visibility & Real-Time Rendering",
        "sess115": "Physically Based Simulation & Dynamic Environments",
        
        # Tuesday, December 16
        "sess116": "Audio-Driven Facial and Portrait Animation",
        "sess117": "Computational Design & Fabricability",
        "sess118": "Computational Photography & Cameras",
        "sess119": "Sampling, Reconstruction & Variance Reduction",
        "sess120": "Generative 3D Shape Synthesis",
        "sess121": "Image Restoration, Editing & Enhancement",
        "sess122": "Differentiable Rendering & Applications",
        "sess123": "Perception and Performance in AR/VR Systems",
        "sess124": "4D Gaussian Splatting for Dynamic Scene Reconstruction",
        "sess125": "Garment & Cloth Modeling, Simulation and Rendering",
        "sess126": "3D Reconstruction & Rendering",
        "sess127": "Animation, Simulation & Deformation",
        "sess128": "Neural Fields and Surface Reconstruction",
        "sess129": "Vector Graphics & Sketches",
        "sess130": "Intelligent CAD: B-Reps, NURBs & Splines",
        "sess131": "It's All About the Motion",
        
        # Wednesday, December 17
        "sess132": "Compositional and Layout-Guided Image Synthesis",
        "sess133": "Computational Design & Geometry",
        "sess134": "Hair & Faces",
        "sess135": "Differentiable Physics and Fabrication-Aware Optimization",
        "sess136": "Generative Scenes & Panoramas",
        "sess137": "Human & Robot Animation & Behavior",
        "sess138": "4D & Dynamic Scene Generation and Reconstruction",
        "sess139": "Advanced Light Transport & PDE Solvers",
        "sess140": "Efficient and Robust Algorithms for Geometric Computing",
        "sess141": "3D Reconstruction & View Synthesis",
        "sess142": "Animating Images, Sketches and Text",
        "sess143": "Real-Time Rendering & System Optimization",
        "sess144": "Cameras, Sensors, and Acquisition",
        "sess145": "Generative 3D Modeling",
        "sess146": "Motion Transfer & Control",
        
        # Thursday, December 18
        "sess147": "Advanced Fluid and Multiphase Simulation",
        "sess148": "Material & Reflectance Modeling",
        "sess149": "Objects in Parts & Articulation",
        "sess150": "Text-to-Image & Customization",
        "sess151": "Expressive and Structured Gaussian Representations",
        "sess152": "Generative Synthesis, Editing & Customization",
        "sess153": "Human Motion Synthesis & Interaction",
        "sess154": "Shape Abstraction and Structural Analysis",
        "sess155": "Advanced Representations and Rendering for 3D Scenes",
        "sess156": "Diffusion-Based Image Editing & Manipulation",
        "sess159": "Geometry Processing & Representations",
    }
    
    # Group by session ID
    by_session = defaultdict(list)
    for p in papers:
        by_session[p['session_id']].append(p)
    
    # Sort sessions by their numeric ID
    sorted_sessions = sorted(by_session.items(), key=lambda x: int(x[0].replace('sess', '')))
    
    # Create session groups with actual topic names
    result = {}
    misc_papers = []
    
    for session_id, paper_list in sorted_sessions:
        if session_id in SESSION_NAMES:
            session_name = SESSION_NAMES[session_id]
            result[session_name] = paper_list
        elif len(paper_list) >= 3:
            # Fallback for unmapped sessions
            session_num = int(session_id.replace('sess', ''))
            session_name = f"Session {session_num}"
            result[session_name] = paper_list
        else:
            misc_papers.extend(paper_list)
    
    # Add miscellaneous papers if any
    if misc_papers:
        result["Other Papers"] = misc_papers
    
    return result


def generate_html(papers_by_session):
    """Generate HTML output with CSS styling."""
    
    url_map = load_urls_for_html()
    abstract_map = load_abstracts_for_html()
    
    css = '''
:root {
    --bg-primary: #fef9f3;
    --bg-secondary: #fff5eb;
    --bg-card: #ffffff;
    --bg-card-hover: #fff8f0;
    --text-primary: #2d2a3e;
    --text-secondary: #6b6880;
    --accent: #ff6b6b;
    --accent-secondary: #4ecdc4;
    --accent-tertiary: #ffe66d;
    --accent-gradient: linear-gradient(135deg, #ff6b6b 0%, #feca57 50%, #4ecdc4 100%);
    --border: #f0e6dc;
    --shadow: rgba(255, 107, 107, 0.15);
}

@import url('https://fonts.googleapis.com/css2?family=Fredoka:wght@400;500;600;700&family=Nunito:wght@400;500;600;700&display=swap');

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

html {
    scroll-behavior: smooth;
}

body {
    font-family: 'Nunito', -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    line-height: 1.7;
    min-height: 100vh;
    font-size: 17px;
}

.bg-pattern {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-image: 
        radial-gradient(circle at 10% 20%, rgba(255, 107, 107, 0.12) 0%, transparent 50%),
        radial-gradient(circle at 90% 80%, rgba(78, 205, 196, 0.1) 0%, transparent 50%),
        radial-gradient(circle at 50% 50%, rgba(255, 230, 109, 0.08) 0%, transparent 60%);
    pointer-events: none;
    z-index: 0;
}

.container {
    max-width: 1500px;
    margin: 0 auto;
    padding: 2rem;
    position: relative;
    z-index: 1;
}

header {
    text-align: center;
    padding: 5rem 2rem 4rem;
    position: relative;
}

header::before {
    content: '';
    position: absolute;
    top: -50px;
    left: 50%;
    transform: translateX(-50%);
    width: 500px;
    height: 500px;
    background: radial-gradient(ellipse at center, rgba(255, 230, 109, 0.25) 0%, transparent 70%);
    pointer-events: none;
    border-radius: 50%;
}

.logo {
    font-family: 'Fredoka', sans-serif;
    font-size: 1rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--accent);
    margin-bottom: 1.5rem;
    font-weight: 600;
}

header h1 {
    font-family: 'Fredoka', sans-serif;
    font-size: 4.5rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    background: var(--accent-gradient);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 0.75rem;
    line-height: 1.1;
}

header .subtitle {
    font-family: 'Fredoka', sans-serif;
    font-size: 1.6rem;
    font-weight: 500;
    color: var(--text-secondary);
    margin-bottom: 2rem;
}

.meta-info {
    display: inline-flex;
    align-items: center;
    gap: 2rem;
    padding: 1rem 2rem;
    background: var(--bg-card);
    border: 2px solid var(--border);
    border-radius: 100px;
    font-size: 1rem;
    box-shadow: 0 4px 20px var(--shadow);
}

.meta-info span {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--text-secondary);
    font-weight: 600;
}

.meta-info .icon {
    font-size: 1.2rem;
}

.stats-bar {
    display: flex;
    justify-content: center;
    gap: 4rem;
    margin-top: 3rem;
    padding-top: 2rem;
    border-top: 2px dashed var(--border);
}

.stat-item {
    text-align: center;
}

.stat-value {
    font-family: 'Fredoka', sans-serif;
    font-size: 3.5rem;
    font-weight: 700;
    background: var(--accent-gradient);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1;
}

.stat-label {
    font-size: 0.9rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-secondary);
    margin-top: 0.5rem;
    font-weight: 600;
}

.session {
    margin-bottom: 4rem;
}

.session-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 2rem;
    padding-bottom: 1rem;
    border-bottom: 3px dashed var(--border);
}

.session-header::before {
    content: '✦';
    font-size: 1.5rem;
    color: var(--accent);
}

.session h2 {
    font-family: 'Fredoka', sans-serif;
    font-size: 1.7rem;
    font-weight: 600;
    flex: 1;
    color: var(--text-primary);
}

.session-count {
    font-size: 0.9rem;
    font-weight: 700;
    color: var(--accent);
    background: rgba(255, 107, 107, 0.1);
    padding: 0.5rem 1.2rem;
    border-radius: 100px;
    border: 2px solid rgba(255, 107, 107, 0.2);
}

.papers-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 1.75rem;
}

.paper-card {
    background: var(--bg-card);
    border-radius: 20px;
    overflow: hidden;
    border: 2px solid var(--border);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    display: flex;
    flex-direction: column;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05);
}

.paper-card:hover {
    transform: translateY(-8px) rotate(-0.5deg);
    box-shadow: 
        0 20px 40px rgba(255, 107, 107, 0.15),
        0 0 0 3px rgba(255, 107, 107, 0.1);
    border-color: var(--accent);
}

.thumbnail-wrapper {
    position: relative;
    width: 100%;
    padding-top: 56.25%;
    overflow: hidden;
    background: var(--bg-secondary);
}

.thumbnail {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    transition: transform 0.5s cubic-bezier(0.4, 0, 0.2, 1);
}

.paper-card:hover .thumbnail {
    transform: scale(1.1);
}

.thumbnail.placeholder {
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 3.5rem;
    color: var(--border);
    background: linear-gradient(135deg, var(--bg-secondary) 0%, var(--bg-card) 100%);
}

.card-content {
    padding: 1.5rem;
    flex: 1;
    display: flex;
    flex-direction: column;
}

.paper-card h3 {
    font-family: 'Fredoka', sans-serif;
    font-size: 1.1rem;
    font-weight: 600;
    line-height: 1.4;
    margin-bottom: 0.85rem;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
    color: var(--text-primary);
}

.authors {
    font-size: 0.95rem;
    color: var(--text-secondary);
    line-height: 1.6;
    margin-top: auto;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    font-weight: 500;
}

.paper-title-link {
    color: inherit;
    text-decoration: none;
}

.paper-title-link:hover {
    text-decoration: underline;
    text-decoration-thickness: 3px;
    text-underline-offset: 3px;
    text-decoration-color: rgba(255, 107, 107, 0.7);
}

.paper-actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 1rem;
    padding-top: 1rem;
    border-top: 2px dashed var(--border);
    align-items: center;
    flex-wrap: wrap;
}

.paper-links {
    display: flex;
    gap: 0.5rem;
}

.abstract-toggle {
    margin-top: 0;
    padding-top: 0;
    border-top: none;
}

.abstract-toggle summary {
    list-style: none;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.45rem 0.9rem;
    border-radius: 100px;
    background: rgba(255, 230, 109, 0.25);
    border: 2px solid rgba(255, 230, 109, 0.45);
    font-weight: 800;
    font-size: 0.9rem;
    color: var(--text-primary);
    user-select: none;
}

.abstract-toggle summary::-webkit-details-marker {
    display: none;
}

.abstract-toggle summary:hover {
    transform: scale(1.03);
}

.abstract-toggle .abstract-body {
    margin-top: 0.75rem;
    padding: 0.9rem 1rem;
    background: rgba(78, 205, 196, 0.08);
    border: 2px solid rgba(78, 205, 196, 0.18);
    border-radius: 14px;
    color: var(--text-primary);
    font-size: 0.98rem;
    line-height: 1.7;
    white-space: pre-wrap;
}

.abstract-toggle .abstract-missing {
    opacity: 0.75;
    font-style: italic;
}

.paper-link {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.5rem 1rem;
    border-radius: 100px;
    font-size: 0.85rem;
    font-weight: 800;
    text-decoration: none;
    transition: all 0.2s ease;
    background: rgba(78, 205, 196, 0.12);
    color: #0f766e;
    border: 2px solid rgba(78, 205, 196, 0.35);
    position: relative;
}

.paper-link:hover {
    transform: scale(1.04);
    background: rgba(78, 205, 196, 0.18);
}

.paper-link .edit-icon-inline {
    margin-left: 0.3rem;
    padding: 0.2rem 0.4rem;
    background: rgba(255, 107, 107, 0.2);
    border-radius: 50%;
    font-size: 0.7rem;
    cursor: pointer;
    transition: all 0.2s ease;
    display: inline-flex;
    align-items: center;
    justify-content: center;
}

.paper-link .edit-icon-inline:hover {
    background: rgba(255, 107, 107, 0.35);
    transform: scale(1.15);
}

.edit-btn, .edit-btn-inline {
    background: rgba(255, 107, 107, 0.15);
    border: 2px solid rgba(255, 107, 107, 0.35);
    border-radius: 100px;
    padding: 0.4rem 0.7rem;
    font-size: 0.75rem;
    font-weight: 700;
    color: #c62828;
    cursor: pointer;
    transition: all 0.2s ease;
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    margin-left: 0.3rem;
}

.edit-btn:hover, .edit-btn-inline:hover {
    background: rgba(255, 107, 107, 0.25);
    transform: scale(1.05);
}

.edit-btn-inline {
    margin-left: 0.5rem;
    padding: 0.25rem 0.5rem;
    font-size: 0.7rem;
}

.abstract-toggle summary {
    display: flex;
    align-items: center;
    justify-content: space-between;
}

/* Edit Modal */
.edit-modal {
    display: none;
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.6);
    z-index: 1000;
    align-items: center;
    justify-content: center;
    padding: 2rem;
}

.edit-modal.active {
    display: flex;
}

.edit-modal-content {
    background: var(--bg-card);
    border: 3px solid var(--accent);
    border-radius: 20px;
    padding: 2rem;
    max-width: 600px;
    width: 100%;
    max-height: 80vh;
    overflow-y: auto;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.edit-modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1.5rem;
    padding-bottom: 1rem;
    border-bottom: 2px dashed var(--border);
}

.edit-modal-header h3 {
    font-family: 'Fredoka', sans-serif;
    font-size: 1.3rem;
    color: var(--text-primary);
    margin: 0;
}

.edit-modal-close {
    background: rgba(255, 107, 107, 0.2);
    border: 2px solid rgba(255, 107, 107, 0.4);
    border-radius: 100px;
    width: 2rem;
    height: 2rem;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    font-size: 1.2rem;
    color: var(--accent);
    transition: all 0.2s ease;
}

.edit-modal-close:hover {
    background: rgba(255, 107, 107, 0.3);
    transform: scale(1.1);
}

.edit-modal-body {
    margin-bottom: 1.5rem;
}

.edit-modal-body label {
    display: block;
    font-weight: 700;
    margin-bottom: 0.5rem;
    color: var(--text-primary);
    font-size: 0.9rem;
}

.edit-modal-body input,
.edit-modal-body textarea {
    width: 100%;
    padding: 0.75rem;
    border: 2px solid var(--border);
    border-radius: 12px;
    font-family: 'Nunito', sans-serif;
    font-size: 0.95rem;
    background: var(--bg-secondary);
    color: var(--text-primary);
    resize: vertical;
}

.edit-modal-body textarea {
    min-height: 150px;
    line-height: 1.6;
}

.edit-modal-body input:focus,
.edit-modal-body textarea:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(255, 107, 107, 0.1);
}

.edit-modal-footer {
    display: flex;
    gap: 0.75rem;
    justify-content: flex-end;
}

.edit-modal-btn {
    padding: 0.6rem 1.5rem;
    border-radius: 100px;
    font-weight: 700;
    font-size: 0.9rem;
    cursor: pointer;
    transition: all 0.2s ease;
    border: 2px solid;
}

.edit-modal-btn.save {
    background: rgba(78, 205, 196, 0.2);
    border-color: rgba(78, 205, 196, 0.4);
    color: #0f766e;
}

.edit-modal-btn.save:hover {
    background: rgba(78, 205, 196, 0.3);
    transform: scale(1.05);
}

.edit-modal-btn.cancel {
    background: rgba(255, 107, 107, 0.1);
    border-color: rgba(255, 107, 107, 0.3);
    color: var(--text-secondary);
}

.edit-modal-btn.cancel:hover {
    background: rgba(255, 107, 107, 0.2);
}

.export-btn-container {
    position: fixed;
    bottom: 2rem;
    right: 2rem;
    z-index: 100;
}

.export-btn {
    background: var(--accent-gradient);
    color: white;
    border: none;
    border-radius: 100px;
    padding: 1rem 1.5rem;
    font-family: 'Fredoka', sans-serif;
    font-weight: 700;
    font-size: 0.9rem;
    cursor: pointer;
    box-shadow: 0 4px 20px rgba(255, 107, 107, 0.3);
    transition: all 0.2s ease;
}

.export-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 25px rgba(255, 107, 107, 0.4);
}

footer {
    text-align: center;
    padding: 3rem 2rem;
    margin-top: 2rem;
    border-top: 3px dashed var(--border);
    color: var(--text-secondary);
    font-size: 1rem;
}

footer a {
    color: var(--accent);
    text-decoration: none;
    font-weight: 600;
}

footer a:hover {
    text-decoration: underline;
}

@media (max-width: 768px) {
    header h1 {
        font-size: 2.8rem;
    }
    
    .papers-grid {
        grid-template-columns: 1fr;
    }
    
    .stats-bar {
        gap: 2rem;
    }
    
    .meta-info {
        flex-direction: column;
        gap: 0.75rem;
    }
}
'''
    
    # Count totals
    total_papers = sum(len(papers) for papers in papers_by_session.values())
    total_sessions = len(papers_by_session)
    
    # Generate session HTML
    sessions_html = ""
    
    for session_name, papers in papers_by_session.items():
        papers_html = ""
        for paper in papers:
            # Thumbnail
            if paper.get('image'):
                thumb_html = f'<img class="thumbnail" src="{paper["image"]}" alt="" loading="lazy">'
            else:
                thumb_html = '<div class="thumbnail placeholder">📄</div>'
            
            # Authors
            authors_str = ", ".join(paper.get('authors', [])[:6])
            authors_html = f'<p class="authors">{html_escape(authors_str)}</p>' if authors_str else ''

            pid = f"papers_{paper['id']}"
            paper_url = url_map.get(pid, "").strip()
            paper_abstract = abstract_map.get(pid, "").strip()

            safe_title = html_escape(paper["title"])
            title_html = safe_title
            link_block_html = ""
            if paper_url:
                safe_url = paper_url.replace('"', "%22")
                title_html = f'<a class="paper-title-link" href="{safe_url}" target="_blank" rel="noopener">{safe_title}</a>'
                # Escape for JavaScript: replace quotes and newlines
                js_url = paper_url.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n').replace('\r', '\\r')
                link_block_html = f'''
                    <div class="paper-links">
                        <a class="paper-link" href="{safe_url}" target="_blank" rel="noopener">
                            🔗 Open link
                            <span class="edit-icon-inline" onclick="event.preventDefault(); event.stopPropagation(); openEditModal('{pid}', 'url', '{js_url}')" title="Edit URL">✏️</span>
                        </a>
                    </div>
                '''
            else:
                link_block_html = f'''
                    <div class="paper-links">
                        <button class="edit-btn" onclick="openEditModal('{pid}', 'url', '')" title="Add URL">✏️ Add link</button>
                    </div>
                '''

            if paper_abstract:
                # Escape for JavaScript
                js_abstract = paper_abstract.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n').replace('\r', '\\r')
                abstract_html = f'''
                    <details class="abstract-toggle">
                        <summary>
                            🧻 Abstract
                            <button class="edit-btn-inline" onclick="event.stopPropagation(); openEditModal('{pid}', 'abstract', '{js_abstract}')" title="Edit Abstract">✏️</button>
                        </summary>
                        <div class="abstract-body">{html_escape(paper_abstract)}</div>
                    </details>
                '''
            else:
                abstract_html = f'''
                    <details class="abstract-toggle">
                        <summary>
                            🧻 Abstract
                            <button class="edit-btn-inline" onclick="event.stopPropagation(); openEditModal('{pid}', 'abstract', '')" title="Add Abstract">✏️</button>
                        </summary>
                        <div class="abstract-body abstract-missing">Abstract not available yet (you can paste it into url.json).</div>
                    </details>
                '''
            
            # Combine link and abstract in one container
            actions_html = ""
            if link_block_html or abstract_html:
                actions_html = f'''
                    <div class="paper-actions">
                        {link_block_html}
                        {abstract_html}
                    </div>
                '''
            
            papers_html += f'''
            <article class="paper-card" data-paper-id="{pid}">
                <div class="thumbnail-wrapper">
                    {thumb_html}
                </div>
                <div class="card-content">
                    <h3>{title_html}</h3>
                    {authors_html}
                    {actions_html}
                </div>
            </article>
            '''
        
        sessions_html += f'''
        <section class="session">
            <div class="session-header">
                <h2>{session_name}</h2>
                <span class="session-count">{len(papers)} papers</span>
            </div>
            <div class="papers-grid">
                {papers_html}
            </div>
        </section>
        '''
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SIGGRAPH Asia 2025 - Technical Papers</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🎬</text></svg>">
    <style>
{css}
    </style>
</head>
<body>
    <div class="bg-pattern"></div>
    
    <header>
        <div class="logo">ACM SIGGRAPH</div>
        <h1>SIGGRAPH Asia 2025</h1>
        <p class="subtitle">Technical Papers Collection</p>
        
        <div class="meta-info">
            <span><span class="icon">📍</span> Hong Kong</span>
            <span><span class="icon">📅</span> December 13-19, 2025</span>
        </div>
        
        <div class="stats-bar">
            <div class="stat-item">
                <div class="stat-value">{total_papers}</div>
                <div class="stat-label">Technical Papers</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">{total_sessions}</div>
                <div class="stat-label">Sessions</div>
            </div>
        </div>
    </header>
    
    <main class="container">
        {sessions_html}
    </main>
    
    <footer>
        <p>Data sourced from <a href="https://sa2025.conference-schedule.org/" target="_blank" rel="noopener">SIGGRAPH Asia 2025 Conference Schedule</a></p>
        <p style="margin-top: 0.5rem; opacity: 0.7;">Generated with Python</p>
    </footer>
    
    <!-- Edit Modal -->
    <div id="editModal" class="edit-modal">
        <div class="edit-modal-content">
            <div class="edit-modal-header">
                <h3 id="modalTitle">Edit</h3>
                <button class="edit-modal-close" onclick="closeEditModal()">×</button>
            </div>
            <div class="edit-modal-body">
                <label id="modalLabel" for="editInput">Value:</label>
                <input type="text" id="editInput" style="display: none;">
                <textarea id="editTextarea" style="display: none;"></textarea>
            </div>
            <div class="edit-modal-footer">
                <button class="edit-modal-btn cancel" onclick="closeEditModal()">Cancel</button>
                <button class="edit-modal-btn save" onclick="saveEdit()">Save</button>
            </div>
        </div>
    </div>
    
    <!-- Export Button -->
    <div class="export-btn-container">
        <button class="export-btn" onclick="exportToJson()">📥 Export url.json</button>
    </div>
    
    <script>
        let currentEdit = {{'paperId': null, 'field': null}};
        const editsKey = 'siggraph_paper_edits';
        
        function openEditModal(paperId, field, currentValue) {{
            currentEdit.paperId = paperId;
            currentEdit.field = field;
            
            const modal = document.getElementById('editModal');
            const title = document.getElementById('modalTitle');
            const label = document.getElementById('modalLabel');
            const input = document.getElementById('editInput');
            const textarea = document.getElementById('editTextarea');
            
            if (field === 'url') {{
                title.textContent = 'Edit URL';
                label.textContent = 'URL:';
                input.style.display = 'block';
                textarea.style.display = 'none';
                input.value = currentValue || '';
                input.focus();
            }} else if (field === 'abstract') {{
                title.textContent = 'Edit Abstract';
                label.textContent = 'Abstract:';
                input.style.display = 'none';
                textarea.style.display = 'block';
                textarea.value = currentValue || '';
                textarea.focus();
            }}
            
            modal.classList.add('active');
        }}
        
        function closeEditModal() {{
            document.getElementById('editModal').classList.remove('active');
            currentEdit.paperId = null;
            currentEdit.field = null;
        }}
        
        function saveEdit() {{
            if (!currentEdit.paperId || !currentEdit.field) return;
            
            const input = document.getElementById('editInput');
            const textarea = document.getElementById('editTextarea');
            const value = currentEdit.field === 'url' ? input.value.trim() : textarea.value.trim();
            
            // Save to localStorage
            let edits = JSON.parse(localStorage.getItem(editsKey) || '{{}}');
            if (!edits[currentEdit.paperId]) {{
                edits[currentEdit.paperId] = {{}};
            }}
            edits[currentEdit.paperId][currentEdit.field] = value;
            localStorage.setItem(editsKey, JSON.stringify(edits));
            
            // Update the UI immediately
            updateUI(currentEdit.paperId, currentEdit.field, value);
            
            closeEditModal();
        }}
        
        function updateUI(paperId, field, value) {{
            const card = document.querySelector(`[data-paper-id="${{paperId}}"]`);
            if (!card) return;
            
            if (field === 'url') {{
                const linkDiv = card.querySelector('.paper-links');
                if (value) {{
                    const link = linkDiv.querySelector('.paper-link');
                    if (link) {{
                        link.href = value;
                        // Update or add edit icon inside the link
                        let editIcon = link.querySelector('.edit-icon-inline');
                        const escapedValue = value.replace(/'/g, "\\\\'");
                        if (!editIcon) {{
                            editIcon = document.createElement('span');
                            editIcon.className = 'edit-icon-inline';
                            editIcon.title = 'Edit URL';
                            editIcon.textContent = '✏️';
                            editIcon.onclick = (e) => {{
                                e.preventDefault();
                                e.stopPropagation();
                                openEditModal(paperId, 'url', value);
                            }};
                            link.appendChild(editIcon);
                        }} else {{
                            editIcon.onclick = (e) => {{
                                e.preventDefault();
                                e.stopPropagation();
                                openEditModal(paperId, 'url', value);
                            }};
                        }}
                    }} else {{
                        const escapedValue = value.replace(/'/g, "\\\\'");
                        linkDiv.innerHTML = `<a class="paper-link" href="${{value}}" target="_blank" rel="noopener">🔗 Open link<span class="edit-icon-inline" onclick="event.preventDefault(); event.stopPropagation(); openEditModal('${{paperId}}', 'url', '${{escapedValue}}')" title="Edit URL">✏️</span></a>`;
                    }}
                }}
                // Update title link too
                const titleLink = card.querySelector('.paper-title-link');
                if (titleLink) {{
                    titleLink.href = value;
                }}
            }} else if (field === 'abstract') {{
                const details = card.querySelector('.abstract-toggle');
                if (details) {{
                    const body = details.querySelector('.abstract-body');
                    if (body) {{
                        body.textContent = value || 'Abstract not available yet (you can paste it into url.json).';
                        body.classList.toggle('abstract-missing', !value);
                    }}
                }}
            }}
        }}
        
        function exportToJson() {{
            const edits = JSON.parse(localStorage.getItem(editsKey) || '{{}}');
            if (Object.keys(edits).length === 0) {{
                alert('No edits to export! Make some edits first.');
                return;
            }}
            
            // Load original url.json structure
            fetch('url.json')
                .then(r => r.json())
                .then(original => {{
                    // Merge edits into original
                    const updated = original.map(entry => {{
                        const pid = entry.id;
                        if (edits[pid]) {{
                            if (edits[pid].url !== undefined) entry.url = edits[pid].url;
                            if (edits[pid].abstract !== undefined) entry.abstract = edits[pid].abstract;
                        }}
                        return entry;
                    }});
                    
                    // Download as JSON file
                    const blob = new Blob([JSON.stringify(updated, null, 2)], {{'type': 'application/json'}});
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'url.json';
                    a.click();
                    URL.revokeObjectURL(url);
                }})
                .catch(() => {{
                    alert('Could not load url.json. Edits saved to localStorage only.');
                }});
        }}
        
        // Load edits from localStorage on page load
        window.addEventListener('DOMContentLoaded', () => {{
            const edits = JSON.parse(localStorage.getItem(editsKey) || '{{}}');
            for (const [paperId, fields] of Object.entries(edits)) {{
                if (fields.url !== undefined) updateUI(paperId, 'url', fields.url);
                if (fields.abstract !== undefined) updateUI(paperId, 'abstract', fields.abstract);
            }}
        }});
        
        // Close modal on background click
        document.getElementById('editModal').addEventListener('click', (e) => {{
            if (e.target.id === 'editModal') closeEditModal();
        }});
    </script>
</body>
</html>
'''
    
    return html


def main():
    print("=" * 60)
    print("SIGGRAPH Asia 2025 Technical Papers Scraper")
    print("=" * 60)
    
    # Fetch schedule data
    print("\nFetching schedule data...")
    html_content = fetch_schedule_data()
    
    if not html_content:
        print("ERROR: Could not fetch schedule data")
        return
    
    print(f"\nTotal HTML: {len(html_content):,} characters")
    
    # Save raw content for debugging
    with open("debug_raw.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("Saved raw HTML to debug_raw.html")
    
    # Extract Technical Papers
    print("\nExtracting Technical Papers...")
    papers = extract_technical_papers(html_content)
    
    print(f"Found {len(papers)} Technical Papers")
    print(f"  With images: {sum(1 for p in papers if p.get('image'))}")
    print(f"  With authors: {sum(1 for p in papers if p.get('authors'))}")
    
    # Group by session
    print("\nGrouping by session...")
    papers_by_session = group_papers_by_session(papers)
    
    print(f"Sessions: {len(papers_by_session)}")
    for session, paper_list in papers_by_session.items():
        print(f"  - {session}: {len(paper_list)} papers")

    # Write url.json scaffold (preserving any existing URLs)
    write_urls_json(papers_by_session)
    
    # Generate HTML
    print("\nGenerating HTML output...")
    output_html = generate_html(papers_by_session)
    
    # Save output
    output_path = Path("papers.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(output_html)
    
    print(f"\n{'=' * 60}")
    print(f"[SUCCESS] Output saved to: {output_path.absolute()}")
    print(f"[SUCCESS] Total: {len(papers)} papers in {len(papers_by_session)} sessions")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()

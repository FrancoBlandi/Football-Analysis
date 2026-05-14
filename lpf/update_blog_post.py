#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_blog_post.py — Pipeline completo: genera analytics, sincroniza blog y hace push.

Uso:
    python lpf/update_blog_post.py              # genera + actualiza + commit + push
    python lpf/update_blog_post.py --no-push    # genera + actualiza, sin push
    python lpf/update_blog_post.py --no-regen   # solo sync + push (sin regenerar analytics)
"""

import re, sys, subprocess
from pathlib import Path

ANALYTICS  = Path(__file__).parent / "analytics.html"
BLOG_POST  = Path(__file__).parent.parent / "blog/posts/lpf-fantasy-cuartos-2026.html"

# IDs de divs estáticos generados por Python que hay que propagar al blog
STATIC_DIV_IDS = ["captain-card", "dt-card", "leaders-bar"]


def extract_div_by_id(html, div_id):
    start_tag = f'id="{div_id}"'
    idx = html.find(start_tag)
    if idx == -1:
        return None
    open_idx = html.rfind('<div', 0, idx)
    depth = 0
    i = open_idx
    while i < len(html):
        if html[i:i+4] == '<div':
            depth += 1; i += 4
        elif html[i:i+6] == '</div>':
            depth -= 1; i += 6
            if depth == 0:
                return html[open_idx:i]
        else:
            i += 1
    return None


def update_blog_post():
    with open(ANALYTICS, encoding='utf-8') as f:
        analytics = f.read()
    with open(BLOG_POST, encoding='utf-8') as f:
        blog = f.read()

    # 1. Reemplazar bloque const D
    new_d = re.search(r'const D = \{.*?\};', analytics, re.DOTALL)
    old_d = re.search(r'const D = \{.*?\};', blog, re.DOTALL)
    if not new_d or not old_d:
        print("ERROR: no se encontró const D en analytics o blog")
        return False
    blog = blog[:old_d.start()] + new_d.group(0) + blog[old_d.end():]
    print(f"  D block: {len(new_d.group(0))} chars — OK")

    # 2. Reemplazar todos los divs estáticos
    for div_id in STATIC_DIV_IDS:
        new_div = extract_div_by_id(analytics, div_id)
        old_div = extract_div_by_id(blog, div_id)
        if not new_div or not old_div:
            print(f"  WARNING: {div_id} no encontrado — saltando")
            continue
        blog = blog.replace(old_div, new_div, 1)
        print(f"  {div_id}: {len(new_div)} chars — OK")

    with open(BLOG_POST, 'w', encoding='utf-8') as f:
        f.write(blog)
    print(f"  {BLOG_POST.name} actualizado")
    return True


def git_push():
    root = Path(__file__).parent.parent
    files = [
        "lpf/analytics.html",
        "blog/posts/lpf-fantasy-cuartos-2026.html",
    ]
    subprocess.run(["git", "add"] + files, cwd=root, check=True)

    status = subprocess.run(["git", "status", "--short"], cwd=root, capture_output=True, text=True)
    staged = [l for l in status.stdout.splitlines() if l.startswith(('M ', 'A '))]
    if not staged:
        print("  Nada nuevo que commitear")
        return

    subprocess.run(
        ["git", "commit", "-m", "blog: sync cuartos con analytics actualizado"],
        cwd=root, check=True
    )
    subprocess.run(["git", "push"], cwd=root, check=True)
    print("  Push OK")


def run_generate_analytics():
    """Corre generate_analytics.py y muestra su output completo (incluyendo role-change y REVISAR)."""
    root = Path(__file__).parent.parent
    script = Path(__file__).parent / "generate_analytics.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    sys.stdout.buffer.write(result.stdout.encode("utf-8", errors="replace"))
    if result.stderr:
        sys.stdout.buffer.write(result.stderr.encode("utf-8", errors="replace"))
    if result.returncode != 0:
        print("ERROR: generate_analytics.py falló")
        return False
    return True


if __name__ == "__main__":
    no_push  = "--no-push"  in sys.argv
    no_regen = "--no-regen" in sys.argv

    if not no_regen:
        print("=== Generando analytics.html ===")
        ok = run_generate_analytics()
        if not ok:
            sys.exit(1)

    print("=== Actualizando blog post ===")
    ok = update_blog_post()
    if not ok:
        sys.exit(1)

    if no_push:
        print("(--no-push: sin commit ni push)")
    else:
        print("\n=== Git commit + push ===")
        git_push()

"""第5回: ページ単位のベクトル検索。"""

import argparse
import json
import math
import re
import sqlite3
from contextlib import contextmanager
from collections import defaultdict, deque
from pathlib import Path

from google import genai
from google.genai import types
from pydantic_ai.exceptions import ModelHTTPError
import sqlite_vec

from app.config import (
    EMBEDDING_DIMENSIONS, EMBEDDING_MAX_TOKENS, EMBEDDING_MODEL,
    RAG_DB, RAG_DOCUMENT_IDS, RAG_SOURCE, RAG_TOP_K, RAG_TREE, get_api_key,
    RAG_GRAPH, GRAPH_START_K, GRAPH_HOPS, GRAPH_MAX_RESULTS,
)


def get_all_materials() -> str:
    """全資料を、講義・章・ページの情報付きで1つの文字列にまとめる。"""
    documents = json.loads(RAG_SOURCE.read_text(encoding="utf-8"))
    return "\n\n".join(
        f"資料: {document['id']} / {document['title']}\n"
        f"章: {section['section']}\n"
        f"ページ: PDF p.{page['page']} / {page['title']}\n{page['content']}"
        for document in documents
        for section in document["content"]
        for page in section["content"]
    )

def load_pages(source: Path = RAG_SOURCE) -> list[dict]:
    """資料→章→ページのJSONを、対象資料のページ一覧に変換する。"""
    documents = json.loads(source.read_text(encoding="utf-8"))
    pages = []
    for document in documents:
        if document["id"] not in RAG_DOCUMENT_IDS:
            continue
        for section in document["content"]:
            for page in section["content"]:
                pages.append({"page_id": page["id"], "document_id": document["id"],
                              "lecture": int(document["id"][3:5]), "document_title": document["title"],
                              "section": section["section"], "title": page["title"],
                              "page": page["page"], "content": page["content"]})
    return pages


_HEADER_PREFIX_RE = re.compile(
    r"^(?:第\s*\d+\s*回|Part\s*\d+|クイズ\s*\d+/\d+|\d+/\d+|まとめ|Appendix|例題で考える)\s*"
)


def _normalize_heading(text: str) -> str:
    cleaned = _HEADER_PREFIX_RE.sub("", text).strip()
    return re.sub(r"[\s　:：・]+", "", cleaned).casefold()


def _extract_page_preview(page: dict, max_chars: int = 120) -> str:
    """見出し重複行やメタ行を除き、実質的な本文リード文を最大max_chars文字で返す。"""
    raw = page["content"].strip()
    if not raw:
        return ""
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    section_norm = _normalize_heading(page.get("section", ""))
    title_norm = _normalize_heading(page.get("title", ""))

    body_lines = []
    skipping_headers = True
    for line in lines:
        compact = re.sub(r"[\s　]+", "", line)
        norm = _normalize_heading(line)
        is_header_only = (
            not norm
            or norm == section_norm
            or norm == title_norm
            or re.fullmatch(r"(?:第\d+回)?(?:\d+/\d+)?(?:（約\d+分）)?", compact) is not None
        )
        if skipping_headers and is_header_only:
            continue
        skipping_headers = False
        if line.startswith(("出典", "©")):
            continue
        body_lines.append(line)

    preview = " ".join(body_lines) if body_lines else lines[0]
    if len(preview) > max_chars:
        return preview[:max_chars].rstrip() + "…"
    return preview


def _browse_tree_with_preview(node_id: str | None, preview_fn) -> dict:
    """目次ノードと直下の一覧を返す共通実装。"""
    tree = json.loads(RAG_TREE.read_text(encoding="utf-8"))
    tree["children"] = [node for node in tree["children"] if node["id"] in RAG_DOCUMENT_IDS]
    node_id = node_id or tree["id"]
    pages = {page["page_id"]: page for page in load_pages(RAG_SOURCE)}

    def describe(node, full=False):
        info = {key: node[key] for key in ("id", "kind", "title")}
        if node["kind"] == "page":
            info.update({key: value for key, value in pages[node["id"]].items() if key != "page_id"})
            if not full:
                info["content"] = preview_fn(info)
        return info

    remaining = [tree]
    while remaining:
        node = remaining.pop()
        if node["id"] == node_id:
            return {
                "node": describe(node, full=True),
                "children": [describe(child) for child in node.get("children", [])],
            }
        remaining.extend(node.get("children", []))
    raise ValueError("対象の目次ノードが見つかりません。")


def browse_tree(node_id: str | None = None) -> dict:
    """直下のページは先頭文、指定したページ自身は全文を返す。"""
    return _browse_tree_with_preview(
        node_id,
        lambda info: re.split(r"(?<=[。！？])|\n", info["content"].strip(), maxsplit=1)[0],
    )


def browse_tree_enhanced(node_id: str | None = None) -> dict:
    """直下のページは見出し重複を除いた本文リード文、指定ページ自身は全文を返す。"""
    return _browse_tree_with_preview(node_id, _extract_page_preview)


def read_page(page_id: str) -> dict:
    """第1〜3回の本講義から、指定した1ページの本文と引用情報を返す。"""
    for page in load_pages(RAG_SOURCE):
        if page["page_id"] == page_id:
            return page
    raise ValueError("対象のページが見つかりません。")


def normalized_vector(values: list[float]) -> list[float]:
    """ベクトルの長さを1に揃える。"""
    norm = math.hypot(*values)
    if norm == 0:
        raise ValueError("埋め込みがゼロベクトルです。")
    return [value / norm for value in values]


def embed_text(text: str, task_type: str) -> list[float]:
    """Geminiで文章を埋め込む。入力上限を超えた場合は切り捨てず停止する。"""
    with genai.Client(api_key=get_api_key()) as client:
        count = client.models.count_tokens(model=EMBEDDING_MODEL, contents=text).total_tokens
        if count is None or count > EMBEDDING_MAX_TOKENS:
            raise ValueError(f"埋め込み入力が上限を超えるか計測不能です: {count} tokens。")
        response = client.models.embed_content(
            model=EMBEDDING_MODEL, contents=text,
            config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=EMBEDDING_DIMENSIONS),
        )
    embedding = response.embeddings[0]
    if embedding.statistics and embedding.statistics.truncated:
        raise ValueError("埋め込みAPIが本文を切り捨てました。")
    return normalized_vector(embedding.values)


@contextmanager
def open_index(path: Path):
    """既存の検索DBを読み取り専用で開き、終了時に閉じる。"""
    if not path.is_file():
        raise FileNotFoundError("検索DBがありません。")
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        db.row_factory = sqlite3.Row
        db.enable_load_extension(True)
        sqlite_vec.load(db)
        db.enable_load_extension(False)
        yield db
    finally:
        db.close()


def search(query: str) -> list[dict]:
    """質問を埋め込み、近いページを最大RAG_TOP_K件返す。"""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("検索語が空です。")
    with open_index(RAG_DB) as db:
        vector = embed_text(query.strip(), "RETRIEVAL_QUERY")
        rows = db.execute("""
            SELECT page_id, document_id, lecture, document_title, section, title, page, content,
                   vec_distance_cosine(embedding, ?) AS distance
            FROM chunks ORDER BY distance, page_id LIMIT ?
        """, (sqlite_vec.serialize_float32(vector), RAG_TOP_K))
        return [dict(row) for row in rows]


def search_with_neighbors(query: str, window: int = 1) -> list[dict]:
    """検索上位ページに加え、同じdocument_idの前後windowページを重複なく返す。"""
    if window < 0:
        raise ValueError("windowは0以上を指定してください。")
    hits = search(query)
    pages_by_doc_page = {
        (page["document_id"], page["page"]): page for page in load_pages(RAG_SOURCE)
    }
    hits_by_id = {hit["page_id"]: hit for hit in hits}
    seen = set()
    expanded = []
    for hit in hits:
        doc_id = hit["document_id"]
        center_page = hit["page"]
        for offset in range(-window, window + 1):
            target = pages_by_doc_page.get((doc_id, center_page + offset))
            if target is None or target["page_id"] in seen:
                continue
            seen.add(target["page_id"])
            if target["page_id"] in hits_by_id:
                expanded.append({**hits_by_id[target["page_id"]], "match_type": "seed"})
            else:
                expanded.append({**target, "match_type": "neighbor", "anchor_page": center_page})
    return expanded


def _load_graph_context(query: str) -> tuple[dict, dict, dict, dict, list[dict], list[dict]]:
    """グラフ探索用のページ辞書・隣接リスト・関連用語・入口ページを準備する。"""
    pages = {page["page_id"]: page for page in load_pages(RAG_SOURCE)}
    graph = json.loads(RAG_GRAPH.read_text(encoding="utf-8"))
    nodes = {node["id"]: node for node in graph["nodes"]
             if node["kind"] == "term" or node["id"] in pages}
    adjacent = defaultdict(set)
    related_terms = defaultdict(set)
    for edge in graph["edges"]:
        a, b = edge["source"], edge["target"]
        if a not in nodes or b not in nodes:
            continue
        if edge["relation"] in ("next_page", "mentions"):
            adjacent[a].add(b)
            adjacent[b].add(a)
        elif edge["relation"] == "related_term":
            related_terms[a].add(b)
            related_terms[b].add(a)

    seeds = [hit for hit in search(query) if hit["page_id"] in pages][:min(GRAPH_START_K, GRAPH_MAX_RESULTS)]
    seed_results = [
        {**pages[seed["page_id"]], "distance": seed["distance"], "hops": 0,
         "path": [{"id": seed["page_id"], "title": pages[seed["page_id"]]["title"]}]}
        for seed in seeds
    ]
    return pages, nodes, adjacent, related_terms, seeds, seed_results


def search_graph(query: str) -> dict:
    """ベクトル検索を入口に、前後ページと共通用語で候補を広げる。"""
    pages, nodes, adjacent, _, seeds, results = _load_graph_context(query)
    seed_ids = {seed["page_id"] for seed in seeds}
    candidates = {}
    for rank, seed in enumerate(seeds):
        root = seed["page_id"]
        queue = deque([(root, [root])])
        visited = {root}
        while queue:
            current, path = queue.popleft()
            if len(path) - 1 >= GRAPH_HOPS:
                continue
            # 同じ深さなら、接続先が少ない用語からたどる。
            neighbors = sorted(adjacent[current], key=lambda n: (len(adjacent[n]), n))
            for neighbor in neighbors:
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                route = path + [neighbor]
                queue.append((neighbor, route))
                if neighbor not in pages or neighbor in seed_ids:
                    continue
                frequency = max((len(adjacent[n]) for n in route if nodes[n]["kind"] == "term"), default=0)
                priority = (len(route) - 1, frequency, rank, neighbor)
                candidate = {**pages[neighbor], "hops": len(route) - 1,
                             "path": [{"id": n, "title": nodes[n]["title"]} for n in route]}
                if neighbor not in candidates or priority < candidates[neighbor][0]:
                    candidates[neighbor] = (priority, candidate)
    expanded = [candidate for _, candidate in sorted(candidates.values())]
    return {"seeds": results, "expanded": expanded[:max(0, GRAPH_MAX_RESULTS - len(results))],
            "max_hops": GRAPH_HOPS}


def search_graph_enhanced(query: str) -> dict:
    """related_term接続と複数シード共起・用語希少度を加味して候補ページを広げる。"""
    pages, nodes, adjacent, related_terms, seeds, results = _load_graph_context(query)
    seed_ids = {seed["page_id"] for seed in seeds}
    per_target_best = {}
    target_seeds = defaultdict(set)

    def record_route(target_id: str, rank: int, root_id: str, effective_hops: float, route: list[str]) -> None:
        if target_id not in pages or target_id in seed_ids:
            return
        target_seeds[target_id].add(root_id)
        term_degree = max((len(adjacent[n]) for n in route if nodes[n]["kind"] == "term"), default=0)
        local_key = (effective_hops, term_degree, rank, route)
        if target_id not in per_target_best or local_key < per_target_best[target_id]:
            per_target_best[target_id] = local_key

    for rank, seed in enumerate(seeds):
        root = seed["page_id"]
        queue = deque([(root, [root])])
        visited = {root}
        while queue:
            current, path = queue.popleft()
            if len(path) - 1 >= GRAPH_HOPS:
                continue
            for neighbor in sorted(adjacent[current], key=lambda n: (len(adjacent[n]), n)):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                route = path + [neighbor]
                queue.append((neighbor, route))
                hops = float(len(route) - 1)
                if len(route) == 3 and nodes[route[1]]["kind"] != "term":
                    hops = 2.6
                record_route(neighbor, rank, root, hops, route)

                if GRAPH_HOPS >= 2 and len(route) == 2 and nodes[neighbor]["kind"] == "term":
                    for rel_term in sorted(related_terms[neighbor], key=lambda n: (len(adjacent[n]), n)):
                        for target in sorted(adjacent[rel_term]):
                            if target != root and target in pages and target not in seed_ids:
                                record_route(target, rank, root, 2.3, [root, neighbor, rel_term, target])

    scored = []
    for target_id, (effective_hops, term_degree, rank, route) in per_target_best.items():
        support = len(target_seeds[target_id])
        score = effective_hops - 0.7 * (support - 1) + 0.02 * term_degree
        priority = (round(score, 6), effective_hops, term_degree, rank, target_id)
        candidate = {
            **pages[target_id],
            "hops": effective_hops,
            "seed_support": support,
            "path": [{"id": n, "title": nodes[n]["title"]} for n in route],
        }
        scored.append((priority, candidate))

    expanded = [candidate for _, candidate in sorted(scored, key=lambda item: item[0])]
    return {"seeds": results, "expanded": expanded[:max(0, GRAPH_MAX_RESULTS - len(results))],
            "max_hops": GRAPH_HOPS}



def run_full_context(agent, question: str, model, instructions: str, prompt_template: str):
    """全資料を一括投入し、検索ツールを使わずに回答する。"""
    prompt = prompt_template.format(materials=get_all_materials(), question=question)
    print(f"[full-context] 入力{len(prompt):,}文字")
    try:
        with agent.override(tools=[], instructions=instructions):
            return agent.run_sync(prompt, model=model)
    except ModelHTTPError as e:
        print(f"[full-context] APIエラー HTTP {e.status_code}: {e.body}")
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="エージェントを使わず、講義資料の検索だけを実行する")
    parser.add_argument("query", help="調べたい内容")
    args = parser.parse_args()
    for i, result in enumerate(search(args.query), 1):
        print(f"\n{'=' * 60}\n検索結果 {i}\n{'=' * 60}")
        print(f"講義: {result['document_title']}")
        print(f"章: {result['section']}")
        print(f"タイトル: {result['title']}")
        print(f"ページ: {result['page']}")
        print(f"\n{result['content']}")

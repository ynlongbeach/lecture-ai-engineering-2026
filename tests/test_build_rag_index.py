"""実SQLiteと固定ベクトルで、索引作成から検索までを確認する。APIは呼ばない。"""

import json
from unittest.mock import Mock

import pytest

from app import retrieval
from scripts.build_rag_index import build_index


@pytest.fixture
def materials(tmp_path):
    source = tmp_path / "lectures.json"
    source.write_text(json.dumps([
        {"id": f"lec{n:02d}-main", "title": f"講義{n}", "content": [
            {"section": "章", "content": [
                {"id": f"lec{n:02d}-main-p001", "title": f"ページ{n}",
                 "page": 1, "content": f"本文{n}"}]}]}
        for n in (1, 2, 5)
    ], ensure_ascii=False), encoding="utf-8")
    return source, tmp_path / "index.sqlite3"


def test_built_index_can_be_searched(materials, monkeypatch):
    source, database = materials
    texts = []

    def embed(text, task):
        assert task == "RETRIEVAL_DOCUMENT"
        texts.append(text)
        return [1, 0] if "本文1" in text else [0, 1]

    result = build_index(source, database, embedder=embed)
    assert result["pages"] == 2  # 第5回の資料は検索対象に含めない
    assert all("章" in text and "ページ" in text for text in texts)
    monkeypatch.setattr(retrieval, "RAG_DB", database)
    monkeypatch.setattr(retrieval, "embed_text", lambda *_: [1, 0])
    hits = retrieval.search("質問")
    assert [h["page_id"] for h in hits] == ["lec01-main-p001", "lec02-main-p001"]
    assert hits[0]["content"] == "本文1"
    assert hits[0]["distance"] == pytest.approx(0)


def test_existing_index_survives_failed_rebuild(materials):
    source, database = materials
    build_index(source, database, embedder=lambda *_: [1, 0])
    before = database.read_bytes()
    embed = Mock(side_effect=RuntimeError("埋め込みに失敗"))
    with pytest.raises(FileExistsError):
        build_index(source, database, embedder=embed)
    embed.assert_not_called()
    with pytest.raises(RuntimeError, match="埋め込みに失敗"):
        build_index(source, database, rebuild=True, embedder=embed)
    assert database.read_bytes() == before
    assert not list(database.parent.glob(".rag-build-*"))


def test_search_with_neighbors_returns_adjacent_pages_without_duplicates(monkeypatch):
    pages = [
        {"page_id": "lec02-main-p051", "document_id": "lec02-main", "lecture": 2,
         "document_title": "講義2", "section": "章", "title": "p51", "page": 51, "content": "前ページ"},
        {"page_id": "lec02-main-p052", "document_id": "lec02-main", "lecture": 2,
         "document_title": "講義2", "section": "章", "title": "p52", "page": 52, "content": "中心ページ"},
        {"page_id": "lec02-main-p053", "document_id": "lec02-main", "lecture": 2,
         "document_title": "講義2", "section": "章", "title": "p53", "page": 53, "content": "次ページ"},
        {"page_id": "lec03-main-p001", "document_id": "lec03-main", "lecture": 3,
         "document_title": "講義3", "section": "章", "title": "p1", "page": 1, "content": "別資料"},
    ]
    hits = [{**pages[1], "distance": 0.1}, {**pages[2], "distance": 0.2}]
    monkeypatch.setattr(retrieval, "search", lambda _q: hits)
    monkeypatch.setattr(retrieval, "load_pages", lambda _s=retrieval.RAG_SOURCE: pages)

    results = retrieval.search_with_neighbors("LoRA", window=1)
    assert [r["page_id"] for r in results] == ["lec02-main-p051", "lec02-main-p052", "lec02-main-p053"]
    assert [r["match_type"] for r in results] == ["neighbor", "seed", "seed"]
    assert results[0]["anchor_page"] == 52


def test_browse_tree_enhanced_skips_duplicate_headers():
    result = retrieval.browse_tree_enhanced("lec03-main-s037")
    by_id = {child["id"]: child for child in result["children"]}
    assert "1つのセッションの中で効くもの" in by_id["lec03-main-p039"]["content"]
    assert "毎晩過去のやり取りを読み直し" in by_id["lec03-main-p040"]["content"]


def test_search_graph_enhanced_traverses_related_terms(tmp_path, monkeypatch):
    pages = [
        {"page_id": "lec03-main-p001", "document_id": "lec03-main", "lecture": 3,
         "document_title": "講義3", "section": "章1", "title": "ページ1", "page": 1, "content": "入口"},
        {"page_id": "lec03-main-p010", "document_id": "lec03-main", "lecture": 3,
         "document_title": "講義3", "section": "章2", "title": "ページ10", "page": 10, "content": "関連先"},
    ]
    graph = {
        "nodes": [
            {"id": "lec03-main-p001", "kind": "page", "title": "ページ1"},
            {"id": "lec03-main-p010", "kind": "page", "title": "ページ10"},
            {"id": "term:a", "kind": "term", "title": "用語A"},
            {"id": "term:b", "kind": "term", "title": "用語B"},
        ],
        "edges": [
            {"source": "lec03-main-p001", "target": "term:a", "relation": "mentions"},
            {"source": "term:a", "target": "term:b", "relation": "related_term"},
            {"source": "lec03-main-p010", "target": "term:b", "relation": "mentions"},
        ],
    }
    graph_file = tmp_path / "graph.json"
    graph_file.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(retrieval, "RAG_GRAPH", graph_file)
    monkeypatch.setattr(retrieval, "load_pages", lambda _s=retrieval.RAG_SOURCE: pages)
    monkeypatch.setattr(retrieval, "search", lambda _q: [{**pages[0], "distance": 0.1}])

    res = retrieval.search_graph_enhanced("テスト")
    assert [s["page_id"] for s in res["seeds"]] == ["lec03-main-p001"]
    assert [e["page_id"] for e in res["expanded"]] == ["lec03-main-p010"]
    assert res["expanded"][0]["hops"] == 2.3

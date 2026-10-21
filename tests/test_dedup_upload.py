"""Property tests for duplicate-upload suppression within a single rewrite.

Feature: dedup-upload-and-title-alias, Property 1 / Property 5 (後方互換)
同一実行内で同じ real_name を複数回参照しても upload は高々 1 回で、
全出現箇所が同一 URL に書き換わることを検証する。
"""

import re
from pathlib import Path
from unittest.mock import MagicMock

from hypothesis import given, settings, strategies as st

from elab_doc_sync.sync import _rewrite_images, _rewrite_videos, _rewrite_file_links


def _fresh_client():
    """upload_file が呼ばれるたびに一意な URL を返すモック。list_uploads は空。"""
    client = MagicMock()
    client.base_url = "https://elab.example.com"
    client.list_uploads.return_value = []
    counter = {"n": 0}

    def _upload(entity, eid, path):
        counter["n"] += 1
        name = Path(path).name
        return {"url": f"https://elab.example.com/dl/{counter['n']}_{name}", "id": counter["n"]}

    client.upload_file.side_effect = _upload
    return client


_DL_URL = re.compile(r"https://elab\.example\.com/dl/\S+?(?=[)\"])")


def _extract_urls(text):
    return _DL_URL.findall(text)


# 画像・動画・ファイルリンクそれぞれの (拡張子, 本文テンプレート, rewrite 関数)
_KINDS = [
    (".png", "![alt]({name})", _rewrite_images),
    (".mp4", "![vid]({name})", _rewrite_videos),
    (".pdf", "[doc]({name})", _rewrite_file_links),
]


@settings(max_examples=120, deadline=None)
@given(refs=st.integers(min_value=1, max_value=6), kind=st.sampled_from(range(3)))
def test_same_reference_uploads_once(tmp_path_factory, refs, kind):
    ext, tmpl, fn = _KINDS[kind]
    tmp = tmp_path_factory.mktemp("dedup")
    docs = tmp / "docs"
    docs.mkdir()
    name = f"asset{ext}"
    (docs / name).write_bytes(b"CONTENT-BYTES")

    body = "\n\n".join(tmpl.format(name=name) for _ in range(refs))
    client = _fresh_client()
    result = fn(body, "items", 1, client, docs, tmp)

    # upload は高々 1 回
    assert client.upload_file.call_count == 1, f"refs={refs} kind={ext}: {client.upload_file.call_count} uploads"

    # 全出現箇所が同一 URL を指す
    urls = _extract_urls(result)
    assert len(urls) == refs
    assert len(set(urls)) == 1


@settings(max_examples=60, deadline=None)
@given(kind=st.sampled_from(range(3)))
def test_single_reference_backward_compatible(tmp_path_factory, kind):
    """参照 1 箇所のケースは従来どおり 1 回アップロードし URL に書き換える（要件 1.8）。"""
    ext, tmpl, fn = _KINDS[kind]
    tmp = tmp_path_factory.mktemp("dedup_single")
    docs = tmp / "docs"
    docs.mkdir()
    name = f"only{ext}"
    (docs / name).write_bytes(b"ONE")

    body = tmpl.format(name=name)
    client = _fresh_client()
    result = fn(body, "items", 1, client, docs, tmp)

    assert client.upload_file.call_count == 1
    urls = _extract_urls(result)
    assert len(urls) == 1  # ローカル参照が 1 本の URL に置換された

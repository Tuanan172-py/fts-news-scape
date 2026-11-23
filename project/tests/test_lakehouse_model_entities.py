"""`entities` publishes only the ids the model named (code-layer ids stay in `intent_code`)."""
import io

import pyarrow.parquet as pq

from src.lakehouse.ingest import keep_model_entities, records_to_parquet_bytes

UKRAINE = {
    "article_id": "a1", "title": "Những sai lầm chết người của Ukraine",
    "entities": ["MACRO_GEO:NGA [MACRO_GEO]", "TICKER:MBB [TICKER]", "TICKER:MDG [TICKER]"],
    "intent_llm": "MACRO_GEO:NGA", "intent_code": "MACRO_GEO:NGA; TICKER:MBB; TICKER:MDG",
    "intent_source": "BOTH:1; CODE_ONLY:2",
}


def test_code_layer_only_ids_are_dropped():
    assert keep_model_entities(UKRAINE["entities"], UKRAINE["intent_llm"], UKRAINE["intent_code"]) == [
        "MACRO_GEO:NGA [MACRO_GEO]"]


def test_model_ids_with_type_tags_and_spacing_match():
    ents = ["TICKER:BID [TICKER]", "IND_GICS3:NGAN_HANG [INDUSTRY_GICS3]", "TICKER:OIL [TICKER]"]
    llm = " TICKER:BID [TICKER] ;IND_GICS3:NGAN_HANG"
    assert keep_model_entities(ents, llm, "TICKER:BID; TICKER:OIL") == ents[:2]


def test_gics_levels_are_not_confused():
    ents = ["IND_GICS2:NGAN_HANG [INDUSTRY_GICS2]", "IND_GICS3:NGAN_HANG [INDUSTRY_GICS3]"]
    assert keep_model_entities(ents, "IND_GICS3:NGAN_HANG", "IND_GICS2:NGAN_HANG") == ents[1:]


def test_bare_codes_from_the_model_match_their_kind_prefixed_ids():
    # `user_output` can write the registry code without its kind ("HPG" for TICKER:HPG).
    assert keep_model_entities(["TICKER:HPG", "TICKER:MBB"], "HPG [TICKER]", "HPG; MBB") == ["TICKER:HPG"]


def test_only_code_layer_ids_leave_entities_empty():
    assert keep_model_entities(["TICKER:API [TICKER]"], "", "TICKER:API") == []


def test_rows_without_provenance_pass_through():
    assert keep_model_entities(["TICKER:HPG [TICKER]"], "", "") == ["TICKER:HPG [TICKER]"]


def test_consolidation_applies_the_rule_to_dropzone_files_written_directly(tmp_path):
    import pyarrow as pa

    from src.lakehouse.consolidator import consolidate_dropzone
    from src.lakehouse.ingest import LAKEHOUSE_ARTICLE_SCHEMA
    from src.lakehouse.storage import LocalOneDriveStorageAdapter

    row = {f.name: None for f in LAKEHOUSE_ARTICLE_SCHEMA}
    row.update(UKRAINE, url="https://x.vn/a1", published_at="2026-11-13T08:00:00+07:00",
               updated_at="2026-11-13T09:00:00+07:00", dev_id="external", batch_id="b1", raw_sha256="s1")
    zone = tmp_path / "dropzone" / "2026" / "11" / "13"
    zone.mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist([row], schema=LAKEHOUSE_ARTICLE_SCHEMA), zone / "external_b1.parquet")
    storage = LocalOneDriveStorageAdapter(root_dir=tmp_path)
    res = consolidate_dropzone(date_str="2026-11-13", storage=storage, auto_purge=False)
    out = pq.read_table(storage.get_local_path(res.partition_file)).to_pylist()
    assert [r["entities"] for r in out] == [["MACRO_GEO:NGA [MACRO_GEO]"]]


def test_ingest_applies_the_rule():
    raw = records_to_parquet_bytes([dict(UKRAINE)], dev_id="d", batch_id="b")
    row = pq.read_table(io.BytesIO(raw)).to_pylist()[0]
    assert row["entities"] == ["MACRO_GEO:NGA [MACRO_GEO]"]
    assert row["intent_code"] == UKRAINE["intent_code"]

"""Routing: raw message → (topic, key, payload); logic wraps newsdock_core."""

import json
from pathlib import Path

from newsdock_core.contracts import RawMessage
from newsdock_processor.domain.route import CLEAN_TOPIC, DLQ_TOPIC, route

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / "packages" / "core" / "tests" / "fixtures"
SLOT = "20261004081500"


def test_good_row_routes_to_clean_keyed_by_url_hash() -> None:
    line = (FIXTURES / "gkg_sample.tsv").read_text().splitlines()[0]
    routed = route(RawMessage(slot=SLOT, row_no=0, line=line))
    assert routed.topic == CLEAN_TOPIC
    payload = json.loads(routed.value)
    assert routed.key == payload["url_hash"]
    assert payload["slot"] == SLOT and payload["title"]


def test_bad_row_routes_to_dlq_keyed_by_slot_row() -> None:
    with (FIXTURES / "bad_rows.json").open() as f:
        bad = json.load(f)
    row = next(b for b in bad if b["name"] == "missing_url")
    routed = route(RawMessage(slot=SLOT, row_no=7, line=row["line"]))
    assert routed.topic == DLQ_TOPIC
    assert routed.key == f"{SLOT}:7"
    payload = json.loads(routed.value)
    assert payload["reason"] == "missing_url" and "at" in payload


def test_exception_in_parse_becomes_bad_field_not_a_crash() -> None:
    # tone column with garbage: parse_row catches it → dlq bad_field
    line = (FIXTURES / "gkg_sample.tsv").read_text().splitlines()[0]
    columns = line.split("\t")
    columns[15] = "not,a,number,at,all,x,y"
    routed = route(RawMessage(slot=SLOT, row_no=9, line="\t".join(columns)))
    assert routed.topic == DLQ_TOPIC
    assert json.loads(routed.value)["reason"] == "bad_field"

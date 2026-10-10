from gmail_core import GmailMessageMetadata


def test_header_lookup_is_case_insensitive_via_lowercase_keys() -> None:
    metadata = GmailMessageMetadata(
        message_id="m1",
        thread_id="t1",
        label_ids=("INBOX",),
        snippet="",
        internal_date_ms=None,
        headers={"subject": "Hello"},
    )

    assert metadata.header("Subject") == "Hello"
    assert metadata.header("List-Id") == ""

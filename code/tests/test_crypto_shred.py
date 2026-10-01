import os

import pytest

import crypto_shred as cs


@pytest.fixture
def store():
    s = cs.CryptoShredStore(os.urandom(32))
    s.put("guest-0001", "stay-1", b"Test Guest Alpha, allergy: peanuts")
    s.put("guest-0001", "stay-2", b"Test Guest Alpha, room 0807")
    s.put("guest-0002", "stay-3", b"Test Guest Bravo, room 0311")
    return s


def test_each_subject_has_its_own_dek(store):
    rows = store.keys.execute("SELECT subject_id, wrapped_dek FROM subject_keys").fetchall()
    assert len(rows) == 2 and rows[0][1] != rows[1][1]


def test_shred_one_subject_others_remain_readable(store):
    result = store.shred("guest-0001")
    assert result == {"subject_id": "guest-0001", "key_destroyed": True, "ciphertext_rows_now_unreadable": 2}
    for rid in ("stay-1", "stay-2"):
        with pytest.raises(cs.SubjectErasedError):
            store.get(rid)
    assert store.get("stay-3") == b"Test Guest Bravo, room 0311"


def test_backup_copies_become_unreadable(store):
    backup = store.export_backup()
    store.shred("guest-0001")
    readable = []
    for rid, sid, nonce, ct in backup:
        try:
            readable.append((rid, store.decrypt_record(sid, rid, nonce, ct)))
        except cs.SubjectErasedError:
            pass
    assert readable == [("stay-3", b"Test Guest Bravo, room 0311")]


def test_shredded_subject_cannot_be_silently_recreated(store):
    store.shred("guest-0001")
    with pytest.raises(cs.SubjectErasedError):
        store.put("guest-0001", "stay-9", b"new data")
    with pytest.raises(KeyError):
        store.shred("guest-0001")


def test_record_bound_to_subject_and_id(store):
    rid, sid, nonce, ct = [r for r in store.export_backup() if r[0] == "stay-3"][0]
    with pytest.raises(ValueError):
        store.decrypt_record(sid, "stay-other", nonce, ct)


def test_wrapped_dek_bytes_gone_from_key_db_file(tmp_path):
    key_db = tmp_path / "keys.db"
    s = cs.CryptoShredStore(os.urandom(32), key_db=str(key_db), data_db=str(tmp_path / "data.db"))
    s.put("guest-0001", "stay-1", b"x")
    wrapped = s.keys.execute("SELECT wrapped_dek FROM subject_keys").fetchone()[0]
    assert wrapped in key_db.read_bytes()
    s.shred("guest-0001")
    s.keys.close()
    assert wrapped not in key_db.read_bytes()  # PRAGMA secure_delete overwrote the old cell

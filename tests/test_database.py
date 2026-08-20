"""Unit tests for SQLite database persistence and state transitions."""

from src.storage.database import Database


def test_baseline_initialization_no_spam(temp_db: Database, sample_accommodation_1, sample_accommodation_2):
    assert temp_db.is_empty()

    # Initial baseline snapshot with 2 existing rooms
    items = [sample_accommodation_1, sample_accommodation_2]
    newly_available, disappeared_items, maintained = temp_db.sync_snapshot(items, is_baseline=True)

    assert len(newly_available) == 0
    assert len(disappeared_items) == 0
    assert temp_db.get_currently_available_count() == 2
    assert not temp_db.is_empty()

    # Verify record in DB
    rec = temp_db.get_accommodation(sample_accommodation_1.id)
    assert rec is not None
    assert rec["currently_available"] == 1
    assert rec["residence_name"] == sample_accommodation_1.residence_name


def test_detect_newly_available_room(temp_db: Database, sample_accommodation_1, sample_accommodation_2, sample_accommodation_3):
    # Baseline with 1 and 2
    temp_db.sync_snapshot([sample_accommodation_1, sample_accommodation_2], is_baseline=True)

    # Next cycle: Room 3 appears!
    newly_available, disappeared_items, maintained = temp_db.sync_snapshot(
        [sample_accommodation_1, sample_accommodation_2, sample_accommodation_3],
        is_baseline=False
    )

    assert len(newly_available) == 1
    assert newly_available[0].id == sample_accommodation_3.id
    assert len(disappeared_items) == 0
    assert maintained == 2
    assert temp_db.get_currently_available_count() == 3


def test_room_disappearance_tracked(temp_db: Database, sample_accommodation_1, sample_accommodation_2):
    # Baseline with 1 and 2
    temp_db.sync_snapshot([sample_accommodation_1, sample_accommodation_2], is_baseline=True)

    # Next cycle: Room 2 disappeared (only 1 remains)
    newly_available, disappeared_items, maintained = temp_db.sync_snapshot(
        [sample_accommodation_1],
        is_baseline=False
    )

    assert len(newly_available) == 0
    assert len(disappeared_items) == 1
    assert disappeared_items[0].id == sample_accommodation_2.id
    assert maintained == 1
    assert temp_db.get_currently_available_count() == 1

    # Verify room 2 is marked unavailable in DB
    rec = temp_db.get_accommodation(sample_accommodation_2.id)
    assert rec is not None
    assert rec["currently_available"] == 0


def test_room_reappearance_triggers_alert(temp_db: Database, sample_accommodation_1, sample_accommodation_2):
    # 1. Baseline with 1 and 2
    temp_db.sync_snapshot([sample_accommodation_1, sample_accommodation_2], is_baseline=True)

    # 2. Room 2 disappears
    temp_db.sync_snapshot([sample_accommodation_1], is_baseline=False)
    assert temp_db.get_currently_available_count() == 1

    # 3. Room 2 reappears later!
    newly_available, disappeared_items, maintained = temp_db.sync_snapshot(
        [sample_accommodation_1, sample_accommodation_2],
        is_baseline=False
    )

    assert len(newly_available) == 1
    assert newly_available[0].id == sample_accommodation_2.id
    assert len(disappeared_items) == 0
    assert temp_db.get_currently_available_count() == 2

    # Verify room 2 is marked available again in DB
    rec = temp_db.get_accommodation(sample_accommodation_2.id)
    assert rec["currently_available"] == 1


def test_ordering_and_duplicates_immunity(temp_db: Database, sample_accommodation_1, sample_accommodation_2):
    # Baseline with [1, 2]
    temp_db.sync_snapshot([sample_accommodation_1, sample_accommodation_2], is_baseline=True)

    # Next cycle with inverted order and duplicates: [2, 1, 2]
    newly_available, disappeared_items, maintained = temp_db.sync_snapshot(
        [sample_accommodation_2, sample_accommodation_1, sample_accommodation_2],
        is_baseline=False
    )

    assert len(newly_available) == 0
    assert len(disappeared_items) == 0
    assert maintained == 2
    assert temp_db.get_currently_available_count() == 2


def test_restart_persistence(tmp_path, sample_accommodation_1, sample_accommodation_2):
    db_file = str(tmp_path / "persistence_test.db")

    # Instance 1: write baseline
    db1 = Database(db_file)
    db1.sync_snapshot([sample_accommodation_1, sample_accommodation_2], is_baseline=True)
    assert db1.get_currently_available_count() == 2

    # Instance 2 (simulating service restart)
    db2 = Database(db_file)
    assert not db2.is_empty()
    assert db2.get_currently_available_count() == 2

    # Running check with same items does not re-alert
    newly_available, disappeared_items, maintained = db2.sync_snapshot(
        [sample_accommodation_1, sample_accommodation_2],
        is_baseline=False
    )
    assert len(newly_available) == 0
    assert len(disappeared_items) == 0
    assert maintained == 2

from smart_life_bot.storage.sqlite import create_sqlite_connection, init_sqlite_schema, SQLiteUsersRepository, SQLiteOAuthConnectionStateRepository


def test_oauth_state_defaults_to_not_connected() -> None:
    conn = create_sqlite_connection('sqlite:///:memory:')
    init_sqlite_schema(conn)
    users = SQLiteUsersRepository(conn)
    oauth = SQLiteOAuthConnectionStateRepository(conn)
    user = users.get_or_create_by_telegram_id(777001, timezone='UTC')
    state = oauth.get_or_create_for_user(user.id)
    assert state.status.value == 'not_connected'


def test_oauth_pending_and_disconnect_roundtrip() -> None:
    conn = create_sqlite_connection('sqlite:///:memory:')
    init_sqlite_schema(conn)
    users = SQLiteUsersRepository(conn)
    oauth = SQLiteOAuthConnectionStateRepository(conn)
    user = users.get_or_create_by_telegram_id(777002, timezone='UTC')
    pending = oauth.start_pending(user.id, 'hashed_state')
    assert pending.status.value == 'pending'
    assert pending.state_token_hash == 'hashed_state'
    disconnected = oauth.disconnect(user.id)
    assert disconnected.status.value == 'not_connected'
    assert disconnected.state_token_hash is None

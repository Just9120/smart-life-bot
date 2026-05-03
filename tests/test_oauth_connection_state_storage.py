from smart_life_bot.storage.sqlite import SQLiteUserOAuthConnectionStateRepository, SQLiteUsersRepository, create_sqlite_connection, init_sqlite_schema

def test_oauth_state_default_pending_disconnect_cycle() -> None:
    conn = create_sqlite_connection('sqlite:///:memory:')
    init_sqlite_schema(conn)
    user = SQLiteUsersRepository(conn).get_or_create_by_telegram_id(1001, timezone='UTC')
    repo = SQLiteUserOAuthConnectionStateRepository(conn)
    state = repo.get_or_create_for_user(user.id)
    assert state.status == 'not_connected'
    pending = repo.mark_pending(user.id, 'h'*64)
    assert pending.status == 'pending'
    assert pending.state_token_hash == 'h'*64
    disconnected = repo.mark_disconnected(user.id)
    assert disconnected.status == 'not_connected'
    assert disconnected.state_token_hash is None

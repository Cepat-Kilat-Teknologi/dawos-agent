"""Tests for session endpoints — mocked accel-cmd calls."""

from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.constants import COLUMNS_DEFAULT, COLUMNS_EXTENDED


@pytest.mark.asyncio
async def test_list_sessions(client, headers):
    mock_sessions = [
        {"ifname": "ppp0", "username": "user1", "ip": "10.0.0.1", "state": "active"},
        {"ifname": "ppp1", "username": "user2", "ip": "10.0.0.2", "state": "active"},
    ]
    with patch(
        "dawos_agent.routers.sessions.accel.show_sessions",
        new_callable=AsyncMock,
        return_value=mock_sessions,
    ) as mock_show:
        resp = await client.get("/api/v1/sessions", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert data["sessions"][0]["username"] == "user1"
    # Default columns used when no ?columns= param
    mock_show.assert_awaited_once_with(columns=COLUMNS_DEFAULT)


@pytest.mark.asyncio
async def test_list_sessions_with_columns(client, headers):
    """Custom ?columns= selects specific fields."""
    mock_sessions = [{"ifname": "ppp0", "sid": "abc123"}]
    with patch(
        "dawos_agent.routers.sessions.accel.show_sessions",
        new_callable=AsyncMock,
        return_value=mock_sessions,
    ) as mock_show:
        resp = await client.get("/api/v1/sessions?columns=ifname,sid", headers=headers)

    assert resp.status_code == 200
    # validate_columns strips and validates — resulting in "ifname,sid"
    mock_show.assert_awaited_once()
    call_cols = mock_show.call_args.kwargs["columns"]
    assert "ifname" in call_cols
    assert "sid" in call_cols


@pytest.mark.asyncio
async def test_list_sessions_columns_all(client, headers):
    """?columns=all returns the extended column set."""
    mock_sessions = []
    with patch(
        "dawos_agent.routers.sessions.accel.show_sessions",
        new_callable=AsyncMock,
        return_value=mock_sessions,
    ) as mock_show:
        resp = await client.get("/api/v1/sessions?columns=all", headers=headers)

    assert resp.status_code == 200
    mock_show.assert_awaited_once_with(columns=COLUMNS_EXTENDED)


@pytest.mark.asyncio
async def test_list_sessions_columns_invalid_chars(client, headers):
    """Shell metacharacters in ?columns= rejected by regex → 422."""
    resp = await client.get("/api/v1/sessions?columns=ifname;rm", headers=headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_sessions_columns_unknown_only(client, headers):
    """All-unknown column names → ValueError → 422."""
    with patch(
        "dawos_agent.routers.sessions.accel.show_sessions",
        new_callable=AsyncMock,
        side_effect=ValueError("No valid columns in: BOGUS"),
    ):
        resp = await client.get("/api/v1/sessions?columns=BOGUS", headers=headers)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_sessions_error(client, headers):
    with patch(
        "dawos_agent.routers.sessions.accel.show_sessions",
        new_callable=AsyncMock,
        side_effect=RuntimeError("conn refused"),
    ):
        resp = await client.get("/api/v1/sessions", headers=headers)

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_session_stats(client, headers):
    mock_stat = {
        "sessions": {"active": 10, "starting": 1, "finishing": 0},
        "cpu": "3",
        "uptime": "1:00:00",
    }
    mock_pool = {"used": "10", "total": "100", "available": "90"}

    with (
        patch(
            "dawos_agent.routers.sessions.accel.show_stat",
            new_callable=AsyncMock,
            return_value=mock_stat,
        ),
        patch(
            "dawos_agent.routers.sessions.accel.show_ippool",
            new_callable=AsyncMock,
            return_value=mock_pool,
        ),
    ):
        resp = await client.get("/api/v1/sessions/stats", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["active"] == 10
    assert isinstance(data["cpu_percent"], float)
    assert data["cpu_percent"] == 3.0
    assert isinstance(data["pool_used"], int)
    assert data["pool_used"] == 10
    assert isinstance(data["pool_total"], int)
    assert data["pool_total"] == 100


@pytest.mark.asyncio
async def test_session_stats_error(client, headers):
    with patch(
        "dawos_agent.routers.sessions.accel.show_stat",
        new_callable=AsyncMock,
        side_effect=RuntimeError("fail"),
    ):
        resp = await client.get("/api/v1/sessions/stats", headers=headers)

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_find_session(client, headers):
    table = (
        " ifname | username | ip\n------+--------+-----\n ppp0 | testuser | 10.0.0.5\n"
    )
    with patch(
        "dawos_agent.routers.sessions.accel.run_cmd",
        new_callable=AsyncMock,
        return_value=table,
    ):
        resp = await client.get("/api/v1/sessions/find/testuser", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1


@pytest.mark.asyncio
async def test_find_session_with_columns(client, headers):
    """?columns= on find endpoint selects specific fields."""
    table = " ifname | sid\n------+-----\n ppp0 | abc\n"
    with patch(
        "dawos_agent.routers.sessions.accel.run_cmd",
        new_callable=AsyncMock,
        return_value=table,
    ) as mock_cmd:
        resp = await client.get(
            "/api/v1/sessions/find/testuser?columns=ifname,sid", headers=headers
        )

    assert resp.status_code == 200
    # Verify the command includes the custom columns
    call_args = mock_cmd.call_args[0][0]
    assert "ifname,sid" in call_args


@pytest.mark.asyncio
async def test_find_session_columns_all(client, headers):
    """?columns=all on find endpoint uses extended set."""
    table = " ifname | username\n------+--------\n ppp0 | testuser\n"
    with patch(
        "dawos_agent.routers.sessions.accel.run_cmd",
        new_callable=AsyncMock,
        return_value=table,
    ) as mock_cmd:
        resp = await client.get(
            "/api/v1/sessions/find/testuser?columns=all", headers=headers
        )

    assert resp.status_code == 200
    call_args = mock_cmd.call_args[0][0]
    assert COLUMNS_EXTENDED in call_args


@pytest.mark.asyncio
async def test_find_session_columns_invalid(client, headers):
    """Invalid columns on find → 422."""
    with patch(
        "dawos_agent.routers.sessions.accel.run_cmd",
        new_callable=AsyncMock,
        side_effect=ValueError("No valid columns"),
    ):
        resp = await client.get(
            "/api/v1/sessions/find/testuser?columns=BOGUS", headers=headers
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_find_session_error(client, headers):
    with patch(
        "dawos_agent.routers.sessions.accel.run_cmd",
        new_callable=AsyncMock,
        side_effect=RuntimeError("fail"),
    ):
        resp = await client.get("/api/v1/sessions/find/testuser", headers=headers)

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_terminate_session_by_username(client, headers):
    with patch(
        "dawos_agent.routers.sessions.accel.terminate_session",
        new_callable=AsyncMock,
        return_value="",
    ):
        resp = await client.post(
            "/api/v1/sessions/terminate", headers=headers, json={"username": "user1"}
        )

    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_terminate_session_by_ifname(client, headers):
    with patch(
        "dawos_agent.routers.sessions.accel.terminate_session",
        new_callable=AsyncMock,
        return_value="",
    ):
        resp = await client.post(
            "/api/v1/sessions/terminate", headers=headers, json={"ifname": "ppp0"}
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_terminate_session_no_target(client, headers):
    resp = await client.post("/api/v1/sessions/terminate", headers=headers, json={})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_terminate_session_error(client, headers):
    with patch(
        "dawos_agent.routers.sessions.accel.terminate_session",
        new_callable=AsyncMock,
        side_effect=RuntimeError("not found"),
    ):
        resp = await client.post(
            "/api/v1/sessions/terminate", headers=headers, json={"username": "x"}
        )

    assert resp.status_code == 500
    assert resp.json()["detail"] == "Internal server error"


# ---------------------------------------------------------------------------
# Session model — extended fields
# ---------------------------------------------------------------------------


def test_session_model_extended_fields():
    """Session model accepts all extended accel-cmd column names."""
    from dawos_agent.models.schemas import Session

    data = {
        "ifname": "ppp0",
        "username": "user1",
        "ip": "10.0.0.1",
        "calling-sid": "AA:BB:CC:DD:EE:FF",
        "called-sid": "00:11:22:33:44:55",
        "sid": "abc123def456",
        "rate-limit": "5M/20M",
        "type": "pppoe",
        "state": "active",
        "uptime": "1:23:45",
        "uptime-raw": "5025",
        "rx-bytes": "1.2 GiB",
        "tx-bytes": "500 MiB",
        "rx-bytes-raw": "1288490188",
        "tx-bytes-raw": "524288000",
        "rx-pkts": "850000",
        "tx-pkts": "420000",
        "inbound-if": "ens19",
        "service-name": "internet",
    }
    session = Session(**data)

    assert session.ifname == "ppp0"
    assert session.calling_sid == "AA:BB:CC:DD:EE:FF"
    assert session.called_sid == "00:11:22:33:44:55"
    assert session.sid == "abc123def456"
    assert session.uptime_raw == "5025"
    assert session.rx_bytes_raw == "1288490188"
    assert session.tx_bytes_raw == "524288000"
    assert session.rx_pkts == "850000"
    assert session.tx_pkts == "420000"
    assert session.inbound_if == "ens19"
    assert session.service_name == "internet"


def test_session_model_defaults():
    """All extended fields default to empty string when not provided."""
    from dawos_agent.models.schemas import Session

    session = Session()

    assert session.sid == ""
    assert session.called_sid == ""
    assert session.uptime_raw == ""
    assert session.rx_bytes_raw == ""
    assert session.tx_bytes_raw == ""
    assert session.rx_pkts == ""
    assert session.tx_pkts == ""
    assert session.inbound_if == ""
    assert session.service_name == ""


def test_session_model_populate_by_name():
    """Session model accepts Python attribute names (not just aliases)."""
    from dawos_agent.models.schemas import Session

    session = Session(
        calling_sid="AA:BB:CC:DD:EE:FF",
        called_sid="00:11:22:33:44:55",
        rate_limit="10M/50M",
        uptime_raw="3600",
        rx_bytes_raw="1000",
        tx_bytes_raw="2000",
        inbound_if="ens19",
        service_name="internet",
    )

    assert session.calling_sid == "AA:BB:CC:DD:EE:FF"
    assert session.called_sid == "00:11:22:33:44:55"
    assert session.rate_limit == "10M/50M"
    assert session.uptime_raw == "3600"
    assert session.inbound_if == "ens19"


def test_session_model_serialises_aliases():
    """Session model serialises using aliases in by_alias mode."""
    from dawos_agent.models.schemas import Session

    session = Session(sid="abc", inbound_if="ens19", service_name="internet")
    data = session.model_dump(by_alias=True)

    assert data["inbound-if"] == "ens19"
    assert data["service-name"] == "internet"
    assert data["sid"] == "abc"


def test_session_list_response_with_extended():
    """SessionListResponse works with extended Session fields."""
    from dawos_agent.models.schemas import Session, SessionListResponse

    sessions = [
        Session(
            ifname="ppp0",
            username="user1",
            sid="abc",
            rx_pkts="100",
            tx_pkts="200",
        ),
    ]
    resp = SessionListResponse(count=1, sessions=sessions)
    assert resp.count == 1
    assert resp.sessions[0].sid == "abc"
    assert resp.sessions[0].rx_pkts == "100"


# ---------------------------------------------------------------------------
# Session search — by MAC / IP / SID (P0.3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_by_mac(client, headers):
    """GET /sessions/search/mac/{mac} returns matching sessions."""
    mock_sessions = [
        {"ifname": "ppp0", "username": "user1", "calling-sid": "AA:BB:CC:DD:EE:FF"}
    ]
    with patch(
        "dawos_agent.routers.sessions.accel.search_sessions",
        new_callable=AsyncMock,
        return_value=mock_sessions,
    ) as mock_search:
        resp = await client.get(
            "/api/v1/sessions/search/mac/AA:BB:CC:DD:EE:FF", headers=headers
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["sessions"][0]["username"] == "user1"
    mock_search.assert_awaited_once_with(
        "calling-sid", "AA:BB:CC:DD:EE:FF", columns=COLUMNS_DEFAULT
    )


@pytest.mark.asyncio
async def test_search_by_mac_with_columns(client, headers):
    """MAC search respects ?columns= parameter."""
    with patch(
        "dawos_agent.routers.sessions.accel.search_sessions",
        new_callable=AsyncMock,
        return_value=[],
    ) as mock_search:
        resp = await client.get(
            "/api/v1/sessions/search/mac/AA:BB:CC:DD:EE:FF?columns=all",
            headers=headers,
        )

    assert resp.status_code == 200
    mock_search.assert_awaited_once_with(
        "calling-sid", "AA:BB:CC:DD:EE:FF", columns=COLUMNS_EXTENDED
    )


@pytest.mark.asyncio
async def test_search_by_mac_invalid_format(client, headers):
    """Invalid MAC format rejected by regex → 422."""
    resp = await client.get("/api/v1/sessions/search/mac/not-a-mac", headers=headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_by_mac_error(client, headers):
    """MAC search returns 500 on accel-cmd failure."""
    with patch(
        "dawos_agent.routers.sessions.accel.search_sessions",
        new_callable=AsyncMock,
        side_effect=RuntimeError("fail"),
    ):
        resp = await client.get(
            "/api/v1/sessions/search/mac/AA:BB:CC:DD:EE:FF", headers=headers
        )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_search_by_mac_invalid_columns(client, headers):
    """MAC search with invalid columns → 422."""
    with patch(
        "dawos_agent.routers.sessions.accel.search_sessions",
        new_callable=AsyncMock,
        side_effect=ValueError("No valid columns"),
    ):
        resp = await client.get(
            "/api/v1/sessions/search/mac/AA:BB:CC:DD:EE:FF?columns=BOGUS",
            headers=headers,
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_by_ip(client, headers):
    """GET /sessions/search/ip/{ip} returns matching sessions."""
    mock_sessions = [{"ifname": "ppp0", "username": "user1", "ip": "10.0.0.5"}]
    with patch(
        "dawos_agent.routers.sessions.accel.search_sessions",
        new_callable=AsyncMock,
        return_value=mock_sessions,
    ) as mock_search:
        resp = await client.get("/api/v1/sessions/search/ip/10.0.0.5", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    mock_search.assert_awaited_once_with("ip", "10.0.0.5", columns=COLUMNS_DEFAULT)


@pytest.mark.asyncio
async def test_search_by_ip_with_columns(client, headers):
    """IP search respects ?columns= parameter."""
    with patch(
        "dawos_agent.routers.sessions.accel.search_sessions",
        new_callable=AsyncMock,
        return_value=[],
    ) as mock_search:
        resp = await client.get(
            "/api/v1/sessions/search/ip/10.0.0.5?columns=ifname,sid",
            headers=headers,
        )

    assert resp.status_code == 200
    call_cols = mock_search.call_args.kwargs["columns"]
    assert "ifname" in call_cols
    assert "sid" in call_cols


@pytest.mark.asyncio
async def test_search_by_ip_error(client, headers):
    """IP search returns 500 on accel-cmd failure."""
    with patch(
        "dawos_agent.routers.sessions.accel.search_sessions",
        new_callable=AsyncMock,
        side_effect=RuntimeError("fail"),
    ):
        resp = await client.get("/api/v1/sessions/search/ip/10.0.0.5", headers=headers)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_search_by_ip_invalid_columns(client, headers):
    """IP search with invalid columns → 422."""
    with patch(
        "dawos_agent.routers.sessions.accel.search_sessions",
        new_callable=AsyncMock,
        side_effect=ValueError("No valid columns"),
    ):
        resp = await client.get(
            "/api/v1/sessions/search/ip/10.0.0.5?columns=BOGUS",
            headers=headers,
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_by_sid(client, headers):
    """GET /sessions/search/sid/{sid} returns matching sessions."""
    mock_sessions = [{"ifname": "ppp0", "sid": "abc123"}]
    with patch(
        "dawos_agent.routers.sessions.accel.search_sessions",
        new_callable=AsyncMock,
        return_value=mock_sessions,
    ) as mock_search:
        resp = await client.get("/api/v1/sessions/search/sid/abc123", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    mock_search.assert_awaited_once_with("sid", "abc123", columns=COLUMNS_DEFAULT)


@pytest.mark.asyncio
async def test_search_by_sid_with_columns_all(client, headers):
    """SID search with ?columns=all uses extended set."""
    with patch(
        "dawos_agent.routers.sessions.accel.search_sessions",
        new_callable=AsyncMock,
        return_value=[],
    ) as mock_search:
        resp = await client.get(
            "/api/v1/sessions/search/sid/abc123?columns=all",
            headers=headers,
        )

    assert resp.status_code == 200
    mock_search.assert_awaited_once_with("sid", "abc123", columns=COLUMNS_EXTENDED)


@pytest.mark.asyncio
async def test_search_by_sid_invalid_columns(client, headers):
    """SID search with invalid columns → 422."""
    with patch(
        "dawos_agent.routers.sessions.accel.search_sessions",
        new_callable=AsyncMock,
        side_effect=ValueError("No valid columns"),
    ):
        resp = await client.get(
            "/api/v1/sessions/search/sid/abc123?columns=BOGUS",
            headers=headers,
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_by_sid_error(client, headers):
    """SID search returns 500 on accel-cmd failure."""
    with patch(
        "dawos_agent.routers.sessions.accel.search_sessions",
        new_callable=AsyncMock,
        side_effect=RuntimeError("fail"),
    ):
        resp = await client.get("/api/v1/sessions/search/sid/abc123", headers=headers)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_search_by_mac_no_auth(client, bad_headers):
    """Search endpoints require valid API key."""
    resp = await client.get(
        "/api/v1/sessions/search/mac/AA:BB:CC:DD:EE:FF", headers=bad_headers
    )
    assert resp.status_code == 401

"""Parity: anything doable over MCP is doable in the UI, on the same data.

Both adapters call the same domain functions, so these tests are cheap — but
they are the ones that catch the failure the architecture exists to prevent.
It has already happened once: REST serialised Decimal as "218.00" while MCP
emitted 218.0, from a single domain call.
"""

from annos.domain import profile as profile_domain
from conftest import SUBJECT

EXPECTED_TOOLS = {"find_food", "get_profile", "update_profile"}


async def mcp_call(client, name: str, arguments: dict | None = None) -> dict:
    result = await client.call_tool(name, arguments or {})
    return result.data


async def test_the_advertised_tool_surface(mcp_client):
    """Registration and hard deletion are absent on purpose: a hallucinating
    client must not be able to create or destroy an account."""
    names = {tool.name for tool in await mcp_client.list_tools()}

    assert names == EXPECTED_TOOLS


async def test_food_search_is_byte_identical_across_surfaces(
    api, mcp_client, make_food, make_unit_type
):
    await make_unit_type("SLICE", name_fi="viipale", name_sv="skiva", name_en="slice")
    await make_food(
        name_fi="Ruisleipä",
        name_sv="Rågbröd",
        name_en="Rye bread",
        kcal=218,
        protein_g=8.5,
        carbs_g=36,
        fat_g=1.5,
        fiber_g=8.6,
        serving_units=(("SLICE", 30),),
    )

    rest = (await api.get("/api/foods/search", params={"q": "ruisleipa"})).json()
    mcp = await mcp_call(mcp_client, "find_food", {"query": "ruisleipa"})

    assert rest["results"] == mcp["results"]
    assert rest["results"][0]["per_100g"]["kcal"] == 218.0


async def test_both_surfaces_resolve_the_same_language(api, mcp_client, make_food, session):
    """The language a name is served in is decided in the domain layer, so both
    surfaces must land on the same one — including after it changes."""
    await profile_domain.create_profile(session, subject=SUBJECT)
    await make_food(name_fi="Ruisleipä", name_sv="Rågbröd", name_en="Rye bread")

    await profile_domain.update_profile(session, subject=SUBJECT, changes={"language": "sv"})

    rest = (await api.get("/api/foods/search", params={"q": "ruisleipa"})).json()
    mcp = await mcp_call(mcp_client, "find_food", {"query": "ruisleipa"})

    assert rest["language"] == mcp["language"] == "sv"
    assert rest["results"][0]["name"] == mcp["results"][0]["name"] == "Rågbröd"


async def test_both_surfaces_echo_server_time(api, mcp_client, make_food):
    await make_food(name_fi="Ruisleipä")

    rest = (await api.get("/api/foods/search", params={"q": "ruisleipa"})).json()
    mcp = await mcp_call(mcp_client, "find_food", {"query": "ruisleipa"})

    assert set(rest["server_time"]) == set(mcp["server_time"]) == {"utc", "timezone", "local_date"}


async def test_profile_values_agree_across_surfaces(api, mcp_client, session):
    """The shapes differ deliberately — MCP nests the coaching material under
    `profile_context` so a client reads it as instruction rather than data — but
    the values behind them are one row."""
    await profile_domain.create_profile(session, subject=SUBJECT)
    await profile_domain.update_profile(
        session,
        subject=SUBJECT,
        changes={"birth_year": 1985, "height_cm": 181, "coaching_notes": "be blunt"},
    )

    rest = (await api.get("/api/profile")).json()
    mcp = await mcp_call(mcp_client, "get_profile")

    assert mcp["nickname"] == rest["nickname"]
    assert mcp["language"] == rest["language"]
    assert mcp["birth_year"] == rest["birth_year"] == 1985
    assert mcp["height_cm"] == rest["height_cm"] == 181
    assert mcp["timezone"] == rest["timezone"]
    assert mcp["profile_context"]["coaching_notes"] == rest["coaching_notes"] == "be blunt"


async def test_a_write_on_one_surface_is_visible_on_the_other(api, mcp_client, session):
    await profile_domain.create_profile(session, subject=SUBJECT)

    updated = await mcp_call(mcp_client, "update_profile", {"changes": {"height_cm": 181}})
    assert updated["updated"] == ["height_cm"]

    assert (await api.get("/api/profile")).json()["height_cm"] == 181


async def test_mcp_scoping_matches_rest_scoping(api, mcp_client, make_food):
    """Another account's private food is invisible on both surfaces, not just
    the one the UI happens to use."""
    await make_food(name_fi="Kaurapuuro", owner_id="someone-else", source="label")

    rest = (await api.get("/api/foods/search", params={"q": "kaurapuuro"})).json()
    mcp = await mcp_call(mcp_client, "find_food", {"query": "kaurapuuro"})

    assert rest["results"] == mcp["results"] == []

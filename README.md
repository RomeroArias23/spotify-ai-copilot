# Spotify AI Copilot

A FastAPI backend that lets users explore and organize their Spotify library through natural language. The AI layer (Claude) plans multi-step actions against the Spotify Web API — searching tracks, reading listening history, creating playlists — and grounds every response in real account data.

> "Make me a 12-song playlist with songs from Arctic Monkeys, The Strokes, and Tame Impala"
> → 3 search calls → 1 playlist creation → 1 batch track add → playlist URL returned.

This project is built deliberately as a portfolio piece for a Solutions Architect / backend engineering profile. Code is structured around production patterns (typed exceptions, dependency injection, swappable storage backends, async I/O) rather than the shortest path to a demo.

---

## What works today

- **OAuth 2.0 Authorization Code flow with PKCE.** State parameter, signed cookie for CSRF protection, automatic token refresh with a 60-second safety buffer.
- **Async Spotify API client.** Handles 401 (force-refresh and retry once), 429 (bounded backoff respecting `Retry-After`), and surfaces typed `SpotifyAPIError` for everything else.
- **Pydantic-modeled API surface.** Endpoints return typed objects, not raw dicts. JSON Schemas for the AI agent's tools are derived automatically from these models — there's no hand-written schema duplication.
- **Tool-calling agent.** Bounded loop (max 10 iterations), structured tool trace returned with every reply. The agent chains tools across multiple turns to satisfy a single user request.
- **5 tools wired up:** `get_me`, `get_top_tracks`, `search_tracks`, `create_playlist`, `add_tracks_to_playlist`.

## Architecture
app/
├── api/
│   ├── deps.py              # Dependency injection wiring
│   └── routes/
│       ├── auth.py          # OAuth login + callback
│       ├── me.py            # User-scoped read endpoints
│       └── chat.py          # POST /chat — natural language entry point
├── agents/
│   ├── copilot.py           # Agent loop (Anthropic tool calling)
│   ├── tools.py             # Tool registry — Pydantic schemas + handlers
│   ├── prompts.py           # System prompt
│   └── context.py           # ToolContext passed to every tool invocation
├── services/
│   ├── token_store.py       # Protocol + InMemoryTokenStore (Redis-ready)
│   └── spotify/
│       ├── auth.py          # OAuth flow, token refresh
│       ├── client.py        # HTTP wrapper: retry, rate limit, typed errors
│       └── api.py           # Business methods: get_me, create_playlist, ...
├── core/
│   └── exceptions.py        # SpotifyError, SpotifyAuthError, SpotifyAPIError
└── config.py                # Pydantic Settings — env-driven configuration

### Notable design decisions

**Tools defined as Pydantic models, not hand-written JSON.** Each tool's argument schema is a Pydantic class. The AI agent receives JSON Schema derived from those classes via `.model_json_schema()`. Editing a model edits the contract — no two-place sync.

**Token storage behind a `Protocol`.** The current implementation is in-memory (lost on restart, fine for development). The `TokenStore` protocol means swapping in Redis is a single file change with no edits to consumers.

**Tool descriptions are part of the prompt.** The `description=` argument on every Pydantic `Field(...)` flows into JSON Schema and then into the LLM's context. Treat them as user-facing copy, not internal docs.

**Defense-in-depth URI normalization.** The `add_tracks_to_playlist` tool accepts Spotify track URIs (`spotify:track:<id>`). The system prompt and tool description both tell the LLM to send URIs, not bare IDs. A Pydantic validator on the tool argument additionally coerces bare IDs into URIs as a safety net — wrong inputs get fixed silently rather than surfacing a 400 from Spotify.

**Singleton `SpotifyAuth` for in-memory state.** PKCE verifiers and OAuth state are held on the auth instance during the brief window between `/login` and `/callback`. The instance is cached via `lru_cache` so both routes see the same in-memory map. This is acknowledged as a single-process limitation — Redis is the production fix and the protocol is already in place.

---

## Running locally

Requires Python 3.12+, a Spotify Developer app, and an Anthropic API key.

```bash
# 1. Clone and enter
git clone https://github.com/RomeroArias23/spotify-ai-copilot.git
cd spotify-ai-copilot

# 2. Create venv with Python 3.12
python3.12 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — fill in the four required values
```

`.env` requires:

- `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` — from [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
- `SPOTIFY_REDIRECT_URI=http://127.0.0.1:8000/auth/callback` — must match the URI registered in the Spotify dashboard exactly
- `ANTHROPIC_API_KEY` — from [console.anthropic.com](https://console.anthropic.com)
- `SESSION_SECRET` — generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"`

In the Spotify dashboard, also make sure:

- **Web API** is checked under "Which API/SDKs are you planning to use?"
- The Spotify account you'll authenticate with is added to **User Management**

Then:

```bash
uvicorn app.main:app --reload
```

Visit `http://127.0.0.1:8000/auth/login` to authenticate, then `http://127.0.0.1:8000/docs` for the Swagger UI. The chat endpoint is `POST /chat` with body `{"message": "..."}`.

---

## Example interaction

Request:
```json
{"message": "Create a chill playlist for studying using my top 10 tracks from the past month"}
```

Response (abbreviated):
```json
{
  "reply": "Done — 'Chill Study Mix' is live with your top 10 tracks from the past month. Open it: <url>",
  "tool_calls": [
    {"name": "get_top_tracks", "input": {"limit": 10, "time_range": "short_term"}, "output": {"tracks": [...]}},
    {"name": "create_playlist", "input": {"name": "Chill Study Mix", "public": false}, "output": {"id": "...", "url": "..."}},
    {"name": "add_tracks_to_playlist", "input": {"playlist_id": "...", "track_uris": [...]}, "output": {"added": 10}}
  ]
}
```

The `tool_calls` array is a structured trace of every step the agent took. It exists primarily for debugging and observability, not for the end user — but it's also the most informative thing in the API for someone evaluating how the agent reasons.

---

## Roadmap

- [x] OAuth flow with PKCE + CSRF protection
- [x] Async Spotify API client with retry, refresh, rate limiting
- [x] Tool-calling agent with multi-step chains
- [x] Read endpoints (`/me`, top tracks)
- [x] Playlist creation
- [ ] Conversation memory (multi-turn threads)
- [ ] Postgres persistence (users, threads, cached Spotify data)
- [ ] Redis-backed token + state store
- [ ] pgvector + embeddings for "find more like this artist" semantic search
- [ ] Streaming responses via SSE
- [ ] Multi-user session handling (currently single-user dev mode)

---

## Known limitations

- **Single in-process user.** `get_current_user_id()` returns a hardcoded value. Real session/JWT auth is a roadmap item — adding it before it's needed would be premature.
- **Token store is in-memory.** Tokens are wiped on every server restart. The `TokenStore` protocol is in place specifically so a Redis backend can be added without changes elsewhere.
- **Partial-failure on playlist creation is not rolled back.** If `add_tracks_to_playlist` fails after `create_playlist` succeeds, you're left with an empty playlist on the user's account. A real production system would either use Spotify's snapshot IDs to attempt rollback or mark the playlist as in-progress in our DB and reconcile asynchronously. Today: the trade-off is accepted, not solved.
- **Spotify Development Mode 403s.** Spotify can return bare 403s on write endpoints when the app or account is in a soft-restricted state (typically clears in 24–48 hours). All scopes, User Management, and configuration may be correct — the rejection is server-side. The `/auth/debug` endpoint (development-only, removed before production) probes this directly.
- **Audio features endpoint is deprecated.** Spotify deprecated `/audio-features` in November 2024 for new apps. "Recommend music with more energy" style queries currently rely on text/genre matching, not audio analysis.

---

## Stack

- **FastAPI** + **Uvicorn** — async web framework
- **httpx** — async HTTP client (Spotify API + Anthropic API)
- **Pydantic v2** — request/response models, settings, tool argument schemas
- **anthropic** — Claude tool-calling
- **Spotify Web API** — OAuth + read/write endpoints

---

## License

MIT

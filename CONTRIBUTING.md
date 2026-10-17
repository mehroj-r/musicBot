# Contributing

Thanks for your interest! Bug reports, ideas and pull requests are welcome.

## Getting Started

You need [uv](https://docs.astral.sh/uv/), ffmpeg, and [Deno](https://deno.com/) for YouTube.

```bash
uv sync
cp .env.example .env   # fill in BOT_API_TOKEN and ADMIN_IDS
uv run musicbot
```

## Before Opening a Pull Request

```bash
uv run ruff check . --fix
uv run ruff format .
uv run pytest
```

- Keep changes focused; one topic per pull request.
- Add or update tests in `tests/` when behaviour changes.
- Database model changes need an Alembic migration
  (`uv run alembic revision --autogenerate -m "..."`, then review it).
- New settings go in `.env.example` and the README's configuration table.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat: ...`, `fix: ...`,
  `docs: ...`).
- Pull requests target the `master` branch and are squash-merged; merging deploys to production.

## Questions and Security

Ask questions in [Discussions](https://github.com/mehroj-r/music-bot/discussions). Report vulnerabilities
privately as described in [`SECURITY.md`](SECURITY.md).

By participating you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

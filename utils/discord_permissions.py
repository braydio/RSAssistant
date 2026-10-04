"""Central Discord operator and administrator authorization checks."""

from discord.ext import commands

from utils.config_utils import (
    DISCORD_ADMIN_IDS,
    DISCORD_ADMIN_ROLE_IDS,
    DISCORD_OPERATOR_IDS,
    DISCORD_OPERATOR_ROLE_IDS,
)


def _is_allowed(ctx: commands.Context, *, admin: bool) -> bool:
    author_id = getattr(ctx.author, "id", None)
    role_ids = {getattr(role, "id", None) for role in getattr(ctx.author, "roles", ())}
    allowed_users = DISCORD_ADMIN_IDS if admin else DISCORD_OPERATOR_IDS | DISCORD_ADMIN_IDS
    allowed_roles = (
        DISCORD_ADMIN_ROLE_IDS
        if admin
        else DISCORD_OPERATOR_ROLE_IDS | DISCORD_ADMIN_ROLE_IDS
    )
    return author_id in allowed_users or bool(role_ids & allowed_roles)


def operator_only():
    """Restrict a state-changing command to configured operator identities."""
    async def predicate(ctx: commands.Context) -> bool:
        return _is_allowed(ctx, admin=False)

    return commands.check(predicate)


def admin_only():
    """Restrict a maintenance command to configured administrator identities."""
    async def predicate(ctx: commands.Context) -> bool:
        return _is_allowed(ctx, admin=True)

    return commands.check(predicate)

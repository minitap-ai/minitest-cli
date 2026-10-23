"""Assemble the request body of `minitest schedules create|update|preview` from flags."""

from dataclasses import dataclass
from typing import Any

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.schedules_scope import ScopeFlags, resolve_scope
from minitest_cli.commands.schedules_spec import (
    DAY_PRESETS,
    check_timezone,
    fail,
    local_timezone,
    parse_days,
    parse_time,
)
from minitest_cli.commands.schedules_options import Family
from minitest_cli.commands.schedules_where import NativeLane, WhereFlags, resolve_where
from minitest_cli.models.targets import DeviceType

_REQUIRED = {"name": "--name", "timeOfDay": "--at", "slackChannelId": "--slack-channel"}


@dataclass
class SpecFlags:
    name: str | None
    at: str | None
    days: str | None
    timezone: str | None
    slack_channel: str | None
    slack_channel_name: str | None
    post_all_clear: bool | None
    scope: ScopeFlags
    where: WhereFlags

    def plain_fields(self) -> dict[str, Any]:
        self.scope.check()
        fields: dict[str, Any] = {}
        if self.name is not None:
            fields["name"] = self.name
        if self.at is not None:
            fields["timeOfDay"] = parse_time(self.at)
        if self.days is not None:
            fields["days"] = parse_days(self.days)
        if self.timezone is not None:
            fields["timezone"] = check_timezone(self.timezone)
        if self.slack_channel is not None:
            fields["slackChannelId"] = self.slack_channel
            fields["slackChannelName"] = (self.slack_channel_name or self.slack_channel).lstrip("#")
        elif self.slack_channel_name is not None:
            fields["slackChannelName"] = self.slack_channel_name.lstrip("#")
        if self.post_all_clear is not None:
            fields["postAllClear"] = self.post_all_clear
        return fields


async def full_body(
    client: ApiClient, app_id: str, spec: SpecFlags, base: dict[str, Any]
) -> dict[str, Any]:
    """A complete schedule: ``base`` (a file or a saved schedule) with the flags on top."""
    body = {**base, **spec.plain_fields()}
    body.setdefault("days", DAY_PRESETS["weekdays"])
    body.setdefault("timezone", local_timezone())
    body.setdefault("slackChannelName", body.get("slackChannelId"))
    missing = [flag for key, flag in _REQUIRED.items() if not body.get(key)]
    if missing:
        fail(f"Missing {', '.join(missing)} (or put them in --from-file).")
    if spec.where.given or "targets" not in body:
        body.update(resolve_where(spec.where, body))
    if spec.scope.given or "scope" not in body:
        body["scope"] = await resolve_scope(client, app_id, spec.scope)
    return body


async def patch_body(
    client: ApiClient,
    app_id: str,
    spec: SpecFlags,
    current: dict[str, Any],
    from_file: dict[str, Any],
) -> dict[str, Any]:
    """Only the fields the flags or the file change."""
    body = {**from_file, **spec.plain_fields()}
    if spec.where.given:
        body.update(resolve_where(spec.where, {**current, **from_file}))
    if spec.scope.given:
        body["scope"] = await resolve_scope(client, app_id, spec.scope)
    if not body:
        fail("Nothing to change: pass at least one flag or --from-file.")
    return body


def spec_flags(
    *,
    name: str | None,
    at: str | None,
    days: str | None,
    timezone: str | None,
    suite: bool,
    tag: list[str] | None,
    exclude: list[str] | None,
    scenario: list[str] | None,
    browser: list[str] | None,
    url: str | None,
    web_branch: str | None,
    ios: bool,
    ios_build: str | None,
    ios_branch: str | None,
    ios_physical: bool,
    ios_device_type: DeviceType | None,
    android: bool,
    android_build: str | None,
    android_branch: str | None,
    android_physical: bool,
    android_device_type: DeviceType | None,
    slack_channel: str | None,
    slack_channel_name: str | None,
    post_all_clear: bool | None,
    drop: list[Family] | None = None,
) -> SpecFlags:
    return SpecFlags(
        name=name,
        at=at,
        days=days,
        timezone=timezone,
        slack_channel=slack_channel,
        slack_channel_name=slack_channel_name,
        post_all_clear=post_all_clear,
        scope=ScopeFlags(suite=suite, tags=tag, excludes=exclude, scenarios=scenario),
        where=WhereFlags(
            browsers=browser,
            url=url,
            web_branch=web_branch,
            ios=NativeLane(ios, ios_build, ios_branch, ios_physical, ios_device_type),
            android=NativeLane(
                android, android_build, android_branch, android_physical, android_device_type
            ),
            drop=[family.value for family in drop or []],
        ),
    )

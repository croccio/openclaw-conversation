"""Config flow for OpenClaw Conversation."""

from __future__ import annotations

import json
import logging

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME

from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_MODEL,
    CONF_SESSION_KEY,
    CONF_STRIP_EMOJI,
    CONF_SYSTEM_PROMPT,
    CONF_TIMEOUT,
    CONF_USER_OVERRIDES,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_SESSION_KEY,
    DEFAULT_STRIP_EMOJI,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TIMEOUT,
    DEFAULT_USER_OVERRIDES,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

def _looks_like_model_error(body: str) -> bool:
    """Detect gateway errors caused by an unknown or unavailable model."""
    if not body:
        return False
    lowered = body.lower()
    if "model" not in lowered:
        return False
    return any(
        hint in lowered
        for hint in (
            "not found",
            "not available",
            "unknown",
            "invalid",
            "does not exist",
            "no such",
        )
    )

class OpenClawConversationConfigFlow(
    config_entries.ConfigFlow, domain=DOMAIN
):
    """Handle a config flow for OpenClaw Conversation."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OpenClawOptionsFlowHandler:
        """Get the options flow handler."""
        return OpenClawOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            base_url = user_input[CONF_BASE_URL].rstrip("/")
            api_key = user_input[CONF_API_KEY]

            url = f"{base_url}/v1/chat/completions"
            try:
                async with aiohttp.ClientSession() as session:
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    }
                    payload = {
                        "model": user_input.get(CONF_MODEL, DEFAULT_MODEL),
                        "messages": [
                            {"role": "user", "content": "ping"}
                        ],
                    }
                    _LOGGER.debug(
                        "Validating OpenClaw Gateway: POST %s (model=%s)",
                        url,
                        payload["model"],
                    )
                    async with session.post(
                        url,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        body = ""
                        if resp.status != 200:
                            try:
                                body = await resp.text()
                            except Exception:
                                body = ""
                        _LOGGER.debug(
                            "OpenClaw Gateway validation response: %s %s — body=%s",
                            resp.status,
                            resp.reason,
                            body[:500],
                        )
                        if resp.status == 200:
                            pass
                        elif resp.status == 400:
                            if _looks_like_model_error(body):
                                errors["base"] = "model_not_available"
                            else:
                                errors["base"] = "bad_request"
                        elif resp.status == 401:
                            errors["base"] = "invalid_auth"
                        elif resp.status == 403:
                            errors["base"] = "forbidden"
                        elif resp.status == 404:
                            errors["base"] = "endpoint_not_found"
                        elif resp.status == 405:
                            errors["base"] = "endpoint_disabled"
                        elif 500 <= resp.status < 600:
                            if _looks_like_model_error(body):
                                errors["base"] = "model_not_available"
                            else:
                                errors["base"] = "server_error"                            
                        else:
                            _LOGGER.warning(
                                "OpenClaw Gateway returned unexpected "
                                "status %s for %s — body=%s",
                                resp.status,
                                url,
                                body[:500],
                            )
                            errors["base"] = "cannot_connect"
            except aiohttp.ClientConnectorError as err:
                _LOGGER.warning(
                    "OpenClaw Gateway unreachable at %s: %s", url, err
                )
                errors["base"] = "cannot_reach"
            except TimeoutError:
                _LOGGER.warning(
                    "OpenClaw Gateway validation timed out at %s", url
                )
                errors["base"] = "timeout"
            except aiohttp.ClientError as err:
                _LOGGER.warning(
                    "OpenClaw Gateway client error at %s: %s", url, err
                )
                errors["base"] = "cannot_connect"

            if not errors:
                name = user_input.get(CONF_NAME, "OpenClaw")
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_BASE_URL: base_url,
                        CONF_API_KEY: api_key,
                        CONF_MODEL: user_input.get(
                            CONF_MODEL, DEFAULT_MODEL
                        ),
                        CONF_TIMEOUT: user_input.get(
                            CONF_TIMEOUT, DEFAULT_TIMEOUT
                        ),
                        CONF_SYSTEM_PROMPT: user_input.get(
                            CONF_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT
                        ),
                        CONF_SESSION_KEY: user_input.get(
                            CONF_SESSION_KEY, DEFAULT_SESSION_KEY
                        ),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_NAME, default="OpenClaw"
                    ): str,
                    vol.Required(
                        CONF_BASE_URL, default=DEFAULT_BASE_URL
                    ): str,
                    vol.Required(CONF_API_KEY): str,
                    vol.Required(
                        CONF_MODEL, default=DEFAULT_MODEL
                    ): str,
                    vol.Optional(
                        CONF_TIMEOUT, default=DEFAULT_TIMEOUT
                    ): vol.Coerce(int),
                    vol.Optional(
                        CONF_SYSTEM_PROMPT, default=DEFAULT_SYSTEM_PROMPT
                    ): str,
                    vol.Optional(
                        CONF_SESSION_KEY, default=DEFAULT_SESSION_KEY
                    ): str,
                }
            ),
            errors=errors,
        )


class OpenClawOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for OpenClaw Conversation."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        entry_overrides = config_entry.options.get(
            CONF_USER_OVERRIDES,
            config_entry.data.get(CONF_USER_OVERRIDES, DEFAULT_USER_OVERRIDES),
        )
        if isinstance(entry_overrides, dict):
            self._overrides = dict(entry_overrides)
        elif isinstance(entry_overrides, str) and entry_overrides.strip():
            try:
                parsed = json.loads(entry_overrides)
                self._overrides = parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, TypeError, ValueError):
                self._overrides = {}
        else:
            self._overrides = {}
        self._defaults = {
            CONF_MODEL: config_entry.options.get(
                CONF_MODEL, config_entry.data.get(CONF_MODEL, DEFAULT_MODEL)
            ),
            CONF_TIMEOUT: config_entry.options.get(
                CONF_TIMEOUT, config_entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
            ),
            CONF_SYSTEM_PROMPT: config_entry.options.get(
                CONF_SYSTEM_PROMPT,
                config_entry.data.get(CONF_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT),
            ),
            CONF_SESSION_KEY: config_entry.options.get(
                CONF_SESSION_KEY,
                config_entry.data.get(CONF_SESSION_KEY, DEFAULT_SESSION_KEY),
            ),
            CONF_STRIP_EMOJI: config_entry.options.get(
                CONF_STRIP_EMOJI, DEFAULT_STRIP_EMOJI
            ),
        }

    async def async_step_init(self, user_input=None):
        """Manage options."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["defaults", "users_overrides", "abort_flow"],
        )

    def _default_label(self, key: str) -> str:
        value = self._defaults.get(key, "")
        return self._short(str(value))

    async def async_step_defaults(self, user_input=None):
        """Manage default options."""
        return self.async_show_menu(
            step_id="defaults",
            menu_options={
                "edit_default_model": (
                    f"Default Model: {self._default_label(CONF_MODEL)}"
                ),
                "edit_default_timeout": (
                    f"Timeout: {self._defaults.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)}"
                ),
                "edit_default_system_prompt": (
                    "Default System Prompt: "
                    f"{self._default_label(CONF_SYSTEM_PROMPT)}"
                ),
                "edit_default_session_key": (
                    "Default Session Key: "
                    f"{self._default_label(CONF_SESSION_KEY)}"
                ),
                "toggle_strip_emoji": (
                    "Strip emojis: "
                    f"{'On' if self._defaults.get(CONF_STRIP_EMOJI) else 'Off'}"
                ),
                "back_to_main": "← Back",
                "abort_flow": "Cancel",
            },
        )

    async def _async_default_field(self, key, step_id, user_input):
        """Edit a single default field."""
        if user_input is not None:
            value = user_input.get(key)
            if key == CONF_TIMEOUT:
                try:
                    value = max(int(value), 0)
                except (TypeError, ValueError):
                    value = DEFAULT_TIMEOUT
            else:
                value = (value or "").strip()
            self._defaults[key] = value
            self._persist()
            return await self.async_step_defaults()
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        key, default=self._defaults.get(key, "")
                    ): vol.Coerce(int) if key == CONF_TIMEOUT else str
                }
            ),
        )

    async def async_step_edit_default_model(self, user_input=None):
        """Edit the default model."""
        return await self._async_default_field(
            CONF_MODEL, "edit_default_model", user_input
        )

    async def async_step_edit_default_timeout(self, user_input=None):
        """Edit the default timeout."""
        return await self._async_default_field(
            CONF_TIMEOUT, "edit_default_timeout", user_input
        )

    async def async_step_edit_default_system_prompt(self, user_input=None):
        """Edit the default system prompt."""
        return await self._async_default_field(
            CONF_SYSTEM_PROMPT, "edit_default_system_prompt", user_input
        )

    async def async_step_edit_default_session_key(self, user_input=None):
        """Edit the default session key."""
        return await self._async_default_field(
            CONF_SESSION_KEY, "edit_default_session_key", user_input
        )

    async def async_step_toggle_strip_emoji(self, user_input=None):
        """Toggle emoji stripping."""
        self._defaults[CONF_STRIP_EMOJI] = not self._defaults.get(
            CONF_STRIP_EMOJI, DEFAULT_STRIP_EMOJI
        )
        self._persist()
        return await self.async_step_defaults()

    def _user_label(self, uid, users):
        for user in users:
            if user.id == uid:
                return user.name or uid
        return uid

    def _persist(self) -> None:
        """Persist current settings immediately."""
        entry = self.hass.config_entries.async_get_entry(
            self._config_entry.entry_id
        ) or self._config_entry
        options = dict(entry.options)
        options.update(self._defaults)
        options[CONF_USER_OVERRIDES] = self._overrides
        self.hass.config_entries.async_update_entry(entry, options=options)

    async def async_step_users_overrides(self, user_input=None):
        """List users and their override state."""
        users = await self.hass.auth.async_get_users()
        menu_options = {}
        for user in users:
            label = user.name or user.id
            if user.id in self._overrides:
                label = f"✓ {label}"
            menu_options[f"user_{user.id}"] = label
        known_ids = {user.id for user in users}
        for uid in list(self._overrides):
            if uid not in known_ids:
                menu_options[f"user_{uid}"] = f"✓ {uid}"
        menu_options["back_to_main"] = "← Back"
        menu_options["abort_flow"] = "Cancel"
        return self.async_show_menu(
            step_id="users_overrides",
            menu_options=menu_options,
        )

    async def async_step_user_menu(self, user_input=None):
        """Show actions for the selected user."""
        uid = getattr(self, "_edit_uid", None)
        if not uid:
            return await self.async_step_users_overrides()
        users = await self.hass.auth.async_get_users()
        return self.async_show_menu(
            step_id="user_menu",
            menu_options={
                "edit_user_values": "Edit values",
                "clear_user": "Clear user override",
                "back_to_users": "← Back to users list",
                "abort_flow": "Cancel",
            },
            description_placeholders={"user": self._user_label(uid, users)},
        )

    @staticmethod
    def _short(value: str) -> str:
        """Shorten a value for menu display."""
        if not value:
            return "(default)"
        return value if len(value) <= 40 else value[:37] + "..."

    async def async_step_edit_user_values(self, user_input=None):
        """Edit the values of the selected user override."""
        uid = getattr(self, "_edit_uid", None)
        if not uid:
            return await self.async_step_users_overrides()
        override = self._overrides.get(uid, {})
        return self.async_show_menu(
            step_id="edit_user_values",
            menu_options={
                "edit_model": f"Model: {self._short(override.get('model', ''))}",
                "edit_session_key": (
                    f"Session key: {self._short(override.get('session_key', ''))}"
                ),
                "edit_system_prompt": (
                    f"System prompt: {self._short(override.get('system_prompt', ''))}"
                ),
                "back_to_user_menu": "← Back",
                "abort_flow": "Cancel",
            },
        )

    async def _async_edit_field(self, key, step_id, user_input):
        """Edit a single override field."""
        uid = getattr(self, "_edit_uid", None)
        if not uid:
            return await self.async_step_users_overrides()
        if user_input is not None:
            value = (user_input.get(key) or "").strip()
            override = dict(self._overrides.get(uid, {}))
            if value:
                override[key] = value
            else:
                override.pop(key, None)
            if override:
                self._overrides[uid] = override
            else:
                self._overrides.pop(uid, None)
            self._persist()
            return await self.async_step_edit_user_values()
        override = self._overrides.get(uid, {})
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {vol.Optional(key, default=override.get(key, "")): str}
            ),
        )

    async def async_step_edit_model(self, user_input=None):
        """Edit the model override."""
        return await self._async_edit_field(CONF_MODEL, "edit_model", user_input)

    async def async_step_edit_session_key(self, user_input=None):
        """Edit the session key override."""
        return await self._async_edit_field(
            CONF_SESSION_KEY, "edit_session_key", user_input
        )

    async def async_step_edit_system_prompt(self, user_input=None):
        """Edit the system prompt override."""
        return await self._async_edit_field(
            CONF_SYSTEM_PROMPT, "edit_system_prompt", user_input
        )

    async def async_step_back_to_user_menu(self, user_input=None):
        """Return to the user menu."""
        return await self.async_step_user_menu()

    async def async_step_clear_user(self, user_input=None):
        """Clear the selected user override."""
        uid = getattr(self, "_edit_uid", None)
        if uid:
            self._overrides.pop(uid, None)
        self._persist()
        return await self.async_step_users_overrides()

    async def async_step_back_to_main(self, user_input=None):
        """Return to the main menu."""
        return await self.async_step_init()

    async def async_step_back_to_users(self, user_input=None):
        """Return to the users list."""
        return await self.async_step_users_overrides()

    async def async_step_abort_flow(self, user_input=None):
        """Close without changing already saved settings."""
        return self.async_abort(reason="user_cancelled")

    def __getattr__(self, name):
        """Handle dynamic per-user steps."""
        if name.startswith("async_step_user_"):
            uid = name[len("async_step_user_"):]

            async def handler(user_input=None):
                self._edit_uid = uid
                return await self.async_step_user_menu()

            return handler
        raise AttributeError(name)

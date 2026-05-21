"""Config flow for Local Wine Cellar."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class WineCellarConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle Local Wine Cellar setup."""

    VERSION = 1

    def is_matching(  # pylint: disable=unused-argument
        self, other_flow: "WineCellarConfigFlow"
    ) -> bool:
        """Return whether another flow is matching this one."""
        return False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle setup from the UI."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title="Local Wine Cellar", data={})

        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))
